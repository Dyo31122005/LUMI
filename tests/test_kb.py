from pathlib import Path

import pytest

from core.kb import KnowledgeBase, KnowledgeBaseError, REQUIRED_SECTIONS, default_kb_path


def test_loads_the_project_knowledge_base() -> None:
    knowledge_base = KnowledgeBase.load()

    assert knowledge_base.source_path == default_kb_path()
    assert knowledge_base.meta["currency"] == "VND"
    assert set(REQUIRED_SECTIONS).issubset(
        {name for name in REQUIRED_SECTIONS if knowledge_base.section(name) is not None}
    )


def test_loaded_data_is_immutable() -> None:
    knowledge_base = KnowledgeBase.load()

    with pytest.raises(TypeError):
        knowledge_base.meta["version"] = "changed"  # type: ignore[index]


def test_missing_required_section_has_a_clear_error(tmp_path: Path) -> None:
    broken_path = tmp_path / "broken.yaml"
    broken_path.write_text(
        "meta:\n  version: '1'\n  currency: VND\n  disclaimer: test\n",
        encoding="utf-8",
    )

    with pytest.raises(KnowledgeBaseError, match="missing section"):
        KnowledgeBase.load(broken_path)


def test_knowledge_base_is_bundled_inside_the_app() -> None:
    """A deployment ships only this folder, so the KB must live in it."""

    from pathlib import Path

    from core.kb import KB_FILENAME, default_kb_path

    bundled = Path(__file__).resolve().parents[1] / "data" / KB_FILENAME
    assert bundled.is_file(), "Thiếu data/lumi_knowledge_base.yaml — deploy sẽ hỏng."
    assert default_kb_path() == bundled


def test_kb_path_can_be_overridden_by_environment(monkeypatch, tmp_path) -> None:
    from core.kb import default_kb_path, kb_path_candidates

    target = tmp_path / "custom.yaml"
    target.write_text("meta: {}", encoding="utf-8")
    monkeypatch.setenv("LUMI_KB_PATH", str(target))
    assert kb_path_candidates()[0] == target
    assert default_kb_path() == target
