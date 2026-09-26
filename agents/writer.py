"""A4 turns already-decided results into Vietnamese advice.

The writer never chooses a product or a type: it receives the decision and the
computed numbers as JSON and may only use figures that appear there. A number
guard checks the output before it reaches the customer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.finance import Scenario
from core.guards import collect_allowed_numbers, strip_unsupported_numbers
from core.kb import KnowledgeBase
from core.llm import LumiOpenAIClient
from core.schemas import InsightFlag, Profile, TypeDecision

DISCLAIMER = (
    "Thông tin trên chỉ mang tính tham khảo. Bạn nên làm việc với tư vấn viên "
    "có chứng chỉ trước khi mua bảo hiểm."
)
FICTION_NOTE = "Dữ liệu minh hoạ · Doanh nghiệp và sản phẩm trong demo là hư cấu."


def _jsonable(value: Any) -> Any:
    if hasattr(value, "items"):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


class AdvisorWriter:
    def __init__(self, client: LumiOpenAIClient, knowledge_base: KnowledgeBase | None = None) -> None:
        self.client = client
        self.kb = knowledge_base or KnowledgeBase.load()
        self.instructions = (
            Path(__file__).resolve().parents[1] / "prompts" / "writer.md"
        ).read_text(encoding="utf-8")
        self.writing_rules = list(self.kb.section("writing_rules"))

    # ------------------------------------------------------------------ calls

    def _write(self, payload: dict[str, Any], allowed: set[str]) -> str:
        text = "".join(
            self.client.stream_text(
                instructions=self.instructions,
                input_text=json.dumps(
                    {**_jsonable(payload), "writing_rules": self.writing_rules},
                    ensure_ascii=False,
                ),
                reasoning_effort="low",
            )
        ).strip()
        text = strip_unsupported_numbers(text, allowed)
        if DISCLAIMER not in text:
            text = f"{text}\n\n{DISCLAIMER}"
        return text

    def write_step_one(
        self,
        *,
        profile: Profile,
        decision: TypeDecision,
        derived: dict[str, Any],
        insights: list[InsightFlag],
        address: dict[str, str],
    ) -> str:
        type_names = {item["id"]: item["name_vi"] for item in self.kb.section("insurance_types")}
        payload: dict[str, Any] = {
            "task": "step_one",
            "address": address,
            "profile": profile.model_dump(exclude={"provenance"}),
            "derived_fields": derived,
            "recommended_type": decision.insurance_type,
            "recommended_type_vi": type_names.get(decision.insurance_type),
            "secondary_type_vi": type_names.get(decision.secondary_type or ""),
            "confidence": decision.confidence,
            "probabilities": decision.type_probabilities.model_dump(),
            "reasons": decision.reasons,
            "insights": [item.model_dump() for item in insights],
            "evidence_quotes": {
                key: value.quote for key, value in profile.provenance.items()
            },
            "instruction_vi": (
                "Viết Bước 1: tóm tắt hồ sơ, nêu loại bảo hiểm đề xuất, 2–3 lý do gắn với "
                "thuộc tính của khách, các loại chưa ưu tiên và lý do, rồi hỏi khách có muốn "
                "so sánh sản phẩm không."
            ),
        }
        return self._write(payload, collect_allowed_numbers(payload))

    def write_step_two(
        self,
        *,
        profile: Profile,
        ranked: list[Any],
        weights: dict[str, float],
        weight_reasons: list[str],
        priority_criteria: list[str],
        scenario: Scenario | None,
        excluded: list[Any],
        address: dict[str, str],
    ) -> str:
        criteria_names = {item["id"]: item["name_vi"] for item in self.kb.section("scoring")["criteria"]}
        payload: dict[str, Any] = {
            "task": "step_two",
            "address": address,
            "profile_name": profile.name,
            "priority_criteria": [criteria_names.get(item, item) for item in priority_criteria],
            "priority_reasons": weight_reasons,
            "ranking": [
                {
                    "rank": item.rank,
                    "product_name": item.product["product_name"],
                    "insurer": item.product["insurer"],
                    "premium": (item.product.get("premium") or {}).get("display"),
                    "fit_score": item.fit_score,
                    "strengths": list((item.product.get("personalization_tags") or {}).get("strengths") or ()),
                    "watch_outs": list((item.product.get("personalization_tags") or {}).get("watch_outs") or ()),
                    "investment_linked": bool(item.product.get("investment_linked")),
                    "notes": item.notes,
                    "filter_notes": list(item.filter_notes),
                }
                for item in ranked
            ],
            "excluded": [
                {"product_name": outcome.product["product_name"], "reasons": list(outcome.reasons)}
                for outcome in excluded
            ],
            "scenario": (
                {
                    "kind": scenario.kind,
                    "title": scenario.title,
                    "lines": [[label, value] for label, value in scenario.lines],
                    "note": scenario.note,
                }
                if scenario
                else None
            ),
            "fiction_note": FICTION_NOTE,
            "instruction_vi": (
                "Viết Bước 2: nêu điều khách ưu tiên, giới thiệu sản phẩm đứng đầu và lý do, "
                "nêu ngắn các lựa chọn sau và điểm bất lợi của từng cái, rồi diễn giải thẻ "
                "«Nếu... thì...». Luôn nêu watch_outs cùng strengths."
            ),
        }
        return self._write(payload, collect_allowed_numbers(payload))

    def write_no_products(self, *, profile: Profile, excluded: list[Any], address: dict[str, str]) -> str:
        payload: dict[str, Any] = {
            "task": "no_products",
            "address": address,
            "excluded": [
                {"product_name": outcome.product["product_name"], "reasons": list(outcome.reasons)}
                for outcome in excluded
            ],
            "budget": {
                "monthly": profile.budget_monthly,
                "annual": profile.budget_annual,
                "single": profile.budget_single,
            },
            "instruction_vi": (
                "Không sản phẩm nào qua được bộ lọc. Giải thích lý do, gợi ý điều chỉnh ngân "
                "sách hoặc trao đổi với tư vấn viên. Không giới thiệu sản phẩm nào."
            ),
        }
        return self._write(payload, collect_allowed_numbers(payload))
