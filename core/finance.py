"""Money calculations for the advisory cards, implementing knowledge-base formulas.

A4 is never allowed to invent a number: every figure it prints comes from the
knowledge base or from one of these functions (writing_rules, build plan §2.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.schemas import Profile

DEFAULT_PAYOUT_MONTHS = 240


@dataclass(frozen=True)
class Scenario:
    """One «Nếu… thì…» card, already reduced to labelled numbers."""

    kind: str
    title: str
    lines: tuple[tuple[str, float | None], ...]
    note: str | None = None

    def numbers(self) -> list[float]:
        return [value for _, value in self.lines if value is not None]


def fund_accumulation(premium_annual: float, years: int, rate: float, initial_charge: float = 0.0) -> float:
    """finance.fund_accumulation: premiums paid at the start of each year, compounded."""

    fund = 0.0
    for _ in range(years):
        fund = (fund + premium_annual * (1 - initial_charge)) * (1 + rate)
    return fund


def annuity_payout(fund_value: float, payout_rate: float, months: int = DEFAULT_PAYOUT_MONTHS) -> float:
    """finance.annuity_payout: level monthly amount drawn from a fund."""

    rate = payout_rate / 12
    if rate == 0:
        return fund_value / months
    return fund_value * rate / (1 - (1 + rate) ** -months)


BHXH_VOLUNTARY_RATE = 0.22  # regulations.reg_bhxh_tn_contribution
BHXH_SHARE_OF_BUDGET = 0.25


def split_retirement_budget(budget_monthly: float) -> tuple[float, float, float]:
    """Split a retirement budget into the state layer and the commercial layer.

    The state layer is BHXH tự nguyện at 22% of a self-chosen income basis.
    The basis is picked so the contribution takes about a quarter of the
    budget, rounded to the nearest million, which keeps the larger share for
    the supplementary product.

    Returns (bhxh_monthly, product_monthly, income_basis).
    """

    if budget_monthly <= 0:
        return 0.0, 0.0, 0.0
    raw_basis = budget_monthly * BHXH_SHARE_OF_BUDGET / BHXH_VOLUNTARY_RATE
    income_basis = max(1_000_000.0, round(raw_basis / 1_000_000) * 1_000_000.0)
    bhxh_monthly = income_basis * BHXH_VOLUNTARY_RATE
    if bhxh_monthly >= budget_monthly:
        income_basis = 1_000_000.0
        bhxh_monthly = income_basis * BHXH_VOLUNTARY_RATE
    return bhxh_monthly, max(0.0, budget_monthly - bhxh_monthly), income_basis


def bhxh_pension_rate(years: float, gender: str | None) -> float:
    """finance.bhxh_pension_rate, as a percentage of the contribution basis."""

    if years < 15:
        return 0.0
    if gender == "male":
        if years < 20:
            return 40 + (years - 15)
        return min(75.0, 45 + 2 * (years - 20))
    return min(75.0, 45 + 2 * (years - 15))


def bhxh_pension(years: float, gender: str | None, income_basis: float) -> float:
    return bhxh_pension_rate(years, gender) / 100 * income_basis


def installment_cover(
    remaining_installments: int, benefit_max_periods: int, installment: float, benefit_cap_per_period: float
) -> float:
    """finance.installment_cover."""

    return min(remaining_installments, benefit_max_periods) * min(installment, benefit_cap_per_period)


def monthly_shortfall(profile: Profile) -> float | None:
    """How much monthly spending is uncovered if the customer's income stops."""

    if profile.monthly_expenses is None:
        return None
    debts = sum(debt.monthly or 0 for debt in profile.debts or [])
    return profile.monthly_expenses + debts


def _product_benefit(product: dict[str, Any]) -> float | None:
    coverage = product.get("coverage") or {}
    return coverage.get("max_total_benefit_vnd")


def unemployment_scenario(profile: Profile, products: list[dict[str, Any]]) -> Scenario:
    """Timeline card: what the chosen packages pay if the job is lost."""

    lines: list[tuple[str, float | None]] = []
    assumptions: list[str] = []
    total = 0.0
    for product in products:
        benefit = _product_benefit(product)
        if benefit is None:
            continue
        coverage = product.get("coverage") or {}
        if coverage.get("benefit_form") == "pay_installments" and profile.debts:
            debt = profile.debts[0]
            max_periods = int(coverage.get("benefit_max_periods") or 0)
            remaining = debt.remaining_months
            if remaining is None:
                # Unknown term: quote the product's own ceiling and say so.
                remaining = max_periods
                assumptions.append("giả định khoản trả góp còn đủ số kỳ để dùng hết quyền lợi")
            benefit = installment_cover(
                remaining_installments=remaining,
                benefit_max_periods=max_periods,
                installment=debt.monthly or 0,
                benefit_cap_per_period=float(coverage.get("benefit_cap_per_period_vnd") or 0),
            )
        if not benefit:
            continue
        lines.append((str(product["product_name"]), float(benefit)))
        total += float(benefit)

    lines.append(("Tổng hỗ trợ ước tính", total))
    gap_months = max(0, 12 - (profile.bhtn_months or 0))
    notes: list[str] = []
    if gap_months:
        lines.append(("Bảo hiểm thất nghiệp Nhà nước chi trả trong giai đoạn này", 0.0))
        notes.append(f"Còn thiếu {gap_months} tháng đóng BHTN mới đủ điều kiện hưởng trợ cấp Nhà nước.")
    notes.extend(assumptions)
    return Scenario(
        kind="timeline",
        title="Nếu mất việc trong năm đầu đi làm",
        lines=tuple(lines),
        note=" ".join(notes) or None,
    )


def retirement_scenario(profile: Profile, product: dict[str, Any], premium_annual: float, income_basis: float) -> Scenario:
    """Comparison-bar card: estimated monthly income at retirement age."""

    years = max(0, (62 if profile.gender == "male" else 60) - (profile.age or 0))
    params = product.get("finance_params") or {}
    guaranteed = float(params.get("guaranteed_rate") or 0.02)
    illustrated = float(params.get("illustrated_rate") or guaranteed)
    initial = float(params.get("initial_charge") or 0)
    payout_rate = float(params.get("payout_rate") or guaranteed)

    credited = 0.0 if profile.bhxh_withdrawn else (profile.bhxh_years or 0)
    pension = bhxh_pension(credited + years, profile.gender, income_basis)

    low_fund = fund_accumulation(premium_annual, years, guaranteed, initial)
    high_fund = fund_accumulation(premium_annual, years, illustrated, initial)
    low = annuity_payout(low_fund, payout_rate)
    high = annuity_payout(high_fund, payout_rate)

    return Scenario(
        kind="bars",
        title="Thu nhập hằng tháng ước tính khi nghỉ hưu",
        lines=(
            ("Lương hưu BHXH", round(pension)),
            (f"{product['product_name']} (theo lãi cam kết)", round(low)),
            (f"{product['product_name']} (theo lãi minh hoạ)", round(high)),
            ("Tổng ước tính thấp", round(pension + low)),
            ("Tổng ước tính cao", round(pension + high)),
        ),
        note="Ước tính theo giá trị danh nghĩa; lạm phát sẽ làm giảm sức mua sau nhiều năm.",
    )


def life_scenario(profile: Profile, products: list[dict[str, Any]]) -> Scenario:
    """Situation-table card: what the dependant receives under each product."""

    pension = profile.expected_pension or 0
    lines: list[tuple[str, float | None]] = []
    for product in products:
        samples = product.get("sample_premiums") or ()
        amount = samples[0].get("sum_assured_vnd") if samples else None
        lines.append((str(product["product_name"]), float(amount) if amount is not None else None))

    top = next((value for _, value in lines if value), None)
    note = None
    if top and pension:
        note = f"Bằng khoảng {round(top / pension)} tháng lương hưu hiện tại."
    return Scenario(
        kind="table",
        title="Nếu người trụ cột mất, người phụ thuộc nhận được gì",
        lines=tuple(lines),
        note=note,
    )
