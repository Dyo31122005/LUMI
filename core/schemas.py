"""Strict data contracts shared by LUMI agents and deterministic code."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

InsuranceType = Literal["unemployment", "retirement", "life", "health"]
NextTopic = Literal[
    "job_income",
    "dependents_family",
    "debts_expenses",
    "social_insurance",
    "health",
    "goals_concerns",
    "risk_attitude",
    "beneficiaries",
    "budget_payment",
    "existing_coverage",
    "ready_to_recommend",
]
CustomerIntent = Literal[
    "agree_continue", "ask_question", "add_or_correct_info", "end_conversation"
]
FitLevel = Literal["Does not meet", "Partly meets", "Meets well", "Meets very well"]
EmploymentStatus = Literal[
    "student",
    "job_seeking",
    "probation",
    "employed",
    "self_employed",
    "near_retirement",
    "retired",
]
IncomeStability = Literal["low", "medium", "high"]
Concern = Literal[
    "job_loss",
    "income_gap",
    "debt_repayment",
    "retirement_income",
    "not_burden_children",
    "spouse_protection",
    "legacy",
    "medical_cost",
    "children_education",
]
RiskTolerance = Literal["Very low", "Low", "Medium", "High", "Unknown"]
AttitudeLevel = Literal["Low", "Medium", "High", "Unknown"]
HealthStatus = Literal["good", "fair", "poor"]
Gender = Literal["male", "female"]
PaymentPreference = Literal["monthly", "annual", "single"]
ProfileField = Literal[
    "name", "age", "gender", "location", "marital_status", "employment_status",
    "occupation", "job_prospect", "expected_income", "has_employment_contract",
    "months_in_current_job", "monthly_income", "income_sources", "income_stability",
    "retirement_timing", "expected_pension", "dependents", "spouse_income",
    "monthly_expenses", "savings", "assets", "debts", "upcoming_expenses",
    "bhxh_years", "bhxh_withdrawn", "bhtn_months", "existing_insurance",
    "health_status", "chronic_conditions", "condition_controlled", "smoker",
    "primary_concerns", "denied_concerns", "goals", "risk_tolerance",
    "need_flexibility", "trust_concern", "budget_monthly", "budget_annual",
    "budget_single", "payment_preference", "beneficiaries",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(StrictModel):
    quote: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    turn_index: int = Field(ge=0)


class Dependent(StrictModel):
    relation: str = Field(min_length=1)
    age: int | None = Field(default=None, ge=0, le=130)
    financially_dependent: bool | None = None


class Debt(StrictModel):
    type: str = Field(min_length=1)
    monthly: float | None = Field(default=None, ge=0)
    remaining_months: int | None = Field(default=None, ge=0)


class Savings(StrictModel):
    amount: float = Field(ge=0)
    earmark: str | None = None


class Profile(StrictModel):
    name: str | None = None
    age: int | None = Field(default=None, ge=0, le=130)
    gender: Gender | None = None
    location: str | None = None
    marital_status: Literal["single", "married", "widowed", "divorced"] | None = None
    employment_status: EmploymentStatus | None = None
    occupation: str | None = None
    job_prospect: str | None = None
    expected_income: float | None = Field(default=None, ge=0)
    has_employment_contract: bool | None = None
    months_in_current_job: int | None = Field(default=None, ge=0)
    monthly_income: float | None = Field(default=None, ge=0)
    income_sources: list[str] | None = None
    income_stability: IncomeStability | None = None
    retirement_timing: str | None = None
    expected_pension: float | None = Field(default=None, ge=0)
    dependents: list[Dependent] | None = None
    spouse_income: float | None = Field(default=None, ge=0)
    monthly_expenses: float | None = Field(default=None, ge=0)
    savings: Savings | None = None
    assets: list[str] | None = None
    debts: list[Debt] | None = None
    upcoming_expenses: list[str] | None = None
    bhxh_years: float | None = Field(default=None, ge=0)
    bhxh_withdrawn: bool | None = None
    bhtn_months: int | None = Field(default=None, ge=0)
    existing_insurance: list[str] | None = None
    health_status: HealthStatus | None = None
    chronic_conditions: list[str] | None = None
    condition_controlled: bool | None = None
    smoker: bool | None = None
    primary_concerns: list[Concern] | None = None
    denied_concerns: list[Concern] | None = None
    goals: str | None = None
    risk_tolerance: RiskTolerance | None = None
    need_flexibility: AttitudeLevel | None = None
    trust_concern: AttitudeLevel | None = None
    budget_monthly: float | None = Field(default=None, ge=0)
    budget_annual: float | None = Field(default=None, ge=0)
    budget_single: float | None = Field(default=None, ge=0)
    payment_preference: PaymentPreference | None = None
    beneficiaries: list[str] | None = None
    provenance: dict[ProfileField, Provenance] = Field(default_factory=dict)


class ProfilePatch(StrictModel):
    """Incremental A1 extraction; values are applied only through Profile validation."""

    updates: dict[ProfileField, Any] = Field(default_factory=dict)
    provenance: dict[ProfileField, Provenance] = Field(default_factory=dict)

    @field_validator("provenance")
    @classmethod
    def provenance_must_describe_an_update(
        cls, value: dict[ProfileField, Provenance], info: Any
    ) -> dict[ProfileField, Provenance]:
        updates = info.data.get("updates", {})
        extra_keys = set(value).difference(updates)
        if extra_keys:
            raise ValueError("Every provenance entry must have a matching update.")
        return value

    def apply(self, profile: Profile) -> Profile:
        values = profile.model_dump(exclude={"provenance"})
        values.update(self.updates)
        merged_provenance = {**profile.provenance, **self.provenance}
        return Profile.model_validate({**values, "provenance": merged_provenance})


class TypeProbabilities(StrictModel):
    unemployment: float = Field(ge=0, le=1)
    retirement: float = Field(ge=0, le=1)
    life: float = Field(ge=0, le=1)
    health: float = Field(ge=0, le=1)


class TurnDecision(StrictModel):
    next_topic: NextTopic
    next_topic_reason: str = Field(min_length=1)
    risk_tolerance: RiskTolerance
    need_flexibility: AttitudeLevel
    trust_concern: AttitudeLevel
    insurance_type: InsuranceType
    type_probabilities: TypeProbabilities
    confidence: float = Field(ge=0, le=1)
    customer_intent: CustomerIntent


class TypeDecision(StrictModel):
    insurance_type: InsuranceType
    secondary_type: InsuranceType | None = None
    type_probabilities: TypeProbabilities
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(min_length=1, max_length=3)


class CriterionScores(StrictModel):
    C1: FitLevel
    C2: FitLevel
    C3: FitLevel
    C4: FitLevel
    C5: FitLevel
    C6: FitLevel


class CriterionNotes(StrictModel):
    """One short justification per criterion; a fixed shape for strict schemas."""

    C1: str
    C2: str
    C3: str
    C4: str
    C5: str
    C6: str


class ProductScores(StrictModel):
    product_id: str = Field(min_length=1)
    scores: CriterionScores
    notes: CriterionNotes


class InsightFlag(StrictModel):
    key: str = Field(min_length=1)
    probability: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


class ChatMessage(StrictModel):
    role: Literal["customer", "assistant", "system"]
    content: str = Field(min_length=1)
    turn_index: int = Field(ge=0)


class SessionLog(StrictModel):
    session_id: str = Field(min_length=1)
    persona_id: str | None = None
    state: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(default_factory=list)
    profile: Profile
    turn_decisions: list[TurnDecision] = Field(default_factory=list)
    type_decision: TypeDecision | None = None
    product_scores: list[ProductScores] = Field(default_factory=list)
    insights: list[InsightFlag] = Field(default_factory=list)


class AdvisorResponse(StrictModel):
    message: str = Field(min_length=1)
    cited_profile_fields: list[ProfileField] = Field(default_factory=list)
    includes_disclaimer: bool
