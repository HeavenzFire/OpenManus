"""Tests for the unified-field bridge (app.agent.protocol / app.agent.publish).

Every test asserts on thrown errors or nonzero exits -- a rendered green
status object is never treated as proof.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent import ledger as L
from app.agent.protocol import (
    INTEGRITY_NOTICE,
    ProtocolError,
    build_record,
    canonical_bytes,
    compare_records,
    freeze_inputs,
)
from app.agent.publish import fixture_root_sha256, publish_ledger_status, write_record
from app.agent.root_anchor import create_root_anchor


def _inputs(**over):
    base = dict(
        repository_commit="deadbeef",
        python_version="3.12.0",
        platform="linux-x64",
        command="pytest",
    )
    base.update(over)
    return freeze_inputs(**base)


class TestClosedVocabulary:
    def test_unknown_status_rejected(self):
        with pytest.raises(ProtocolError) as exc:
            build_record(subject="x", status="PROBABLY_FINE", reason_code=None, inputs=_inputs())
        assert exc.value.code == "E-RECORD-STATUS"

    def test_empty_subject_rejected(self):
        with pytest.raises(ProtocolError) as exc:
            build_record(subject="   ", status="MATCHED", reason_code=None, inputs=_inputs())
        assert exc.value.code == "E-RECORD-SUBJECT"

    def test_missing_commit_identity_rejected(self):
        bad = _inputs()
        bad["repository_commit"] = ""
        with pytest.raises(ProtocolError) as exc:
            build_record(subject="x", status="MATCHED", reason_code=None, inputs=bad)
        assert exc.value.code == "E-RECORD-INPUTS"


class TestCanonicalization:
    def test_key_order_does_not_change_digest(self):
        a = {"z": 1, "a": {"y": 2, "b": 3}}
        b = {"a": {"b": 3, "y": 2}, "z": 1}
        assert canonical_bytes(a) == canonical_bytes(b)

    def test_record_hash_is_self_consistent_and_notice_embedded(self):
        rec = build_record(subject="s", status="MATCHED", reason_code=None, inputs=_inputs())
        stripped = {k: v for k, v in rec.items() if k != "record_sha256"}
        from app.agent.protocol import canonical_sha256

        assert rec["record_sha256"] == canonical_sha256(stripped)
        assert rec["integrity_notice"] == INTEGRITY_NOTICE

    def test_tampering_a_published_record_breaks_its_own_hash(self):
        rec = build_record(subject="s", status="MATCHED", reason_code=None, inputs=_inputs())
        tampered = json.loads(json.dumps(rec))
        tampered["status"] = "UNEXPLAINED_DIVERGENCE"
        from app.agent.protocol import canonical_sha256

        stripped = {k: v for k, v in tampered.items() if k != "record_sha256"}
        assert tampered["record_sha256"] != canonical_sha256(stripped)


class TestComparisonSemantics:
    def _pair(self, **over_b):
        ia, ib = _inputs(), _inputs(**{"command": over_b.get("command", "pytest")})
        if "commit" in over_b:
            ib = _inputs(repository_commit=over_b["commit"])
        a = build_record(subject="ledger:x.jsonl", status="MATCHED", reason_code=None, inputs=ia)
        b = build_record(subject="ledger:x.jsonl", status="MATCHED", reason_code=None, inputs=ib)
        return a, b

    def test_identical_records_match(self):
        a, b = self._pair()
        verdict = compare_records(a, b)
        assert verdict["status"] == "MATCHED"

    def test_differing_commit_is_not_comparable_not_drift(self):
        a, b = self._pair(commit="cafebabe")
        verdict = compare_records(a, b)
        assert verdict["status"] == "NOT_COMPARABLE"
        assert verdict["reason_code"] == "E-INPUTS-DIFFER"
        assert "repository_commit" in verdict["observed"]["differing_inputs"]

    def test_command_only_difference_is_expected_variance(self):
        a, b = self._pair(command="different invocation text")
        verdict = compare_records(a, b)
        assert verdict["status"] == "EXPECTED_VARIANCE"
        assert verdict["observed"]["variance_fields"] == ["command"]

    def test_subject_mismatch_refused(self):
        a, _ = self._pair()
        b = build_record(subject="other", status="MATCHED", reason_code=None, inputs=_inputs())
        verdict = compare_records(a, b)
        assert verdict["status"] == "NOT_COMPARABLE"
        assert verdict["reason_code"] == "E-SUBJECT-MISMATCH"


@pytest.fixture()
def anchored(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    for i in range(4):
        L.append_event(ledger, {"seq": i, "agent": "t", "state": "IDLE", "detail": i})
    anchor = create_root_anchor(ledger, tmp_path / "anchors")
    return ledger, Path(anchor["anchor_file"])


class TestPublishEndToEnd:
    def test_healthy_ledger_publishes_matched_with_roots(self, anchored):
        ledger, anchor_file = anchored
        rec = publish_ledger_status(
            ledger_path=ledger, anchor_file=anchor_file, command="pytest"
        )
        assert rec["status"] == "MATCHED"
        assert rec["observed"]["local_chain_valid"] is True
        assert len(rec["observed"]["anchored_root"]) == 64
        assert rec["observed"]["anchored_root"] == rec["observed"]["recomputed_root"]

    def test_alter_then_full_rehash_caught_only_by_anchor(self, anchored, tmp_path):
        """The nine-step protocol through the bridge: chaining alone loses to
        a cascaded rewrite; the separately preserved root wins."""
        ledger, anchor_file = anchored
        events = L.read_events(ledger)
        events[1]["detail"] = "ALTERED"
        # attacker rebuilds the whole chain consistently against itself
        evil = tmp_path / "evil.jsonl"
        prev = L.GENESIS_HASH
        lines = []
        for ev in events:
            h = L.compute_event_hash(ev, prev)
            rec = {**ev, "prev_hash": prev, "event_hash": h}
            lines.append(json.dumps(rec, sort_keys=True, separators=(",", ":")))
            prev = h
        evil.write_text("\n".join(lines) + "\n")
        assert L.verify_chain(L.read_events(evil))[0] is True  # local check fooled
        rec = publish_ledger_status(ledger_path=evil, anchor_file=anchor_file, command="pytest")
        assert rec["status"] == "UNEXPLAINED_DIVERGENCE"
        assert rec["reason_code"] == "E-ANCHOR-TIP-MISMATCH"

    def test_missing_anchor_fails_closed_as_not_comparable(self, anchored, tmp_path):
        ledger, _ = anchored
        rec = publish_ledger_status(
            ledger_path=ledger, anchor_file=tmp_path / "nope.json", command="pytest"
        )
        assert rec["status"] == "NOT_COMPARABLE"
        assert rec["reason_code"] == "E-ANCHOR-MISSING"

    def test_write_record_atomic_and_content_addressed(self, anchored, tmp_path):
        ledger, anchor_file = anchored
        rec = publish_ledger_status(
            ledger_path=ledger, anchor_file=anchor_file, command="pytest"
        )
        out = write_record(rec, tmp_path / "published")
        assert out.name.startswith(rec["record_sha256"][:16])
        assert not list((tmp_path / "published").glob("*.tmp"))
        reread = json.loads(out.read_text())
        assert reread["record_sha256"] == rec["record_sha256"]

    def test_fixture_hash_detects_one_byte_change(self, tmp_path):
        f = tmp_path / "claims.json"
        f.write_bytes(b'{"a":1}')
        h1 = fixture_root_sha256(f)
        f.write_bytes(b'{"a":2}')
        assert fixture_root_sha256(f) != h1

    def test_cli_demo_exit_zero(self):
        proc = subprocess.run(
            [sys.executable, "-m", "app.agent.publish"],
            capture_output=True, text=True, cwd=ROOT, timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["healthy"] == "MATCHED"
        assert payload["tampered"] == "UNEXPLAINED_DIVERGENCE"

    def test_cli_real_mode_divergence_exits_nonzero(self, anchored, tmp_path):
        proc = subprocess.run(
            [
                sys.executable, "-m", "app.agent.publish",
                "--ledger", str(anchored[0]),
                "--anchor-file", str(tmp_path / "absent.json"),
                "--out", str(tmp_path / "pub"),
            ],
            capture_output=True, text=True, cwd=ROOT, timeout=60,
        )
        assert proc.returncode == 2  # NOT_COMPARABLE = honest refusal, not success
