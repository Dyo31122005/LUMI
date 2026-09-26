from core.decision import OpenAIEngine, RuleEngine, normalize_probabilities
from core.llm import LLMSettings, LUMI_MODEL, LumiOpenAIClient
from core.schemas import Profile

def test_normalize_probabilities_totals_one() -> None:
    assert sum(normalize_probabilities({"unemployment": 3, "retirement": 1, "life": 0, "health": 0}).model_dump().values()) == 1

def test_rule_engine_matches_three_persona_types() -> None:
    engine = RuleEngine()
    assert engine.decide_type(Profile(employment_status="job_seeking", primary_concerns=["job_loss"])).insurance_type == "unemployment"
    assert engine.decide_type(Profile(age=44, bhxh_years=8, primary_concerns=["retirement_income"])).insurance_type == "retirement"
    assert engine.decide_type(Profile(primary_concerns=["spouse_protection"])).insurance_type == "life"

def test_openai_engine_normalizes_structured_output() -> None:
    class Response:
        status = "completed"
        output_text = '{"insurance_type":"life","secondary_type":"health","type_probabilities":{"unemployment":0.8,"retirement":0,"life":0.8,"health":0},"confidence":0.7,"reasons":["test"]}'
    class Responses:
        def create(self, **_: object) -> Response: return Response()
    class Client:
        responses = Responses()
    client = LumiOpenAIClient(LLMSettings("test", LUMI_MODEL, LUMI_MODEL, "openai"), client=Client())
    result = OpenAIEngine(client, "test").decide_type(Profile(), {})
    assert sum(result.type_probabilities.model_dump().values()) == 1


def test_offline_d5_is_not_a_lookup_of_the_expected_answer() -> None:
    """D5 must read the catalog, not a stored winner."""

    from core.kb import KnowledgeBase

    kb = KnowledgeBase.load()
    engine = RuleEngine(kb)
    products = {item["id"]: dict(item) for item in kb.section("products")}

    cautious = Profile(age=44, gender="female", risk_tolerance="Very low")
    # Tương Lai Vững is unit-linked, so its guarantee criterion must suffer.
    unit_linked = engine.score_product(cautious, products["bm_tuonglai"])
    guaranteed = engine.score_product(cautious, products["ap_huu_annhan"])
    assert unit_linked.scores.C3 == "Does not meet"
    assert guaranteed.scores.C3 == "Meets very well"


def test_offline_d5_flexibility_depends_on_the_customer() -> None:
    from core.kb import KnowledgeBase

    kb = KnowledgeBase.load()
    engine = RuleEngine(kb)
    annhan = dict(next(item for item in kb.section("products") if item["id"] == "ap_huu_annhan"))

    needs_pause = Profile(age=44, upcoming_expenses=["con vào đại học"])
    relaxed = Profile(age=44)
    assert engine.score_product(needs_pause, annhan).scores.C4 == "Partly meets"
    assert engine.score_product(relaxed, annhan).scores.C4 == "Meets well"


def test_flags_report_the_pension_gap_with_its_number() -> None:
    from core.kb import KnowledgeBase
    from core import scoring

    kb = KnowledgeBase.load()
    profile = Profile(age=58, gender="female", bhxh_years=8, bhxh_withdrawn=True)
    derived = scoring.derive(profile, "retirement", kb).as_dict()
    flags = {item.key: item for item in RuleEngine(kb).flags(profile, derived)}
    assert "pension_gap" in flags
    assert "13" in flags["pension_gap"].reason
