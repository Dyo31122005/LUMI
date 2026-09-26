"""Speech in and speech out.

Two models beyond the conversation model, and only these two: transcription
turns what the customer said into text for A1, and synthesis reads LUMI's reply
back. Neither decides anything — they sit at the edges of the existing pipeline
so the text path behaves exactly as before.

Transcription returns Vietnamese numbers as words ("ba triệu rưỡi"), which is
why `agents.extractor.parse_money` has to understand spoken forms.
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from core.llm import LLMSettings, load_settings

# Audio longer than this is almost certainly a stuck recording rather than an
# answer, and it is the main way a voice feature runs up a bill.
MAX_AUDIO_SECONDS = 120
MAX_AUDIO_BYTES = 10 * 1024 * 1024
# Anything shorter is silence or a mis-tap, not speech.
MIN_AUDIO_BYTES = 2 * 1024

# Reading a whole Bước 2 card aloud is neither pleasant nor cheap.
MAX_SPEAK_CHARS = 1_200


class SpeechError(RuntimeError):
    """Raised when audio cannot be transcribed or synthesised."""


class AudioTooShortError(SpeechError):
    """The recording holds no usable speech."""


class AudioTooLargeError(SpeechError):
    """The recording is past the size LUMI accepts."""


@dataclass(frozen=True)
class VoiceStyle:
    """How LUMI should sound, derived from the customer's address style."""

    voice: str
    instructions: str


# enums.address_styles already decides how LUMI writes; the voice follows it so
# a senior customer hears the same register they read.
VOICE_STYLES = {
    "young": VoiceStyle(
        voice="alloy",
        instructions=(
            "Giọng trẻ, thân thiện, tốc độ bình thường. Nói tự nhiên như đang "
            "trò chuyện với bạn bè, không trịnh trọng."
        ),
    ),
    "mid": VoiceStyle(
        voice="alloy",
        instructions=(
            "Giọng rõ ràng, điềm đạm, tốc độ bình thường. Nhấn nhẹ vào các con "
            "số tiền để người nghe nắm được."
        ),
    ),
    "senior": VoiceStyle(
        voice="shimmer",
        instructions=(
            "Giọng lễ phép, ấm áp, nói CHẬM và tách câu rõ ràng. Ngắt nghỉ lâu "
            "hơn bình thường giữa các ý. Đọc số tiền thong thả, tách từng phần."
        ),
    ),
}


def style_for_age(age: int | None) -> VoiceStyle:
    """Same thresholds as enums.address_styles."""

    if age is None:
        return VOICE_STYLES["mid"]
    if age <= 29:
        return VOICE_STYLES["young"]
    if age >= 55:
        return VOICE_STYLES["senior"]
    return VOICE_STYLES["mid"]


class SpeechClient:
    """Thin wrapper over the audio endpoints, mirroring core.llm's retry rules."""

    def __init__(
        self,
        settings: LLMSettings | None = None,
        *,
        client: Any | None = None,
        max_attempts: int = 2,
    ) -> None:
        self.settings = settings or load_settings()
        self._client = client or OpenAI(api_key=self.settings.api_key)
        self.max_attempts = max_attempts

    @property
    def enabled(self) -> bool:
        return self.settings.voice_enabled

    def _retry(self, call: Any) -> Any:
        for attempt in range(1, self.max_attempts + 1):
            try:
                return call()
            except (APIConnectionError, RateLimitError, APIStatusError) as error:
                if attempt == self.max_attempts:
                    raise SpeechError(str(error)) from error
                time.sleep(0.4 * attempt)
        raise SpeechError("Speech retry loop ended unexpectedly.")

    # ------------------------------------------------------------- listening

    def transcribe(self, audio: bytes, *, filename: str = "speech.wav", prompt: str = "") -> str:
        """Turn a recording into Vietnamese text.

        `prompt` carries domain vocabulary so insurance terms come back spelled
        correctly; the transcription model treats it as a hint, not content.
        """

        if not self.enabled:
            raise SpeechError("Tính năng giọng nói đang tắt.")
        if len(audio) < MIN_AUDIO_BYTES:
            raise AudioTooShortError("Bản ghi quá ngắn, LUMI chưa nghe được gì.")
        if len(audio) > MAX_AUDIO_BYTES:
            raise AudioTooLargeError("Bản ghi quá dài, bạn thử nói ngắn hơn nhé.")

        payload = io.BytesIO(audio)
        payload.name = filename

        request: dict[str, Any] = {
            "model": self.settings.stt_model,
            "file": payload,
            "language": "vi",
        }
        if prompt:
            request["prompt"] = prompt

        result = self._retry(lambda: self._client.audio.transcriptions.create(**request))
        text = (getattr(result, "text", "") or "").strip()
        if not text:
            raise AudioTooShortError("LUMI không nghe rõ, bạn thử ghi lại nhé.")
        return text

    # ------------------------------------------------------------- speaking

    def speak(self, text: str, style: VoiceStyle | None = None) -> bytes:
        """Read a reply aloud. Long replies are trimmed at a sentence break."""

        if not self.enabled:
            raise SpeechError("Tính năng giọng nói đang tắt.")
        spoken = shorten_for_speech(text)
        if not spoken:
            raise SpeechError("Không có nội dung để đọc.")

        style = style or VOICE_STYLES["mid"]
        response = self._retry(
            lambda: self._client.audio.speech.create(
                model=self.settings.tts_model,
                voice=style.voice,
                input=spoken,
                instructions=style.instructions,
            )
        )
        audio = response.read() if hasattr(response, "read") else bytes(response)
        if not audio:
            raise SpeechError("Không nhận được âm thanh từ máy chủ.")
        return audio


def transcription_prompt(kb: Any = None) -> str:
    """Domain vocabulary to steer transcription.

    Insurance terms and scheme abbreviations are the words a general model is
    most likely to mangle, and they come straight from the knowledge base so
    the hint never drifts from the catalog.
    """

    if kb is None:
        from core.kb import KnowledgeBase

        kb = KnowledgeBase.load()

    terms: list[str] = ["BHXH", "BHTN", "BHYT", "bảo hiểm xã hội tự nguyện"]
    terms += [str(item["short_vi"]) for item in kb.section("insurance_types")]
    terms += [str(item["term"]) for item in kb.section("glossary")]
    terms += [
        str(item["product_name"])
        for item in kb.section("products")
        if not item.get("is_reference")
    ]

    seen: list[str] = []
    for term in terms:
        if term and term not in seen:
            seen.append(term)
    return (
        "Cuộc trò chuyện tư vấn bảo hiểm bằng tiếng Việt. "
        "Các từ có thể xuất hiện: " + ", ".join(seen) + "."
    )


def shorten_for_speech(text: str, limit: int = MAX_SPEAK_CHARS) -> str:
    """Trim to `limit`, cutting at the last sentence end rather than mid-word."""

    spoken = " ".join(text.split())
    if len(spoken) <= limit:
        return spoken
    window = spoken[:limit]
    cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if cut > limit // 2:
        return window[: cut + 1]
    return window.rsplit(" ", 1)[0] + "…"
