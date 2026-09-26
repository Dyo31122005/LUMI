"""Decision engines: OpenAI Structured Outputs with a deterministic offline fallback.

Both engines answer the same questions (D1–D6 in the knowledge base) and return
the same strict schemas, so `DECISION_ENGINE` can switch between them without
touching the orchestrator. Probabilities are estimates from the model; code
normalises them and every arithmetic step stays in `scoring`/`finance`.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from core.kb import KnowledgeBase
from core.llm import LumiOpenAIClient
from core.schemas import (
    CriterionNotes,
    CriterionScores,
    InsightFlag,
    InsuranceType,
    ProductScores,
    Profile,
    TurnDecision,
    TypeDecision,
    TypeProbabilities,
)

TYPES: tuple[InsuranceType, ...] = ("unemployment", "retirement", "life", "health")


def normalize_probabilities(values: dict[str, float]) -> TypeProbabilities:
    total = sum(max(0.0, value) for value in values.values())
    if total == 0:
        return TypeProbabilities(unemployment=0.25, retirement=0.25, life=0.25, health=0.25)
    return TypeProbabilities(**{key: max(0.0, value) / total for key, value in values.items()})


def _ranked(probabilities: TypeProbabilities) -> list[tuple[str, float]]:
    return sorted(probabilities.model_dump().items(), key=lambda item: -item[1])


class DecisionEngine(Protocol):
    def decide_turn(self, profile: Profile, derived: dict[str, Any], context: dict[str, Any]) -> TurnDecision: ...
    def decide_type(self, profile: Profile, derived: dict[str, Any]) -> TypeDecision: ...
    def score_product(self, profile: Profile, product: dict[str, Any]) -> ProductScores: ...
    def flags(self, profile: Profile, derived: dict[str, Any]) -> list[InsightFlag]: ...


class RuleEngine:
    """Offline engine built from insurance_types.need_signals_vi.

    Used when there is no network and as the cross-check that D3 is sane
    (decision_questions.D3.cross_check_vi).
    """

    def __init__(self, knowledge_base: KnowledgeBase | None = None) -> None:
        self.kb = knowledge_base or KnowledgeBase.load()

    def probabilities(self, profile: Profile, derived: dict[str, Any] | None = None) -> TypeProbabilities:
        derived = derived or {}
        concerns = set(profile.primary_concerns or ())
        denied = set(profile.denied_concerns or ())
        scores = dict.fromkeys(TYPES, 0.2)

        # Thất nghiệp: chưa đủ 12 tháng BHTN, việc làm chưa ổn định, có khoản trả góp.
        if profile.employment_status in {"job_seeking", "probation", "student"}:
            scores["unemployment"] += 0.9
        gap = derived.get("unemployment_gap_months")
        if gap:
            scores["unemployment"] += 0.5
        if profile.debts:
            scores["unemployment"] += 0.4
        if profile.income_stability == "low":
            scores["unemployment"] += 0.3
        scores["unemployment"] += 0.6 * len(concerns & {"job_loss", "income_gap", "debt_repayment"})
        if profile.employment_status in {"near_retirement", "retired"} or (profile.age or 0) > 55:
            scores["unemployment"] = 0.0

        # Hưu trí: còn khoảng cách đến 15 năm BHXH và còn thời gian tích luỹ.
        remaining = derived.get("years_to_retirement")
        if remaining is not None and 5 <= remaining <= 25:
            scores["retirement"] += 0.7
        if derived.get("pension_missing_years"):
            scores["retirement"] += 0.8
        if profile.employment_status == "self_employed":
            scores["retirement"] += 0.5
        scores["retirement"] += 0.9 * len(concerns & {"retirement_income", "not_burden_children"})
        if (profile.bhxh_years or 0) >= 20 and (remaining is not None and remaining < 3):
            scores["retirement"] = 0.0

        # Nhân thọ: có người phụ thuộc tài chính, muốn để lại tài sản.
        dependants = [item for item in (profile.dependents or ()) if item.financially_dependent is not False]
        if dependants:
            scores["life"] += 0.6
        if profile.spouse_income == 0 or (profile.marital_status == "married" and profile.spouse_income is None and (profile.age or 0) >= 55):
            scores["life"] += 0.5
        scores["life"] += 1.0 * len(concerns & {"spouse_protection", "legacy"})
        if "not_burden_children" in concerns and dependants:
            scores["life"] += 0.4
        if (profile.age or 0) > 70:
            scores["life"] = 0.0

        # Sức khoẻ: chủ yếu là loại phụ trong demo.
        if profile.chronic_conditions:
            scores["health"] += 0.4
        if "medical_cost" in concerns:
            scores["health"] += 0.7
        if (profile.age or 0) >= 50:
            scores["health"] += 0.2
        if "medical_cost" in denied:
            scores["health"] = 0.0

        return normalize_probabilities(scores)

    def decide_type(self, profile: Profile, derived: dict[str, Any] | None = None) -> TypeDecision:
        probabilities = self.probabilities(profile, derived)
        ranked = _ranked(probabilities)
        secondary_min = float(self.kb.section("scoring")["thresholds"]["secondary_type_prob_min"])
        secondary = ranked[1][0] if ranked[1][1] >= secondary_min else None
        return TypeDecision(
            insurance_type=ranked[0][0],  # type: ignore[arg-type]
            secondary_type=secondary,  # type: ignore[arg-type]
            type_probabilities=probabilities,
            confidence=round(ranked[0][1], 2),
            reasons=["Đối chiếu bằng bảng luật offline dựa trên tín hiệu nhu cầu trong knowledge base."],
        )

    def decide_turn(self, profile: Profile, derived: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> TurnDecision:
        final = self.decide_type(profile, derived)
        known = profile.model_dump(exclude={"provenance"})
        fallback = self.kb.section("decision_questions")["D1"]["fallback_order"]
        topics = self.kb.section("profile_schema")["fields"]
        missing_topics = {
            field["topic"]
            for field in topics
            if known.get(field["key"]) in (None, [], {}) and field.get("level") in {"core", "type"}
        }
        next_topic = next((topic for topic in fallback if topic in missing_topics), "ready_to_recommend")
        return TurnDecision(
            next_topic=next_topic,  # type: ignore[arg-type]
            next_topic_reason="Chọn theo thứ tự dự phòng vì đang chạy bằng bảng luật offline.",
            risk_tolerance=profile.risk_tolerance or "Unknown",
            need_flexibility=profile.need_flexibility or "Unknown",
            trust_concern=profile.trust_concern or "Unknown",
            insurance_type=final.insurance_type,
            type_probabilities=final.type_probabilities,
            confidence=final.confidence,
            customer_intent="add_or_correct_info",
        )

    def score_product(self, profile: Profile, product: dict[str, Any]) -> ProductScores:
        """Offline D5 derived from catalog facts, not from a preferred answer."""

        tags = product.get("personalization_tags") or {}
        concerns = set(profile.primary_concerns or ())
        eligibility = product.get("eligibility") or {}
        flexibility = product.get("flexibility") or {}

        overlap = len(concerns & set(tags.get("fits_concerns") or ()))
        c1 = "Meets very well" if overlap >= 2 else "Meets well" if overlap == 1 else "Partly meets"

        from core.scoring import monthly_budget, premium_of

        amount, period = premium_of(product)
        budget = monthly_budget(profile)
        c2 = "Meets well"
        if amount is not None and period == "monthly" and budget:
            share = amount / budget
            c2 = "Meets very well" if share <= 0.5 else "Meets well" if share <= 0.85 else "Partly meets"

        params = product.get("finance_params") or {}
        cautious = profile.risk_tolerance in {"Very low", "Low"}
        if product.get("investment_linked") or params.get("guaranteed_rate") is None and params:
            c3 = "Does not meet" if cautious else "Partly meets"
        elif params.get("guaranteed_rate"):
            c3 = "Meets very well" if float(params["guaranteed_rate"]) >= 0.03 else "Meets well"
        else:
            c3 = "Meets well"

        # C4 is customer-relative: a late pause window only hurts a customer who
        # actually expects to need one.
        needs_flexibility = profile.need_flexibility == "High" or bool(profile.upcoming_expenses)
        pause_year = flexibility.get("pause_from_year")
        penalty = flexibility.get("withdrawal_penalty_schedule") or flexibility.get("withdrawal_fee")
        if flexibility.get("cancel_anytime") or pause_year == 2:
            c4 = "Meets very well"
        elif pause_year and pause_year > 2:
            c4 = "Partly meets" if needs_flexibility else "Meets well"
        elif penalty:
            c4 = "Partly meets" if needs_flexibility else "Meets well"
        else:
            c4 = "Meets well"

        underwriting = eligibility.get("underwriting")
        if underwriting in {"none", "simplified"}:
            c5 = "Meets very well"
        elif underwriting == "full":
            c5 = "Partly meets" if profile.chronic_conditions else "Meets well"
        else:
            c5 = "Meets well"
        if eligibility.get("requires_passed_probation") and profile.has_employment_contract is False:
            c5 = "Partly meets"

        days = (product.get("claims") or {}).get("days")
        c6 = "Meets very well" if isinstance(days, int) and days <= 7 else "Meets well"

        levels = {"C1": c1, "C2": c2, "C3": c3, "C4": c4, "C5": c5, "C6": c6}
        return ProductScores(
            product_id=str(product["id"]),
            scores=CriterionScores(**levels),
            notes=CriterionNotes(**{key: "Chấm bằng bảng luật offline từ dữ liệu catalog." for key in levels}),
        )

    def flags(self, profile: Profile, derived: dict[str, Any] | None = None) -> list[InsightFlag]:
        derived = derived or {}
        found: list[InsightFlag] = []
        templates = self.kb.section("decision_questions")["D6"]["flags"]

        if derived.get("has_large_expense_2y"):
            found.append(InsightFlag(key="large_expense_2y", probability=0.9, reason=templates["large_expense_2y"]["insight_template_vi"]))
        if any(item.financially_dependent for item in (profile.dependents or ())) or profile.spouse_income == 0:
            found.append(InsightFlag(key="dependent_without_income", probability=0.9, reason=templates["dependent_without_income"]["insight_template_vi"]))
        missing = derived.get("pension_missing_years")
        if missing:
            found.append(
                InsightFlag(
                    key="pension_gap",
                    probability=0.85,
                    reason=str(templates["pension_gap"]["insight_template_vi"]).replace("{missing_years}", f"{missing:g}"),
                )
            )
        if derived.get("unemployment_gap_months"):
            found.append(InsightFlag(key="first_year_unemployment_gap", probability=0.9, reason=templates["first_year_unemployment_gap"]["insight_template_vi"]))
        if profile.chronic_conditions:
            found.append(InsightFlag(key="chronic_condition", probability=0.9, reason=templates["chronic_condition"]["insight_template_vi"]))
        return found


class OpenAIEngine:
    """D1–D4 in one call per turn, D3 again at Bước 1, D5 in parallel per product."""

    def __init__(self, client: LumiOpenAIClient, system_prompt: str, knowledge_base: KnowledgeBase | None = None) -> None:
        self.client = client
        self.system_prompt = system_prompt
        self.kb = knowledge_base or KnowledgeBase.load()
        self.rules = RuleEngine(self.kb)

    @staticmethod
    def _payload(**parts: Any) -> str:
        return json.dumps(parts, ensure_ascii=False, default=str)

    def decide_turn(self, profile: Profile, derived: dict[str, Any], context: dict[str, Any]) -> TurnDecision:
        result = self.client.structured_response(
            instructions=self.system_prompt,
            input_text=self._payload(
                known_profile=profile.model_dump(exclude={"provenance"}),
                derived_fields=derived,
                last_bot_message=context.get("last_bot_message"),
                last_customer_message=context.get("last_customer_message"),
                missing_fields=context.get("missing_fields", []),
            ),
            schema=TurnDecision,
            schema_name="lumi_turn_decision",
            reasoning_effort="low",
        )
        return result.model_copy(
            update={"type_probabilities": normalize_probabilities(result.type_probabilities.model_dump())}
        )

    def decide_type(self, profile: Profile, derived: dict[str, Any]) -> TypeDecision:
        """The most important call of the session, so it runs at medium reasoning."""

        result = self.client.structured_response(
            instructions=self.system_prompt,
            input_text=self._payload(
                full_profile=profile.model_dump(exclude={"provenance"}),
                derived_fields=derived,
                task="D3_final",
            ),
            schema=TypeDecision,
            schema_name="lumi_type_decision",
            reasoning_effort="medium",
        )
        return result.model_copy(
            update={"type_probabilities": normalize_probabilities(result.type_probabilities.model_dump())}
        )

    def score_product(self, profile: Profile, product: dict[str, Any]) -> ProductScores:
        criteria = [
            {"id": item["id"], "instruction": item["decision_instruction"]}
            for item in self.kb.section("scoring")["criteria"]
        ]
        result = self.client.structured_response(
            instructions=self.system_prompt,
            input_text=self._payload(
                task="D5_product_scoring",
                profile_summary=profile.model_dump(exclude={"provenance"}),
                product=_jsonable(product),
                criteria=criteria,
                levels=list(self.kb.section("decision_questions")["D5"]["levels"]),
            ),
            schema=ProductScores,
            schema_name="lumi_product_scores",
            reasoning_effort="low",
        )
        return result.model_copy(update={"product_id": str(product["id"])})

    def score_products(self, profile: Profile, products: list[dict[str, Any]]) -> list[ProductScores]:
        """D5 runs per product; the calls are independent so they go in parallel."""

        if not products:
            return []
        with ThreadPoolExecutor(max_workers=min(4, len(products))) as pool:
            return list(pool.map(lambda item: self.score_product(profile, item), products))

    def flags(self, profile: Profile, derived: dict[str, Any]) -> list[InsightFlag]:
        return self.rules.flags(profile, derived)


def _jsonable(value: Any) -> Any:
    """Knowledge-base values are frozen mappings/tuples; make them serializable."""

    if hasattr(value, "items"):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
