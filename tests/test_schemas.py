import pytest
from pydantic import ValidationError

from core.schemas import Profile, ProfilePatch, TurnDecision


def test_profile_patch_validates_a_kb_enum_and_keeps_provenance() -> None:
    patch = ProfilePatch.model_validate_json(
        '''{
          "updates": {"employment_status": "job_seeking"},
          "provenance": {
            "employment_status": {
              "quote": "Em đang tìm việc.", "confidence": 0.98, "turn_index": 1
            }
          }
        }'''
    )

    profile = patch.apply(Profile())

    assert profile.employment_status == "job_seeking"
    assert profile.provenance["employment_status"].turn_index == 1


def test_profile_rejects_an_enum_value_outside_the_knowledge_base() -> None:
    with pytest.raises(ValidationError):
        Profile.model_validate({"employment_status": "unknown_job"})


def test_turn_decision_rejects_an_unknown_topic() -> None:
    with pytest.raises(ValidationError):
        TurnDecision.model_validate(
            {
                "next_topic": "invent_a_topic",
                "next_topic_reason": "test",
                "risk_tolerance": "Unknown",
                "need_flexibility": "Unknown",
                "trust_concern": "Unknown",
                "insurance_type": "life",
                "type_probabilities": {
                    "unemployment": 0.1,
                    "retirement": 0.2,
                    "life": 0.6,
                    "health": 0.1,
                },
                "confidence": 0.6,
                "customer_intent": "ask_question",
            }
        )
