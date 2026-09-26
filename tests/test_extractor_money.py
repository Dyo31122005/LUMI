"""Money parsing must survive speech, not just typing.

Speech-to-text returns numbers as words ("ba triệu rưỡi"), so this safety net
has to read spoken Vietnamese as well as the written forms. A wrong amount is
worse than a missing one: it flows straight into the advice.
"""

from __future__ import annotations

import pytest

from agents.extractor import parse_money

SPOKEN = [
    ("hai mươi triệu", 20_000_000),
    ("mười lăm triệu", 15_000_000),
    ("mười triệu", 10_000_000),
    ("hai mươi lăm triệu", 25_000_000),
    ("năm mươi triệu", 50_000_000),
    ("ba trăm năm mươi triệu", 350_000_000),
    ("một trăm năm mươi nghìn", 150_000),
    ("chín trăm nghìn", 900_000),
    ("một trăm lẻ năm triệu", 105_000_000),
    ("ba triệu năm trăm nghìn", 3_500_000),
    ("một tỷ hai trăm triệu", 1_200_000_000),
    ("hai muoi trieu", 20_000_000),  # phiên âm không dấu
]

WRITTEN = [
    ("3tr", 3_000_000),
    ("11 triệu mỗi tháng", 11_000_000),
    ("100-150k", 150_000),
    ("59.000đ", 59_000),
    ("3 đến 3,5 triệu", 3_500_000),
    ("khoảng 1,2 tỷ", 1_200_000_000),
    ("350 triệu", 350_000_000),
    ("150000", 150_000),
]

HALF = [
    ("ba triệu rưỡi", 3_500_000),
    ("3 triệu rưỡi", 3_500_000),
    ("hai tỷ rưỡi", 2_500_000_000),
]

TENTHS = [
    ("một tỷ hai", 1_200_000_000),
    ("1 tỷ 2", 1_200_000_000),
]


@pytest.mark.parametrize(("text", "expected"), SPOKEN)
def test_spoken_vietnamese_numbers(text: str, expected: int) -> None:
    assert parse_money(text) == pytest.approx(expected)


@pytest.mark.parametrize(("text", "expected"), WRITTEN)
def test_written_forms_still_work(text: str, expected: int) -> None:
    assert parse_money(text) == pytest.approx(expected)


@pytest.mark.parametrize(("text", "expected"), HALF)
def test_ruoi_means_half_of_the_scale(text: str, expected: int) -> None:
    """Regression: «3 triệu rưỡi» used to return 3.000.000 and silently drop
    the half — a wrong figure reaching the customer, not a missing one."""

    assert parse_money(text) == pytest.approx(expected)


@pytest.mark.parametrize(("text", "expected"), TENTHS)
def test_a_bare_tail_is_tenths_of_the_scale(text: str, expected: int) -> None:
    assert parse_money(text) == pytest.approx(expected)


def test_a_range_yields_its_upper_bound() -> None:
    """A budget stated as a range is a ceiling: «100-150k» means 150k."""

    assert parse_money("100-150k") == 150_000
    assert parse_money("3 đến 3,5 triệu") == 3_500_000
    assert parse_money("từ hai đến ba triệu") == 3_000_000


def test_numbers_and_mappings_pass_through() -> None:
    assert parse_money(150_000) == 150_000
    assert parse_money(150_000.0) == 150_000
    assert parse_money({"min": 100_000, "max": 150_000}) == 150_000
    assert parse_money({"amount": 59_000}) == 59_000


def test_non_amounts_are_rejected_rather_than_guessed() -> None:
    for value in ("không rõ", "", "   ", True, False, None, [], "chưa nghĩ tới"):
        assert parse_money(value) is None


def test_zero_is_not_treated_as_an_amount() -> None:
    assert parse_money("không đồng") is None
    assert parse_money(0) == 0
