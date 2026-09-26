"""Number guard: A4 may only print figures that its input actually contains.

Rule 1 of writing_rules — every number comes from the knowledge base or from
`finance`. The guard collects the numbers present in the writer's payload and
removes any sentence that introduces a different one.
"""

from __future__ import annotations

import re
from typing import Any

NUMBER = re.compile(r"\d[\d.,]*")
SENTENCE = re.compile(r"[^.!?\n]+[.!?]?\n?")

# A number followed by one of these is a money claim however small it looks,
# so "100 triệu" must be backed even though 100 on its own would not be.
MONEY_SUFFIX = re.compile(r"\s*(triệu|tỷ|ty|nghìn|nghin|ngàn|k\b|đ\b|vnd)", re.IGNORECASE)

# Bare small integers are list positions, counts and plan years, not amounts.
SAFE_SMALL_INTEGER = 20


def _variants(value: Any) -> set[str]:
    """Every spelling a number may legitimately take in Vietnamese copy."""

    if isinstance(value, bool) or value is None:
        return set()
    if not isinstance(value, (int, float)):
        return set()

    number = float(value)
    found: set[str] = set()
    whole = int(number) if float(number).is_integer() else None

    if whole is not None:
        found.add(str(whole))
        found.add(f"{whole:,}".replace(",", "."))
        found.add(f"{whole:,}")
        for unit in (1_000, 1_000_000, 1_000_000_000):
            if whole % unit == 0 and whole >= unit:
                scaled = whole // unit
                found.add(str(scaled))
        for unit in (1_000_000, 1_000_000_000):
            if whole >= unit:
                scaled = whole / unit
                found.add(f"{scaled:.1f}".replace(".", ","))
                found.add(f"{scaled:.1f}".rstrip("0").rstrip(".").replace(".", ","))
                found.add(str(round(scaled)))
    else:
        found.add(f"{number:g}")
        found.add(f"{number:g}".replace(".", ","))
        found.add(str(round(number * 100)))
    return {item for item in found if item}


def collect_allowed_numbers(payload: Any) -> set[str]:
    """Walk the writer payload and index every number it may quote back."""

    allowed: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for item in node.values():
                walk(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            for match in NUMBER.finditer(node):
                allowed.add(match.group(0))
                allowed.add(match.group(0).replace(".", "").replace(",", ""))
        else:
            allowed.update(_variants(node))

    walk(payload)
    return {item for item in allowed if item}


def unsupported_numbers(text: str, allowed: set[str]) -> list[str]:
    """Numbers in `text` that the payload does not justify."""

    found: list[str] = []
    for match in NUMBER.finditer(text):
        token = match.group(0).strip(".,")
        if not token or token in allowed:
            continue
        digits = token.replace(".", "").replace(",", "")
        if digits in allowed:
            continue
        is_money = bool(MONEY_SUFFIX.match(text[match.end():]))
        if not is_money and digits.isdigit() and int(digits) <= SAFE_SMALL_INTEGER:
            continue
        found.append(token)
    return found


def strip_unsupported_numbers(text: str, allowed: set[str]) -> str:
    """Drop sentences carrying an unsupported number rather than ship a wrong figure."""

    if not unsupported_numbers(text, allowed):
        return text

    kept = [
        sentence
        for sentence in SENTENCE.findall(text)
        if not unsupported_numbers(sentence, allowed)
    ]
    return "".join(kept).strip() or text
