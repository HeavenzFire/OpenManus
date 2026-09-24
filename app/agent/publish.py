"""Publish local verification evidence into unified-field protocol records.

Read-only over existing artifacts: it consumes the hash-chained ledger,
root anchors, and test outcomes already produced by this repository, and
emits canonical, integrity-noticed records that any external consumer of
the unified field program can verify independently.

Usage:
    python -m app.agent.publish [--ledger PATH] [--anchor-dir DIR] [--out DIR]

With no arguments it runs a self-contained demonstration against a temp
directory (same isolation discipline as demos/root_anchor_negative_test.py):
build a small synthetic ledger, anchor it, re-verify it, publish records.

Exit codes:
    0  all published observations are MATCHED / EXPECTED_VARIANCE
    1  at least one UNEXPLAINED_DIVERGENCE was published
    2  NOT_COMPARABLE (e.g. missing anchor) -- honest refusal, not success
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform as _platform
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent import ledger as L  # noqa: E402
from app.agent.protocol import (  # noqa: E402
    EXPECTED_VARIANCE_FIELDS,
    build_record,
    canonical_bytes,
    compare_records,
    current_commit,
    freeze_inputs,
)
from app.agent.root_anchor import verify_against_anchor  # noqa: E402

FAIL_STATUSES = {"UNEXPLAINED_DIVERGENCE"}
REFUSE_STATUSES = {"NOT_COMPARABLE"}


def fixture_root_sha256(path: Path) -> str:
    """Hash a fixture archive so comparisons can prove they saw the same data."""
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def publish_ledger_status(
    *,
    ledger_path: Path,
    anchor_file: Path,
    command: str,
    fixture_sha: Optional[str] = None,
) -> dict[str, Any]:
    """One observation record: does this ledger still match its preserved root?

    The anchor is the separately-preserved trusted root; a MATCHED status
    here means exactly 'bytes agree against that root', nothing more.
    """
    events = L.read_events(ledger_path)
    inputs = freeze_inputs(
        repository_commit=current_commit(),
        python_version=sys.version.split()[0],
        platform=f"{_platform.system().lower()}-{_platform.machine().lower()}",
        command=command,
        fixture_root_sha256=fixture_sha,
    )
    result = verify_against_anchor(ledger_path, anchor_file)
    status = result["status"]
    observed = {
        "event_count": len(events),
        "local_chain_valid": L.verify_chain(events)[0],
        "first_divergent_index": result.get("first_divergent_index"),
        "anchored_root": result.get("anchored_root"),
        "recomputed_root": result.get("recomputed_root"),
    }
    reason = result.get("reason")  # root_anchor reports reason codes under "reason"
    return build_record(
        subject=f"ledger:{ledger_path.name}",
        status=status,
        reason_code=reason,
        inputs=inputs,
        observed=observed,
    )


def write_record(record: dict[str, Any], out_dir: Path) -> Path:
    """Atomically write one record; filename derives from its own hash."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{record['record_sha256'][:16]}.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(canonical_bytes(record) + b"\n")
    tmp.replace(target)
    return target


def _demo(tmp: Path) -> int:
    """Self-contained publish run: healthy ledger, then tampered copy."""
    ledger = tmp / "ledger.jsonl"
    for i in range(5):
        L.append_event(ledger, {"seq": i, "agent": "publish-demo", "state": "IDLE", "detail": i})
    anchor_dir = tmp / "anchors"
    from app.agent.root_anchor import create_root_anchor

    anchor = create_root_anchor(ledger, anchor_dir)
    anchor_file = Path(anchor["anchor_file"])  # root_anchor-1.0 reports path under "anchor_file"

    ok = publish_ledger_status(ledger_path=ledger, anchor_file=anchor_file, command="python -m app.agent.publish (demo)")
    write_record(ok, tmp / "published")

    # Tamper with a COPY after the root was preserved; expect divergence.
    tampered = tmp / "tampered.jsonl"
    tampered.write_bytes(ledger.read_bytes())
    events = L.read_events(tampered)
    events[2]["detail"] = "ALTERED"
    tampered.write_text("".join(json.dumps(e, sort_keys=True, separators=(",", ":")) + "\n" for e in events))
    bad = publish_ledger_status(ledger_path=tampered, anchor_file=anchor_file, command="python -m app.agent.publish (demo-tamper)")
    write_record(bad, tmp / "published")

    verdict = compare_records(ok, {**bad, "subject": ok["subject"]})
    print(json.dumps({"healthy": ok["status"], "tampered": bad["status"], "comparison": verdict["status"]}, indent=2))
    assert ok["status"] == "MATCHED", ok
    assert bad["status"] == "UNEXPLAINED_DIVERGENCE", bad
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--anchor-file", type=Path)
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--out", type=Path, default=Path("logs/published"))
    parser.add_argument("--demo", action="store_true", help="run isolated demo instead of real paths")
    args = parser.parse_args(argv)

    if args.demo or not (args.ledger and args.anchor_file):
        with tempfile.TemporaryDirectory(prefix="ufp-publish-") as td:
            return _demo(Path(td))

    record = publish_ledger_status(
        ledger_path=args.ledger,
        anchor_file=args.anchor_file,
        command=" ".join(sys.argv),
        fixture_sha=fixture_root_sha256(args.fixtures) if args.fixtures else None,
    )
    written = write_record(record, args.out)
    print(f"published {written} status={record['status']} reason={record['reason_code']}")
    if record["status"] in FAIL_STATUSES:
        return 1
    if record["status"] in REFUSE_STATUSES:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
