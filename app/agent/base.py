import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent import ledger
from app.config import PROJECT_ROOT
from app.llm import LLM
from app.logger import logger
from app.schema import AgentState, Memory, Message, ROLE_TYPE


class AuditEvent(BaseModel):
    """Append-only record of a consequential state transition.

    Every agent state change produces a visible, timestamped audit event so
    that no state transition is ever silent or unlogged. Events form a
    SHA-256 hash chain (prev_hash/event_hash): editing, deleting, or
    reordering any historical record breaks ``ledger.verify_chain()``.
    """

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC time the event occurred",
    )
    agent: str = Field(..., description="Name of the agent that emitted the event")
    from_state: Optional[str] = Field(None, description="Previous state (if any)")
    to_state: str = Field(..., description="New state")
    reason: Optional[str] = Field(None, description="Why the transition happened")
    detail: Optional[str] = Field(
        None, description="Additional evidence (error text, tool name, ...)"
    )
    prev_hash: Optional[str] = Field(
        None, description="event_hash of the preceding ledger entry (set on write)"
    )
    event_hash: Optional[str] = Field(
        None, description="SHA-256 chain commitment over this event (set on write)"
    )


def _audit_log_path() -> Path:
    return PROJECT_ROOT / "logs" / "agent_audit.jsonl"


def write_audit_event(event: AuditEvent) -> AuditEvent:
    """Persist an audit event as one line of the hash-chained ledger.

    The recorded event (now carrying prev_hash/event_hash) is returned so
    callers keep an in-memory trail identical to the durable one.

    If persistence itself fails, log loudly and re-raise: an audit trail that
    silently drops events is worse than no audit trail at all, because it
    cannot be trusted as evidence.
    """
    path = _audit_log_path()
    try:
        recorded, _ = ledger.append_event(path, json.loads(event.model_dump_json()))
    except (OSError, RuntimeError) as e:
        logger.error(f"🚨 Failed to write audit event to {path}: {e}")
        raise RuntimeError(f"Audit trail unavailable: {e}") from e
    return AuditEvent(**recorded)


class BaseAgent(BaseModel, ABC):
    """Abstract base class for managing agent state and execution.

    Provides foundational functionality for state transitions, memory management,
    and a step-based execution loop. Subclasses must implement the `step` method.
    """

    # Core attributes
    name: str = Field(..., description="Unique name of the agent")
    description: Optional[str] = Field(None, description="Optional agent description")

    # Prompts
    system_prompt: Optional[str] = Field(
        None, description="System-level instruction prompt"
    )
    next_step_prompt: Optional[str] = Field(
        None, description="Prompt for determining next action"
    )

    # Dependencies
    llm: LLM = Field(default_factory=LLM, description="Language model instance")
    memory: Memory = Field(default_factory=Memory, description="Agent's memory store")
    state: AgentState = Field(
        default=AgentState.IDLE, description="Current agent state"
    )

    # Execution control
    max_steps: int = Field(default=10, description="Maximum steps before termination")
    current_step: int = Field(default=0, description="Current step in execution")

    duplicate_threshold: int = 2

    # Execution evidence: every transition of this agent instance is recorded
    # here in order, and mirrored to the append-only audit log on disk.
    audit_trail: List[AuditEvent] = Field(default_factory=list)

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="allow",  # Allow extra fields for flexibility in subclasses
    )

    @model_validator(mode="after")
    def initialize_agent(self) -> "BaseAgent":
        """Initialize agent with default settings if not provided."""
        if self.llm is None or not isinstance(self.llm, LLM):
            self.llm = LLM(config_name=self.name.lower())
        if not isinstance(self.memory, Memory):
            self.memory = Memory()
        return self

    def _record_event(self, event: AuditEvent) -> None:
        """Persist the event to the chained ledger, then attach it to the
        in-memory trail (fail-loud: on write failure nothing is appended)."""
        recorded = write_audit_event(event)
        self.audit_trail.append(recorded)

    def transition_to(
        self,
        new_state: AgentState,
        reason: str = "",
        detail: Optional[str] = None,
    ) -> bool:
        """Perform an audited state transition.

        Guarantees:
        - No unsupported claim: only transitions declared in the state
          machine are allowed; anything else is rejected with a visible
          warning and the state is left untouched.
        - No silent state change: every accepted transition produces an
          audit event with timestamp, previous/new state, and reason.
        - Fail-safe: if the audit event cannot be persisted, the
          transition is NOT applied.

        Args:
            new_state: The target state.
            reason: Human-readable justification for the transition.
            detail: Optional evidence (error text, tool name, ...).

        Returns:
            True if the transition was applied, False if it was rejected.
        """
        if not isinstance(new_state, AgentState):
            logger.warning(
                f"⛔ Rejected invalid state transition for '{self.name}': "
                f"{new_state!r} is not an AgentState (reason: {reason})"
            )
            return False

        current = self.state
        legal = self._LEGAL_TRANSITIONS.get(current, set())
        if new_state not in legal:
            logger.warning(
                f"⛔ Rejected illegal state transition for '{self.name}': "
                f"{current.value} -> {new_state.value} (reason: {reason}). "
                f"Legal targets from {current.value}: "
                f"{sorted(s.value for s in legal) or 'none'}"
            )
            return False

        # Attempt the write FIRST: if auditing fails, we stay in the
        # current state rather than moving without evidence.
        event = AuditEvent(
            agent=self.name,
            from_state=current.value,
            to_state=new_state.value,
            reason=reason,
            detail=detail,
        )
        self._record_event(event)  # raises RuntimeError if persistence fails
        self.state = new_state
        logger.info(
            f"📝 [{self.name}] state: {current.value} -> {new_state.value} "
            f"(reason: {reason})"
        )
        return True

    # Declared, testable state machine. IDLE->IDLE is legal so that a
    # completed or failed run can always be reset for the next request.
    _LEGAL_TRANSITIONS = {
        AgentState.IDLE: {AgentState.RUNNING, AgentState.IDLE},
        AgentState.RUNNING: {
            AgentState.FINISHED,
            AgentState.ERROR,
            AgentState.IDLE,
        },
        AgentState.FINISHED: {AgentState.IDLE},
        AgentState.ERROR: {AgentState.IDLE},
    }

    def verify_audit_trail(self) -> bool:
        """Recompute this agent's hash chain and report integrity.

        NOTE: each agent records its own transitions; cross-agent global
        ordering is NOT guaranteed (single-writer prototype limitation).
        """
        ok, _ = ledger.verify_chain(
            json.loads(e.model_dump_json()) for e in self.audit_trail
        )
        return ok

    def export_execution_record(self) -> dict:
        """Export this agent's authorized execution record for review.

        Returns a JSON-serializable dict containing the full ordered audit
        trail — the evidence behind every state change made by this agent —
        plus a manifest root over the canonical serialization of that trail.

        The manifest_root attests to BYTE INTEGRITY ONLY. It is not proof
        that the recorded events are true, complete, or authoritative.
        """
        events = [json.loads(e.model_dump_json()) for e in self.audit_trail]
        record = {
            "agent": self.name,
            "final_state": self.state.value,
            "events": events,
        }
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
        record["integrity"] = {
            "manifest_root": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "chain_valid": ledger.verify_chain(events)[0],
            "attestation": "byte-integrity-only; does not attest to truth of contents",
        }
        return record

    def update_memory(
        self,
        role: ROLE_TYPE, # type: ignore
        content: str,
        **kwargs,
    ) -> None:
        """Add a message to the agent's memory.

        Args:
            role: The role of the message sender (user, system, assistant, tool).
            content: The message content.
            **kwargs: Additional arguments (e.g., tool_call_id for tool messages).

        Raises:
            ValueError: If the role is unsupported.
        """
        message_map = {
            "user": Message.user_message,
            "system": Message.system_message,
            "assistant": Message.assistant_message,
            "tool": lambda content, **kw: Message.tool_message(content, **kw),
        }

        if role not in message_map:
            raise ValueError(f"Unsupported message role: {role}")

        msg_factory = message_map[role]
        msg = msg_factory(content, **kwargs) if role == "tool" else msg_factory(content)
        self.memory.add_message(msg)

    async def run(self, request: Optional[str] = None) -> str:
        """Execute the agent's main loop asynchronously.

        Reliability contract (measurable, not aspirational):
        - No unlogged state transitions: every move goes through
          ``transition_to`` and lands in the audit trail.
        - Every failure produces a visible ERROR state, a reason code, and
          a recovery path (the agent is reset to IDLE and remains reusable).
        - No "resolved" status without a verified outcome: FINISHED is only
          reported when the state machine actually reached FINISHED; hitting
          the step budget is reported as an incomplete run, never as success.

        Args:
            request: Optional initial user request to process.

        Returns:
            A string summarizing the execution results, including explicit
            uncertainty labels when the outcome is not verified.

        Raises:
            RuntimeError: If the agent is not in IDLE state at start.
        """
        if self.state != AgentState.IDLE:
            raise RuntimeError(f"Cannot run agent from state: {self.state}")

        if request:
            self.update_memory("user", request)

        results: List[str] = []
        self.current_step = 0  # guarantee a fresh budget for every run

        if not self.transition_to(AgentState.RUNNING, reason="run() started"):
            # Audit persistence failed: refuse to execute rather than run
            # without an evidence trail.
            raise RuntimeError(
                "Refusing to start: audit trail unavailable (E-AUDIT-WRITE)"
            )

        try:
            while (
                self.current_step < self.max_steps
                and self.state == AgentState.RUNNING
            ):
                self.current_step += 1
                logger.info(f"Executing step {self.current_step}/{self.max_steps}")
                step_result = await self.step()

                # Check for stuck state
                if self.is_stuck():
                    self.handle_stuck_state()

                results.append(f"Step {self.current_step}: {step_result}")

            # Terminate on reaching max steps: report as UNVERIFIED, not done.
            if self.state == AgentState.RUNNING:
                self.transition_to(
                    AgentState.IDLE,
                    reason=f"max steps ({self.max_steps}) reached without a "
                    "verified finish",
                )
                results.append(
                    f"Incomplete (reason code E-MAX-STEPS): reached max steps "
                    f"({self.max_steps}) without a verified finish. Outcome "
                    f"UNCONFIRMED — human review required."
                )

            # Verify the claimed outcome against actual state before saying
            # anything was resolved.
            if self.state == AgentState.FINISHED:
                self.transition_to(
                    AgentState.IDLE, reason="run() completed successfully"
                )
                results.append("Outcome: FINISHED (verified against agent state).")
            elif self.state == AgentState.ERROR:
                results.append(
                    "Outcome: ERROR — see audit trail for reason code and detail."
                )

        except Exception as e:
            # Fail safely: visible error state + reason code + recovery path.
            error_code = f"E-{type(e).__name__}"
            self.transition_to(
                AgentState.ERROR,
                reason=f"unhandled exception during run ({error_code})",
                detail=str(e),
            )
            results.append(
                f"Execution failed (reason code {error_code}): {e}. "
                f"Agent state is ERROR; audit trail preserved."
            )
            # Recovery path: reset so the agent can be used again after
            # review. The ERROR event remains in the trail as evidence.
            self.transition_to(
                AgentState.IDLE, reason="recovery reset after ERROR"
            )
            self.current_step = 0
            logger.error(f"🚨 Agent '{self.name}' run failed [{error_code}]: {e}")

        return "\n".join(results) if results else "No steps executed"

    @abstractmethod
    async def step(self) -> str:
        """Execute a single step in the agent's workflow.

        Must be implemented by subclasses to define specific behavior.
        """

    def handle_stuck_state(self):
        """Handle stuck state by adding a prompt to change strategy"""
        stuck_prompt = "\
        Observed duplicate responses. Consider new strategies and avoid repeating ineffective paths already attempted."
        self.next_step_prompt = f"{stuck_prompt}\n{self.next_step_prompt}"
        logger.warning(f"Agent detected stuck state. Added prompt: {stuck_prompt}")

    def is_stuck(self) -> bool:
        """Check if the agent is stuck in a loop by detecting duplicate content"""
        if len(self.memory.messages) < 2:
            return False

        last_message = self.memory.messages[-1]
        if not last_message.content:
            return False

        # Count identical content occurrences
        duplicate_count = sum(
            1
            for msg in reversed(self.memory.messages[:-1])
            if msg.role == "assistant" and msg.content == last_message.content
        )

        return duplicate_count >= self.duplicate_threshold

    @property
    def messages(self) -> List[Message]:
        """Retrieve a list of messages from the agent's memory."""
        return self.memory.messages

    @messages.setter
    def messages(self, value: List[Message]):
        """Set the list of messages in the agent's memory."""
        self.memory.messages = value
