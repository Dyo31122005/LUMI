"""Finance formulas are checked against finance.worked_examples in the knowledge base."""

from __future__ import annotations

import pytest

from core import finance
from core.kb import KnowledgeBase
from core.schemas import Debt, Profile


@pytest.fixture(scope="module")
def worked() -> dict[str, dict]:
    examples = KnowledgeBase.load().section("finance")["worked_examples"]
    return {str(item["name"]).split("–")[0].strip(): item for item in examples}


def test_retirement_fund_matches_the_worked_example(worked: dict[str, dict]) -> None:
    inputs = worked["Chị Mai"]["inputs"]
    guaranteed = finance.fund_accumulation(inputs["premium_annual_vnd"], inputs["years"], 0.02, 0.02)
    illustrated = finance.fund_accumulation(inputs["premium_annual_vnd"], inputs["years"], 0.045, 0.02)
    assert guaranteed == pytest.approx(537_000_000, rel=0.01)
    assert illustrated == pytest.approx(670_000_000, rel=0.01)


def test_annuity_payout_matches_the_worked_example(worked: dict[str, dict]) -> None:
    expected = worked["Chị Mai"]["outputs"]["product_monthly_vnd"]
    guaranteed = finance.fund_accumulation(28_800_000, 16, 0.02, 0.02)
    illustrated = finance.fund_accumulation(28_800_000, 16, 0.045, 0.02)
    assert finance.annuity_payout(guaranteed, 0.02) == pytest.approx(expected["guaranteed"], rel=0.01)
    assert finance.annuity_payout(illustrated, 0.02) == pytest.approx(expected["illustrated"], rel=0.01)


def test_pension_rate_follows_the_legal_schedule(worked: dict[str, dict]) -> None:
    outputs = worked["Chị Mai"]["outputs"]
    assert finance.bhxh_pension_rate(24, "female") == outputs["pension_rate_pct"]
    assert finance.bhxh_pension(24, "female", 4_000_000) == pytest.approx(outputs["bhxh_pension_vnd"])
    assert finance.bhxh_pension_rate(10, "female") == 0
    assert finance.bhxh_pension_rate(40, "female") == 75


def test_male_and_female_schedules_differ() -> None:
    assert finance.bhxh_pension_rate(18, "male") == 43
    assert finance.bhxh_pension_rate(18, "female") == 51


def test_installment_cover_matches_the_worked_example(worked: dict[str, dict]) -> None:
    inputs = worked["Vương"]["inputs"]
    cover = finance.installment_cover(
        remaining_installments=inputs["remaining_installments_at_loss"],
        benefit_max_periods=6,
        installment=inputs["installment_vnd"],
        benefit_cap_per_period=1_500_000,
    )
    assert cover == worked["Vương"]["outputs"]["tragop_cover_vnd"]


def test_monthly_shortfall_includes_debt_repayments() -> None:
    profile = Profile(monthly_expenses=5_500_000, debts=[Debt(type="laptop", monthly=1_200_000)])
    assert finance.monthly_shortfall(profile) == 6_700_000


def test_scenario_only_exposes_computed_numbers() -> None:
    profile = Profile(age=44, gender="female", bhxh_years=8, bhxh_withdrawn=False)
    product = {
        "product_name": "Hưu Trí Linh Hoạt",
        "finance_params": {"guaranteed_rate": 0.02, "illustrated_rate": 0.045, "initial_charge": 0.02, "payout_rate": 0.02},
    }
    scenario = finance.retirement_scenario(profile, product, 28_800_000, 4_000_000)
    assert scenario.kind == "bars"
    assert all(isinstance(value, (int, float)) for value in scenario.numbers())
