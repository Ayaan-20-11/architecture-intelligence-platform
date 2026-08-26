from app.graph.reconciliation import KNOWN_RELATION_TYPES
from app.graph_schema.registry import RELATIONS


def test_registry_keys_exactly_match_known_relation_types():
    # Drift-safety net (AC-H2-1): every relation type the security validator/importer knows about
    # must have a domain/range definition here, and vice versa.
    assert set(RELATIONS.keys()) == KNOWN_RELATION_TYPES


def test_registry_name_matches_key():
    for key, definition in RELATIONS.items():
        assert definition.name == key


def test_registry_domain_range_matches_spec_table():
    expected = {
        "PROVIDES": ({"Service"}, {"Operation"}),
        "CALLS": ({"Service"}, {"Operation"}),
        "REQUEST_SCHEMA": ({"Operation"}, {"Schema"}),
        "RESPONSE_SCHEMA": ({"Operation"}, {"Schema"}),
        "SENDS": ({"Service"}, {"Queue"}),
        "RECEIVES_FROM": ({"Service"}, {"Queue"}),
        "CARRIES": ({"Queue"}, {"Message"}),
        "CONFORMS_TO": ({"Message"}, {"Schema"}),
        "DEAD_LETTERS_TO": ({"Queue"}, {"Queue"}),
    }
    for name, (source, target) in expected.items():
        definition = RELATIONS[name]
        assert definition.source_labels == frozenset(source)
        assert definition.target_labels == frozenset(target)
