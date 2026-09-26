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
        def extract(self, *_: object):
            from core.schemas import ProfilePatch

            return ProfilePatch(updates={}, provenance={})

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


# ----------------------------------------------------------- voice input


class FakeSpeech:
    """Stands in for SpeechClient inside the page."""

    def __init__(
        self,
        text: str = "mình để ra được ba triệu rưỡi mỗi tháng",
        fail: str = "",
        max_actions: int = 20,
    ) -> None:
        self.text, self.fail = text, fail
        self.enabled = True
        self.calls = 0
        self.spoken: list[tuple[str, object]] = []
        self.settings = type("S", (), {"voice_max_actions": max_actions})()

    def transcribe(self, audio: bytes, **_: object) -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError(self.fail)
        return self.text

    def speak(self, text: str, style: object = None) -> bytes:
        self.spoken.append((text, style))
        if self.fail:
            raise RuntimeError(self.fail)
        return b"ID3FAKEAUDIO"


def _voice_app(monkeypatch: pytest.MonkeyPatch, speech: object | None, **state: object):
    from streamlit.testing.v1 import AppTest

    orchestrator, session = _live_session_with_empty_profile()
    app = AppTest.from_file(str(PAGES / "consult.py"), default_timeout=TIMEOUT)
    app.session_state["lumi_mode"] = "manual"
    app.session_state["lumi_live"] = (orchestrator, session)
    app.session_state["lumi_engine_label"] = "Rule"
    # live_session() and speech_client() both read straight from session state.
    app.session_state["lumi_speech"] = speech
    for key, value in state.items():
        app.session_state[key] = value
    return app.run()


def test_voice_widget_is_absent_when_voice_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _voice_app(monkeypatch, None)

    assert not app.exception
    assert not app.get("audio_input"), "Tắt giọng nói thì không được hiện micro"
    assert app.chat_input, "Gõ phím vẫn phải dùng được"


def test_voice_widget_appears_when_voice_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _voice_app(monkeypatch, FakeSpeech())

    assert not app.exception
    assert app.get("audio_input")


def test_transcript_is_shown_for_review_before_sending(monkeypatch: pytest.MonkeyPatch) -> None:
    """A misheard amount must never reach the advice unseen."""

    draft = "mình để ra được ba triệu rưỡi mỗi tháng"
    app = _voice_app(monkeypatch, FakeSpeech(), lumi_draft=draft)

    assert not app.exception
    boxes = [item for item in app.text_area if item.value == draft]
    assert boxes, "Phải hiện văn bản đã phiên âm để khách kiểm tra"
    assert not app.session_state.get("lumi_pending_prompt"), "Chưa bấm gửi thì chưa gửi"


def test_the_edited_transcript_is_what_gets_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _voice_app(monkeypatch, FakeSpeech(), lumi_draft="ba triệu")

    app.text_area(key="lumi_draft_text").set_value("ba triệu rưỡi")
    next(item for item in app.button if item.label == "Gửi").click().run()

    # The pending prompt is consumed on the next run, so check the session.
    _, session = app.session_state["lumi_live"]
    sent = [item.content for item in session.messages if item.role == "customer"]
    assert sent == ["ba triệu rưỡi"], "Phải gửi bản đã sửa, không phải bản phiên âm gốc"
    assert "lumi_draft" not in app.session_state


def test_discarding_a_transcript_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _voice_app(monkeypatch, FakeSpeech(), lumi_draft="nghe nhầm hết rồi")

    next(item for item in app.button if "Bỏ" in item.label).click().run()

    assert not app.session_state.get("lumi_pending_prompt")
    assert "lumi_draft" not in app.session_state


def test_a_transcription_failure_keeps_typing_available(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _voice_app(
        monkeypatch,
        FakeSpeech(),
        lumi_voice_error="Bản ghi quá ngắn, LUMI chưa nghe được gì.",
    )

    assert not app.exception
    assert app.warning, "Phải nói rõ vì sao không nghe được"
    assert app.chat_input, "Người dùng vẫn phải gõ được"


# --------------------------------------------------------- voice playback


def _messages_with_reply(session) -> None:
    from core.schemas import ChatMessage

    session.messages.append(
        ChatMessage(role="customer", content="mình 60 tuổi", turn_index=len(session.messages))
    )
    session.messages.append(
        ChatMessage(role="assistant", content="Cháu chào bác ạ.", turn_index=len(session.messages))
    )


def _playback_app(speech: object | None, senior: bool = False, **state: object):
    from streamlit.testing.v1 import AppTest

    orchestrator, session = _live_session_with_empty_profile()
    _messages_with_reply(session)

    app = AppTest.from_file(str(PAGES / "consult.py"), default_timeout=TIMEOUT)
    app.session_state["lumi_mode"] = "manual"
    app.session_state["lumi_live"] = (orchestrator, session)
    app.session_state["lumi_engine_label"] = "Rule"
    app.session_state["lumi_speech"] = speech
    if senior:
        app.session_state["lumi_senior_mode"] = True
    for key, value in state.items():
        app.session_state[key] = value
    return app.run(), speech


def test_no_audio_is_generated_until_someone_asks() -> None:
    """Synthesising every reply on every redraw would be slow and costly."""

    app, speech = _playback_app(FakeSpeech())

    assert not app.exception
    assert speech.spoken == [], "Chưa bấm nghe thì không được gọi TTS"
    assert any(item.label == "Nghe" for item in app.button)


def test_pressing_listen_produces_a_player() -> None:
    app, speech = _playback_app(FakeSpeech())

    next(item for item in app.button if item.label == "Nghe").click().run()

    assert speech.spoken, "Bấm nghe thì phải sinh giọng"
    assert app.get("audio"), "Phải hiện trình phát"


def test_audio_is_reused_rather_than_regenerated() -> None:
    app, speech = _playback_app(FakeSpeech())
    next(item for item in app.button if item.label == "Nghe").click().run()
    first = len(speech.spoken)

    app.run()  # a plain redraw

    assert len(speech.spoken) == first, "Vẽ lại không được sinh giọng lần nữa"


def test_large_text_mode_plays_the_newest_reply_by_itself() -> None:
    app, speech = _playback_app(FakeSpeech(), senior=True)

    assert not app.exception
    assert speech.spoken, "Chế độ chữ lớn phải tự đọc câu trả lời mới"
    assert app.get("audio")


def test_large_text_autoplay_does_not_repeat_on_redraw() -> None:
    app, speech = _playback_app(FakeSpeech(), senior=True)
    first = len(speech.spoken)

    app.run()

    assert len(speech.spoken) == first


def test_no_listen_button_when_voice_is_off() -> None:
    app, _ = _playback_app(None)

    assert not app.exception
    assert not any(item.label == "Nghe" for item in app.button)


def test_a_synthesis_failure_does_not_break_the_page() -> None:
    app, _ = _playback_app(FakeSpeech(fail="Máy chủ giọng nói bận"))

    next(item for item in app.button if item.label == "Nghe").click().run()

    assert not app.exception
    assert app.chat_input


# ------------------------------------------------------- voice spend cap


def test_the_microphone_disappears_once_the_budget_is_spent() -> None:
    """A public deployment carries a real key, so one visitor must not be able
    to spend without limit."""

    app, _ = _playback_app(FakeSpeech(max_actions=2), lumi_voice_used=2)

    assert not app.exception
    assert not app.get("audio_input"), "Hết lượt thì không hiện micro nữa"
    assert app.info, "Phải giải thích vì sao micro biến mất"
    assert app.chat_input, "Gõ phím vẫn dùng được"


def test_the_listen_button_disappears_once_the_budget_is_spent() -> None:
    app, speech = _playback_app(FakeSpeech(max_actions=2), lumi_voice_used=2)

    assert not any(item.label == "Nghe" for item in app.button)
    assert speech.spoken == []


def test_spending_is_counted_per_synthesis() -> None:
    app, _ = _playback_app(FakeSpeech(max_actions=5))
    assert app.session_state.get("lumi_voice_used", 0) == 0

    next(item for item in app.button if item.label == "Nghe").click().run()

    assert app.session_state["lumi_voice_used"] == 1


def test_cached_audio_does_not_spend_the_budget_again() -> None:
    app, _ = _playback_app(FakeSpeech(max_actions=5))
    next(item for item in app.button if item.label == "Nghe").click().run()
    spent = app.session_state["lumi_voice_used"]

    app.run()

    assert app.session_state["lumi_voice_used"] == spent


def test_autoplay_leaves_a_turn_for_a_deliberate_request() -> None:
    """Auto playback must not eat the very last action."""

    app, speech = _playback_app(FakeSpeech(max_actions=3), senior=True, lumi_voice_used=2)

    assert speech.spoken == [], "Còn một lượt cuối thì để dành cho khách tự bấm"
    assert not app.exception
