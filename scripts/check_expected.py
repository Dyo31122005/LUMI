"""Run each persona several times and report how often LUMI lands on the expected answer.

Acceptance criterion 2 of the build plan: the insurance type must be right in at
least 8 of 9 runs.

    python scripts/check_expected.py --runs 3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yaml  # noqa: E402

from core.session_io import session_to_dict  # noqa: E402
from scripts.run_cli import build_orchestrator  # noqa: E402

PERSONAS = ("vuong", "mai", "duc")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3, help="Runs per persona.")
    parser.add_argument("--engine", default="openai", choices=["openai", "rule"])
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "data" / "expected_report.json")
    args = parser.parse_args()

    expected = yaml.safe_load((PROJECT_ROOT / "data" / "expected.yaml").read_text(encoding="utf-8"))
    results: list[dict[str, object]] = []

    for persona_id in PERSONAS:
        want = expected[persona_id]
        for attempt in range(1, args.runs + 1):
            started = time.time()
            row: dict[str, object] = {"persona": persona_id, "run": attempt}
            try:
                orchestrator = build_orchestrator(persona_id, args.engine)
                session = orchestrator.run_auto(persona_id)
                record = session_to_dict(session)
                top = record["ranking"][0]["product_id"] if record["ranking"] else None
                row.update(
                    insurance_type=record["insurance_type"],
                    top_product=top,
                    type_ok=record["insurance_type"] == want["insurance_type"],
                    product_ok=top == want["top_product_id"],
                    questions=record["question_count"],
                    provenance=len(record["profile"].get("provenance", {})),
                    seconds=round(time.time() - started, 1),
                )
            except Exception as error:
                row.update(error=f"{type(error).__name__}: {error}", type_ok=False, product_ok=False)
            results.append(row)
            status = "OK " if row.get("type_ok") and row.get("product_ok") else "SAI"
            print(f"{status} {persona_id} #{attempt}: {row.get('insurance_type')} / {row.get('top_product')}"
                  f" ({row.get('seconds', '?')}s){' — ' + str(row['error']) if row.get('error') else ''}", flush=True)

    total = len(results)
    type_ok = sum(1 for row in results if row.get("type_ok"))
    product_ok = sum(1 for row in results if row.get("product_ok"))

    print("\n--- Tổng kết ---")
    print(f"Đúng loại bảo hiểm : {type_ok}/{total}")
    print(f"Đúng sản phẩm đầu  : {product_ok}/{total}")

    args.report.write_text(
        json.dumps({"results": results, "type_ok": type_ok, "product_ok": product_ok, "total": total},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Báo cáo: {args.report}")
    return 0 if type_ok >= total - 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
