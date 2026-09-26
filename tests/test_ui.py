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
    assert any("ba hành trình" in item.value.lower() for item in app.subheader)


def test_landing_offers_a_button_per_persona() -> None:
    app = run("landing.py")
    labels = [button.label for button in app.button]
    assert any("Vương" in label for label in labels)
    assert any("Mai" in label for label in labels)
    assert any("Đức" in label for label in labels)


def test_consult_start_screen_renders() -> None:
    app = run("consult.py")
    assert not app.exception
    assert "bắt đầu thế nào" in app.title[0].value.lower()


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
