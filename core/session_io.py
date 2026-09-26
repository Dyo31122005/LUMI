"""Serialise a consultation so it can be replayed without any API call."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.finance import Scenario
from core.schemas import ChatMessage, InsightFlag, Profile

RECORDINGS_DIR = Path(__file__).resolve().parents[1] / "data" / "recordings"


def session_to_dict(session: Any) -> dict[str, Any]:
    return {
        "persona_id": session.persona_id,
        "address": session.address,
        "state": str(session.state),
        "question_count": session.question_count,
        "messages": [message.model_dump() for message in session.messages],
        "profile": session.profile.model_dump(),
        "derived": session.derived,
        "insurance_type": session.type_decision.insurance_type if session.type_decision else None,
        "type_decision": session.type_decision.model_dump() if session.type_decision else None,
        "turn_decisions": [item.model_dump() for item in session.turn_decisions],
        "insights": [item.model_dump() for item in session.insights],
        "why_ask": {str(key): value for key, value in session.why_ask.items()},
        "weights": session.weights,
        "weight_reasons": session.weight_reasons,
        "priority_criteria": session.priority_criteria,
        "ranking": [
            {
                "rank": item.rank,
                "product_id": item.product_id,
                "product_name": item.product["product_name"],
                "insurer": item.product["insurer"],
                "premium_display": (item.product.get("premium") or {}).get("display"),
                "fit_score": item.fit_score,
                "scores": item.scores.model_dump(),
                "notes": item.notes,
                "filter_notes": list(item.filter_notes),
                "strengths": list((item.product.get("personalization_tags") or {}).get("strengths") or ()),
                "watch_outs": list((item.product.get("personalization_tags") or {}).get("watch_outs") or ()),
                "investment_linked": bool(item.product.get("investment_linked")),
                "comparison_values": dict(item.product.get("comparison_values") or {}),
            }
            for item in session.ranked
        ],
        "excluded": [
            {"product_name": outcome.product["product_name"], "reasons": list(outcome.reasons)}
            for outcome in session.excluded
        ],
        "scenario": (
            {
                "kind": session.scenario.kind,
                "title": session.scenario.title,
                "lines": [[label, value] for label, value in session.scenario.lines],
                "note": session.scenario.note,
            }
            if session.scenario
            else None
        ),
    }


class Recording:
    """A finished session read back from disk, with no agent involved."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    @classmethod
    def load(cls, persona_id: str, directory: Path | None = None) -> "Recording":
        path = (directory or RECORDINGS_DIR) / f"{persona_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Chưa có phiên đã ghi cho {persona_id}: {path}")
        return cls(json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def available(directory: Path | None = None) -> list[str]:
        root = directory or RECORDINGS_DIR
        return sorted(path.stem for path in root.glob("*.json"))

    @property
    def persona_id(self) -> str | None:
        return self.data.get("persona_id")

    @property
    def messages(self) -> list[ChatMessage]:
        return [ChatMessage.model_validate(item) for item in self.data.get("messages", [])]

    @property
    def profile(self) -> Profile:
        return Profile.model_validate(self.data["profile"])

    @property
    def insights(self) -> list[InsightFlag]:
        return [InsightFlag.model_validate(item) for item in self.data.get("insights", [])]

    @property
    def ranking(self) -> list[dict[str, Any]]:
        return list(self.data.get("ranking", []))

    @property
    def scenario(self) -> Scenario | None:
        raw = self.data.get("scenario")
        if not raw:
            return None
        return Scenario(
            kind=raw["kind"],
            title=raw["title"],
            lines=tuple((label, value) for label, value in raw["lines"]),
            note=raw.get("note"),
        )

    def why_ask(self, index: int) -> str | None:
        return self.data.get("why_ask", {}).get(str(index))

    def probabilities_at(self, index: int) -> dict[str, float] | None:
        """Hypothesis bars as they stood when the message at `index` was written."""

        turns = self.data.get("turn_decisions", [])
        seen = 0
        for message in self.data.get("messages", []):
            if message["role"] == "customer":
                if message["turn_index"] >= index:
                    break
                seen += 1
        if not turns:
            return None
        return turns[min(max(seen - 1, 0), len(turns) - 1)]["type_probabilities"]
