"""Run a LUMI persona in Auto mode from the terminal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.conversation import ConversationAgent  # noqa: E402
from agents.extractor import ProfileExtractor  # noqa: E402
from agents.simulator import CustomerSimulator  # noqa: E402
from agents.writer import AdvisorWriter  # noqa: E402
from core.decision import OpenAIEngine, RuleEngine  # noqa: E402
from core.kb import KnowledgeBase  # noqa: E402
from core.llm import LumiOpenAIClient  # noqa: E402
from core.orchestrator import Orchestrator  # noqa: E402
from core.session_io import session_to_dict  # noqa: E402


def build_orchestrator(persona: str, engine_name: str) -> Orchestrator:
    knowledge_base = KnowledgeBase.load()
    client = LumiOpenAIClient()
    decision_prompt = (PROJECT_ROOT / "prompts" / "decision.md").read_text(encoding="utf-8")
    engine = (
        RuleEngine(knowledge_base)
        if engine_name == "rule"
        else OpenAIEngine(client, decision_prompt, knowledge_base)
    )
    return Orchestrator(
        knowledge_base=knowledge_base,
        extractor=ProfileExtractor(client),
        conversation=ConversationAgent(client),
        engine=engine,
        writer=AdvisorWriter(client, knowledge_base),
        simulator=CustomerSimulator(persona, client),
    )


def main() -> int:
    # Windows PowerShell can default to CP1252, which cannot render Vietnamese.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("--persona", required=True, choices=["vuong", "mai", "duc"])
    parser.add_argument("--mode", required=True, choices=["auto"])
    parser.add_argument("--engine", default="openai", choices=["openai", "rule"])
    parser.add_argument("--max-questions", type=int, default=None)
    parser.add_argument("--output", type=Path, help="Optional JSON path for the session transcript.")
    parser.add_argument("--quiet", action="store_true", help="Only print the final summary.")
    args = parser.parse_args()

    orchestrator = build_orchestrator(args.persona, args.engine)

    def print_live(message: object) -> None:
        print(f"[{message.role}] {message.content}\n", flush=True)  # type: ignore[attr-defined]

    session = orchestrator.run_auto(
        args.persona,
        max_questions=args.max_questions,
        on_message=None if args.quiet else print_live,
    )

    record = session_to_dict(session)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    top = record["ranking"][0]["product_id"] if record["ranking"] else None
    print("--- Kết quả ---")
    print(f"Trạng thái      : {record['state']}")
    print(f"Số câu đã hỏi   : {record['question_count']}")
    print(f"Loại đề xuất    : {record['insurance_type']}")
    print(f"Sản phẩm đầu    : {top}")
    print(f"Trường có trích : {len(record['profile'].get('provenance', {}))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
