"""Read-only access to the LUMI knowledge base."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

REQUIRED_SECTIONS = frozenset(
    {
        "meta",
        "enums",
        "insurance_types",
        "decision_questions",
        "scoring",
        "comparison_rows",
        "products",
        "regulations",
        "finance",
        "glossary",
        "faq",
        "writing_rules",
        "profile_schema",
        "question_bank",
    }
)
REQUIRED_META_FIELDS = frozenset({"version", "currency", "disclaimer"})


class KnowledgeBaseError(ValueError):
    """Raised when the source YAML does not meet the LUMI data contract."""


KB_FILENAME = "lumi_knowledge_base.yaml"


def kb_path_candidates() -> list[Path]:
    """Where the knowledge base may live, most specific first.

    Local development keeps one copy at the repository root. A deployment that
    only ships `lumi/` needs it inside the app, and `LUMI_KB_PATH` overrides
    both.
    """

    app_root = Path(__file__).resolve().parents[1]
    candidates: list[Path] = []
    override = os.getenv("LUMI_KB_PATH", "").strip()
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(app_root / "data" / KB_FILENAME)
    candidates.append(app_root.parent / "data" / KB_FILENAME)
    return candidates


def default_kb_path() -> Path:
    for candidate in kb_path_candidates():
        if candidate.is_file():
            return candidate
    return kb_path_candidates()[-1]


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


class KnowledgeBase:
    """Validated, immutable view of the YAML used by every LUMI agent."""

    def __init__(self, data: Mapping[str, Any], source_path: Path) -> None:
        self._validate(data, source_path)
        self._data: Mapping[str, Any] = _freeze(dict(data))
        self.source_path = source_path

    @classmethod
    def load(cls, source_path: Path | None = None) -> "KnowledgeBase":
        path = source_path or default_kb_path()
        if not path.is_file():
            raise KnowledgeBaseError(f"Knowledge base not found: {path}")

        with path.open("r", encoding="utf-8") as source_file:
            data = yaml.safe_load(source_file)
        if not isinstance(data, dict):
            raise KnowledgeBaseError("Knowledge base root must be a YAML mapping.")
        return cls(data, path)

    @property
    def meta(self) -> Mapping[str, Any]:
        return self.section("meta")

    def section(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError as error:
            raise KnowledgeBaseError(f"Unknown knowledge base section: {name}") from error

    @staticmethod
    def _validate(data: Mapping[str, Any], source_path: Path) -> None:
        missing = REQUIRED_SECTIONS.difference(data)
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise KnowledgeBaseError(
                f"Knowledge base {source_path} is missing section(s): {missing_list}"
            )

        meta = data["meta"]
        if not isinstance(meta, dict):
            raise KnowledgeBaseError("Knowledge base meta must be a mapping.")
        missing_meta = REQUIRED_META_FIELDS.difference(meta)
        if missing_meta:
            missing_list = ", ".join(sorted(missing_meta))
            raise KnowledgeBaseError(
                f"Knowledge base meta is missing field(s): {missing_list}"
            )
        if not isinstance(meta["version"], str) or not meta["version"].strip():
            raise KnowledgeBaseError("Knowledge base meta.version must be a non-empty string.")
        if meta["currency"] != "VND":
            raise KnowledgeBaseError("Knowledge base meta.currency must be VND.")
        if not isinstance(meta["disclaimer"], str) or not meta["disclaimer"].strip():
            raise KnowledgeBaseError("Knowledge base meta.disclaimer must be a non-empty string.")
