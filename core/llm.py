"""Cổng gọi OpenAI Responses API cho LUMI.

Mọi agent đều dùng duy nhất gpt-5.6-luna. Các lớp nghiệp vụ ở các task sau
sẽ dùng lại client và hàm Structured Outputs trong file này.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Literal, TypeVar

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError
from pydantic import BaseModel

LUMI_MODEL = "gpt-5.6-luna"

# Speech is the one deliberate exception to the single-model rule in the build
# plan: transcription and speech synthesis cannot be done by the conversation
# model. Every agent that thinks or writes still uses LUMI_MODEL alone.
DEFAULT_STT_MODEL = "gpt-4o-transcribe"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE_MAX_ACTIONS = 20

ReasoningEffort = Literal["none", "low", "medium"]
SchemaT = TypeVar("SchemaT", bound=BaseModel)


class ModelConfigurationError(RuntimeError):
    """Raised when the local OpenAI configuration does not meet LUMI rules."""


@dataclass(frozen=True)
class LLMSettings:
    api_key: str
    model: str
    writer_model: str
    decision_engine: Literal["openai", "rule"]
    stt_model: str = DEFAULT_STT_MODEL
    tts_model: str = DEFAULT_TTS_MODEL
    voice_enabled: bool = True
    # A ceiling per visitor, so one session cannot run up the bill on a
    # public deployment. Spending limits at OpenAI are the last line, not
    # the first.
    voice_max_actions: int = DEFAULT_VOICE_MAX_ACTIONS


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "on", "yes"}:
        return True
    if raw in {"0", "false", "off", "no"}:
        return False
    raise ModelConfigurationError(f"{name} must be on or off.")


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ModelConfigurationError(f"{name} must be a whole number.") from error
    if value < 0:
        raise ModelConfigurationError(f"{name} must not be negative.")
    return value


def load_settings(env_path: Path | None = None) -> LLMSettings:
    """Load local configuration without ever logging the API key."""

    if env_path is None:
        env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("MODEL", "").strip()
    writer_model = os.getenv("MODEL_WRITER", "").strip()
    decision_engine = os.getenv("DECISION_ENGINE", "openai").strip().lower()

    if not api_key:
        raise ModelConfigurationError("OPENAI_API_KEY is missing in lumi/.env.")
    if model != LUMI_MODEL or writer_model != LUMI_MODEL:
        raise ModelConfigurationError(
            "LUMI requires MODEL and MODEL_WRITER to be gpt-5.6-luna."
        )
    if decision_engine not in {"openai", "rule"}:
        raise ModelConfigurationError("DECISION_ENGINE must be openai or rule.")

    return LLMSettings(
        api_key=api_key,
        model=model,
        writer_model=writer_model,
        decision_engine=decision_engine,  # type: ignore[arg-type]
        stt_model=os.getenv("MODEL_STT", "").strip() or DEFAULT_STT_MODEL,
        tts_model=os.getenv("MODEL_TTS", "").strip() or DEFAULT_TTS_MODEL,
        # A public deployment carries a real key, so voice must be switchable
        # off without touching code.
        voice_enabled=_flag("LUMI_VOICE", default=True),
        voice_max_actions=_positive_int("LUMI_VOICE_MAX_ACTIONS", DEFAULT_VOICE_MAX_ACTIONS),
    )


def strict_json_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Adapt a Pydantic schema to OpenAI strict Structured Outputs.

    Strict mode requires every property to appear in `required` and every
    object to forbid extra properties; Pydantic omits fields that have
    defaults, so they are added back here (optional ones stay nullable).
    """

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node

        result = {key: walk(value) for key, value in node.items()}
        if result.get("type") == "object" and "properties" in result:
            result["required"] = list(result["properties"])
            result["additionalProperties"] = False
        return result

    return walk(schema.model_json_schema())


class LumiOpenAIClient:
    """Thin, testable wrapper around the Responses API."""

    def __init__(
        self, settings: LLMSettings | None = None, *, client: Any | None = None, max_attempts: int = 2
    ) -> None:
        self.settings = settings or load_settings()
        self._client = client or OpenAI(api_key=self.settings.api_key)
        self.max_attempts = max_attempts

    def _create_with_retry(self, **request: Any) -> Any:
        """Retry only transient OpenAI failures and keep attempts bounded."""

        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._client.responses.create(**request)
            except (APIConnectionError, RateLimitError, APIStatusError):
                if attempt == self.max_attempts:
                    raise
                time.sleep(0.4 * attempt)
        raise RuntimeError("OpenAI retry loop ended unexpectedly.")

    def structured_response(
        self,
        *,
        instructions: str,
        input_text: str,
        schema: type[SchemaT],
        schema_name: str,
        reasoning_effort: ReasoningEffort,
    ) -> SchemaT:
        """Request a strict JSON-schema response and validate it locally."""

        response = self._create_with_retry(
            model=self.settings.model,
            reasoning={"effort": reasoning_effort},
            instructions=instructions,
            input=input_text,
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": strict_json_schema(schema),
                }
            },
            store=False,
        )
        if response.status != "completed" or not response.output_text:
            raise RuntimeError(
                f"OpenAI response did not complete: status={response.status!r}."
            )
        return schema.model_validate_json(response.output_text)

    def stream_text(
        self,
        *,
        instructions: str,
        input_text: str,
        reasoning_effort: ReasoningEffort,
    ) -> Iterator[str]:
        """Yield text deltas for A3/A4, with the same model and retry policy."""

        request = {
            "model": self.settings.writer_model,
            "reasoning": {"effort": reasoning_effort},
            "instructions": instructions,
            "input": input_text,
            "stream": True,
            "store": False,
        }
        for attempt in range(1, self.max_attempts + 1):
            try:
                stream = self._client.responses.create(**request)
                for event in stream:
                    if getattr(event, "type", None) == "response.output_text.delta":
                        yield event.delta
                return
            except (APIConnectionError, RateLimitError, APIStatusError):
                if attempt == self.max_attempts:
                    raise
                time.sleep(0.4 * attempt)


def format_probe_result(result: BaseModel) -> str:
    """Return safe UTF-8 JSON for terminal output; no credentials are included."""

    return json.dumps(result.model_dump(), ensure_ascii=False)
