"""Vérifie que contracts/ (schémas JSON + exemples) et orchestrator/contracts.py restent alignés."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import TypeAdapter, ValidationError
from referencing import Registry, Resource

from orchestrator import contracts as c

ROOT = Path(__file__).resolve().parents[2] / "contracts"
SCHEMAS = ROOT / "schemas"
VALID = sorted((ROOT / "examples" / "valid").glob("*.json"))
INVALID = sorted((ROOT / "examples" / "invalid").glob("*.json"))

# préfixe du nom de fichier d'exemple -> (schéma, modèle pydantic)
KINDS = {
    "intent": ("intent.schema.json", c.Intent),
    "option": ("option.schema.json", c.Option),
    "order-summary": ("order-summary.schema.json", c.OrderSummary),
    "approval-request": ("approval-request.schema.json", c.ApprovalRequest),
    "approval-status": ("approval-status.schema.json", c.ApprovalStatus),
    "site-card": ("site-card.schema.json", c.SiteCard),
    "ws": ("ws-message.schema.json", c.ClientMessage | c.ServerMessage),
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _registry() -> Registry:
    resources = []
    for p in SCHEMAS.glob("*.schema.json"):
        schema = _load(p)
        res = Resource.from_contents(schema)
        resources.append((schema["$id"], res))
    return Registry().with_resources(resources)


REGISTRY = _registry()


def _validator(schema_file: str) -> Draft202012Validator:
    return Draft202012Validator(
        _load(SCHEMAS / schema_file), registry=REGISTRY, format_checker=FormatChecker()
    )


def _kind(path: Path):
    for prefix in sorted(KINDS, key=len, reverse=True):
        if path.name.startswith(prefix + "-"):
            return KINDS[prefix]
    raise AssertionError(f"Préfixe inconnu pour {path.name}")


def test_schemas_are_valid_json_schema():
    for p in SCHEMAS.glob("*.schema.json"):
        Draft202012Validator.check_schema(_load(p))


def test_every_schema_has_examples():
    used = {_kind(p)[0] for p in VALID}
    assert used == {f for f, _ in KINDS.values()}


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_examples_pass_schema_and_pydantic(path: Path):
    schema_file, model = _kind(path)
    data = _load(path)
    _validator(schema_file).validate(data)
    TypeAdapter(model).validate_python(data)


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_invalid_examples_fail_schema_and_pydantic(path: Path):
    schema_file, model = _kind(path)
    data = _load(path)
    assert list(_validator(schema_file).iter_errors(data)), "le schéma aurait dû refuser"
    with pytest.raises(ValidationError):
        TypeAdapter(model).validate_python(data)


@pytest.mark.parametrize(
    ("schema_file", "model"),
    [v for k, v in KINDS.items() if k != "ws"],
    ids=[k for k in KINDS if k != "ws"],
)
def test_pydantic_fields_match_schema(schema_file, model):
    schema = _load(SCHEMAS / schema_file)
    assert set(model.model_fields) == set(schema["properties"])
    # tous les champs sont requis : une valeur absente vaut null
    assert set(schema["required"]) == set(schema["properties"])


def test_ws_states_match():
    schema = _load(SCHEMAS / "ws-message.schema.json")
    assert set(schema["$defs"]["State"]["enum"]) == set(c.State.__args__)


def test_example_hashes_are_correct():
    for path in VALID:
        if path.name.startswith("order-summary-"):
            s = c.OrderSummary.model_validate(_load(path))
            assert s.hash == c.summary_hash(s.items, s.total_cents), path.name


def _item(name, qty=1, options=()):
    return c.OrderItem(name=name, quantity=qty, unit_price_cents=None, total_cents=100, options=list(options))


def test_hash_ignores_order_case_accents_and_spacing():
    a = c.summary_hash([_item("Pizza Margherita", options=["Grande"]), _item("Tiramisu maison")], 1900)
    b = c.summary_hash([_item("tiramisu  MAISON"), _item("pizza margherita", options=["grande"])], 1900)
    assert a == b
    assert c.summary_hash([_item("Crème brûlée")], 100) == c.summary_hash([_item("creme brulee")], 100)


@pytest.mark.parametrize(
    "changed",
    [
        ([_item("Pizza margherita", qty=2)], 1900),
        ([_item("Pizza margherita", options=["Moyenne"])], 1900),
        ([_item("Pizza reine")], 1900),
        ([_item("Pizza margherita")], 2100),
    ],
)
def test_hash_changes_when_order_changes(changed):
    base = c.summary_hash([_item("Pizza margherita")], 1900)
    assert c.summary_hash(*changed) != base
