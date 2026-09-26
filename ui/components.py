"""Reusable LUMI interface pieces.

Each helper returns an HTML string so the caller decides where it lands; the
Streamlit pages only compose them. Every user-facing figure arrives already
computed — components format, they never calculate.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Iterable

CSS_PATH = Path(__file__).resolve().parent / "theme.css"

TYPE_LABELS = {
    "unemployment": "Thất nghiệp",
    "retirement": "Hưu trí",
    "life": "Nhân thọ",
    "health": "Sức khoẻ",
}

CRITERION_LABELS = {
    "C1": "Đáp ứng nhu cầu",
    "C2": "Khả năng chi trả",
    "C3": "Mức cam kết",
    "C4": "Linh hoạt",
    "C5": "Điều kiện tham gia",
    "C6": "Uy tín, bồi thường",
}

LEVEL_TONE = {
    "Does not meet": ("bad", "✕", "Không phù hợp"),
    "Partly meets": ("warn", "!", "Đáp ứng một phần"),
    "Meets well": ("good", "✓", "Đáp ứng tốt"),
    "Meets very well": ("good", "✓✓", "Đáp ứng rất tốt"),
}

FICTION_NOTE = "Dữ liệu minh hoạ · Doanh nghiệp và sản phẩm trong demo là hư cấu."
ESTIMATE_NOTE = "Số liệu ước tính, lãi minh hoạ không phải cam kết."


def load_css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def render(st: Any, markup: str | None) -> None:
    """Write markup with `st.html`, skipping anything empty.

    Several builders below legitimately return "" — no insights yet, no
    scenario for this insurance type — and `st.html("")` raises
    StreamlitMissingRequiredParameterError, which aborts the rest of the page.
    """

    if markup and markup.strip():
        st.html(markup)


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def money(value: float | int | None) -> str:
    """Vietnamese money formatting with a dot as the thousands separator."""

    if value is None:
        return "—"
    return f"{round(value):,}".replace(",", ".") + "đ"


def persona_class(age: int | None) -> str:
    if age is None:
        return "persona-mid"
    if age <= 29:
        return "persona-young"
    if age >= 55:
        return "persona-senior"
    return "persona-mid"


def card(body: str, *, eyebrow: str | None = None, title: str | None = None) -> str:
    parts = ['<div class="lumi-card">']
    if eyebrow:
        parts.append(f'<div class="lumi-eyebrow">{esc(eyebrow)}</div>')
    if title:
        parts.append(f"<h3>{esc(title)}</h3>")
    parts.append(body)
    parts.append("</div>")
    return "".join(parts)


# ------------------------------------------------------------------- profile


def profile_chips(profile: Any, labels: dict[str, str], new_keys: Iterable[str] = ()) -> str:
    """One chip per known field, each carrying its quote and confidence."""

    known = profile.model_dump(exclude={"provenance"})
    new_keys = set(new_keys)
    chips: list[str] = []

    for key, value in known.items():
        if value in (None, [], {}):
            continue
        evidence = profile.provenance.get(key)
        classes = ["lumi-chip"]
        if key in new_keys:
            classes.append("lumi-chip-new")
        dot = ""
        if evidence:
            level = "lumi-dot-high" if evidence.confidence >= 0.85 else "lumi-dot-mid"
            dot = f'<span class="lumi-dot {level}"></span>'
        tooltip = f"«{evidence.quote}» · độ tin cậy {evidence.confidence:.2f}" if evidence else "Suy ra từ hội thoại"
        chips.append(
            f'<span class="{" ".join(classes)}" title="{esc(tooltip)}">{dot}'
            f'{esc(labels.get(key, key))}: <b>{esc(_short(value))}</b></span>'
        )
    return "".join(chips) or '<span class="lumi-caption">Chưa có thông tin nào.</span>'


def _short(value: Any) -> str:
    if isinstance(value, bool):
        return "Có" if value else "Không"
    if isinstance(value, (int, float)) and value >= 1000:
        return money(value)
    if isinstance(value, list):
        return ", ".join(_short(item) for item in value[:3]) or "—"
    if isinstance(value, dict):
        return ", ".join(f"{key}: {_short(item)}" for key, item in value.items() if item not in (None, ""))
    text = str(value)
    return text if len(text) <= 60 else text[:57] + "…"


def completeness_bar(fraction: float) -> str:
    percent = round(max(0.0, min(1.0, fraction)) * 100)
    return (
        '<div class="lumi-bar-row lumi-bar-lead">'
        '<span>Độ đầy đủ</span>'
        f'<span class="lumi-bar-track"><span class="lumi-bar-fill" style="width:{percent}%"></span></span>'
        f'<span class="lumi-bar-value">{percent}%</span></div>'
    )


def insight_cards(insights: Iterable[Any]) -> str:
    """Accepts InsightFlag models or their serialised form."""

    blocks = [
        '<div class="lumi-insight"><div class="lumi-eyebrow">💡 LUMI nhận ra</div>'
        f"{esc(item['reason'] if isinstance(item, dict) else item.reason)}</div>"
        for item in insights
    ]
    return "".join(blocks)


def hypothesis_bars(probabilities: dict[str, float] | None, confidence: float | None = None) -> str:
    """The «LUMI đang cân nhắc» panel; always labelled as an estimate."""

    if not probabilities:
        return '<span class="lumi-caption">LUMI chưa có đủ thông tin để cân nhắc.</span>'

    ordered = sorted(probabilities.items(), key=lambda item: -item[1])
    rows: list[str] = []
    for index, (key, value) in enumerate(ordered):
        percent = round(value * 100)
        lead = " lumi-bar-lead" if index == 0 else ""
        rows.append(
            f'<div class="lumi-bar-row{lead}"><span>{esc(TYPE_LABELS.get(key, key))}</span>'
            f'<span class="lumi-bar-track"><span class="lumi-bar-fill" style="width:{percent}%"></span></span>'
            f'<span class="lumi-bar-value">{percent}%</span></div>'
        )
    footer = "Xác suất ước lượng"
    if confidence is not None:
        footer += f" · Độ tin cậy: {confidence:.2f}".replace(".", ",")
    rows.append(f'<div class="lumi-caption" style="margin-top:8px">{esc(footer)}</div>')
    return "".join(rows)


def why_ask(text: str) -> str:
    return f'<div class="lumi-why">ⓘ {esc(text)}</div>'


# -------------------------------------------------------------------- step 1


def step_one_card(decision: dict[str, Any], insights: Iterable[Any], type_name: str) -> str:
    reasons = "".join(f"<li>{esc(item)}</li>" for item in decision.get("reasons", []))
    probabilities = decision.get("type_probabilities") or {}
    secondary = decision.get("secondary_type")

    body = [
        f'<div class="lumi-rank-head"><span class="lumi-rank-name">★ {esc(type_name)}</span>'
        f'<span class="lumi-rank-score">Tin cậy {decision.get("confidence", 0):.2f}'.replace(".", ",") + "</span></div>",
        f"<ul style='margin:10px 0 6px'>{reasons}</ul>" if reasons else "",
        insight_cards(insights),
    ]
    if secondary:
        share = round(probabilities.get(secondary, 0) * 100)
        body.append(
            f'<div class="lumi-caption">Cân nhắc sau: {esc(TYPE_LABELS.get(secondary, secondary))} ({share}%)</div>'
        )
    body.append(
        '<div class="lumi-caption" style="margin-top:8px">'
        "Nếu các thông tin trên khác đi, đề xuất cũng sẽ khác.</div>"
    )
    return card("".join(body), eyebrow="Bước 1 · Loại bảo hiểm phù hợp")


# -------------------------------------------------------------------- step 2


def priority_chips(criteria: list[str], reasons: list[str], name: str | None) -> str:
    who = f" với {name}" if name else ""
    chips = "".join(f'<span class="lumi-chip"><b>{esc(item)}</b></span>' for item in criteria)
    note = f'<div class="lumi-caption">{esc(" · ".join(reasons))}</div>' if reasons else ""
    return f'<div class="lumi-eyebrow">Quan trọng{esc(who)}</div>{chips}{note}'


def ranking_cards(ranking: list[dict[str, Any]], name: str | None) -> str:
    blocks: list[str] = []
    for item in ranking:
        top = item["rank"] == 1
        classes = "lumi-rank lumi-rank-top" if top else "lumi-rank"
        tags = [
            f'<span class="lumi-tag lumi-tag-good">{esc(text)}</span>'
            for text in item.get("strengths", [])[:2]
        ]
        tags += [
            f'<span class="lumi-tag lumi-tag-warn">{esc(text)}</span>'
            for text in item.get("watch_outs", [])[:2]
        ]
        if item.get("investment_linked"):
            tags.append('<span class="lumi-tag lumi-tag-bad">Liên kết đầu tư · không cam kết lãi</span>')
        tags += [
            f'<span class="lumi-tag lumi-tag-note">{esc(text)}</span>'
            for text in item.get("filter_notes", [])
        ]
        badge = f'<div class="lumi-caption">Phù hợp nhất{" với " + esc(name) if name else ""}</div>' if top else ""
        blocks.append(
            f'<div class="{classes}">'
            f'<div class="lumi-rank-head"><span class="lumi-rank-name">{item["rank"]}. {esc(item["product_name"])}</span>'
            f'<span class="lumi-rank-score">{item["fit_score"]:.0f}/100</span></div>'
            f'<div class="lumi-caption">{esc(item["insurer"])}'
            + (f' · {esc(item["premium_display"])}' if item.get("premium_display") else "")
            + "</div>"
            f"{badge}<div>{''.join(tags)}</div></div>"
        )
    return "".join(blocks)


def heatmap(ranking: list[dict[str, Any]], priority: list[str]) -> str:
    """Six-criterion grid; every colour also carries a symbol and a label."""

    header = "".join(
        f'<th class="{"lumi-priority" if key in priority else ""}">{esc(CRITERION_LABELS[key])}</th>'
        for key in CRITERION_LABELS
    )
    rows: list[str] = []
    for item in ranking:
        cells: list[str] = []
        for key in CRITERION_LABELS:
            level = item["scores"][key]
            tone, symbol, label = LEVEL_TONE[level]
            note = (item.get("notes") or {}).get(key, "")
            cells.append(
                f'<td class="cell-{tone}" title="{esc(f"{label}. {note}")}">{symbol}'
                f'<div class="lumi-caption" style="color:inherit">{esc(label)}</div></td>'
            )
        rows.append(f'<tr><td class="row-head">{esc(item["product_name"])}</td>{"".join(cells)}</tr>')
    return (
        '<div class="lumi-table-wrap"><table class="lumi-table">'
        f"<thead><tr><th>Sản phẩm</th>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def comparison_table(ranking: list[dict[str, Any]], rows: list[str], priority_rows: list[str]) -> str:
    """Detail table; rows the customer cares about are pulled to the top."""

    ordered = [row for row in priority_rows if row in rows]
    ordered += [row for row in rows if row not in ordered]

    header = "".join(f"<th>{esc(item['product_name'])}</th>" for item in ranking)
    body: list[str] = []
    for row in ordered:
        if not any(row in (item.get("comparison_values") or {}) for item in ranking):
            continue
        marker = ' <span class="lumi-tag lumi-tag-note">Quan trọng</span>' if row in priority_rows else ""
        cells = "".join(
            f"<td>{esc((item.get('comparison_values') or {}).get(row, '—'))}</td>" for item in ranking
        )
        body.append(f'<tr><td class="row-head">{esc(row)}{marker}</td>{cells}</tr>')
    return (
        '<div class="lumi-table-wrap"><table class="lumi-table">'
        f"<thead><tr><th>Tiêu chí</th>{header}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


def scenario_card(scenario: dict[str, Any] | None) -> str:
    if not scenario:
        return ""
    rows = "".join(
        f'<div class="lumi-scenario-row"><span>{esc(label)}</span>'
        f'<span class="lumi-scenario-value">{money(value) if value is not None else "—"}</span></div>'
        for label, value in scenario["lines"]
    )
    note = f'<div class="lumi-caption" style="margin-top:10px">{esc(scenario["note"])}</div>' if scenario.get("note") else ""
    return card(rows + note, eyebrow="Nếu… thì…", title=scenario["title"])


def data_footer() -> str:
    return f'<div class="lumi-footer-note">{esc(FICTION_NOTE)}<br>{esc(ESTIMATE_NOTE)}</div>'
