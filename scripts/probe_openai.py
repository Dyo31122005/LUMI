"""Probe gpt-5.6-luna through the Responses API before building LUMI agents."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.llm import (  # noqa: E402
    LumiOpenAIClient,
    ModelConfigurationError,
    format_probe_result,
)


class ProbeAdvice(BaseModel):
    """Strict schema used only to verify the API gateway."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(description="Một câu tư vấn tiếng Việt, không có con số.")
    caution: str = Field(description="Một câu nhắc đây chỉ là thông tin tham khảo.")


def main() -> int:
    # PowerShell on Windows may default to a legacy code page that cannot print
    # Vietnamese output returned by the model.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    try:
        client = LumiOpenAIClient()
        for effort in ("none", "low", "medium"):
            started_at = time.perf_counter()
            result = client.structured_response(
                instructions=(
                    "Bạn là LUMI, trợ lý tư vấn bảo hiểm bằng tiếng Việt. "
                    "Chỉ trả về JSON đúng schema. Không đề xuất sản phẩm, không dùng con số."
                ),
                input_text=(
                    "Một người mới đi làm muốn hiểu vì sao cần làm rõ nhu cầu "
                    "trước khi xem bảo hiểm. Hãy trả lời ngắn gọn."
                ),
                schema=ProbeAdvice,
                schema_name="lumi_probe_advice",
                reasoning_effort=effort,
            )
            elapsed_ms = round((time.perf_counter() - started_at) * 1000)
            print(f"reasoning={effort} latency_ms={elapsed_ms} output={format_probe_result(result)}")
    except ModelConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    except Exception as error:  # API errors must be visible to the project owner.
        print(f"OpenAI probe failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
