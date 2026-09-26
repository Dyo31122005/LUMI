"""Speech layer: correct models, correct guards, no surprises.

Every test here runs offline against a fake client; the audio endpoints are
never called for real.
"""

from __future__ import annotations

from typing import Any

import pytest

from core import speech
from core.llm import DEFAULT_STT_MODEL, DEFAULT_TTS_MODEL, LLMSettings, LUMI_MODEL
from core.speech import (
    AudioTooLargeError,
    AudioTooShortError,
    SpeechClient,
    SpeechError,
    shorten_for_speech,
    style_for_age,
)


def settings(**overrides: Any) -> LLMSettings:
    base = {
        "api_key": "test",
        "model": LUMI_MODEL,
        "writer_model": LUMI_MODEL,
        "decision_engine": "openai",
    }
    base.update(overrides)
    return LLMSettings(**base)  # type: ignore[arg-type]


class FakeAudio:
    def __init__(self, text: str = "ba triệu rưỡi", audio: bytes = b"MP3DATA") -> None:
        self.text, self.audio = text, audio
        self.transcribe_calls: list[dict[str, Any]] = []
        self.speech_calls: list[dict[str, Any]] = []
        outer = self

        class Transcriptions:
            @staticmethod
            def create(**kwargs: Any) -> Any:
                outer.transcribe_calls.append(kwargs)
                return type("R", (), {"text": outer.text})()

        class Speech:
            @staticmethod
            def create(**kwargs: Any) -> Any:
                outer.speech_calls.append(kwargs)
                return type("R", (), {"read": staticmethod(lambda: outer.audio)})()

        self.transcriptions = Transcriptions()
        self.speech = Speech()


class FakeClient:
    def __init__(self, audio: FakeAudio) -> None:
        self.audio = audio


def build(fake: FakeAudio, **overrides: Any) -> SpeechClient:
    return SpeechClient(settings(**overrides), client=FakeClient(fake))


def sample(size: int = 50_000) -> bytes:
    return b"\x00" * size


# ------------------------------------------------------------------ models


def test_transcription_uses_the_configured_model_and_vietnamese() -> None:
    fake = FakeAudio()
    build(fake).transcribe(sample())

    call = fake.transcribe_calls[0]
    assert call["model"] == DEFAULT_STT_MODEL
    assert call["language"] == "vi"


def test_synthesis_uses_the_configured_model() -> None:
    fake = FakeAudio()
    build(fake).speak("Xin chào")

    assert fake.speech_calls[0]["model"] == DEFAULT_TTS_MODEL


def test_audio_models_can_be_overridden_without_touching_the_chat_model() -> None:
    fake = FakeAudio()
    client = build(fake, stt_model="whisper-1", tts_model="tts-1")

    client.transcribe(sample())
    client.speak("Xin chào")

    assert fake.transcribe_calls[0]["model"] == "whisper-1"
    assert fake.speech_calls[0]["model"] == "tts-1"
    # The conversation model is untouched by the voice exception.
    assert client.settings.model == LUMI_MODEL
    assert client.settings.writer_model == LUMI_MODEL


# ------------------------------------------------------------------- guards


def test_voice_can_be_switched_off_entirely() -> None:
    client = build(FakeAudio(), voice_enabled=False)

    assert not client.enabled
    with pytest.raises(SpeechError):
        client.transcribe(sample())
    with pytest.raises(SpeechError):
        client.speak("Xin chào")


def test_a_silent_recording_is_rejected_before_any_call() -> None:
    fake = FakeAudio()
    with pytest.raises(AudioTooShortError):
        build(fake).transcribe(b"\x00" * 10)
    assert not fake.transcribe_calls, "Không được gọi API với bản ghi rỗng"


def test_an_oversized_recording_is_rejected_before_any_call() -> None:
    fake = FakeAudio()
    with pytest.raises(AudioTooLargeError):
        build(fake).transcribe(b"\x00" * (speech.MAX_AUDIO_BYTES + 1))
    assert not fake.transcribe_calls


def test_an_empty_transcript_is_an_error_not_an_empty_message() -> None:
    with pytest.raises(AudioTooShortError):
        build(FakeAudio(text="   ")).transcribe(sample())


# -------------------------------------------------------------------- voice


def test_voice_style_follows_the_address_style_thresholds() -> None:
    assert style_for_age(22) is speech.VOICE_STYLES["young"]
    assert style_for_age(44) is speech.VOICE_STYLES["mid"]
    assert style_for_age(60) is speech.VOICE_STYLES["senior"]
    assert style_for_age(None) is speech.VOICE_STYLES["mid"]


def test_the_senior_voice_asks_for_slower_speech() -> None:
    fake = FakeAudio()
    build(fake).speak("Xin chào bác", style_for_age(60))

    instructions = fake.speech_calls[0]["instructions"].lower()
    assert "chậm" in instructions


def test_each_persona_gets_different_instructions() -> None:
    heard = {style_for_age(age).instructions for age in (22, 44, 60)}
    assert len(heard) == 3


# ------------------------------------------------------------------ trimming


def test_short_replies_are_spoken_whole() -> None:
    text = "LUMI đề xuất bảo hiểm hưu trí."
    assert shorten_for_speech(text) == text


def test_long_replies_are_cut_at_a_sentence_boundary() -> None:
    text = ("Đây là một câu dài về bảo hiểm. " * 80).strip()
    spoken = shorten_for_speech(text, limit=200)

    assert len(spoken) <= 200
    assert spoken.endswith(".")


def test_trimming_never_splits_a_word() -> None:
    spoken = shorten_for_speech("mộtchuỗirấtdàikhôngcódấucách " * 40, limit=100)
    assert len(spoken) <= 101
    assert "  " not in spoken


# ------------------------------------------------------------------- prompt


def test_transcription_prompt_carries_domain_vocabulary() -> None:
    prompt = speech.transcription_prompt()

    for term in ("BHXH", "BHTN", "Hưu trí", "GenZ Bảo Vệ"):
        assert term in prompt


def test_transcription_prompt_is_passed_through() -> None:
    fake = FakeAudio()
    build(fake).transcribe(sample(), prompt="BHXH, BHTN")

    assert fake.transcribe_calls[0]["prompt"] == "BHXH, BHTN"


def test_no_prompt_key_when_none_is_given() -> None:
    fake = FakeAudio()
    build(fake).transcribe(sample())

    assert "prompt" not in fake.transcribe_calls[0]
