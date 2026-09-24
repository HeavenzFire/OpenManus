"""Tests for the hash-chained, tamper-evident audit ledger.

Encodes: "No silent state change" strengthened to
"No retroactive edit goes undetected" — and proves it with NEGATIVE tests
(alter-after-write, delete, reorder, re-hash attempts).
"""

import json
from pathlib import Path

import pytest

from app.agent import ledger


@pytest.fixture
def chain_file(tmp_path):
    return tmp_path / "ledger.jsonl"


def _append_n(path, n):
    for i in range(n):
        ledger.append_event(path, {"seq": i, "note": f"event-{i}"})


def test_append_links_to_genesis(chain_file):
    recorded, h = ledger.append_event(chain_file, {"seq": 0})
    assert recorded["prev_hash"] == ledger.GENESIS_HASH
    assert h == recorded["event_hash"]
    assert ledger.verify_chain(ledger.read_events(chain_file)) == (True, None)


def test_valid_chain_after_many_appends(chain_file):
    _append_n(chain_file, 5)
    events = ledger.read_events(chain_file)
    ok, broken = ledger.verify_chain(events)
    assert ok and broken is None
    # linkage actually links
    for a, b in zip(events, events[1:]):
        assert b["prev_hash"] == a["event_hash"]


def test_tamper_mid_event_detected_in_used_data(chain_file):
    """Alter a field AFTER hash creation, in the file verification reads."""
    _append_n(chain_file, 4)
    lines = chain_file.read_text().splitlines()
    ev = json.loads(lines[2])
    ev["note"] = "FORGED"          # post-hoc edit, hashes untouched
    lines[2] = json.dumps(ev, sort_keys=True)
    chain_file.write_text("\n".join(lines) + "\n")

    ok, broken = ledger.verify_chain(ledger.read_events(chain_file))
    assert ok is False and broken == 2


def test_deletion_detected(chain_file):
    _append_n(chain_file, 4)
    lines = chain_file.read_text().splitlines()
    del lines[1]                    # remove one event entirely
    chain_file.write_text("\n".join(lines) + "\n")
    ok, broken = ledger.verify_chain(ledger.read_events(chain_file))
    assert ok is False and broken == 1


def test_reorder_detected(chain_file):
    _append_n(chain_file, 3)
    lines = chain_file.read_text().splitlines()
    lines[0], lines[1] = lines[1], lines[0]
    chain_file.write_text("\n".join(lines) + "\n")
    ok, _ = ledger.verify_chain(ledger.read_events(chain_file))
    assert ok is False


def test_naive_rehash_without_upstream_cascade_detected(chain_file):
    """Attacker edits event 1 AND recomputes its own hash, but cannot fix
    event 2's prev_hash commitment without rewriting the whole tail."""
    _append_n(chain_file, 3)
    events = ledger.read_events(chain_file)
    events[1]["note"] = "FORGED"
    events[1]["event_hash"] = ledger.compute_event_hash(
        events[1], events[1]["prev_hash"]
    )
    ok, broken = ledger.verify_chain(events)
    assert ok is False and broken == 2   # breaks at the NEXT link


def test_append_refused_on_broken_chain(chain_file):
    _append_n(chain_file, 2)
    lines = chain_file.read_text().splitlines()
    ev = json.loads(lines[0])
    ev["note"] = "FORGED"
    lines[0] = json.dumps(ev, sort_keys=True)
    chain_file.write_text("\n".join(lines) + "\n")

    with pytest.raises(RuntimeError, match="E-LEDGER-BROKEN"):
        ledger.append_event(chain_file, {"seq": 99})
    # refusal must not have written anything
    assert len(ledger.read_events(chain_file)) == 2


def test_canonical_serialization_is_key_order_independent():
    a = {"b": 1, "a": 2, "c": {"y": 2, "x": 1}}
    b = {"c": {"x": 1, "y": 2}, "a": 2, "b": 1}
    assert ledger.compute_event_hash(a, "p") == ledger.compute_event_hash(b, "p")
    # ...and content-sensitive
    c = {"a": 2, "b": 1, "c": {"x": 1, "y": 999}}
    assert ledger.compute_event_hash(a, "p") != ledger.compute_event_hash(c, "p")


def test_empty_chain_is_valid_and_tip_is_genesis():
    assert ledger.verify_chain([]) == (True, None)
    assert ledger.chain_tip([]) == ledger.GENESIS_HASH


# ---------------------------------------------------------------------------
# Root anchors: detect alterations against a SEPARATELY PRESERVED trusted root
# ---------------------------------------------------------------------------


def test_anchor_matches_untouched_ledger(tmp_path):
    from app.agent.root_anchor import create_root_anchor, verify_against_anchor

    log = tmp_path / "ledger.jsonl"
    for i in range(3):
        ledger.append_event(log, {"agent": "a", "to_state": "RUNNING", "i": i})
    anchor = create_root_anchor(log, tmp_path / "roots")
    result = verify_against_anchor(log, Path(anchor["anchor_file"]))
    assert result["status"] == "MATCHED"
    assert result["ok"] is True
    # Integrity-only self-labeling on every export (oath requirement).
    assert "does not attest to truth" in result["integrity_notice"]


def test_anchor_detects_full_consistent_rewrite(tmp_path):
    """The exact attack local chaining cannot see — re-hash everything —
    IS caught against the preserved root."""
    import json

    from app.agent.root_anchor import create_root_anchor, verify_against_anchor

    log = tmp_path / "ledger.jsonl"
    for i in range(3):
        ledger.append_event(log, {"agent": "a", "to_state": "RUNNING", "i": i})
    anchor = create_root_anchor(log, tmp_path / "roots")

    # Attacker edits event 1 and recomputes the whole chain consistently.
    events = ledger.read_events(log)
    events[1]["to_state"] = "FORGED"
    prev = "0" * 64
    lines = []
    for e in events:
        e.pop("prev_hash", None)
        e.pop("event_hash", None)
        h = ledger.compute_event_hash({**e, "prev_hash": prev}, prev)
        e["prev_hash"], e["event_hash"] = prev, h
        lines.append(json.dumps(e, sort_keys=True, separators=(",", ":")))
        prev = h
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Internally consistent again...
    ok, _ = ledger.verify_chain(ledger.read_events(log))
    assert ok is True
    # ...but the preserved root exposes it.
    result = verify_against_anchor(log, Path(anchor["anchor_file"]))
    assert result["status"] == "UNEXPLAINED_DIVERGENCE"
    assert result["reason"] == "E-ANCHOR-TIP-MISMATCH"
    assert result["recomputed_root"] != result["anchored_root"]


def test_anchor_refuses_empty_ledger(tmp_path):
    from app.agent.root_anchor import AnchorError, create_root_anchor

    empty = tmp_path / "empty.jsonl"
    empty.touch()
    with pytest.raises(AnchorError) as exc:
        create_root_anchor(empty, tmp_path / "roots")
    assert exc.value.code == "E-ANCHOR-EMPTY-LEDGER"


def test_anchor_missing_is_not_comparable_not_silently_ok(tmp_path):
    """A missing anchor must NEVER read as success — fail closed."""
    from app.agent.root_anchor import verify_against_anchor

    log = tmp_path / "ledger.jsonl"
    ledger.append_event(log, {"agent": "a", "to_state": "RUNNING"})
    result = verify_against_anchor(log, tmp_path / "nope.json")
    assert result["ok"] is False
    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "E-ANCHOR-MISSING"


def test_anchor_detects_truncation(tmp_path):
    """Valid prefix of an anchored chain still diverges by count+root."""
    from app.agent.root_anchor import create_root_anchor, verify_against_anchor

    log = tmp_path / "ledger.jsonl"
    for i in range(4):
        ledger.append_event(log, {"agent": "a", "to_state": "RUNNING", "i": i})
    anchor = create_root_anchor(log, tmp_path / "roots")

    lines = log.read_text(encoding="utf-8").splitlines()
    log.write_text("\n".join(lines[:3]) + "\n", encoding="utf-8")  # drop last event
    result = verify_against_anchor(log, Path(anchor["anchor_file"]))
    assert result["status"] == "UNEXPLAINED_DIVERGENCE"
    assert result["reason"] in ("E-ANCHOR-COUNT-MISMATCH", "E-ANCHOR-CHAIN-BROKEN")
