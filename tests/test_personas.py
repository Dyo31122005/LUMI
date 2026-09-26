from pathlib import Path

import yaml

from core.kb import KnowledgeBase
from core.schemas import Profile

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_personas_are_valid_profiles_and_expected_products_exist() -> None:
    expected = load_yaml(DATA_DIR / "expected.yaml")
    knowledge_base = KnowledgeBase.load()
    product_ids = {product["id"] for product in knowledge_base.section("products")}

    for persona_id, expectations in expected.items():
        persona = load_yaml(DATA_DIR / "personas" / f"{persona_id}.yaml")
        profile = Profile.model_validate(persona["facts"])

        assert persona["id"] == persona_id
        assert persona["opening"]
        assert persona["completion_condition"]
        assert expectations["top_product_id"] in product_ids
        for field_name in expectations["required_profile_fields"]:
            assert getattr(profile, field_name) is not None
