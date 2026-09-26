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
