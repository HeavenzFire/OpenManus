"""Reliability tests for the audited agent state machine.

These encode the measurable guarantees:
- No unlogged state transitions.
- Every failure produces a visible error state, reason code, and recovery path.
- No "resolved" status without a verified outcome.
"""

import asyncio
import json

import pytest

from app.agent.base import BaseAgent, _audit_log_path
from app.schema import AgentState


class DummyAgent(BaseAgent):
    """Minimal concrete agent whose step behaviour is test-controlled."""

    name: str = "dummy"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.step_outputs = []
        self.step_error = None

    async def step(self) -> str:
        if self.step_error:
            raise self.step_error
        if self.step_outputs:
            return self.step_outputs.pop(0)
        return "ok"


@pytest.fixture(autouse=True)
def isolated_audit_log(tmp_path, monkeypatch):
    """Redirect the audit log into a temp dir so tests leave no side effects."""
    log_file = tmp_path / "logs" / "agent_audit.jsonl"
    monkeypatch.setattr(
        "app.agent.base._audit_log_path", lambda: log_file, raising=True
    )
    return log_file


def make_agent(**kwargs) -> DummyAgent:
    # Construct through the normal validator path so memory/llm are
    # initialized; tests never actually call the model.
    agent = DummyAgent(
        name="dummy",
        description="test agent",
        system_prompt=None,
        next_step_prompt=None,
        state=AgentState.IDLE,
        max_steps=kwargs.get("max_steps", 3),
    )
    agent.step_outputs = kwargs.get("step_outputs", [])
    agent.step_error = kwargs.get("step_error")
    return agent


class TestTransitionTo:
    def test_legal_transition_is_audited(self):
        agent = make_agent()
        assert agent.transition_to(AgentState.RUNNING, reason="test start")
        assert agent.state == AgentState.RUNNING
        assert len(agent.audit_trail) == 1
        event = agent.audit_trail[0]
        assert event.from_state == "IDLE"
        assert event.to_state == "RUNNING"
        assert event.reason == "test start"
        assert event.timestamp is not None

    def test_illegal_transition_rejected_and_state_unchanged(self):
        agent = make_agent()
        # IDLE -> FINISHED is not a legal edge.
        assert not agent.transition_to(AgentState.FINISHED, reason="shortcut")
        assert agent.state == AgentState.IDLE
        # Rejection itself must be visible in logs, but must NOT mutate state.
        assert agent.audit_trail == []

    def test_invalid_state_type_rejected(self):
        agent = make_agent()
        assert not agent.transition_to("RUNNING", reason="string not enum")
        assert agent.state == AgentState.IDLE

    def test_audit_write_failure_blocks_transition(self, monkeypatch):
        # Simulate an unavailable audit sink (full disk, read-only mount...).
        # We cannot rely on chmod here because tests may run as root.
        def fail_write(*args, **kwargs):
            raise OSError("simulated disk failure")

        # Patch the ledger sink directly so write_audit_event's own
        # wrap-and-reraise (RuntimeError) is what callers observe.
        monkeypatch.setattr("app.agent.base.ledger.append_event", fail_write)
        agent = make_agent()
        with pytest.raises(RuntimeError, match="simulated disk failure"):
            agent.transition_to(AgentState.RUNNING, reason="should not apply")
        # Fail-safe: state was NOT changed because evidence could not be kept.
        assert agent.state == AgentState.IDLE
        # Nothing enters the in-memory trail either: an event that never
        # reached the durable ledger must not masquerade as recorded evidence.
        assert len(agent.audit_trail) == 0


class TestRunLoop:
    @pytest.mark.asyncio
    async def test_finished_requires_verified_state(self, isolated_audit_log):
        agent = make_agent(step_outputs=["a", "b"])

        original_step = agent.step

        async def step_then_finish():
            result = await original_step()
            # Simulate the terminate tool signalling completion via the
            # audited transition (as ToolCallAgent now does).
            agent.transition_to(AgentState.FINISHED, reason="terminate called")
            return result

        agent.step = step_then_finish
        output = await agent.run("do a thing")
        assert "FINISHED (verified against agent state)" in output
        # Recovery: agent returns to IDLE and is reusable.
        assert agent.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_max_steps_reported_as_unconfirmed(self, isolated_audit_log):
        agent = make_agent(max_steps=2)
        output = await agent.run("loop forever")
        assert "E-MAX-STEPS" in output
        assert "UNCONFIRMED" in output
        assert "FINISHED" not in output  # never claim success without evidence
        assert agent.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_current_step_resets_between_runs(self, isolated_audit_log):
        agent = make_agent(max_steps=2)
        await agent.run("first")
        assert agent.current_step == 2  # exhausted budget
        agent.step_outputs = ["x"]
        out = await agent.run("second")
        # Second run got a FRESH budget (bug fix: previously it would
        # immediately re-trigger termination or RuntimeError).
        assert "Step 1: x" in out
        assert agent.current_step == 2  # ran steps 1..2 again

    @pytest.mark.asyncio
    async def test_failure_produces_error_state_reason_code_recovery(
        self, isolated_audit_log
    ):
        agent = make_agent(step_error=ValueError("boom"))
        output = await agent.run("will fail")
        assert "E-ValueError" in output  # visible reason code
        assert "audit trail preserved" in output
        # Recovery path: reset to IDLE...
        assert agent.state == AgentState.IDLE
        # ...but the ERROR evidence remains in the trail.
        states = [(e.from_state, e.to_state) for e in agent.audit_trail]
        assert ("RUNNING", "ERROR") in states
        assert ("ERROR", "IDLE") in states
        # Agent is reusable after failure.
        agent.step_error = None
        agent.step_outputs = ["recovered"]
        out2 = await agent.run("retry")
        assert "Step 1: recovered" in out2


class TestAuditPersistence:
    @pytest.mark.asyncio
    async def test_events_persisted_as_jsonl(self, isolated_audit_log):
        agent = make_agent(max_steps=1)
        await agent.run("persist me")
        lines = isolated_audit_log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 2  # at least IDLE->RUNNING and RUNNING->IDLE
        for line in lines:
            record = json.loads(line)
            assert {"timestamp", "agent", "from_state", "to_state", "reason"} <= set(
                record
            )

    def test_export_execution_record(self):
        agent = make_agent()
        agent.transition_to(AgentState.RUNNING, reason="export test")
        record = agent.export_execution_record()
        assert record["agent"] == "dummy"
        assert record["final_state"] == "RUNNING"
        assert record["events"][0]["to_state"] == "RUNNING"
        # Must be JSON-serializable for user export.
        json.dumps(record)


if __name__ == "__main__":
    print(f"(audit log default location for reference: {_audit_log_path()})")


# ---- chained-ledger integration (this turn's increment) ----


def test_transitions_form_valid_hash_chain():
    agent = make_agent()
    assert agent.transition_to(AgentState.RUNNING, reason="start")
    assert agent.transition_to(AgentState.FINISHED, reason="done")
    assert agent.verify_audit_trail() is True
    # in-memory trail carries the chain fields written by the ledger
    for e in agent.audit_trail:
        assert e.prev_hash and e.event_hash


def test_persisted_ledger_detects_after_the_fact_edit(isolated_audit_log):
    """Edit the durable file after the fact; verification must go red."""
    agent = make_agent()
    assert agent.transition_to(AgentState.RUNNING, reason="start")
    assert agent.transition_to(AgentState.FINISHED, reason="done")
    lines = isolated_audit_log.read_text().splitlines()
    ev = json.loads(lines[0])
    ev["reason"] = "REWRITTEN HISTORY"
    lines[0] = json.dumps(ev, sort_keys=True)
    isolated_audit_log.write_text("\n".join(lines) + "\n")

    from app.agent import ledger

    ok, broken = ledger.verify_chain(ledger.read_events(isolated_audit_log))
    assert ok is False and broken == 0


def test_export_record_manifest_root_and_integrity_only_label():
    from app.agent import ledger

    agent = make_agent()
    agent.transition_to(AgentState.RUNNING, reason="start")
    rec = agent.export_execution_record()
    integ = rec["integrity"]
    assert len(integ["manifest_root"]) == 64
    assert integ["chain_valid"] is True
    assert "byte-integrity-only" in integ["attestation"]
    # a tampered copy of the exported events fails chain verification
    tampered = json.loads(json.dumps(rec))
    tampered["events"][0]["reason"] = "FORGED"
    assert ledger.verify_chain(tampered["events"])[0] is False


@pytest.mark.asyncio
async def test_run_loop_records_chain_through_completion(isolated_audit_log):
    from app.agent import ledger

    agent = make_agent(step_outputs=["Thinking: done\nFinal Answer: 42"])
    await agent.run()
    events = ledger.read_events(isolated_audit_log)
    assert len(events) >= 2
    assert ledger.verify_chain(events)[0] is True
