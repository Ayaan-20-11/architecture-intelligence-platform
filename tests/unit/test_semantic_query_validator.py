import pytest

from app.ai.semantic_query_validator import SemanticQueryValidator, SemanticValidationError

validator = SemanticQueryValidator()


def validate(cypher: str) -> None:
    validator.validate(cypher)


# --- spec §5.11 valid/invalid table ----------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service)-[:SENDS]->(q:Queue) RETURN s, q",
        "MATCH (s:Service)-[:RECEIVES_FROM]->(q:Queue) RETURN s, q",
        "MATCH (s:Service)-[:PROVIDES]->(o:Operation) RETURN s, o",
        "MATCH (s:Service)-[:CALLS]->(o:Operation) RETURN s, o",
        "MATCH (q:Queue)-[:CARRIES]->(m:Message) RETURN q, m",
        "MATCH (m:Message)-[:CONFORMS_TO]->(s:Schema) RETURN m, s",
        "MATCH (q:Queue)-[:DEAD_LETTERS_TO]->(dlq:Queue) RETURN q, dlq",
        "MATCH (o:Operation)-[:REQUEST_SCHEMA]->(s:Schema) RETURN o, s",
        "MATCH (o:Operation)-[:RESPONSE_SCHEMA]->(s:Schema) RETURN o, s",
    ],
)
def test_valid_relation_direction_passes(query):
    validate(query)  # must not raise


@pytest.mark.parametrize(
    "query,relation",
    [
        ("MATCH (q:Queue)-[:SENDS]->(s:Service) RETURN q, s", "SENDS"),
        ("MATCH (q:Queue)-[:RECEIVES_FROM]->(s:Service) RETURN q, s", "RECEIVES_FROM"),
        ("MATCH (o:Operation)-[:PROVIDES]->(s:Service) RETURN o, s", "PROVIDES"),
        ("MATCH (m:Message)-[:CARRIES]->(q:Queue) RETURN m, q", "CARRIES"),
    ],
)
def test_wrong_relation_direction_rejected(query, relation):
    with pytest.raises(SemanticValidationError, match=relation) as exc_info:
        validate(query)
    assert exc_info.value.relation == relation


def test_ac_h2_2_live_test_regression():
    # The exact live-test failure the hardening spec's H2 section exists to catch (§5.1/§5.5).
    with pytest.raises(SemanticValidationError) as exc_info:
        validate("MATCH (q:Queue)-[:SENDS]->(s:Service) RETURN q")
    err = exc_info.value
    assert err.relation == "SENDS"
    assert err.expected_source == frozenset({"Service"})
    assert err.expected_target == frozenset({"Queue"})
    assert "Service -> Queue" in str(err)
    assert "Queue -> Service" in str(err)


# --- unknown relation types --------------------------------------------------------------------


def test_unknown_relationship_type_rejected():
    with pytest.raises(SemanticValidationError, match="unknown relationship type"):
        validate("MATCH (s:Service)-[:EVIL]->(q:Queue) RETURN s")


def test_unknown_type_in_alternation_rejected_even_if_other_alternative_is_valid():
    with pytest.raises(SemanticValidationError, match="unknown relationship type"):
        validate("MATCH (s:Service)-[:SENDS|EVIL]->(q:Queue) RETURN s")


# --- permissive when labels can't be determined ------------------------------------------------


def test_missing_labels_are_not_flagged_as_violations():
    validate("MATCH (a)-[:SENDS]->(b) RETURN a, b")  # must not raise


def test_one_sided_missing_label_is_permissive():
    validate("MATCH (a:Service)-[:SENDS]->(b) RETURN a, b")  # must not raise


# --- alias reuse / multiple MATCH blocks / OPTIONAL MATCH / correlated subqueries ---------------


def test_alias_reused_across_separate_match_clauses_resolves_via_symbol_table():
    query = "MATCH (s:Service) MATCH (q:Queue) MATCH (s)-[:SENDS]->(q) RETURN s, q"
    validate(query)  # must not raise


def test_alias_reused_across_separate_match_clauses_still_catches_violation():
    query = "MATCH (s:Service) MATCH (q:Queue) MATCH (q)-[:SENDS]->(s) RETURN s, q"
    with pytest.raises(SemanticValidationError, match="SENDS"):
        validate(query)


def test_correlated_exists_subquery_resolves_outer_alias():
    # Real shape from app/analysis/queues.py's A3/A4 queries.
    query = (
        "MATCH (consumer:Service)-[:RECEIVES_FROM]->(q:Queue) "
        "WHERE NOT EXISTS { MATCH (:Service)-[:SENDS]->(q) } "
        "RETURN consumer.name, q.name"
    )
    validate(query)  # must not raise


def test_optional_match_is_checked():
    query = "MATCH (s:Service) OPTIONAL MATCH (s)-[:SENDS]->(q:Queue) RETURN s, q"
    validate(query)  # must not raise


def test_optional_match_violation_is_caught():
    query = "MATCH (s:Service) OPTIONAL MATCH (q:Queue)-[:SENDS]->(s) RETURN s, q"
    with pytest.raises(SemanticValidationError, match="SENDS"):
        validate(query)


# --- variable-length traversal -------------------------------------------------------------------


def test_variable_length_traversal_valid_direction_passes():
    validate("MATCH (s:Service)-[:CALLS*1..3]->(o:Operation) RETURN s, o")  # must not raise


def test_variable_length_traversal_wrong_direction_rejected():
    with pytest.raises(SemanticValidationError, match="CALLS"):
        validate("MATCH (o:Operation)-[:CALLS*1..3]->(s:Service) RETURN s, o")


# --- real multi-hop shape (blast radius) ---------------------------------------------------------


def test_blast_radius_shaped_query_with_anonymous_nodes_and_property_map_passes():
    # From app/analysis/blast_radius.py::_NEIGHBORS_QUERY (UNION dropped - the security validator
    # already forbids UNION; only the per-branch shape is exercised here).
    query = (
        "MATCH (:Service {id: $service_id})-[:CALLS]->(:Operation)<-[:PROVIDES]-(b:Service) "
        "RETURN DISTINCT b.id AS id"
    )
    validate(query)  # must not raise


def test_blast_radius_shaped_query_async_branch_passes():
    query = (
        "MATCH (:Service {id: $service_id})-[:SENDS]->(:Queue)<-[:RECEIVES_FROM]-(b:Service) "
        "RETURN DISTINCT b.id AS id"
    )
    validate(query)  # must not raise


def test_incoming_arrow_correct_direction_passes():
    # <-[:CALLS]- reverses the arrow, so actual source/target is (Service)->(Operation) here.
    validate("MATCH (:Operation)<-[:CALLS]-(s:Service) RETURN s")  # must not raise


def test_incoming_arrow_wrong_direction_rejected():
    # <-[:PROVIDES]- reverses the arrow: actual is (Operation)->(Service), but PROVIDES expects
    # Service -> Operation.
    query = "MATCH (:Service)<-[:PROVIDES]-(o:Operation) RETURN o"
    with pytest.raises(SemanticValidationError, match="PROVIDES"):
        validate(query)


# --- nested parens inside a property map ----------------------------------------------------------


def test_nested_parens_in_property_map_does_not_break_node_boundary_detection():
    query = "MATCH (s:Service {id: toLower($id)})-[:SENDS]->(q:Queue) RETURN s, q"
    validate(query)  # must not raise

    bad_query = "MATCH (q:Queue {id: toLower($id)})-[:SENDS]->(s:Service) RETURN s, q"
    with pytest.raises(SemanticValidationError, match="SENDS"):
        validate(bad_query)


# --- relationship-type alternation is OR'd for domain/range --------------------------------------


def test_alternation_passes_if_any_known_alternative_is_compatible():
    # SENDS alone would not be compatible with Operation, but CALLS is - the alternative means
    # "the stored edge is SENDS OR CALLS", so this must not be rejected.
    validate("MATCH (s:Service)-[:SENDS|CALLS]->(o:Operation) RETURN s, o")


def test_alternation_rejected_if_no_alternative_is_compatible():
    with pytest.raises(SemanticValidationError):
        validate("MATCH (o:Operation)-[:SENDS|RECEIVES_FROM]->(s:Service) RETURN s, o")
