"""A3 rephrases a question-bank template without changing its scope.

A3 may adjust wording and tone but must not drop a target, add a new one, or
introduce a product, an insurance type or a number.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from core.llm import LumiOpenAIClient


class ConversationAgent:
    def __init__(self, client: LumiOpenAIClient) -> None:
        self.client = client
        self.instructions = (
            Path(__file__).resolve().parents[1] / "prompts" / "conversation.md"
        ).read_text(encoding="utf-8")

    @staticmethod
    def render_template(template: str, address: dict[str, str]) -> str:
        """Fill {bot}/{Bot}/{kh}/{Kh}/{a} from question_bank.address_fill."""

        try:
            return template.format(**address)
        except KeyError:
            return template

    def _payload(self, **parts: Any) -> str:
        return json.dumps(parts, ensure_ascii=False)

    def write_question(
        self,
        *,
        template: str,
        targets: list[str],
        address: dict[str, str],
        tone: str = "",
        why_ask: str | None = None,
    ) -> str:
        """Blocking variant used by the CLI and by Auto mode."""

        try:
            return "".join(
                self.stream_question(
                    template=template, targets=targets, address=address, tone=tone, why_ask=why_ask
                )
            ).strip()
        except Exception:
            return template

    def stream_question(
        self,
        *,
        template: str,
        targets: list[str],
        address: dict[str, str],
        tone: str = "",
        why_ask: str | None = None,
    ) -> Iterator[str]:
        return self.client.stream_text(
            instructions=self.instructions,
            input_text=self._payload(
                template=template,
                targets=targets,
                address=address,
                tone=tone,
                why_ask=why_ask,
            ),
            reasoning_effort="none",
        )
