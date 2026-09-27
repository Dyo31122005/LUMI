"""Deterministic What-if experiments over a finished LUMI consultation.

The module keeps trial state separate from the consultation.  A caller may
preview a change as often as needed and only writes it back through
``keep_changes``.  Field dependencies come from ``profile_schema.fields`` in
the knowledge base; code does not maintain a second hand-written dependency
table.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping

from core import finance, scoring
from core.decision import RuleEngine
from core.finance import Scenario
from core.kb import KnowledgeBase
from core.schemas import (
    ProductScores,
    Profile,
    Provenance,
    TypeDecision,
)


# These feeds can change a result visible in Step 1, Step 2 or the scenario.
# ``writer`` and ``address_style`` deliberately stay out: editing them would
# only alter prose, while What-if promises a decision/result change.
RESULT_FEEDS = frozenset(
    {
        "D2.need_flexibility",
        "D3",
        "D5",
        "D6",
        "affordability",
        "finance",
        "hard_filter",
        "insight",
        "life_stage",
        "pension_gap",
        "premium_to_income_ratio",
        "sample_premium",
        "unemployment_gap",
        "weights",
        "years_to_retirement",
    }
)


@dataclass(frozen=True)
class EditableField:
    key: str
    label: str
    value_type: str
    widget: str
    feeds: tuple[str, ...]
    value: Any
    options: tuple[str, ...] = ()
    option_labels: Mapping[str, str] = field(default_factory=dict)
    sensitive: bool = False


@dataclass(frozen=True)
class RankChange:
    product_id: str
    product_name: str
    before_rank: int | None
    after_rank: int | None
    before_score: float | None
    after_score: float | None


@dataclass(frozen=True)
class WhatIfDiff:
    summary: str
    ranking_changed: bool
    # When the recommended type changes, the before and after rankings describe
    # two different catalogs. That is the largest change What-if can produce, so
    # it is reported on its own rather than inferred from rank movements.
    type_before: str | None
    type_after: str | None
    type_changed: bool
    top_before: str | None
    top_after: str | None
    rank_changes: tuple[RankChange, ...]
    newly_excluded: tuple[str, ...]
    newly_eligible: tuple[str, ...]
    priority_before: tuple[str, ...]
    priority_after: tuple[str, ...]
    changed_cells: tuple[tuple[str, str], ...]
    weight_changes: Mapping[str, float]


@dataclass
class WhatIfSnapshot:
    profile: Profile
    insurance_type: str
    type_decision: TypeDecision | None
    derived: dict[str, Any]
    insights: list[Any]
    ranked: list[scoring.RankedProduct]
    weights: dict[str, float]
    weight_reasons: list[str]
    priority_criteria: list[str]
    excluded: list[scoring.FilterOutcome]
    scenario: Scenario | None


@dataclass
class WhatIfResult:
    before: WhatIfSnapshot
    after: WhatIfSnapshot
    changes: dict[str, Any]
    changed_fields: tuple[str, ...]
    feeds: frozenset[str]
    d3_recomputed: bool
    d5_recomputed: bool
    api_actions: int
    diff: WhatIfDiff


def _field_options(definition: Mapping[str, Any], kb: KnowledgeBase) -> tuple[tuple[str, ...], dict[str, str]]:
    value_type = str(definition.get("type", ""))
    if value_type.startswith("enum["):
        values = tuple(item.strip() for item in value_type[5:-1].split(","))
        return values, {item: item for item in values}
    if value_type.startswith("enum:"):
        path = value_type.removeprefix("enum:").split(".")
        current: Any = kb.section("enums")
        for part in path:
            current = current[part]
        if isinstance(current, Mapping):
            return tuple(current), {str(key): str(value) for key, value in current.items()}
        return tuple(str(item) for item in current), {str(item): str(item) for item in current}
    if "enum:" in value_type:
        path = value_type.split("enum:", 1)[1].rstrip("]").split(".")
        current = kb.section("enums")
        for part in path:
            current = current[part]
        if isinstance(current, Mapping):
            return tuple(current), {str(key): str(value) for key, value in current.items()}
    return (), {}


def _widget(value_type: str) -> str:
    if value_type == "bool":
        return "toggle"
    if value_type.startswith("enum"):
        return "select"
    if value_type in {"money", "int", "number"}:
        return "number"
    if value_type.startswith("list"):
        return "list"
    return "text"


def editable_fields(
    profile: Profile,
    insurance_type: str,
    kb: KnowledgeBase | None = None,
) -> list[EditableField]:
    """Return result-affecting fields relevant to the selected insurance type."""

    kb = kb or KnowledgeBase.load()
    values = profile.model_dump(exclude={"provenance"})
    result: list[EditableField] = []
    for definition in kb.section("profile_schema")["fields"]:
        feeds = tuple(str(item) for item in definition.get("feeds", ()))
        if not RESULT_FEEDS.intersection(feeds):
            continue
        required_for = tuple(str(item) for item in definition.get("required_for", ()))
        if required_for and insurance_type not in required_for:
            continue
        value_type = str(definition.get("type", "text"))
        options, option_labels = _field_options(definition, kb)
        result.append(
            EditableField(
                key=str(definition["key"]),
                label=str(definition["label_vi"]),
                value_type=value_type,
                widget=_widget(value_type),
                feeds=feeds,
                value=values.get(str(definition["key"])),
                options=options,
                option_labels=option_labels,
                sensitive=bool(definition.get("sensitive")),
            )
        )
    return result


def _definitions(kb: KnowledgeBase) -> dict[str, Mapping[str, Any]]:
    return {str(item["key"]): item for item in kb.section("profile_schema")["fields"]}


def _profile_with_changes(profile: Profile, changes: Mapping[str, Any]) -> Profile:
    values = profile.model_dump(exclude={"provenance"})
    provenance = dict(profile.provenance)
    last_turn = max((item.turn_index for item in provenance.values()), default=-1) + 1

    for key, value in changes.items():
        if key not in Profile.model_fields or key == "provenance":
            raise ValueError(f"Trường hồ sơ không hợp lệ: {key}")
        values[key] = value
        provenance[key] = Provenance(
            quote="Bạn tự sửa trong What-if",
            confidence=1.0,
            turn_index=last_turn,
        )

    # ``need_flexibility`` is inferred from the same statement that supplied
    # ``upcoming_expenses``.  Once that source is removed, retaining the old
    # High value and quote would make both the score and provenance false.
    if "upcoming_expenses" in changes and "need_flexibility" not in changes:
        values["need_flexibility"] = "Unknown"
        provenance.pop("need_flexibility", None)

    return Profile.model_validate({**values, "provenance": provenance})


def _source_data(session: Any) -> dict[str, Any]:
    if isinstance(session, Mapping):
        return deepcopy(dict(session))
    from core.session_io import session_to_dict

    return session_to_dict(session)


def _insurance_type(data: Mapping[str, Any]) -> str:
    kind = data.get("insurance_type")
    if kind:
        return str(kind)
    decision = data.get("type_decision") or {}
    if decision.get("insurance_type"):
        return str(decision["insurance_type"])
    raise ValueError("Phiên tư vấn chưa có loại bảo hiểm để chạy What-if.")


def _score_all(engine: Any, profile: Profile, products: list[dict[str, Any]]) -> list[ProductScores]:
    scorer = getattr(engine, "score_products", None)
    if callable(scorer):
        return list(scorer(profile, products))
    return [engine.score_product(profile, product) for product in products]


def _scenario(profile: Profile, ranked: list[scoring.RankedProduct], insurance_type: str) -> Scenario | None:
    products = [item.product for item in ranked]
    if not products:
        return None
    if insurance_type == "unemployment":
        return finance.unemployment_scenario(profile, products[:2])
    if insurance_type == "retirement":
        budget = scoring.monthly_budget(profile) or 0
        _, product_monthly, income_basis = finance.split_retirement_budget(budget)
        return finance.retirement_scenario(profile, products[0], product_monthly * 12, income_basis)
    if insurance_type == "life":
        return finance.life_scenario(profile, products)
    return None


def _calculate(
    profile: Profile,
    insurance_type: str,
    type_decision: TypeDecision | None,
    kb: KnowledgeBase,
    engine: Any,
) -> WhatIfSnapshot:
    derived_object = scoring.derive(profile, insurance_type, kb)
    outcomes = scoring.hard_filter(profile, insurance_type, kb)
    kept = [item for item in outcomes if item.kept]
    excluded = [item for item in outcomes if not item.kept]
    products = [item.product for item in kept]
    scored = _score_all(engine, profile, products)
    by_id = {item.product_id: item for item in scored}
    weights, weight_reasons = scoring.criterion_weights(profile, derived_object, insurance_type, kb)
    ranked = scoring.rank_products(
        [
            (product, by_id[str(product["id"])].scores, by_id[str(product["id"])].notes.model_dump())
            for product in products
            if str(product["id"]) in by_id
        ],
        weights,
        kb,
        filter_notes={str(item.product["id"]): item.notes for item in kept},
    )
    return WhatIfSnapshot(
        profile=profile,
        insurance_type=insurance_type,
        type_decision=type_decision,
        derived=derived_object.as_dict(),
        insights=list(RuleEngine(kb).flags(profile, derived_object.as_dict())),
        ranked=ranked,
        weights=weights,
        weight_reasons=weight_reasons,
        priority_criteria=scoring.priority_criteria(weights, kb),
        excluded=excluded,
        scenario=_scenario(profile, ranked, insurance_type),
    )


def _decision(data: Mapping[str, Any]) -> TypeDecision | None:
    raw = data.get("type_decision")
    return TypeDecision.model_validate(raw) if raw else None


TYPE_NAMES = {
    "unemployment": "Thất nghiệp",
    "retirement": "Hưu trí",
    "life": "Nhân thọ",
    "health": "Sức khoẻ",
}


def _type_name(insurance_type: str) -> str:
    return TYPE_NAMES.get(insurance_type, insurance_type)


def diff(before: WhatIfSnapshot, after: WhatIfSnapshot) -> WhatIfDiff:
    """Describe every visible result change without asking a writer model."""

    before_by_id = {item.product_id: item for item in before.ranked}
    after_by_id = {item.product_id: item for item in after.ranked}
    all_ids = tuple(dict.fromkeys([*before_by_id, *after_by_id]))
    rank_changes: list[RankChange] = []
    changed_cells: list[tuple[str, str]] = []
    for product_id in all_ids:
        old = before_by_id.get(product_id)
        new = after_by_id.get(product_id)
        if old and new:
            for criterion in scoring.CRITERIA:
                if getattr(old.scores, criterion) != getattr(new.scores, criterion):
                    changed_cells.append((product_id, criterion))
        if not old or not new or old.rank != new.rank or old.fit_score != new.fit_score:
            product = new or old
            assert product is not None
            rank_changes.append(
                RankChange(
                    product_id=product_id,
                    product_name=str(product.product["product_name"]),
                    before_rank=old.rank if old else None,
                    after_rank=new.rank if new else None,
                    before_score=old.fit_score if old else None,
                    after_score=new.fit_score if new else None,
                )
            )

    old_top = before.ranked[0] if before.ranked else None
    new_top = after.ranked[0] if after.ranked else None
    top_before = str(old_top.product["product_name"]) if old_top else None
    top_after = str(new_top.product["product_name"]) if new_top else None
    ranking_changed = [item.product_id for item in before.ranked] != [item.product_id for item in after.ranked]

    type_changed = before.insurance_type != after.insurance_type
    type_before = _type_name(before.insurance_type)
    type_after = _type_name(after.insurance_type)

    if type_changed:
        # The headline is the category, not which product came first inside it.
        summary = f"Loại bảo hiểm đề xuất đổi từ «{type_before}» sang «{type_after}»."
        if top_after:
            summary += f" Đứng đầu nhóm mới là {top_after}."
    elif before.ranked and not after.ranked:
        # Every product was filtered out; saying the ranking is unchanged would
        # contradict the list of products shown dropping out right below it.
        summary = "Không còn sản phẩm nào qua được bộ lọc với giả định này."
    elif after.ranked and not before.ranked:
        summary = f"Đã có sản phẩm qua được bộ lọc: {top_after} đứng đầu."
    elif new_top and (not old_top or new_top.product_id != old_top.product_id):
        old_rank = before_by_id.get(new_top.product_id)
        if old_rank:
            summary = f"{top_after} từ hạng {old_rank.rank} lên hạng 1."
        else:
            summary = f"{top_after} mới đủ điều kiện và lên hạng 1."
    elif rank_changes:
        summary = "Thứ hạng chưa đổi, nhưng điểm phù hợp hoặc trọng số ưu tiên đã thay đổi."
    else:
        summary = "Kết quả xếp hạng chưa thay đổi với giả định này."

    before_excluded = {str(item.product["id"]): item for item in before.excluded}
    after_excluded = {str(item.product["id"]): item for item in after.excluded}
    if type_changed:
        # Different catalogs: a product "newly excluded" here was never under
        # consideration before, so reporting it would mislead.
        newly_excluded = ()
        newly_eligible = ()
    else:
        newly_excluded = tuple(
            str(after_excluded[key].product["product_name"])
            for key in after_excluded.keys() - before_excluded.keys()
        )
        newly_eligible = tuple(
            str(before_excluded[key].product["product_name"])
            for key in before_excluded.keys() - after_excluded.keys()
        )
    weight_changes = {
        key: round(after.weights.get(key, 0) - before.weights.get(key, 0), 2)
        for key in scoring.CRITERIA
        if round(after.weights.get(key, 0) - before.weights.get(key, 0), 2) != 0
    }
    return WhatIfDiff(
        summary=summary,
        ranking_changed=ranking_changed,
        type_before=type_before,
        type_after=type_after,
        type_changed=type_changed,
        top_before=top_before,
        top_after=top_after,
        rank_changes=tuple(rank_changes),
        newly_excluded=newly_excluded,
        newly_eligible=newly_eligible,
        priority_before=tuple(before.priority_criteria),
        priority_after=tuple(after.priority_criteria),
        changed_cells=tuple(changed_cells),
        weight_changes=weight_changes,
    )


def recompute(
    session: Any,
    changes: Mapping[str, Any],
    *,
    kb: KnowledgeBase | None = None,
    engine: Any | None = None,
    reconsider_type: bool = False,
) -> WhatIfResult:
    """Preview changes and return old/new deterministic result snapshots.

    Code-only experiments use ``RuleEngine`` for both snapshots.  This keeps
    replay fully offline and gives the comparison one consistent scorer.
    Fields that explicitly feed D5 use the supplied live engine for the new
    snapshot; D3 is called only when ``reconsider_type`` is true.
    """

    if not changes:
        raise ValueError("Cần thay đổi ít nhất một thông tin để chạy What-if.")
    kb = kb or KnowledgeBase.load()
    data = _source_data(session)
    original_profile = Profile.model_validate(data["profile"])
    changed_profile = _profile_with_changes(original_profile, changes)
    definitions = _definitions(kb)
    unknown = set(changes).difference(definitions)
    if unknown:
        raise ValueError(f"Trường không có trong knowledge base: {', '.join(sorted(unknown))}")
    feeds = frozenset(
        str(feed)
        for key in changes
        for feed in definitions[key].get("feeds", ())
    )

    current_type = _insurance_type(data)
    current_decision = _decision(data)
    rule_engine = RuleEngine(kb)
    live_engine = engine or rule_engine
    before = _calculate(original_profile, current_type, current_decision, kb, rule_engine)

    d3_recomputed = bool(reconsider_type and "D3" in feeds)
    after_decision = current_decision
    after_type = current_type
    api_actions = 0
    if d3_recomputed:
        preliminary = scoring.derive(changed_profile, current_type, kb)
        after_decision = live_engine.decide_type(changed_profile, preliminary.as_dict())
        after_type = after_decision.insurance_type
        if not isinstance(live_engine, RuleEngine):
            api_actions += 1

    d5_recomputed = "D5" in feeds or after_type != current_type
    scoring_engine = live_engine if d5_recomputed else rule_engine
    after = _calculate(changed_profile, after_type, after_decision, kb, scoring_engine)
    if d5_recomputed and not isinstance(scoring_engine, RuleEngine):
        api_actions += len(after.ranked)

    change_keys = tuple(str(key) for key in changes)
    return WhatIfResult(
        before=before,
        after=after,
        changes=dict(changes),
        changed_fields=change_keys,
        feeds=feeds,
        d3_recomputed=d3_recomputed,
        d5_recomputed=d5_recomputed,
        api_actions=api_actions,
        diff=diff(before, after),
    )


def _ranked_dict(item: scoring.RankedProduct) -> dict[str, Any]:
    return {
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


def snapshot_data(snapshot: WhatIfSnapshot, base: Mapping[str, Any]) -> dict[str, Any]:
    """Overlay a snapshot on the page's existing serialised session shape."""

    result = deepcopy(dict(base))
    result.update(
        {
            "profile": snapshot.profile.model_dump(),
            "derived": dict(snapshot.derived),
            "insurance_type": snapshot.insurance_type,
            "type_decision": snapshot.type_decision.model_dump() if snapshot.type_decision else None,
            "insights": [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in snapshot.insights],
            "weights": dict(snapshot.weights),
            "weight_reasons": list(snapshot.weight_reasons),
            "priority_criteria": list(snapshot.priority_criteria),
            "ranking": [_ranked_dict(item) for item in snapshot.ranked],
            "excluded": [
                {"product_name": item.product["product_name"], "reasons": list(item.reasons)}
                for item in snapshot.excluded
            ],
            "scenario": (
                {
                    "kind": snapshot.scenario.kind,
                    "title": snapshot.scenario.title,
                    "lines": [list(item) for item in snapshot.scenario.lines],
                    "note": snapshot.scenario.note,
                }
                if snapshot.scenario
                else None
            ),
        }
    )
    return result


def keep_changes(session: Any, result: WhatIfResult) -> dict[str, Any] | None:
    """Commit a preview to a live session, or return updated replay data."""

    after = result.after
    if isinstance(session, Mapping):
        return snapshot_data(after, session)

    session.profile = after.profile
    session.derived = dict(after.derived)
    session.type_decision = after.type_decision
    session.insights = list(after.insights)
    session.ranked = list(after.ranked)
    session.weights = dict(after.weights)
    session.weight_reasons = list(after.weight_reasons)
    session.priority_criteria = list(after.priority_criteria)
    session.excluded = list(after.excluded)
    session.scenario = after.scenario
    return None
