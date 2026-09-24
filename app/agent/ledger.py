"""Tamper-evident, hash-chained append-only audit ledger.

Every event commits to every prior event via a SHA-256 chain, so deleting,
reordering, or editing any historical record breaks the chain and is loudly
detectable by ``verify_chain()``.

HONEST LIMITS (see LIMITATIONS.md): this proves *bit-level* integrity of the
file only. It is not WORM storage, not a court-admissible timestamp, not a
blockchain, and not proof that the recorded facts are true.
"""

import hashlib
import json
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

GENESIS_HASH = "0" * 64


def _canonical(event: dict) -> str:
    """Deterministic serialization: sorted keys, no whitespace.

    Key order must never change the digest, otherwise verification would
    depend on dict insertion history rather than content.
    """
    return json.dumps(event, sort_keys=True, separators=(",", ":"))


def compute_event_hash(event: dict, prev_hash: str) -> str:
    body = dict(event)
    body.pop("prev_hash", None)
    body.pop("event_hash", None)
    payload = prev_hash + "\n" + _canonical(body)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_event(path: Path, event: dict) -> Tuple[dict, str]:
    """Append one chained event. Returns (recorded_event, event_hash).

    Fail-safe ordering: if the previous line in the file does not verify
    against its own claimed hash, the append is REFUSED with reason code
    E-LEDGER-BROKEN — we never extend a ledger whose past is already suspect.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_events(path)
    ok, _ = verify_chain(existing)
    if not ok:
        raise RuntimeError(
            f"E-LEDGER-BROKEN refusing append to {path}: existing chain invalid"
        )
    prev_hash = existing[-1]["event_hash"] if existing else GENESIS_HASH
    recorded = dict(event)
    recorded["prev_hash"] = prev_hash
    recorded["event_hash"] = compute_event_hash(recorded, prev_hash)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(recorded, sort_keys=True, separators=(",", ":")) + "\n")
    return recorded, recorded["event_hash"]


def read_events(path: Path) -> List[dict]:
    if not Path(path).exists():
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def verify_chain(events: Iterable[dict]) -> Tuple[bool, Optional[int]]:
    """Return (valid, first_broken_index). Broken means: wrong hash, broken
    linkage, or genesis mismatch. An empty chain is valid (nothing forged yet).
    """
    prev_hash = GENESIS_HASH
    for i, ev in enumerate(events):
        if ev.get("prev_hash") != prev_hash:
            return False, i
        recomputed = compute_event_hash(ev, prev_hash)
        if recomputed != ev.get("event_hash"):
            return False, i
        prev_hash = ev["event_hash"]
    return True, None


def chain_tip(events: Iterable[dict]) -> str:
    """Hash over the whole chain — the 'manifest root' of the ledger."""
    tip = GENESIS_HASH
    for ev in events:
        tip = ev.get("event_hash", tip)
    return tip
