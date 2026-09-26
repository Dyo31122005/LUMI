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


# Scale words, longest prefix first so "nghìn" is not read as "ng".
MONEY_SCALES = (
    ("tỷ", 1_000_000_000),
    ("tỉ", 1_000_000_000),
    ("ty", 1_000_000_000),
    ("triệu", 1_000_000),
    ("trieu", 1_000_000),
    ("tr", 1_000_000),
    ("nghìn", 1_000),
    ("nghin", 1_000),
    ("ngàn", 1_000),
    ("ngan", 1_000),
    ("k", 1_000),
)

# Spoken digits. Vietnamese changes the word by position: "năm" becomes "lăm"
# after a tens word, "một" becomes "mốt", "bốn" becomes "tư".
NUMBER_WORDS = {
    "không": 0, "khong": 0,
    "một": 1, "mot": 1, "mốt": 1,
    "hai": 2,
    "ba": 3,
    "bốn": 4, "bon": 4, "tư": 4,
    "năm": 5, "nam": 5, "lăm": 5, "nhăm": 5,
    "sáu": 6, "sau": 6,
    "bảy": 7, "bay": 7, "bẩy": 7,
    "tám": 8, "tam": 8,
    "chín": 9, "chin": 9,
}
HUNDRED = {"trăm", "tram"}
TEN_MULTIPLIER = {"mươi"}           # "hai mươi" = 2 × 10
TEN = {"mười"}                      # "mười lăm" = 10 + 5
# Without diacritics the two collapse into one word; the preceding digit tells
# them apart ("hai muoi" is 20, a bare "muoi" is 10).
TEN_AMBIGUOUS = {"muoi"}
ZERO_FILLER = {"lẻ", "le", "linh"}  # "một trăm lẻ năm" = 105
HALF = {"rưỡi", "ruoi"}             # half of the scale just spoken

RANGE_SEPARATORS = re.compile(r"\s*(?:-|–|—|đến|den|tới|toi|hoặc|hoac)\s*")
# A digit run (with . or , separators) or a word.
_TOKEN = re.compile(r"\d[\d.,]*|[a-zà-ỹ]+", re.IGNORECASE)


def _to_number(token: str) -> float | None:
    """Read a digit token: '59.000' is 59000, '1,2' is 1.2."""

    if "," in token:
        cleaned = token.replace(".", "").replace(",", ".")
    else:
        cleaned = token.replace(".", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_below_thousand(tokens: list[str]) -> float:
    """Read the 0–999 part of a Vietnamese number, e.g. 'ba trăm năm mươi'."""

    total = 0.0
    pending = 0.0
    for token in tokens:
        if token in ZERO_FILLER:
            continue
        if token in HUNDRED:
            total += (pending or 1) * 100
            pending = 0.0
        elif token in TEN_MULTIPLIER or (token in TEN_AMBIGUOUS and pending):
            total += (pending or 1) * 10
            pending = 0.0
        elif token in TEN or token in TEN_AMBIGUOUS:
            total += 10
            pending = 0.0
        elif token in NUMBER_WORDS:
            pending = NUMBER_WORDS[token]
        else:
            number = _to_number(token)
            if number is not None:
                pending = number
    return total + pending


def _split_scale(token: str) -> tuple[str, float] | None:
    """Match a scale word, tolerating '3tr' where digits and unit are joined."""

    for prefix, factor in MONEY_SCALES:
        if token == prefix:
            return prefix, factor
    return None


def _parse_amount(text: str) -> float | None:
    """One amount, spoken or written: 'ba triệu rưỡi', '150k', '1 tỷ 2'."""

    raw = _TOKEN.findall(text)
    if not raw:
        return None

    # Split joined forms such as "3tr" or "150k" into a number and a unit.
    tokens: list[str] = []
    for token in raw:
        match = re.fullmatch(r"(\d[\d.,]*)([a-zà-ỹ]+)", token, re.IGNORECASE)
        if match and _split_scale(match.group(2)):
            tokens.extend(match.groups())
        else:
            tokens.append(token)

    total = 0.0
    segment: list[str] = []
    last_scale: float | None = None
    saw_scale = False

    for token in tokens:
        if token in HALF:
            # "ba triệu rưỡi" adds half of the scale just used.
            if last_scale:
                total += last_scale / 2
            continue
        scale = _split_scale(token)
        if scale:
            total += (_parse_below_thousand(segment) or 1) * scale[1]
            last_scale = scale[1]
            saw_scale = True
            segment = []
        else:
            segment.append(token)

    tail = _parse_below_thousand(segment) if segment else 0.0
    if tail:
        if saw_scale and last_scale and tail < 10:
            # "một tỷ hai" means 1.2 tỷ: a bare tail is tenths of the scale.
            total += tail * last_scale / 10
        else:
            total += tail

    return total if total > 0 else None


def parse_money(value: object) -> float | None:
    """Turn a Vietnamese money expression into VND.

    Handles both written forms ("3tr", "100-150k", "59.000đ") and spoken ones
    ("ba triệu rưỡi", "hai mươi triệu", "một tỷ hai"). Speech-to-text returns
    numbers as words, so the spoken forms are not optional.

    A range yields its upper bound, which is how customers state a budget
    ceiling ("100-150k" means they can afford 150k).
    """

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Mapping):
        for key in ("max", "amount", "value", "min"):
            if key in value:
                return parse_money(value[key])
        return None
    if not isinstance(value, str):
        return None

    text = value.strip().lower()
    for noise in ("đồng", "dong", "vnd", "vnđ", "đ/", "₫"):
        text = text.replace(noise, " ")

    amounts = [
        amount
        for part in RANGE_SEPARATORS.split(text)
        if (amount := _parse_amount(part)) is not None
    ]
    if not amounts:
        return None
    return max(amounts)


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
