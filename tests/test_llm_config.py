from pathlib import Path

import pytest

from pydantic import BaseModel, ConfigDict

from core.llm import LLMSettings, LUMI_MODEL, LumiOpenAIClient, ModelConfigurationError, load_settings


def write_env(path: Path, *, model: str = LUMI_MODEL) -> None:
    path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=test-key",
                f"MODEL={model}",
                f"MODEL_WRITER={model}",
                "DECISION_ENGINE=openai",
            ]
        ),
        encoding="utf-8",
    )


def test_load_settings_accepts_only_lumi_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    write_env(env_path)
    for name in ("OPENAI_API_KEY", "MODEL", "MODEL_WRITER", "DECISION_ENGINE"):
        monkeypatch.delenv(name, raising=False)

    settings = load_settings(env_path)

    assert settings.model == LUMI_MODEL
    assert settings.writer_model == LUMI_MODEL


def test_load_settings_rejects_another_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    write_env(env_path, model="another-model")
    for name in ("OPENAI_API_KEY", "MODEL", "MODEL_WRITER", "DECISION_ENGINE"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ModelConfigurationError, match="gpt-5.6-luna"):
        load_settings(env_path)


class ProbeSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str


class FakeResponse:
    status = "completed"
    output_text = '{"message": "đúng schema"}'


class FakeResponses:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    def create(self, **request: object) -> FakeResponse:
        self.requests.append(request)
        return FakeResponse()


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_structured_response_locks_model_reasoning_and_schema() -> None:
    fake_client = FakeClient()
    settings = LLMSettings(
        api_key="test-key",
        model=LUMI_MODEL,
        writer_model=LUMI_MODEL,
        decision_engine="openai",
    )
    client = LumiOpenAIClient(settings, client=fake_client)

    response = client.structured_response(
        instructions="JSON only",
        input_text="test",
        schema=ProbeSchema,
        schema_name="probe_schema",
        reasoning_effort="low",
    )

    request = fake_client.responses.requests[0]
    assert response.message == "đúng schema"
    assert request["model"] == LUMI_MODEL
    assert request["reasoning"] == {"effort": "low"}
    assert request["store"] is False
    assert request["text"]["format"]["type"] == "json_schema"  # type: ignore[index]


# ------------------------------------------------- audio models (VOICE-00)


def _base_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("MODEL", LUMI_MODEL)
    monkeypatch.setenv("MODEL_WRITER", LUMI_MODEL)
    monkeypatch.setenv("DECISION_ENGINE", "openai")
    for name in ("MODEL_STT", "MODEL_TTS", "LUMI_VOICE"):
        monkeypatch.delenv(name, raising=False)


def test_audio_models_default_without_configuration(monkeypatch, tmp_path) -> None:
    from core.llm import DEFAULT_STT_MODEL, DEFAULT_TTS_MODEL

    _base_env(monkeypatch)
    settings = load_settings(tmp_path / "absent.env")

    assert settings.stt_model == DEFAULT_STT_MODEL
    assert settings.tts_model == DEFAULT_TTS_MODEL
    assert settings.voice_enabled is True


def test_audio_models_are_overridable(monkeypatch, tmp_path) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("MODEL_STT", "whisper-1")
    monkeypatch.setenv("MODEL_TTS", "tts-1-hd")

    settings = load_settings(tmp_path / "absent.env")

    assert settings.stt_model == "whisper-1"
    assert settings.tts_model == "tts-1-hd"
    # The single-model rule still holds for everything that thinks or writes.
    assert settings.model == LUMI_MODEL
    assert settings.writer_model == LUMI_MODEL


def test_voice_can_be_disabled_by_environment(monkeypatch, tmp_path) -> None:
    _base_env(monkeypatch)
    for value in ("off", "0", "false", "no"):
        monkeypatch.setenv("LUMI_VOICE", value)
        assert load_settings(tmp_path / "absent.env").voice_enabled is False
    for value in ("on", "1", "true", "yes"):
        monkeypatch.setenv("LUMI_VOICE", value)
        assert load_settings(tmp_path / "absent.env").voice_enabled is True


def test_a_meaningless_voice_flag_is_rejected(monkeypatch, tmp_path) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("LUMI_VOICE", "maybe")

    with pytest.raises(ModelConfigurationError):
        load_settings(tmp_path / "absent.env")


def test_whatif_api_limit_is_configurable(monkeypatch, tmp_path) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("LUMI_WHATIF_MAX_ACTIONS", "5")

    assert load_settings(tmp_path / "absent.env").whatif_max_actions == 5


def test_whatif_api_limit_rejects_invalid_values(monkeypatch, tmp_path) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("LUMI_WHATIF_MAX_ACTIONS", "many")

    with pytest.raises(ModelConfigurationError):
        load_settings(tmp_path / "absent.env")


def test_audio_settings_do_not_relax_the_chat_model_rule(monkeypatch, tmp_path) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("MODEL_WRITER", "gpt-4o")

    with pytest.raises(ModelConfigurationError):
        load_settings(tmp_path / "absent.env")
