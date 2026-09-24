"""Unified-Field Program bridge: canonical, byte-stable protocol records.

This module is the ONLY sanctioned connection point between local
verification artifacts (ledgers, root anchors, test runs) and any external
"unified field program" or downstream consumer. It exists so that a claim
about an artifact can be reduced to exactly one kind of sentence:

    "Under recorded inputs X, this code produced bytes B (hash H)."

Design rules (each enforced in code, not just prose):

1. Closed vocabulary.  A record may only carry statuses drawn from the
   four-value comparison lexicon.  Unknown values are rejected at
   construction time -- no silent state change reaches the outside world.
2. Integrity-only notice.  Every serialized record embeds the fixed
   byte-integrity notice.  Nothing produced here ever attests to truth,
   correctness, security, authorization, admissibility, or safety.
3. Canonical serialization.  Sorted keys, no whitespace, UTF-8 --
   identical to app.agent.ledger._canonical, so a record built here and a
   ledger root built there are comparable byte-for-byte across machines.
4. No ambient authority.  This module performs no network I/O, reads no
   secrets, and mutates nothing.  It turns evidence into text; humans
   decide what to do with the text.
5. Reproducibility inputs are explicit.  ``freeze_inputs`` captures the
   environment facts a comparison needs; if any frozen input differs,
   comparisons must be labeled NOT_COMPARABLE rather than "drift".
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from typing import Any, Optional

PROTOCOL_VERSION = "unified-field-bridge-1.0"
SERIALIZATION_VERSION = "canonical-json-1.0"

#: The complete status vocabulary.  Extend only by version bump + tests.
COMPARISON_STATUSES = ("MATCHED", "EXPECTED_VARIANCE", "UNEXPLAINED_DIVERGENCE", "NOT_COMPARABLE")

#: Declared non-semantic input fields: differences confined to these keys
#: (with identical evidence bytes) are EXPECTED_VARIANCE, never drift.
#: 'command' qualifies because invocation text does not change what ran.
EXPECTED_VARIANCE_FIELDS = frozenset({"command"})

#: Fixed wording.  If you are tempted to make it softer: no.
INTEGRITY_NOTICE = (
    "Byte-integrity-only; does not attest to truth, completeness, "
    "authorization, admissibility, correctness, security, or safety of contents."
)


class ProtocolError(Exception):
    """Raised when a record would violate the bridge's closed vocabulary."""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


def canonical_bytes(record: dict[str, Any]) -> bytes:
    """Deterministic serialization shared with the ledger's chain rule."""
    return json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")


def canonical_sha256(record: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(record)).hexdigest()


def freeze_inputs(
    *,
    repository_commit: str,
    python_version: str,
    platform: str,
    command: str,
    fixture_root_sha256: Optional[str] = None,
    extra: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Record the declared inputs of one execution.

    A dual-instance comparison is only meaningful over a frozen input set;
    anything absent here cannot later be blamed for a divergence, and
    anything present-but-different makes the honest label NOT_COMPARABLE.
    """
    frozen = {
        "repository_commit": repository_commit,
        "python_version": python_version,
        "platform": platform,
        "command": command,
        "protocol_version": PROTOCOL_VERSION,
        "serialization_version": SERIALIZATION_VERSION,
    }
    if fixture_root_sha256 is not None:
        frozen["fixture_root_sha256"] = fixture_root_sha256
    if extra:
        frozen.update({k: str(v) for k, v in extra.items()})
    return frozen


def build_record(
    *,
    subject: str,
    status: str,
    reason_code: Optional[str],
    inputs: dict[str, str],
    observed: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Assemble one unified-field observation record.

    Rejects (fail-closed, with a reason code) any status outside the
    closed vocabulary and any empty subject -- an unlabelled observation
    is exactly the kind of silent claim this bridge exists to prevent.
    """
    if not subject or not subject.strip():
        raise ProtocolError("E-RECORD-SUBJECT", "record subject must be non-empty")
    if status not in COMPARISON_STATUSES:
        raise ProtocolError(
            "E-RECORD-STATUS",
            f"status {status!r} not in closed vocabulary {COMPARISON_STATUSES}",
        )
    if not inputs.get("repository_commit"):
        raise ProtocolError(
            "E-RECORD-INPUTS", "records require a frozen input set with a commit identity"
        )
    record: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "subject": subject,
        "status": status,
        "reason_code": reason_code,
        "inputs": inputs,
        "integrity_notice": INTEGRITY_NOTICE,
    }
    if observed is not None:
        record["observed"] = observed
    record["record_sha256"] = canonical_sha256(record)
    return record


def compare_records(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Reduce two records from two environments to one honest verdict.

    Ordering matters and encodes the oath: incomparable *identity* inputs
    outrank any apparent agreement or disagreement, because matching bytes
    from different universes prove nothing. Differences confined to fields
    declared non-semantic (EXPECTED_VARIANCE_FIELDS, e.g. the recorded
    command line) are labeled EXPECTED_VARIANCE, not drift.
    """
    identity_keys = (set(a["inputs"]) | set(b["inputs"])) - EXPECTED_VARIANCE_FIELDS
    input_mismatch = sorted(
        k
        for k in identity_keys
        if a["inputs"].get(k) != b["inputs"].get(k)
    )
    variance_only = sorted(
        k
        for k in EXPECTED_VARIANCE_FIELDS & (set(a["inputs"]) | set(b["inputs"]))
        if a["inputs"].get(k) != b["inputs"].get(k)
    )
    if input_mismatch:
        status, reason = "NOT_COMPARABLE", "E-INPUTS-DIFFER"
        detail = {"differing_inputs": input_mismatch}
    elif a["subject"] != b["subject"]:
        status, reason = "NOT_COMPARABLE", "E-SUBJECT-MISMATCH"
        detail = {}
    else:
        # Inputs identical: compare everything except the volatile hash we add last.
        strip = lambda r: {k: v for k, v in r.items() if k != "record_sha256"}
        if canonical_bytes(strip(a)) == canonical_bytes(strip(b)):
            status, reason = "MATCHED", None
        elif variance_only:
            status, reason = "EXPECTED_VARIANCE", "V-NONSEMANTIC-FIELDS"
        else:
            status, reason = "UNEXPLAINED_DIVERGENCE", "E-BYTES-DIFFER"
        detail = {"variance_fields": variance_only} if variance_only else {}
    return build_record(
        subject=f"comparison:{a['subject']}",
        status=status,
        reason_code=reason,
        inputs=a["inputs"],
        observed={"left": a["record_sha256"], "right": b["record_sha256"], **detail},
    )


def current_commit() -> str:
    """Best-effort HEAD identity for freezing inputs (read-only)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() or "UNKNOWN"
    except Exception:
        return "UNKNOWN"
