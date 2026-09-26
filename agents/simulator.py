"""LLM customer simulator used exclusively by Auto mode."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from core.llm import LumiOpenAIClient


class SimulatorReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply: str = Field(min_length=1, max_length=500)


class CustomerSimulator:
    def __init__(self, persona_id: str, client: LumiOpenAIClient) -> None:
        self.persona = self.load_persona(persona_id)
        self.client = client

    @staticmethod
    def load_persona(persona_id: str) -> dict[str, Any]:
        path = Path(__file__).resolve().parents[1] / "data" / "personas" / f"{persona_id}.yaml"
        if not path.is_file():
            raise ValueError(f"Unknown persona: {persona_id}")
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def reply(self, question: str, history: list[dict[str, str]]) -> str:
        instructions = (Path(__file__).resolve().parents[1] / "prompts" / "simulator.md").read_text(
            encoding="utf-8"
        )
        input_text = json.dumps(
            {"persona": self.persona, "question": question, "history": history[-4:]}, ensure_ascii=False
        )
        return self.client.structured_response(
            instructions=instructions,
            input_text=input_text,
            schema=SimulatorReply,
            schema_name="lumi_simulator_reply",
            reasoning_effort="none",
        ).reply
