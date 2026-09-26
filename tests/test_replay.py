"""Recorded sessions must replay with no API key and no network."""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from core.session_io import Recording

DATA = Path(__file__).resolve().parents[1] / "data"
PERSONAS = ("vuong", "mai", "duc")


@pytest.fixture(scope="module")
def expected() -> dict[str, dict]:
    return yaml.safe_load((DATA / "expected.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module", params=PERSONAS)
def recording(request: pytest.FixtureRequest) -> Recording:
    return Recording.load(request.param)


def test_every_persona_has_a_recording() -> None:
    assert set(PERSONAS) <= set(Recording.available())


def test_replay_loads_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    for persona_id in PERSONAS:
        assert Recording.load(persona_id).messages


def test_recording_reached_the_comparison(recording: Recording) -> None:
    assert recording.data["state"] in {"FOLLOW_UP", "CLOSING"}
    assert recording.ranking
    assert recording.data["type_decision"] is not None


def test_recording_matches_expected_outcome(recording: Recording, expected: dict[str, dict]) -> None:
    want = expected[recording.persona_id]
    assert recording.data["insurance_type"] == want["insurance_type"]
    assert recording.ranking[0]["product_id"] == want["top_product_id"]


def test_recording_is_a_real_conversation(recording: Recording) -> None:
    """A replay must contain the discovery turns, not just a canned result."""

    messages = recording.messages
    customer_turns = [item for item in messages if item.role == "customer"]
    questions = [item for item in messages if item.role == "assistant" and item.content.rstrip().endswith("?")]
    assert len(customer_turns) >= 5
    assert len(questions) >= 5


def test_every_known_field_has_a_quote(recording: Recording) -> None:
    profile = recording.profile
    known = {
        key
        for key, value in profile.model_dump(exclude={"provenance"}).items()
        if value not in (None, [], {})
    }
    inferred = {"risk_tolerance", "need_flexibility", "trust_concern"}
    assert (known - inferred) <= set(profile.provenance)


def test_weights_and_scores_were_recorded(recording: Recording) -> None:
    assert sum(recording.data["weights"].values()) == pytest.approx(100)
    assert len(recording.data["priority_criteria"]) == 2
    for item in recording.ranking:
        assert set(item["scores"]) == {"C1", "C2", "C3", "C4", "C5", "C6"}
        assert 0 <= item["fit_score"] <= 100


def test_ranking_is_ordered(recording: Recording) -> None:
    scores = [item["fit_score"] for item in recording.ranking]
    assert scores == sorted(scores, reverse=True)


def test_why_ask_is_available_for_replay(recording: Recording) -> None:
    assert recording.data["why_ask"]
