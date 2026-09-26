"""Derived fields, hard filters, criterion weights and product ranking.

Every number produced here is computed by code from the knowledge base and
the customer profile. Decision agents supply only the categorical fit levels
(D5); the arithmetic that turns those into a ranking lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.kb import KnowledgeBase
from core.schemas import CriterionScores, InsuranceType, Profile

CRITERIA = ("C1", "C2", "C3", "C4", "C5", "C6")

# Bộ luật Lao động 2019, Điều 169 (regulations.reg_retirement_age).
RETIREMENT_AGE = {"male": 62, "female": 60}
DEFAULT_RETIREMENT_AGE = 60


@dataclass(frozen=True)
class DerivedFields:
    life_stage: str | None = None
    years_to_retirement: int | None = None
    pension_missing_years: float | None = None
    unemployment_gap_months: int | None = None
    premium_to_income_ratio: float | None = None
    has_large_expense_2y: bool = False
    has_chronic_condition: bool = False
    completeness: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "life_stage": self.life_stage,
            "years_to_retirement": self.years_to_retirement,
            "pension_missing_years": self.pension_missing_years,
            "unemployment_gap_months": self.unemployment_gap_months,
            "premium_to_income_ratio": self.premium_to_income_ratio,
            "has_large_expense_2y": self.has_large_expense_2y,
            "has_chronic_condition": self.has_chronic_condition,
            "completeness": self.completeness,
        }


@dataclass(frozen=True)
class FilterOutcome:
    product: dict[str, Any]
    kept: bool
    reasons: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass
class RankedProduct:
    product: dict[str, Any]
    scores: CriterionScores
    fit_score: float
    rank: int = 0
    notes: dict[str, str] = field(default_factory=dict)
    filter_notes: tuple[str, ...] = ()

    @property
    def product_id(self) -> str:
        return str(self.product["id"])


def life_stage(age: int | None) -> str | None:
    if age is None:
        return None
    if age < 25:
        return "young_adult"
    if age < 40:
        return "early_career"
    if age < 55:
        return "mid_career"
    if age < 65:
        return "pre_retirement"
    return "retired"


def years_to_retirement(profile: Profile) -> int | None:
    if profile.age is None:
        return None
    target = RETIREMENT_AGE.get(profile.gender or "", DEFAULT_RETIREMENT_AGE)
    return max(0, target - profile.age)


def pension_missing_years(profile: Profile) -> float | None:
    """finance.pension_gap: years still needed to reach the 15-year threshold."""

    if profile.bhxh_years is None:
        return None
    credited = 0.0 if profile.bhxh_withdrawn else profile.bhxh_years
    remaining = years_to_retirement(profile)
    reachable = credited + (remaining if remaining is not None else 0)
    return max(0.0, 15 - reachable)


def unemployment_gap_months(profile: Profile) -> int | None:
    if profile.bhtn_months is None:
        return None
    return max(0, 12 - profile.bhtn_months)


def monthly_budget(profile: Profile) -> float | None:
    """The customer's budget expressed per month, whichever form they gave."""

    if profile.budget_monthly is not None:
        return profile.budget_monthly
    if profile.budget_annual is not None:
        return profile.budget_annual / 12
    return None


def premium_to_income_ratio(profile: Profile) -> float | None:
    income = profile.monthly_income or profile.expected_income
    budget = monthly_budget(profile)
    if not income or budget is None:
        return None
    return budget / income


def completeness(profile: Profile, insurance_type: InsuranceType | None, kb: KnowledgeBase) -> float:
    """Share of the readiness fields that are already known (profile_schema.readiness)."""

    readiness = kb.section("profile_schema")["readiness"]
    required = list(readiness["step1_recommend_type"]["core"])
    if insurance_type:
        required += list(readiness["step2_compare_products"][insurance_type])

    known = profile.model_dump(exclude={"provenance"})
    groups = kb.section("profile_schema")["conventions"]["one_of_groups"]

    total = 0
    filled = 0
    for entry in dict.fromkeys(required):
        total += 1
        if entry.startswith("one_of:"):
            members = groups[entry.split(":", 1)[1]]
            if any(known.get(member) not in (None, [], {}) for member in members):
                filled += 1
        elif known.get(entry) not in (None, [], {}):
            filled += 1
    return filled / total if total else 0.0


def derive(profile: Profile, insurance_type: InsuranceType | None = None, kb: KnowledgeBase | None = None) -> DerivedFields:
    kb = kb or KnowledgeBase.load()
    return DerivedFields(
        life_stage=life_stage(profile.age),
        years_to_retirement=years_to_retirement(profile),
        pension_missing_years=pension_missing_years(profile),
        unemployment_gap_months=unemployment_gap_months(profile),
        premium_to_income_ratio=premium_to_income_ratio(profile),
        has_large_expense_2y=bool(profile.upcoming_expenses),
        has_chronic_condition=bool(profile.chronic_conditions),
        completeness=completeness(profile, insurance_type, kb),
    )


def premium_of(product: dict[str, Any]) -> tuple[float | None, str | None]:
    """The comparable premium as (amount, period).

    The catalog carries three shapes: a fixed amount, a customer-chosen amount
    with a floor, and a profile-dependent sample premium.
    """

    premium = product.get("premium") or {}
    basis = premium.get("basis")

    if basis == "fixed":
        return float(premium["amount_vnd"]), str(premium.get("period"))
    if basis == "chosen":
        floor = premium.get("min_annual_vnd")
        return (float(floor), "annual") if floor is not None else (None, None)
    if basis == "fixed_by_profile":
        samples = product.get("sample_premiums") or ()
        if samples:
            sample = samples[0]
            return float(sample["premium_vnd"]), str(sample.get("period"))
    return None, None


def _monthly_premium(product: dict[str, Any]) -> float | None:
    amount, period = premium_of(product)
    if amount is None:
        return None
    if period == "monthly":
        return amount
    if period == "annual":
        return amount / 12
    return None


def _affordable(product: dict[str, Any], profile: Profile) -> tuple[bool, str | None]:
    """Compare the premium with the budget stated in the same payment form."""

    amount, period = premium_of(product)
    if amount is None:
        return True, None

    if period == "single":
        if profile.budget_single is not None and amount > profile.budget_single:
            return False, "Phí đóng một lần vượt ngân sách khách nêu"
        return True, None

    if period == "annual":
        if profile.budget_annual is not None:
            if amount > profile.budget_annual:
                return False, "Phí hằng năm vượt ngân sách khách nêu"
        elif profile.budget_monthly is not None and amount / 12 > profile.budget_monthly:
            return False, "Phí tối thiểu quy đổi theo tháng vượt ngân sách khách nêu"
        return True, None

    if period == "monthly":
        budget = monthly_budget(profile)
        if budget is not None and amount > budget:
            return False, "Phí hằng tháng vượt ngân sách khách nêu"
    return True, None


def hard_filter(profile: Profile, insurance_type: InsuranceType, kb: KnowledgeBase | None = None) -> list[FilterOutcome]:
    """Apply scoring.hard_filters_vi to every catalog product of this type."""

    kb = kb or KnowledgeBase.load()
    outcomes: list[FilterOutcome] = []

    for entry in kb.section("products"):
        product = {key: value for key, value in entry.items()}
        if product.get("insurance_type") != insurance_type or product.get("is_reference"):
            continue

        eligibility = product.get("eligibility") or {}
        reasons: list[str] = []
        notes: list[str] = []

        if profile.age is not None:
            minimum = eligibility.get("entry_age_min")
            maximum = eligibility.get("entry_age_max")
            if minimum is not None and profile.age < minimum:
                reasons.append(f"Khách {profile.age} tuổi, dưới tuổi tham gia tối thiểu {minimum}")
            if maximum is not None and profile.age > maximum:
                reasons.append(f"Khách {profile.age} tuổi, vượt tuổi tham gia tối đa {maximum}")

        affordable, reason = _affordable(product, profile)
        if not affordable and reason:
            reasons.append(reason)

        if eligibility.get("requires_loan") and not profile.debts:
            reasons.append("Sản phẩm yêu cầu đang có khoản vay hoặc trả góp")

        if eligibility.get("requires_employment_contract") and profile.has_employment_contract is False:
            notes.append("Đăng ký sau khi ký hợp đồng lao động")
        if eligibility.get("requires_passed_probation") and profile.has_employment_contract is False:
            notes.append("Chỉ mua được sau khi qua thử việc")

        outcomes.append(
            FilterOutcome(
                product=product,
                kept=not reasons,
                reasons=tuple(reasons),
                notes=tuple(notes),
            )
        )
    return outcomes


def criterion_weights(
    profile: Profile,
    derived: DerivedFields,
    insurance_type: InsuranceType,
    kb: KnowledgeBase | None = None,
) -> tuple[dict[str, float], list[str]]:
    """scoring.base_weights plus the adjustments this customer triggers."""

    kb = kb or KnowledgeBase.load()
    scoring = kb.section("scoring")
    weights = {key: float(value) for key, value in scoring["base_weights"][insurance_type].items()}
    reasons: list[str] = []

    ratio = derived.premium_to_income_ratio
    triggers = {
        "income_stability == 'low' or premium_to_income_ratio > 0.05": (
            profile.income_stability == "low" or (ratio is not None and ratio > 0.05)
        ),
        "risk_tolerance in ['Very low', 'Low']": profile.risk_tolerance in {"Very low", "Low"},
        "need_flexibility == 'High' or has_large_expense_2y": (
            profile.need_flexibility == "High" or derived.has_large_expense_2y
        ),
        "has_chronic_condition": derived.has_chronic_condition,
        "trust_concern == 'High'": profile.trust_concern == "High",
    }

    for adjustment in scoring["adjustments"]:
        if not triggers.get(adjustment["when"]):
            continue
        for criterion, extra in adjustment["add"].items():
            weights[criterion] = weights.get(criterion, 0.0) + float(extra)
        reasons.append(str(adjustment["reason_vi"]))

    total = sum(weights.values())
    target = float(scoring["normalize_to"])
    if total:
        weights = {key: value * target / total for key, value in weights.items()}
    return weights, reasons


def priority_criteria(weights: dict[str, float], kb: KnowledgeBase | None = None) -> list[str]:
    kb = kb or KnowledgeBase.load()
    count = int(kb.section("scoring")["priority_criteria_count"])
    ordered = sorted(weights.items(), key=lambda item: (-item[1], item[0]))
    return [criterion for criterion, _ in ordered[:count]]


def fit_score(weights: dict[str, float], scores: CriterionScores, kb: KnowledgeBase | None = None) -> float:
    """scoring.fit_score: sum(weight_i * points_i) / 10, on a 0–100 scale."""

    kb = kb or KnowledgeBase.load()
    points = kb.section("scoring")["level_to_points"]
    levels = scores.model_dump()
    total = sum(weights.get(criterion, 0.0) * points[levels[criterion]] for criterion in CRITERIA)
    return round(total / 10, 1)


def rank_products(
    scored: list[tuple[dict[str, Any], CriterionScores, dict[str, str]]],
    weights: dict[str, float],
    kb: KnowledgeBase | None = None,
    filter_notes: dict[str, tuple[str, ...]] | None = None,
) -> list[RankedProduct]:
    """Order products by fit score; ties fall back to the cheaper premium."""

    kb = kb or KnowledgeBase.load()
    filter_notes = filter_notes or {}
    ranked = [
        RankedProduct(
            product=product,
            scores=scores,
            fit_score=fit_score(weights, scores, kb),
            notes=notes,
            filter_notes=filter_notes.get(str(product["id"]), ()),
        )
        for product, scores, notes in scored
    ]
    ranked.sort(key=lambda item: (-item.fit_score, _monthly_premium(item.product) or float("inf"), item.product_id))
    for position, item in enumerate(ranked, start=1):
        item.rank = position
    return ranked
