"""Conversation state machine: GREETING → … → CLOSING.

The orchestrator owns every transition and every number. Agents contribute
language (A1, A3, A4) and categorical decisions (A2); ranking and money come
from `scoring` and `finance`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from agents.conversation import ConversationAgent
from agents.extractor import ProfileExtractor
from agents.simulator import CustomerSimulator
from agents.writer import AdvisorWriter
from core import finance, scoring
from core.decision import RuleEngine
from core.finance import Scenario
from core.kb import KnowledgeBase
from core.schemas import ChatMessage, InsightFlag, Profile, ProductScores, TurnDecision, TypeDecision


class ConversationState(StrEnum):
    GREETING = "GREETING"
    DISCOVERY = "DISCOVERY"
    RECOMMEND_TYPE = "RECOMMEND_TYPE"
    CONFIRM = "CONFIRM"
    COMPARE = "COMPARE"
    FOLLOW_UP = "FOLLOW_UP"
    CLOSING = "CLOSING"


@dataclass
class ConsultationSession:
    persona_id: str | None
    address: dict[str, str]
    profile: Profile = field(default_factory=Profile)
    state: ConversationState = ConversationState.GREETING
    question_count: int = 0
    messages: list[ChatMessage] = field(default_factory=list)
    turn_decisions: list[TurnDecision] = field(default_factory=list)
    type_decision: TypeDecision | None = None
    derived: dict[str, Any] = field(default_factory=dict)
    insights: list[InsightFlag] = field(default_factory=list)
    asked_question_ids: set[str] = field(default_factory=set)
    why_ask: dict[int, str] = field(default_factory=dict)
    ranked: list[scoring.RankedProduct] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)
    weight_reasons: list[str] = field(default_factory=list)
    priority_criteria: list[str] = field(default_factory=list)
    excluded: list[scoring.FilterOutcome] = field(default_factory=list)
    scenario: Scenario | None = None
    disambiguated: bool = False

    @property
    def top_type(self) -> str | None:
        if self.type_decision:
            return self.type_decision.insurance_type
        if self.turn_decisions:
            return self.turn_decisions[-1].insurance_type
        return None


def address_context(profile: Profile, address: dict[str, str], kb: KnowledgeBase) -> dict[str, str]:
    """Placeholders for question templates, following enums.address_styles."""

    age = profile.age or 0
    style = "young" if age and age <= 29 else "senior" if age >= 55 else "mid"
    fill = dict(kb.section("question_bank")["rules"]["address_fill"][style])
    if address.get("assistant_self"):
        fill["bot"] = address["assistant_self"]
        fill["Bot"] = address["assistant_self"].capitalize()
    if address.get("customer"):
        fill["kh"] = address["customer"]
        fill["Kh"] = address["customer"].capitalize()
    elif profile.name and style == "young":
        fill["kh"] = profile.name
        fill["Kh"] = profile.name
    return {key: str(value) for key, value in fill.items()}


def _pair_key(pair: set[str]) -> str:
    """question_bank.disambiguation keys follow the insurance_types order."""

    order = ("unemployment", "retirement", "life", "health")
    return "|".join(sorted(pair, key=order.index))


def _condition_holds(expression: str | None, profile: Profile, top_type: str | None) -> bool:
    """Evaluate a question_bank `ask_if` against the profile.

    The expressions come from the trusted local knowledge base and use only
    comparisons over profile fields, so they are evaluated with no builtins
    and a namespace limited to those fields.
    """

    if not expression:
        return True
    namespace: dict[str, Any] = profile.model_dump(exclude={"provenance"})
    namespace["top_type"] = top_type
    try:
        return bool(eval(expression, {"__builtins__": {}}, namespace))  # noqa: S307
    except Exception:
        return False


class Orchestrator:
    def __init__(
        self,
        *,
        knowledge_base: KnowledgeBase,
        extractor: ProfileExtractor,
        conversation: ConversationAgent,
        engine: Any,
        writer: AdvisorWriter | None = None,
        simulator: CustomerSimulator | None = None,
    ) -> None:
        self.kb = knowledge_base
        self.extractor = extractor
        self.conversation = conversation
        self.engine = engine
        self.writer = writer
        self.simulator = simulator
        self.rules = RuleEngine(knowledge_base)

        bank = knowledge_base.section("question_bank")
        self.questions = {question["id"]: question for question in bank["questions"]}
        self.topic_questions = bank["topic_questions"]
        self.max_questions = int(bank["rules"]["max_questions"])
        self.thresholds = knowledge_base.section("scoring")["thresholds"]

    # ---------------------------------------------------------------- session

    def new_session(self, persona_id: str | None, address: dict[str, str]) -> ConsultationSession:
        return ConsultationSession(persona_id=persona_id, address=address)

    def greeting(self, session: ConsultationSession) -> str:
        opening = self.kb.section("question_bank")["opening"]["template"]
        session.state = ConversationState.DISCOVERY
        self._append(session, "assistant", opening)
        return opening

    # ---------------------------------------------------------------- one turn

    def handle_customer_message(self, session: ConsultationSession, message: str) -> str | None:
        """Run one full turn: A1 → derived fields → A2 (D1–D4) → A3."""

        turn_index = len(session.messages)
        self._append(session, "customer", message)

        patch = self.extractor.extract(message, session.profile, turn_index)
        session.profile = patch.apply(session.profile)
        self._refresh_derived(session)

        decision = self.engine.decide_turn(
            session.profile,
            session.derived,
            {
                "last_bot_message": self._last(session, "assistant"),
                "last_customer_message": message,
                "missing_fields": self._missing_fields(session),
                "missing_for_step2": self._missing_for_step_two(session),
                "questions_left": max(0, self.max_questions - session.question_count),
            },
        )
        session.turn_decisions.append(decision)
        self._apply_attitudes(session, decision)
        session.insights = self.engine.flags(session.profile, session.derived)

        if session.state is ConversationState.CONFIRM:
            return self._handle_confirmation(session, decision)

        if session.state is not ConversationState.DISCOVERY:
            return None

        if self._ready_for_step_one(session, decision):
            return self.recommend_type(session)

        question = self._select_question(session, decision.next_topic)
        if question is None:
            return self.recommend_type(session)
        return self._ask(session, question, decision)

    def _ready_for_step_one(self, session: ConsultationSession, decision: TurnDecision) -> bool:
        """profile_schema.readiness.step1_recommend_type."""

        if session.question_count >= self.max_questions:
            return True
        blocking = self.kb.section("profile_schema")["readiness"]["step1_recommend_type"]["blocking"]
        known = session.profile.model_dump(exclude={"provenance"})
        if any(known.get(key) in (None, [], {}) for key in blocking):
            return False
        if session.derived.get("completeness", 0) >= float(self.thresholds["completeness_min"]):
            return True
        return decision.next_topic == "ready_to_recommend"

    def _topics_for(self, session: ConsultationSession, keys: list[str]) -> list[str]:
        """Which question topics would fill the given profile fields."""

        known = session.profile.model_dump(exclude={"provenance"})
        topics: list[str] = []
        for definition in self.kb.section("profile_schema")["fields"]:
            key = definition["key"]
            if key not in keys or known.get(key) not in (None, [], {}):
                continue
            topic = str(definition.get("topic") or "")
            if topic and topic not in topics:
                topics.append(topic)
        return topics

    def _select_question(self, session: ConsultationSession, topic: str) -> dict[str, Any] | None:
        """Pick the next question.

        Order follows question_bank.rules.selection_flow_vi: blocking fields
        first, then D1's topic, then whatever Bước 2 still needs for the
        leading insurance type, then the fallback order.
        """

        readiness = self.kb.section("profile_schema")["readiness"]
        blocking = self._topics_for(session, list(readiness["step1_recommend_type"]["blocking"]))

        step_two_keys: list[str] = []
        if session.top_type:
            step_two_keys = [
                key
                for key in readiness["step2_compare_products"][session.top_type]
                if not key.startswith("one_of:")
            ]
        needed = self._topics_for(session, step_two_keys)

        order: list[str] = []
        for candidate in [*blocking, topic, *needed, *self.kb.section("decision_questions")["D1"]["fallback_order"]]:
            if candidate and candidate not in order:
                order.append(candidate)

        known = session.profile.model_dump(exclude={"provenance"})
        for candidate in order:
            for question_id in self.topic_questions.get(candidate, ()):
                if question_id in session.asked_question_ids:
                    continue
                question = self.questions[question_id]
                if not any(known.get(target) in (None, [], {}) for target in question["targets"]):
                    continue
                if not _condition_holds(question.get("ask_if"), session.profile, session.top_type):
                    continue
                return dict(question)
        return None

    def _ask(self, session: ConsultationSession, question: dict[str, Any], decision: TurnDecision) -> str:
        address = address_context(session.profile, session.address, self.kb)
        template = self.conversation.render_template(question["template"], address)
        text = self.conversation.write_question(
            template=template,
            targets=list(question["targets"]),
            address=address,
            tone=session.address.get("tone", ""),
            why_ask=question.get("why_ask_vi"),
        ) or template

        session.asked_question_ids.add(str(question["id"]))
        session.question_count += 1
        self._append(session, "assistant", text)
        session.why_ask[len(session.messages) - 1] = self._why_ask(decision)
        return text

    def _why_ask(self, decision: TurnDecision) -> str:
        labels = self.kb.section("decision_questions")["D1"]["topic_labels_vi"]
        template = self.kb.section("decision_questions")["D1"]["ui_explanation_template_vi"]
        probabilities = decision.type_probabilities.model_dump()
        top = max(probabilities, key=lambda key: probabilities[key])
        type_names = {item["id"]: item["short_vi"] for item in self.kb.section("insurance_types")}
        return (
            template.replace("{topic_vi}", str(labels.get(decision.next_topic, decision.next_topic)))
            .replace("{top_type_vi}", str(type_names.get(top, top)))
            .replace("{top_prob}", str(round(probabilities[top] * 100)))
        )

    # ------------------------------------------------------------- step 1 & 2

    def recommend_type(self, session: ConsultationSession) -> str:
        """Bước 1: final D3 at medium reasoning, cross-checked against the rule table."""

        session.state = ConversationState.RECOMMEND_TYPE
        self._refresh_derived(session)
        decision = self.engine.decide_type(session.profile, session.derived)

        cross_check = self.rules.decide_type(session.profile, session.derived)
        threshold = float(self.thresholds["type_confidence_min"])
        unsure = decision.confidence < threshold or decision.insurance_type != cross_check.insurance_type
        # Past the 8-question budget LUMI states an assumption instead of asking again.
        may_ask_again = not session.disambiguated and session.question_count < self.max_questions
        if unsure and may_ask_again:
            question = self._disambiguation_question(session, decision, cross_check)
            if question:
                session.disambiguated = True
                session.state = ConversationState.DISCOVERY
                self._append(session, "assistant", question)
                return question

        session.type_decision = decision
        self._refresh_derived(session)
        session.insights = self.engine.flags(session.profile, session.derived)

        text = self.writer.write_step_one(
            profile=session.profile,
            decision=decision,
            derived=session.derived,
            insights=session.insights,
            address=address_context(session.profile, session.address, self.kb),
        )
        self._append(session, "assistant", text)
        session.state = ConversationState.CONFIRM
        return text

    def _disambiguation_question(
        self, session: ConsultationSession, decision: TypeDecision, cross_check: TypeDecision
    ) -> str | None:
        bank = self.kb.section("question_bank")["disambiguation"]
        candidates = [{decision.insurance_type, cross_check.insurance_type}]
        probabilities = decision.type_probabilities.model_dump()
        candidates.append(set(sorted(probabilities, key=lambda key: -probabilities[key])[:2]))

        template = None
        for pair in candidates:
            if len(pair) != 2:
                continue
            template = bank["by_pair"].get(_pair_key(pair))
            if template:
                break
        if not template:
            return None
        session.question_count += 1
        return self.conversation.render_template(
            str(template), address_context(session.profile, session.address, self.kb)
        )

    def _handle_confirmation(self, session: ConsultationSession, decision: TurnDecision) -> str | None:
        """Bước 2 only runs once D4 reads the customer as agreeing (build plan §9.6)."""

        if decision.customer_intent == "agree_continue":
            return self.compare_products(session)
        if decision.customer_intent == "end_conversation":
            session.state = ConversationState.CLOSING
            return None

        # New information after Bước 1 may reopen discovery, but never past the
        # 8-question budget.
        question = (
            self._select_question(session, decision.next_topic)
            if session.question_count < self.max_questions
            else None
        )
        if question is None:
            session.state = ConversationState.CONFIRM
            return None
        session.state = ConversationState.DISCOVERY
        return self._ask(session, question, decision)

    def compare_products(self, session: ConsultationSession) -> str:
        """Bước 2: hard filters → D5 per product → weights → ranking → A4."""

        assert session.type_decision is not None
        session.state = ConversationState.COMPARE
        insurance_type = session.type_decision.insurance_type

        outcomes = scoring.hard_filter(session.profile, insurance_type, self.kb)
        kept = [outcome for outcome in outcomes if outcome.kept]
        session.excluded = [outcome for outcome in outcomes if not outcome.kept]

        if not kept:
            text = self.writer.write_no_products(
                profile=session.profile,
                excluded=session.excluded,
                address=address_context(session.profile, session.address, self.kb),
            )
            self._append(session, "assistant", text)
            session.state = ConversationState.CLOSING
            return text

        products = [outcome.product for outcome in kept]
        scores = self._score_products(session.profile, products)
        by_id = {item.product_id: item for item in scores}

        weights, reasons = scoring.criterion_weights(session.profile, self._derived_object(session), insurance_type, self.kb)
        session.weights = weights
        session.weight_reasons = reasons
        session.priority_criteria = scoring.priority_criteria(weights, self.kb)

        session.ranked = scoring.rank_products(
            [
                (product, by_id[str(product["id"])].scores, by_id[str(product["id"])].notes.model_dump())
                for product in products
                if str(product["id"]) in by_id
            ],
            weights,
            self.kb,
            filter_notes={outcome.product["id"]: outcome.notes for outcome in kept},
        )
        session.scenario = self._build_scenario(session, insurance_type)

        text = self.writer.write_step_two(
            profile=session.profile,
            ranked=session.ranked,
            weights=weights,
            weight_reasons=reasons,
            priority_criteria=session.priority_criteria,
            scenario=session.scenario,
            excluded=session.excluded,
            address=address_context(session.profile, session.address, self.kb),
        )
        self._append(session, "assistant", text)
        session.state = ConversationState.FOLLOW_UP
        return text

    def _score_products(self, profile: Profile, products: list[dict[str, Any]]) -> list[ProductScores]:
        scorer = getattr(self.engine, "score_products", None)
        if callable(scorer):
            return scorer(profile, products)
        return [self.engine.score_product(profile, product) for product in products]

    def _build_scenario(self, session: ConsultationSession, insurance_type: str) -> Scenario | None:
        products = [item.product for item in session.ranked]
        if not products:
            return None
        if insurance_type == "unemployment":
            return finance.unemployment_scenario(session.profile, products[:2])
        if insurance_type == "retirement":
            budget = scoring.monthly_budget(session.profile) or 0
            _, product_monthly, income_basis = finance.split_retirement_budget(budget)
            return finance.retirement_scenario(
                session.profile, products[0], product_monthly * 12, income_basis
            )
        if insurance_type == "life":
            return finance.life_scenario(session.profile, products)
        return None

    # ----------------------------------------------------------------- helpers

    def _derived_object(self, session: ConsultationSession) -> scoring.DerivedFields:
        return scoring.derive(session.profile, session.top_type, self.kb)  # type: ignore[arg-type]

    def _refresh_derived(self, session: ConsultationSession) -> None:
        session.derived = self._derived_object(session).as_dict()

    def _missing_fields(self, session: ConsultationSession) -> list[str]:
        known = session.profile.model_dump(exclude={"provenance"})
        return [
            field_definition["key"]
            for field_definition in self.kb.section("profile_schema")["fields"]
            if field_definition.get("level") in {"core", "type"}
            and known.get(field_definition["key"]) in (None, [], {})
        ]

    def _missing_for_step_two(self, session: ConsultationSession) -> list[str]:
        """Fields Bước 2 still needs for the insurance type currently in the lead."""

        if not session.top_type:
            return []
        known = session.profile.model_dump(exclude={"provenance"})
        readiness = self.kb.section("profile_schema")["readiness"]["step2_compare_products"]
        return [
            key
            for key in readiness[session.top_type]
            if not key.startswith("one_of:") and known.get(key) in (None, [], {})
        ]

    def _apply_attitudes(self, session: ConsultationSession, decision: TurnDecision) -> None:
        """D2 infers attitudes; they are stored on the profile for the weights."""

        updates: dict[str, Any] = {}
        for key in ("risk_tolerance", "need_flexibility", "trust_concern"):
            value = getattr(decision, key)
            if value != "Unknown" and getattr(session.profile, key) is None:
                updates[key] = value
        if updates:
            session.profile = session.profile.model_copy(update=updates)

    @staticmethod
    def _last(session: ConsultationSession, role: str) -> str | None:
        for message in reversed(session.messages):
            if message.role == role:
                return message.content
        return None

    @staticmethod
    def _append(session: ConsultationSession, role: str, content: str) -> None:
        session.messages.append(ChatMessage(role=role, content=content, turn_index=len(session.messages)))

    # -------------------------------------------------------------- auto mode

    def run_auto(
        self,
        persona_id: str,
        max_questions: int | None = None,
        on_message: Callable[[ChatMessage], None] | None = None,
    ) -> ConsultationSession:
        """Drive a full session with the simulator playing the customer."""

        if self.simulator is None:
            raise RuntimeError("Auto mode requires CustomerSimulator.")

        limit = max_questions or self.max_questions
        session = self.new_session(persona_id, self.simulator.persona["address"])
        self.greeting(session)
        if on_message:
            on_message(session.messages[-1])

        customer_message = self.simulator.persona["opening"]
        guard = 0
        while session.state not in {ConversationState.CLOSING, ConversationState.FOLLOW_UP} and guard < limit + 6:
            guard += 1
            before = len(session.messages)
            reply = self.handle_customer_message(session, customer_message)
            if on_message:
                for message in session.messages[before:]:
                    on_message(message)
            if session.state in {ConversationState.CLOSING, ConversationState.FOLLOW_UP}:
                break
            if reply is None:
                break
            customer_message = self.simulator.reply(
                reply,
                [{"role": message.role, "content": message.content} for message in session.messages],
            )
        return session
