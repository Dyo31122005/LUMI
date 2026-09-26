"""Pages must actually execute — AppTest runs the real Streamlit script."""

from __future__ import annotations

import pytest
from pathlib import Path

from streamlit.testing.v1 import AppTest

PAGES = Path(__file__).resolve().parents[1] / "pages"
TIMEOUT = 30


def run(page: str, **session_state: object) -> AppTest:
    app = AppTest.from_file(str(PAGES / page), default_timeout=TIMEOUT)
    for key, value in session_state.items():
        app.session_state[key] = value
    return app.run()


def test_landing_renders_without_exception() -> None:
    app = run("landing.py")
    assert not app.exception
    rendered = " ".join(str(item.value) for item in app.get("html"))
    assert "ba hành trình" in rendered.lower()


def test_landing_includes_the_production_mascot() -> None:
    from ui.components import MASCOT_PATH

    assert MASCOT_PATH.is_file()
    assert MASCOT_PATH.name == "mascot.png"


def test_landing_offers_a_button_per_persona() -> None:
    app = run("landing.py")
    labels = [button.label for button in app.button]
    assert any("Vương" in label for label in labels)
    assert any("Mai" in label for label in labels)
    assert any("Đức" in label for label in labels)


def test_consult_start_screen_renders() -> None:
    app = run("consult.py")
    assert not app.exception
    rendered = " ".join(str(item.value) for item in app.get("html"))
    assert "bắt đầu từ điều bạn đang quan tâm nhất" in rendered.lower()


@pytest.mark.parametrize("persona_id", ["vuong", "mai", "duc"])
def test_consult_replay_renders_for_each_persona(persona_id: str) -> None:
    app = run("consult.py", lumi_mode="replay", lumi_persona=persona_id)
    assert not app.exception
    assert app.chat_message, "Phiên phát lại phải hiện hội thoại"


def test_replay_shows_both_result_steps() -> None:
    app = run("consult.py", lumi_mode="replay", lumi_persona="vuong")
    rendered = " ".join(str(item.value) for item in app.get("html"))
    assert "Bước 1" in rendered
    assert "Bước 2" in rendered
    assert "Xác suất ước lượng" in rendered


def test_replay_labels_fictional_data() -> None:
    app = run("consult.py", lumi_mode="replay", lumi_persona="duc")
    rendered = " ".join(str(item.value) for item in app.get("html"))
    assert "hư cấu" in rendered


def test_senior_mode_is_on_by_default_for_older_customers() -> None:
    app = run("consult.py", lumi_mode="replay", lumi_persona="duc")
    assert app.session_state.get("lumi_senior_mode") is True


def test_report_page_renders_for_a_recorded_session() -> None:
    app = run("report.py", lumi_persona="mai")
    assert not app.exception
    assert "Báo cáo tư vấn" in app.title[0].value


def test_report_page_without_a_session_explains_itself() -> None:
    app = run("report.py")
    assert not app.exception
    assert app.info


def test_journeys_page_renders_all_recorded_personas() -> None:
    app = run("journeys.py")
    assert not app.exception
    rendered = " ".join(str(item.value) for item in app.get("html"))
    for name in ("Vương", "Mai", "Đức"):
        assert name in rendered


def test_manual_mode_without_credentials_offers_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    """A connection problem must degrade to Phát lại, never to a crash."""

    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setattr(
        "core.llm.load_settings",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("OPENAI_API_KEY is missing in lumi/.env.")),
    )
    app = run("consult.py", lumi_mode="manual")
    assert not app.exception
    assert app.error
    assert any("Phát lại" in button.label for button in app.button)


def test_render_skips_empty_markup() -> None:
    """st.html("") raises, so ui.render must no-op on empty builders."""

    from ui import components as ui

    calls: list[str] = []

    class FakeSt:
        @staticmethod
        def html(markup: str) -> None:
            calls.append(markup)

    ui.render(FakeSt, ui.insight_cards([]))
    ui.render(FakeSt, ui.scenario_card(None))
    ui.render(FakeSt, None)
    ui.render(FakeSt, "   ")
    assert calls == []

    ui.render(FakeSt, "<b>có nội dung</b>")
    assert calls == ["<b>có nội dung</b>"]


def _live_session_with_empty_profile():
    """A real orchestrator + session whose profile has nothing in it yet."""

    from core.decision import RuleEngine
    from core.kb import KnowledgeBase
    from core.orchestrator import Orchestrator

    kb = KnowledgeBase.load()

    class Stub:
        def extract(self, *_: object) -> object: ...
        def write_question(self, *, template: str, **__: object) -> str:
            return template

        @staticmethod
        def render_template(template: str, address: dict) -> str:
            return template

    orchestrator = Orchestrator(
        knowledge_base=kb, extractor=Stub(), conversation=Stub(),
        engine=RuleEngine(kb), writer=Stub(),
    )
    session = orchestrator.new_session(None, {"assistant_self": "mình", "customer": "bạn"})
    orchestrator.greeting(session)
    return orchestrator, session


def test_manual_mode_survives_a_profile_with_no_insights() -> None:
    """Regression from production: the first live turn crashed with
    StreamlitMissingRequiredParameterError because there were no insights yet
    and st.html() was handed an empty string, which killed the chat input."""

    app = run(
        "consult.py",
        lumi_mode="manual",
        lumi_live=_live_session_with_empty_profile(),
        lumi_engine_label="Rule",
    )

    assert not app.exception, f"Trang vỡ: {app.exception}"
    assert app.chat_input, "Ô nhập phải luôn được vẽ để người dùng gõ được"
    assert any("LUMI" in message.markdown[0].value for message in app.chat_message)


def test_manual_mode_survives_a_profile_that_has_no_insights_yet() -> None:
    """The exact production crash: a filled profile whose insight list is empty
    made ui.insight_cards() return "", and st.html("") aborted the page."""

    from core.schemas import Profile

    orchestrator, session = _live_session_with_empty_profile()
    session.profile = Profile(age=31, employment_status="employed", monthly_income=18_000_000)
    session.insights = []
    session.derived = {"completeness": 0.4}

    app = run("consult.py", lumi_mode="manual", lumi_live=(orchestrator, session), lumi_engine_label="Rule")

    assert not app.exception, f"Trang vỡ: {app.exception}"
    assert app.chat_input


def test_manual_mode_explains_the_empty_profile_panel() -> None:
    app = run(
        "consult.py",
        lumi_mode="manual",
        lumi_live=_live_session_with_empty_profile(),
        lumi_engine_label="Rule",
    )
    messages = " ".join(item.value for item in app.info)
    assert "điền dần" in messages
