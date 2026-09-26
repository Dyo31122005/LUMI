"""Scoring must follow the profile, not a stored answer."""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from core.decision import RuleEngine
from core.kb import KnowledgeBase
from core.schemas import CriterionScores, Profile
from core import scoring

PERSONAS = Path(__file__).resolve().parents[1] / "data" / "personas"


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase.load()


def persona_profile(persona_id: str) -> Profile:
    data = yaml.safe_load((PERSONAS / f"{persona_id}.yaml").read_text(encoding="utf-8"))
    return Profile.model_validate(data["facts"])


def rank(profile: Profile, insurance_type: str, kb: KnowledgeBase) -> list[scoring.RankedProduct]:
    rules = RuleEngine(kb)
    kept = [outcome for outcome in scoring.hard_filter(profile, insurance_type, kb) if outcome.kept]
    weights, _ = scoring.criterion_weights(profile, scoring.derive(profile, insurance_type, kb), insurance_type, kb)
    return scoring.rank_products(
        [(item.product, rules.score_product(profile, item.product).scores, {}) for item in kept],
        weights,
        kb,
    )


# ------------------------------------------------------------------- derived


def test_pension_gap_counts_future_contributions(kb: KnowledgeBase) -> None:
    mai = persona_profile("mai")
    derived = scoring.derive(mai, "retirement", kb)
    assert derived.years_to_retirement == 16
    # 8 năm đã đóng + 16 năm còn lại vượt mốc 15 năm, nên không còn thiếu.
    assert derived.pension_missing_years == 0


def test_withdrawn_bhxh_resets_credited_years(kb: KnowledgeBase) -> None:
    profile = Profile(age=58, gender="female", bhxh_years=8, bhxh_withdrawn=True)
    assert scoring.derive(profile, "retirement", kb).pension_missing_years == 13


def test_unemployment_gap_uses_bhtn_months(kb: KnowledgeBase) -> None:
    assert scoring.derive(Profile(bhtn_months=0), "unemployment", kb).unemployment_gap_months == 12
    assert scoring.derive(Profile(bhtn_months=14), "unemployment", kb).unemployment_gap_months == 0


# -------------------------------------------------------------- hard filters


def test_age_outside_entry_range_is_excluded(kb: KnowledgeBase) -> None:
    older = Profile(age=50, budget_monthly=200_000, debts=None)
    excluded = {
        outcome.product["id"]
        for outcome in scoring.hard_filter(older, "unemployment", kb)
        if not outcome.kept
    }
    # GenZ Bảo Vệ nhận 18–35, Việc Làm Vững nhận 18–45.
    assert {"ta_genz", "bm_vieclam"} <= excluded


def test_premium_above_budget_is_excluded(kb: KnowledgeBase) -> None:
    tight = Profile(age=22, budget_monthly=40_000)
    outcomes = {outcome.product["id"]: outcome for outcome in scoring.hard_filter(tight, "unemployment", kb)}
    assert not outcomes["ta_genz"].kept
    assert "ngân sách" in outcomes["ta_genz"].reasons[0]


def test_loan_product_needs_a_loan(kb: KnowledgeBase) -> None:
    without_loan = Profile(age=22, budget_monthly=200_000)
    outcomes = {outcome.product["id"]: outcome for outcome in scoring.hard_filter(without_loan, "unemployment", kb)}
    assert not outcomes["sv_tragop"].kept


def test_missing_contract_is_a_note_not_an_exclusion(kb: KnowledgeBase) -> None:
    vuong = persona_profile("vuong")
    outcomes = {outcome.product["id"]: outcome for outcome in scoring.hard_filter(vuong, "unemployment", kb)}
    assert outcomes["ta_genz"].kept
    assert outcomes["ta_genz"].notes


# ------------------------------------------------------------------- weights


def test_weights_normalise_to_one_hundred(kb: KnowledgeBase) -> None:
    for persona_id, insurance_type in (("vuong", "unemployment"), ("mai", "retirement"), ("duc", "life")):
        weights, _ = scoring.criterion_weights(
            persona_profile(persona_id),
            scoring.derive(persona_profile(persona_id), insurance_type, kb),
            insurance_type,
            kb,
        )
        assert sum(weights.values()) == pytest.approx(100)


def test_adjustments_lift_the_criterion_the_customer_cares_about(kb: KnowledgeBase) -> None:
    base = Profile(age=44, gender="female")
    cautious = base.model_copy(update={"risk_tolerance": "Very low"})
    plain, _ = scoring.criterion_weights(base, scoring.derive(base, "retirement", kb), "retirement", kb)
    safe, reasons = scoring.criterion_weights(cautious, scoring.derive(cautious, "retirement", kb), "retirement", kb)
    assert safe["C3"] > plain["C3"]
    assert any("rủi ro" in reason for reason in reasons)


def test_priority_criteria_are_the_two_heaviest(kb: KnowledgeBase) -> None:
    weights = {"C1": 10.0, "C2": 40.0, "C3": 5.0, "C4": 30.0, "C5": 10.0, "C6": 5.0}
    assert scoring.priority_criteria(weights, kb) == ["C2", "C4"]


# ---------------------------------------------------------------- fit scores


def test_fit_score_matches_the_knowledge_base_formula(kb: KnowledgeBase) -> None:
    weights = {criterion: 100 / 6 for criterion in scoring.CRITERIA}
    perfect = CriterionScores(**{criterion: "Meets very well" for criterion in scoring.CRITERIA})
    none = CriterionScores(**{criterion: "Does not meet" for criterion in scoring.CRITERIA})
    assert scoring.fit_score(weights, perfect, kb) == pytest.approx(100, abs=0.1)
    assert scoring.fit_score(weights, none, kb) == 0


def test_a_weighted_criterion_changes_the_score(kb: KnowledgeBase) -> None:
    strong_c4 = CriterionScores(C1="Meets well", C2="Meets well", C3="Meets well", C4="Meets very well", C5="Meets well", C6="Meets well")
    cares = {"C1": 10.0, "C2": 10.0, "C3": 10.0, "C4": 50.0, "C5": 10.0, "C6": 10.0}
    ignores = {"C1": 18.0, "C2": 18.0, "C3": 18.0, "C4": 10.0, "C5": 18.0, "C6": 18.0}
    assert scoring.fit_score(cares, strong_c4, kb) > scoring.fit_score(ignores, strong_c4, kb)


# ------------------------------------------------------------------- ranking


@pytest.mark.parametrize(
    ("persona_id", "insurance_type", "expected_top"),
    [("vuong", "unemployment", "ta_genz"), ("mai", "retirement", "ta_huu_linhhoat"), ("duc", "life", "sv_baotin")],
)
def test_expected_top_product_per_persona(persona_id: str, insurance_type: str, expected_top: str, kb: KnowledgeBase) -> None:
    assert rank(persona_profile(persona_id), insurance_type, kb)[0].product_id == expected_top


def test_ranking_follows_the_profile_rather_than_a_fixed_answer(kb: KnowledgeBase) -> None:
    """Design note: without the university expense, Hưu An Nhàn should lead."""

    mai = persona_profile("mai")
    relaxed = mai.model_copy(update={"upcoming_expenses": None, "need_flexibility": "Low"})
    assert rank(mai, "retirement", kb)[0].product_id == "ta_huu_linhhoat"
    assert rank(relaxed, "retirement", kb)[0].product_id == "ap_huu_annhan"


def test_ranks_are_ordered_by_fit_score(kb: KnowledgeBase) -> None:
    ranked = rank(persona_profile("duc"), "life", kb)
    assert [item.rank for item in ranked] == list(range(1, len(ranked) + 1))
    assert ranked == sorted(ranked, key=lambda item: -item.fit_score)
