import pytest

from agents.conversation import ConversationAgent
from agents.extractor import ExtractedField, ExtractionResult, ProfileExtractor, to_json_value
from core.kb import KnowledgeBase
from agents.simulator import CustomerSimulator
from core.schemas import Profile


def test_persona_loader_reads_a_known_persona() -> None:
    persona = CustomerSimulator.load_persona("vuong")

    assert persona["address"]["assistant_self"] == "mình"
    assert persona["facts"]["employment_status"] == "job_seeking"


def test_persona_loader_rejects_unknown_persona() -> None:
    with pytest.raises(ValueError, match="Unknown persona"):
        CustomerSimulator.load_persona("nobody")


def test_extractor_converts_only_json_values_to_profile_patch() -> None:
    result = ExtractionResult(
        fields=[
            ExtractedField(
                field="age", value_json="22", quote="mình là Vương, 22 tuổi", confidence=0.99
            )
        ]
    )

    profile = ProfileExtractor.patch_from_result(result, turn_index=1).apply(Profile())

    assert profile.age == 22
    assert profile.provenance["age"].quote == "mình là Vương, 22 tuổi"


def test_question_template_respects_persona_address() -> None:
    """Placeholders are filled from question_bank.rules.address_fill."""

    senior = ConversationAgent.render_template(
        "Cho {bot} hỏi {kh} năm nay bao nhiêu tuổi{a}?",
        {"bot": "cháu", "Bot": "Cháu", "kh": "bác", "Kh": "Bác", "a": " ạ"},
    )
    young = ConversationAgent.render_template(
        "Cho {bot} hỏi {kh} năm nay bao nhiêu tuổi{a}?",
        {"bot": "mình", "Bot": "Mình", "kh": "bạn", "Kh": "Bạn", "a": ""},
    )

    assert senior == "Cho cháu hỏi bác năm nay bao nhiêu tuổi ạ?"
    assert young == "Cho mình hỏi bạn năm nay bao nhiêu tuổi?"


def test_extractor_contract_is_json_serializable() -> None:
    import json

    enum_values = to_json_value(KnowledgeBase.load().section("enums"))

    assert "employment_status" in json.dumps(enum_values, ensure_ascii=False)
