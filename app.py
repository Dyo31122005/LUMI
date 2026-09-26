"""LUMI — Streamlit entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import gate  # noqa: E402
from ui.components import load_css  # noqa: E402

st.set_page_config(
    page_title="LUMI — Hiểu bạn trước, rồi mới đề xuất",
    page_icon=":material/shield:",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def apply_theme() -> None:
    senior = st.session_state.get("lumi_senior_mode", False)
    st.html(f"<style>{load_css()}</style>")
    if senior:
        st.html(
            "<script>window.parent.document.querySelectorAll('.stApp')"
            ".forEach(n => n.classList.add('lumi-senior'));</script>"
            "<style>:root { --chat-size: 19px; --line-height: 1.75; }"
            ".stApp { font-size: 17px; } .lumi-caption { font-size: 15px; }</style>"
        )


apply_theme()

if not gate.render(st):
    st.stop()

pages = [
    st.Page("pages/landing.py", title="Trang chủ", icon=":material/home:", default=True),
    st.Page("pages/consult.py", title="Tư vấn", icon=":material/forum:"),
    st.Page("pages/report.py", title="Báo cáo", icon=":material/description:"),
    st.Page("pages/journeys.py", title="Hành trình mẫu", icon=":material/route:"),
]

st.navigation(pages, position="hidden").run()
