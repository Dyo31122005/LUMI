"""A1 extracts only cited profile facts from a customer message."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from core.kb import KnowledgeBase
from core.llm import LumiOpenAIClient
from core.schemas import Profile, ProfileField, ProfilePatch, Provenance


def to_json_value(value: object) -> object:
    """Copy immutable KB values into JSON-serializable request data."""

    if isinstance(value, Mapping):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [to_json_value(item) for item in value]
    return value


MONEY_UNITS = (
    ("tỷ", 1_000_000_000),
    ("ty", 1_000_000_000),
    ("triệu", 1_000_000),
    ("trieu", 1_000_000),
    ("tr", 1_000_000),
    ("nghìn", 1_000),
    ("nghin", 1_000),
    ("ngàn", 1_000),
    ("k", 1_000),
)
_AMOUNT = re.compile(r"(\d+(?:[.,]\d+)?)\s*([a-zA-ZÀ-ỹ]*)")


def parse_money(value: object) -> float | None:
    """Turn a Vietnamese money phrase into VND.

    A1 is told to emit integers, but a model occasionally returns "11 triệu
    mỗi tháng". Coercing here keeps one bad field from ending the session.
    """

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, Mapping):
        for key in ("max", "amount", "value", "min"):
            if key in value:
                return parse_money(value[key])
        return None
    if not isinstance(value, str):
        return None

    text = value.strip().lower().replace("đ", "").replace("vnd", "")
    pairs: list[tuple[str, float, int | None]] = []
    for raw_number, raw_unit in _AMOUNT.findall(text):
        digits = raw_number.replace(".", "").replace(",", ".") if "," in raw_number else raw_number.replace(".", "")
        try:
            number = float(digits)
        except ValueError:
            continue
        unit = next((factor for prefix, factor in MONEY_UNITS if raw_unit.startswith(prefix)), None)
        pairs.append((raw_number, number, unit))
    if not pairs:
        return None

    amounts: list[float] = []
    for index, (raw_number, number, unit) in enumerate(pairs):
        if unit is not None:
            amounts.append(number * unit)
            continue
        later = next((item for _, _, item in pairs[index + 1 :] if item is not None), None)
        if later is not None:
            # A range such as "100-150k": the unit sits on the last number only.
            amounts.append(number * later)
            continue
        earlier = next((item for _, _, item in reversed(pairs[:index]) if item is not None), None)
        if earlier is not None and amounts:
            # "1 tỷ 2" means 1.2 tỷ: a bare tail is a fraction of the unit before it.
            amounts[-1] += number / (10 ** len(raw_number.lstrip("0") or "0")) * earlier
            continue
        amounts.append(number)

    total = max(amounts)
    return total if total > 0 else None


class ExtractedField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: ProfileField
    value_json: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[ExtractedField] = Field(max_length=8)


MONEY_FIELDS = {
    "expected_income",
    "monthly_income",
    "spouse_income",
    "monthly_expenses",
    "expected_pension",
    "budget_monthly",
    "budget_annual",
    "budget_single",
}


class ProfileExtractor:
    def __init__(self, client: LumiOpenAIClient) -> None:
        self.client = client
        self.instructions = (Path(__file__).resolve().parents[1] / "prompts" / "extractor.md").read_text(
            encoding="utf-8"
        )
        knowledge_base = KnowledgeBase.load()
        self.field_contract = {
            field["key"]: field["type"]
            for field in knowledge_base.section("profile_schema")["fields"]
        }
        self.money_fields = {
            key for key, kind in self.field_contract.items() if kind == "money"
        }
        self.enums = to_json_value(knowledge_base.section("enums"))
        self.value_shapes = {
            "income_sources": "JSON array of strings only",
            "assets": "JSON array of strings only",
            "upcoming_expenses": "JSON array of strings only",
            "existing_insurance": "JSON array of strings only",
            "chronic_conditions": "JSON array of strings only",
            "beneficiaries": "JSON array of strings only",
            "dependents": "JSON array; each item has relation, optional age, optional financially_dependent",
            "debts": "JSON array; each item has type, optional monthly, optional remaining_months",
            "savings": "JSON object with amount and optional earmark",
        }

    def extract(self, message: str, profile: Profile, turn_index: int) -> ProfilePatch:
        result = self.client.structured_response(
            instructions=self.instructions,
            input_text=json.dumps(
                {
                    "customer_message": message,
                    "known_profile": profile.model_dump(exclude={"provenance"}),
                    "profile_field_contract": self.field_contract,
                    "enum_values": self.enums,
                    "value_shapes": self.value_shapes,
                },
                ensure_ascii=False,
            ),
            schema=ExtractionResult,
            schema_name="lumi_profile_extraction",
            reasoning_effort="low",
        )
        return self.patch_from_result(result, turn_index, self.money_fields)

    @staticmethod
    def patch_from_result(
        result: ExtractionResult, turn_index: int, money_fields: set[str] | None = None
    ) -> ProfilePatch:
        money_fields = money_fields or MONEY_FIELDS
        updates: dict[ProfileField, object] = {}
        evidence: dict[ProfileField, Provenance] = {}
        for item in result.fields:
            try:
                value = json.loads(item.value_json)
            except json.JSONDecodeError:
                value = item.value_json
            if item.field in money_fields:
                value = parse_money(value)
                if value is None:
                    continue
            updates[item.field] = value
            evidence[item.field] = Provenance(
                quote=item.quote, confidence=item.confidence, turn_index=turn_index
            )
        return ProfilePatch(updates=updates, provenance=evidence)
