from __future__ import annotations

from copy import deepcopy

import pytest

from core.decision import RuleEngine
from core.kb import KnowledgeBase
from core.schemas import Profile
from core.session_io import Recording
from core.whatif import editable_fields, keep_changes, recompute, snapshot_data


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase.load()


@pytest.fixture()
def mai_data() -> dict:
    return deepcopy(Recording.load("mai").data)


def test_editable_fields_come_from_feeds_and_follow_insurance_type(kb: KnowledgeBase, mai_data: dict) -> None:
    profile = Profile.model_validate(mai_data["profile"])
    retirement = {item.key: item for item in editable_fields(profile, "retirement", kb)}
    unemployment = {item.key: item for item in editable_fields(profile, "unemployment", kb)}

    assert "goals" not in retirement, "Trường chỉ nuôi writer không thuộc What-if"
    assert "assets" not in retirement
    assert retirement["budget_monthly"].widget == "number"
    assert retirement["bhxh_withdrawn"].widget == "toggle"
    assert retirement["risk_tolerance"].widget == "select"
    assert "bhxh_years" in retirement and "bhxh_years" not in unemployment
    assert "bhtn_months" in unemployment and "bhtn_months" not in retirement


class CountingEngine:
    def __init__(self, kb: KnowledgeBase) -> None:
        self.rules = RuleEngine(kb)
        self.score_calls = 0
        self.type_calls = 0

    def score_product(self, profile, product):
        self.score_calls += 1
        return self.rules.score_product(profile, product)

    def decide_type(self, profile, derived):
        self.type_calls += 1
        return self.rules.decide_type(profile, derived)


def test_budget_change_is_code_only_and_leaves_original_untouched(kb: KnowledgeBase, mai_data: dict) -> None:
    original = deepcopy(mai_data)
    engine = CountingEngine(kb)

    result = recompute(mai_data, {"budget_monthly": 3_000_000}, kb=kb, engine=engine)

    assert engine.score_calls == 0
    assert engine.type_calls == 0
    assert result.api_actions == 0
    assert result.after.profile.budget_monthly == 3_000_000
    assert mai_data == original


def test_d5_field_rescores_products_but_d3_stays_opt_in(kb: KnowledgeBase, mai_data: dict) -> None:
    engine = CountingEngine(kb)

    result = recompute(mai_data, {"chronic_conditions": ["tăng huyết áp"]}, kb=kb, engine=engine)

    assert engine.score_calls == len(result.after.ranked)
    assert engine.type_calls == 0
    assert result.d5_recomputed is True
    assert result.d3_recomputed is False
    assert result.api_actions == len(result.after.ranked)


def test_d3_only_runs_when_the_customer_explicitly_requests_it(kb: KnowledgeBase, mai_data: dict) -> None:
    engine = CountingEngine(kb)

    passive = recompute(mai_data, {"income_stability": "high"}, kb=kb, engine=engine)
    assert passive.d3_recomputed is False
    assert engine.type_calls == 0

    active = recompute(
        mai_data,
        {"income_stability": "high"},
        kb=kb,
        engine=engine,
        reconsider_type=True,
    )
    assert active.d3_recomputed is True
    assert engine.type_calls == 1


def test_mai_without_upcoming_expense_moves_huu_an_nhan_to_first(kb: KnowledgeBase, mai_data: dict) -> None:
    result = recompute(mai_data, {"upcoming_expenses": None}, kb=kb)

    assert result.before.ranked[0].product_id == "ta_huu_linhhoat"
    assert result.after.ranked[0].product_id == "ap_huu_annhan"
    assert result.diff.summary == "Hưu An Nhàn từ hạng 2 lên hạng 1."
    assert result.after.profile.need_flexibility == "Unknown"
    assert "need_flexibility" not in result.after.profile.provenance


def test_keep_records_manual_provenance_without_the_old_quote(kb: KnowledgeBase, mai_data: dict) -> None:
    result = recompute(mai_data, {"upcoming_expenses": None}, kb=kb)
    updated = keep_changes(mai_data, result)

    assert updated is not None
    evidence = updated["profile"]["provenance"]["upcoming_expenses"]
    assert evidence["quote"] == "Bạn tự sửa trong What-if"
    assert "đại học" not in evidence["quote"]
    assert mai_data["profile"]["upcoming_expenses"] == ["Con lớn năm sau vào đại học"]


def test_snapshot_data_contains_the_new_heatmap_and_scenario(kb: KnowledgeBase, mai_data: dict) -> None:
    result = recompute(mai_data, {"upcoming_expenses": None}, kb=kb)
    rendered = snapshot_data(result.after, mai_data)

    assert rendered["ranking"][0]["product_id"] == "ap_huu_annhan"
    assert rendered["ranking"][0]["scores"]
    assert rendered["weights"] == result.after.weights
    assert rendered["scenario"]["lines"]


def test_filtering_everything_out_is_not_reported_as_unchanged(kb: KnowledgeBase, mai_data: dict) -> None:
    """A budget that eliminates every product used to say «thứ hạng chưa đổi»,
    contradicting the list of dropped products shown right beneath it."""

    result = recompute(mai_data, {"budget_monthly": 400_000}, kb=kb)

    assert result.after.ranked == []
    assert "Không còn sản phẩm nào" in result.diff.summary
    assert "chưa đổi" not in result.diff.summary
    # The reason is available so the customer learns why, not just that.
    assert set(result.diff.newly_excluded) == {
        "Hưu Trí Linh Hoạt", "Hưu An Nhàn", "Tương Lai Vững",
    }


def test_a_type_change_is_reported_as_the_headline(kb: KnowledgeBase, mai_data: dict) -> None:
    """Switching the recommended category is the biggest change What-if can
    make; it must not be described as one product moving to first place."""

    result = recompute(
        mai_data,
        {"primary_concerns": ["job_loss", "income_gap"]},
        kb=kb,
        reconsider_type=True,
    )

    assert result.after.insurance_type != result.before.insurance_type
    assert result.diff.type_changed is True
    assert result.diff.type_before == "Hưu trí"
    assert result.diff.type_after == "Thất nghiệp"
    assert "Hưu trí" in result.diff.summary and "Thất nghiệp" in result.diff.summary
    # Before and after describe different catalogs, so cross-catalog exclusion
    # lists would name products that were never under consideration.
    assert result.diff.newly_excluded == ()
    assert result.diff.newly_eligible == ()


def test_an_ordinary_change_still_reads_as_a_rank_move(kb: KnowledgeBase, mai_data: dict) -> None:
    """The new branches must not swallow the common case."""

    result = recompute(mai_data, {"upcoming_expenses": None}, kb=kb)

    assert result.diff.type_changed is False
    assert result.diff.summary == "Hưu An Nhàn từ hạng 2 lên hạng 1."
