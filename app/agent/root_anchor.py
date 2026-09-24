"""Separately-preserved trusted root anchors for hash-chained ledgers.

Trust model (deliberately narrow):
    A local SHA-256 hash chain makes post-capture modification detectable
    *against a separately preserved trusted root*, within this threat model:

      - The anchor file must live outside the attacker's write scope
        (printed on paper, notarized, or published elsewhere). This module
        only provides the software half; it cannot protect an attacker who
        can rewrite the ledger AND the anchor together.
      - Byte-integrity only: matching anchors attest that bytes are unchanged
        since capture. They do not attest to truth, completeness,
        authorization, admissibility, or safety of contents.

Failure is explicit: every refusal carries a reason code (E-ANCHOR-*).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.agent.ledger import (
    GENESIS_HASH,
    _canonical,
    compute_event_hash,
    read_events,
)

SERIALIZATION_VERSION = "canonical-json-1.0"  # matches ledger._canonical exactly


class AnchorError(RuntimeError):
    """Raised when an anchor operation fails safely (no partial state)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_root_anchor(
    ledger_path: str | Path,
    anchor_dir: str | Path,
) -> dict[str, Any]:
    """Capture the current chain tip as a trusted root in a separate directory.

    Refuses empty ledgers (EMPTY_BUNDLE class of failure) so a vacuous root
    can never silently 'verify' anything.
    """
    ledger_path = Path(ledger_path)
    if not ledger_path.exists():
        raise AnchorError("E-ANCHOR-NO-LEDGER", f"ledger not found: {ledger_path}")
    events = read_events(ledger_path)
    if not events:
        raise AnchorError("E-ANCHOR-EMPTY-LEDGER", "refusing to anchor an empty ledger")

    last_event = events[-1]
    tip_hash = last_event.get("event_hash")
    if not isinstance(tip_hash, str) or len(tip_hash) != 64:
        raise AnchorError("E-ANCHOR-BAD-TIP", "last ledger event has no valid event_hash field")

    anchor_dir = Path(anchor_dir)
    anchor_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "protocol": "root-anchor-1.0",
        "ledger_file": str(ledger_path),
        "event_count": len(events),
        "tip_index": len(events) - 1,
        "tip_hash": tip_hash,
        "serialization_version": SERIALIZATION_VERSION,
        "anchored_at_utc": _utc_now_iso(),
        "integrity_notice": (
            "Byte-integrity-only; does not attest to truth, completeness, "
            "authorization, admissibility, or safety of contents."
        ),
    }
    # Deterministic file name derived from content identity + tip so repeated
    # anchors of the same ledger state collide loudly rather than silently.
    name = f"anchor-{tip_hash[:16]}.json"
    anchor_file = anchor_dir / name
    if anchor_file.exists():
        existing = json.loads(anchor_file.read_text(encoding="utf-8"))
        if existing["tip_hash"] != tip_hash or existing["event_count"] != len(events):
            raise AnchorError(
                "E-ANCHOR-COLLISION",
                f"different ledger state maps to same anchor name: {anchor_file}",
            )
    payload = _canonical(record)
    # Atomic write: temp file in the anchor dir, then rename. No partial anchors.
    fd, tmp = tempfile.mkstemp(dir=str(anchor_dir), prefix=".anchor-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
        os.replace(tmp, anchor_file)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    record["anchor_file"] = str(anchor_file)
    return record


def verify_against_anchor(
    ledger_path: str | Path, anchor_file: str | Path
) -> dict[str, Any]:
    """Verify a ledger against one preserved anchor. Never mutates either file."""
    ledger_path = Path(ledger_path)
    anchor_file = Path(anchor_file)
    result: dict[str, Any] = {
        "ok": False,
        "status": "NOT_COMPARABLE",
        "reason": None,
        "first_divergent_seq": None,
        "recomputed_root": None,
        "anchored_root": None,
        "integrity_notice": (
            "Byte-integrity-only; does not attest to truth, completeness, "
            "authorization, admissibility, or safety of contents."
        ),
    }
    if not ledger_path.exists():
        result["reason"] = "E-ANCHOR-NO-LEDGER"
        return result
    if not anchor_file.exists():
        result["reason"] = "E-ANCHOR-MISSING"
        return result

    try:
        anchor = json.loads(anchor_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        result["reason"] = "E-ANCHOR-CORRUPT"
        return result
    if anchor.get("protocol") != "root-anchor-1.0":
        result["reason"] = "E-ANCHOR-PROTOCOL"
        return result

    events = read_events(ledger_path)
    recomputed_tip, first_bad = _recompute_chain(events)
    result["recomputed_root"] = recomputed_tip
    result["anchored_root"] = anchor.get("tip_hash")
    result["first_divergent_index"] = first_bad

    if first_bad is not None:
        result["status"] = "UNEXPLAINED_DIVERGENCE"
        result["reason"] = "E-ANCHOR-CHAIN-BROKEN"
        return result
    if len(events) != anchor.get("event_count"):
        # Chain internally consistent but extended/truncated vs the captured root.
        result["status"] = "UNEXPLAINED_DIVERGENCE"
        result["reason"] = "E-ANCHOR-COUNT-MISMATCH"
        return result
    if recomputed_tip != anchor.get("tip_hash"):
        result["status"] = "UNEXPLAINED_DIVERGENCE"
        result["reason"] = "E-ANCHOR-TIP-MISMATCH"
        return result
    result["status"] = "MATCHED"
    result["ok"] = True
    result["reason"] = None
    return result


def _recompute_chain(events: list[dict]) -> tuple[Optional[str], Optional[int]]:
    """Replay the chain; return (tip_hash_or_None, first_divergent_index_or_None)."""
    if not events:
        return None, None
    prev_hash = GENESIS_HASH
    for i, ev in enumerate(events):
        if ev.get("prev_hash") != prev_hash:
            return None, i
        recomputed = compute_event_hash(ev, prev_hash)
        if recomputed != ev.get("event_hash"):
            return None, i
        prev_hash = recomputed
    return prev_hash, None
