"""The number guard is the last line between A4 and an invented figure."""

from __future__ import annotations

from core.guards import collect_allowed_numbers, strip_unsupported_numbers, unsupported_numbers


def test_numbers_present_in_the_payload_are_allowed() -> None:
    allowed = collect_allowed_numbers({"premium": 59000, "display": "59.000đ/tháng"})
    assert not unsupported_numbers("Phí là 59.000đ mỗi tháng.", allowed)


def test_scaled_spellings_of_the_same_amount_are_allowed() -> None:
    allowed = collect_allowed_numbers({"benefit": 4_000_000, "fund": 537_000_000})
    assert not unsupported_numbers("Quyền lợi 4 triệu, quỹ khoảng 537 triệu.", allowed)


def test_an_invented_figure_is_reported() -> None:
    allowed = collect_allowed_numbers({"premium": 59000})
    assert unsupported_numbers("Gói này trả tới 250.000.000đ.", allowed)


def test_sentences_with_invented_figures_are_dropped() -> None:
    allowed = collect_allowed_numbers({"premium": 59000})
    text = "Phí là 59.000đ mỗi tháng. Quyền lợi lên tới 250.000.000đ. Bạn nên cân nhắc."
    cleaned = strip_unsupported_numbers(text, allowed)
    assert "59.000" in cleaned
    assert "250.000.000" not in cleaned
    assert "Bạn nên cân nhắc." in cleaned


def test_clean_text_is_returned_unchanged() -> None:
    allowed = collect_allowed_numbers({"premium": 59000})
    text = "Gói này phù hợp với ngân sách của bạn."
    assert strip_unsupported_numbers(text, allowed) == text


def test_small_counts_are_not_treated_as_financial_claims() -> None:
    allowed = collect_allowed_numbers({})
    assert not unsupported_numbers("Có 3 lý do và 2 điểm cần lưu ý.", allowed)


def test_a_money_amount_is_checked_however_small_the_digits_look() -> None:
    """«100 triệu» is a claim about money, not a count of 100."""

    allowed = collect_allowed_numbers({"benefit": 4_000_000})
    assert unsupported_numbers("Quyền lợi lên tới 100 triệu.", allowed)
    assert not unsupported_numbers("Quyền lợi 4 triệu.", allowed)


def test_supported_money_amounts_still_pass() -> None:
    allowed = collect_allowed_numbers({"sum_assured": 450_000_000, "premium": 350_000_000})
    assert not unsupported_numbers("Đóng 350 triệu, nhận 450 triệu.", allowed)
