"""State machine behaviour, exercised offline with stand-in agents."""

from __future__ import annotations

from typing import Any

import pytest

from core.decision import RuleEngine
from core.kb import KnowledgeBase
from core.orchestrator import ConversationState, Orchestrator, address_context
from core.schemas import Profile, ProfilePatch, Provenance, TurnDecision, TypeDecision, TypeProbabilities


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase.load()


class ScriptedExtractor:
    """Returns one prepared patch per customer turn."""

    def __init__(self, patches: list[dict[str, Any]]) -> None:
        self.patches = patches
        self.calls = 0

    def extract(self, message: str, profile: Profile, turn_index: int) -> ProfilePatch:
        updates = self.patches[min(self.calls, len(self.patches) - 1)]
        self.calls += 1
        return ProfilePatch(
            updates=dict(updates),
            provenance={key: Provenance(quote=message[:40] or "…", confidence=0.9, turn_index=turn_index) for key in updates},
        )


class TemplateConversation:
    @staticmethod
    def render_template(template: str, address: dict[str, str]) -> str:
        try:
            return template.format(**address)
        except KeyError:
            return template

    def write_question(self, *, template: str, **_: object) -> str:
        return template


class StubWriter:
    def write_step_one(self, **kwargs: Any) -> str:
        return f"Bước 1: đề xuất {kwargs['decision'].insurance_type}."

    def write_step_two(self, **kwargs: Any) -> str:
        return f"Bước 2: đứng đầu là {kwargs['ranked'][0].product['product_name']}."

    def write_no_products(self, **_: Any) -> str:
        return "Bước 2: chưa có sản phẩm nào phù hợp."

    def write_follow_up(self, **kwargs: Any) -> str:
        return f"Trả lời thêm: {kwargs['question']}"

    def write_closing(self, **_: Any) -> str:
        return "Lời kết: cảm ơn bạn."


class FakeSimulator:
    def __init__(self, replies: list[str]) -> None:
        self.persona = {
            "address": {"assistant_self": "mình", "customer": "Vương", "tone": "thân mật"},
            "opening": "mình 22 tuổi, mới tốt nghiệp và đang tìm việc",
        }
        self.replies = replies
        self.calls = 0

    def reply(self, question: str, history: list[dict[str, str]]) -> str:
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return reply


VUONG_PATCHES = [
    {"age": 22, "employment_status": "job_seeking", "primary_concerns": ["job_loss"]},
    {"monthly_income": 3_000_000, "income_stability": "low"},
    {"debts": [{"type": "laptop", "monthly": 1_200_000, "remaining_months": 10}]},
    {"bhtn_months": 0, "has_employment_contract": False},
    {"budget_monthly": 150_000, "goals": "cầm cự vài tháng"},
]


def build(kb: KnowledgeBase, patches: list[dict[str, Any]], replies: list[str]) -> Orchestrator:
    return Orchestrator(
        knowledge_base=kb,
        extractor=ScriptedExtractor(patches),  # type: ignore[arg-type]
        conversation=TemplateConversation(),  # type: ignore[arg-type]
        engine=RuleEngine(kb),
        writer=StubWriter(),  # type: ignore[arg-type]
        simulator=FakeSimulator(replies),  # type: ignore[arg-type]
    )


# ------------------------------------------------------------------- basics


def test_state_names_match_the_planned_state_machine() -> None:
    assert [state.value for state in ConversationState] == [
        "GREETING", "DISCOVERY", "RECOMMEND_TYPE", "CONFIRM", "COMPARE", "FOLLOW_UP", "CLOSING",
    ]


def test_greeting_is_identical_for_every_customer(kb: KnowledgeBase) -> None:
    orchestrator = build(kb, VUONG_PATCHES, ["ừ"])
    session = orchestrator.new_session("vuong", {"assistant_self": "mình", "customer": "Vương"})
    assert orchestrator.greeting(session) == kb.section("question_bank")["opening"]["template"]
    assert session.state is ConversationState.DISCOVERY


def test_address_style_follows_age(kb: KnowledgeBase) -> None:
    young = address_context(Profile(age=22), {}, kb)
    senior = address_context(Profile(age=60), {}, kb)
    assert young["bot"] == "mình"
    assert senior["bot"] == "cháu"
    assert senior["kh"] == "bác"


# ---------------------------------------------------------------- discovery


def test_questions_are_never_repeated(kb: KnowledgeBase) -> None:
    orchestrator = build(kb, VUONG_PATCHES, ["ừ"] * 10)
    session = orchestrator.run_auto("vuong")
    asked = [message.content for message in session.messages if message.role == "assistant"]
    questions = [item for item in asked if item.endswith("?")]
    assert len(questions) == len(set(questions))


def test_discovery_stops_at_the_question_limit(kb: KnowledgeBase) -> None:
    # A patch that never fills anything would otherwise loop forever.
    orchestrator = build(kb, [{}], ["vẫn thế"] * 20)
    session = orchestrator.run_auto("vuong")
    assert session.question_count <= kb.section("question_bank")["rules"]["max_questions"]


def test_every_extracted_field_keeps_its_quote(kb: KnowledgeBase) -> None:
    orchestrator = build(kb, VUONG_PATCHES, ["ừ"] * 10)
    session = orchestrator.run_auto("vuong")
    known = session.profile.model_dump(exclude={"provenance"})
    filled = {key for key, value in known.items() if value not in (None, [], {})}
    # Attitudes come from D2, not from a customer sentence.
    inferred = {"risk_tolerance", "need_flexibility", "trust_concern"}
    assert (filled - inferred) <= set(session.profile.provenance)


def test_why_ask_is_recorded_for_each_question(kb: KnowledgeBase) -> None:
    orchestrator = build(kb, VUONG_PATCHES, ["ừ"] * 10)
    session = orchestrator.run_auto("vuong")
    questions = [
        index
        for index, message in enumerate(session.messages)
        if message.role == "assistant" and message.content.endswith("?") and index > 0
    ]
    assert questions
    assert all(index in session.why_ask for index in questions)


# ------------------------------------------------------------- step 1 and 2


def test_step_two_waits_for_agreement(kb: KnowledgeBase) -> None:
    """Build plan §9.6: the comparison only runs after D4 reads agreement."""

    orchestrator = build(kb, VUONG_PATCHES, ["ừ"] * 10)
    session = orchestrator.new_session("vuong", {"assistant_self": "mình", "customer": "Vương"})
    session.profile = Profile(
        age=22, employment_status="job_seeking", primary_concerns=["job_loss"],
        monthly_income=3_000_000, income_stability="low", budget_monthly=150_000, bhtn_months=0,
    )
    orchestrator.recommend_type(session)
    assert session.state is ConversationState.CONFIRM
    assert not session.ranked

    class Undecided(RuleEngine):
        def decide_turn(self, profile, derived=None, context=None) -> TurnDecision:  # type: ignore[override]
            decision = super().decide_turn(profile, derived, context)
            return decision.model_copy(update={"customer_intent": "ask_question"})

    orchestrator.engine = Undecided(kb)
    orchestrator.handle_customer_message(session, "cho mình hỏi thêm đã")
    assert not session.ranked

    class Agrees(RuleEngine):
        def decide_turn(self, profile, derived=None, context=None) -> TurnDecision:  # type: ignore[override]
            decision = super().decide_turn(profile, derived, context)
            return decision.model_copy(update={"customer_intent": "agree_continue"})

    orchestrator.engine = Agrees(kb)
    session.state = ConversationState.CONFIRM
    orchestrator.handle_customer_message(session, "ok bạn so sánh giúp mình")
    assert session.ranked
    assert session.ranked[0].product_id == "ta_genz"


def test_low_confidence_triggers_a_disambiguation_question(kb: KnowledgeBase) -> None:
    class Unsure(RuleEngine):
        def decide_type(self, profile, derived=None) -> TypeDecision:  # type: ignore[override]
            return TypeDecision(
                insurance_type="retirement",
                type_probabilities=TypeProbabilities(unemployment=0.4, retirement=0.4, life=0.1, health=0.1),
                confidence=0.4,
                reasons=["Chưa rõ"],
            )

    orchestrator = build(kb, VUONG_PATCHES, ["ừ"])
    orchestrator.engine = Unsure(kb)
    session = orchestrator.new_session("vuong", {"assistant_self": "mình", "customer": "Vương"})
    session.profile = Profile(age=22, employment_status="job_seeking", primary_concerns=["job_loss"])

    text = orchestrator.recommend_type(session)
    assert session.state is ConversationState.DISCOVERY
    assert session.type_decision is None
    assert "?" in text


def test_no_eligible_product_produces_an_explanation_not_a_pick(kb: KnowledgeBase) -> None:
    orchestrator = build(kb, VUONG_PATCHES, ["ừ"])
    session = orchestrator.new_session("vuong", {"assistant_self": "mình", "customer": "Vương"})
    session.profile = Profile(age=22, employment_status="job_seeking", primary_concerns=["job_loss"], budget_monthly=1_000)
    session.type_decision = RuleEngine(kb).decide_type(session.profile)
    text = orchestrator.compare_products(session)
    assert not session.ranked
    assert "chưa có sản phẩm" in text.lower()
    assert session.excluded


# --------------------------------------------------------------- end to end


def test_full_offline_run_reaches_a_ranked_comparison(kb: KnowledgeBase) -> None:
    class Agreeable(RuleEngine):
        def decide_turn(self, profile, derived=None, context=None) -> TurnDecision:  # type: ignore[override]
            decision = super().decide_turn(profile, derived, context)
            message = (context or {}).get("last_customer_message", "")
            intent = "agree_continue" if "so sánh" in message else "add_or_correct_info"
            return decision.model_copy(update={"customer_intent": intent})

    orchestrator = build(kb, VUONG_PATCHES, ["ừ mình kể tiếp"] * 6 + ["ok bạn so sánh giúp mình"] * 4)
    orchestrator.engine = Agreeable(kb)
    session = orchestrator.run_auto("vuong")

    assert session.type_decision is not None
    assert session.type_decision.insurance_type == "unemployment"
    assert session.ranked and session.ranked[0].product_id == "ta_genz"
    assert session.weights and sum(session.weights.values()) == pytest.approx(100)
    assert session.scenario is not None


# ------------------------------------------------------------- follow-up


def _intent_engine(kb: KnowledgeBase, intent: str) -> RuleEngine:
    class Fixed(RuleEngine):
        def decide_turn(self, profile, derived=None, context=None) -> TurnDecision:  # type: ignore[override]
            return super().decide_turn(profile, derived, context).model_copy(
                update={"customer_intent": intent}
            )

    return Fixed(kb)


def _session_past_step_two(kb: KnowledgeBase):
    orchestrator = build(kb, VUONG_PATCHES, ["ừ"])
    orchestrator.engine = _intent_engine(kb, "agree_continue")
    session = orchestrator.new_session("vuong", {"assistant_self": "mình", "customer": "Vương"})
    session.profile = Profile(
        age=22, employment_status="job_seeking", primary_concerns=["job_loss"],
        monthly_income=3_000_000, budget_monthly=150_000, bhtn_months=0,
    )
    orchestrator.recommend_type(session)
    orchestrator.handle_customer_message(session, "ok so sánh giúp mình")
    assert session.state is ConversationState.FOLLOW_UP
    return orchestrator, session


def test_customer_can_keep_asking_after_the_comparison(kb: KnowledgeBase) -> None:
    """The 8-question budget caps LUMI's questions, never the customer's."""

    orchestrator, session = _session_past_step_two(kb)
    orchestrator.engine = _intent_engine(kb, "ask_question")

    for index in range(1, 6):
        reply = orchestrator.handle_customer_message(session, f"cho mình hỏi thêm {index}")
        assert reply, f"LUMI phải trả lời câu hỏi thứ {index}"
        assert session.state is ConversationState.FOLLOW_UP

    answers = [item for item in session.messages if item.content.startswith("Trả lời thêm:")]
    assert len(answers) == 5


def test_follow_up_ends_only_when_the_customer_says_so(kb: KnowledgeBase) -> None:
    orchestrator, session = _session_past_step_two(kb)
    orchestrator.engine = _intent_engine(kb, "end_conversation")

    reply = orchestrator.handle_customer_message(session, "thôi mình dừng ở đây")

    assert session.state is ConversationState.CLOSING
    assert reply and "Lời kết" in reply


def test_a_closed_session_still_answers_rather_than_going_silent(kb: KnowledgeBase) -> None:
    orchestrator, session = _session_past_step_two(kb)
    orchestrator.engine = _intent_engine(kb, "end_conversation")
    orchestrator.handle_customer_message(session, "thôi nhé")

    orchestrator.engine = _intent_engine(kb, "ask_question")
    reply = orchestrator.handle_customer_message(session, "à khoan, cho mình hỏi lại")

    assert reply, "Khách nhắn tiếp sau lời kết vẫn phải được trả lời"
    assert session.state is ConversationState.FOLLOW_UP
