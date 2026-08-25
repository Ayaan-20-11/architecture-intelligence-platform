import pytest

from app.ai.cypher_validator import CypherValidationError, validate_cypher

# --- valid queries pass through, with LIMIT enforcement -----------------------------------


def test_valid_query_gets_default_limit_appended():
    result = validate_cypher("MATCH (s:Service) RETURN s.id AS id, s.name AS name")
    assert result == "MATCH (s:Service) RETURN s.id AS id, s.name AS name LIMIT 100"


def test_valid_query_with_limit_under_max_is_unchanged():
    query = "MATCH (s:Service) RETURN s.id LIMIT 10"
    assert validate_cypher(query) == query


def test_limit_over_max_is_clamped():
    query = "MATCH (s:Service) RETURN s.id LIMIT 99999"
    assert validate_cypher(query) == "MATCH (s:Service) RETURN s.id LIMIT 100"


def test_custom_max_result_rows_respected():
    result = validate_cypher("MATCH (s:Service) RETURN s.id", max_result_rows=5)
    assert result.endswith("LIMIT 5")


def test_full_allowed_pipeline_passes():
    query = (
        "MATCH (s:Service) "
        "OPTIONAL MATCH (s)-[:SENDS]->(q:Queue) "
        "WHERE s.name IS NOT NULL "
        "WITH s, q "
        "RETURN s.name AS name, q.name AS queue "
        "ORDER BY s.name "
        "LIMIT 20"
    )
    assert validate_cypher(query) == query


def test_relationship_alternation_of_known_types_passes():
    query = "MATCH (s:Service)-[:SENDS|RECEIVES_FROM]->(q:Queue) RETURN s.id"
    validate_cypher(query)  # must not raise


def test_property_name_resembling_forbidden_keyword_is_not_a_false_positive():
    query = "MATCH (n:Service) RETURN n.createdAt AS createdAt"
    validate_cypher(query)  # "createdAt" must not be confused with CREATE


def test_calls_relationship_type_is_not_confused_with_call_keyword():
    query = "MATCH (a:Service)-[:CALLS]->(o:Operation) RETURN a.id"
    validate_cypher(query)  # must not raise - CALLS != CALL


# --- structural requirements ---------------------------------------------------------------


def test_empty_query_rejected():
    with pytest.raises(CypherValidationError):
        validate_cypher("")


def test_missing_return_clause_rejected():
    with pytest.raises(CypherValidationError, match="RETURN"):
        validate_cypher("MATCH (n:Service)")


def test_single_trailing_semicolon_is_tolerated():
    validate_cypher("MATCH (n:Service) RETURN n.id;")  # must not raise


def test_internal_semicolon_multi_statement_rejected():
    with pytest.raises(CypherValidationError, match="multiple statements"):
        validate_cypher("MATCH (n) RETURN n; MATCH (m) RETURN m")


# --- forbidden constructs (spec §15.3) ------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (n:Service) CREATE (m:Service {id: 'x'}) RETURN m",
        "MATCH (n:Service) DELETE n RETURN n",
        "MATCH (n:Service) DETACH DELETE n",
        "MATCH (n:Service) SET n.name = 'x' RETURN n",
        "MATCH (n:Service) REMOVE n.name RETURN n",
        "MATCH (n:Service) MERGE (m:Service {id: 'x'}) RETURN m",
        "DROP CONSTRAINT service_id",
        "LOAD CSV FROM 'file:///x.csv' AS row RETURN row",
        "CALL db.labels() YIELD label RETURN label",
    ],
)
def test_forbidden_construct_rejected(query):
    with pytest.raises(CypherValidationError, match="forbidden"):
        validate_cypher(query)


@pytest.mark.parametrize(
    "query",
    [
        "UNWIND [1, 2, 3] AS x RETURN x",
        "MATCH (n:Service) RETURN n UNION MATCH (m:Queue) RETURN m",
        "FOREACH (x IN [1] | SET x.y = 1) RETURN 1",
        "SHOW CONSTRAINTS RETURN 1",
    ],
)
def test_additional_disallowed_clauses_rejected(query):
    with pytest.raises(CypherValidationError):
        validate_cypher(query)


def test_forbidden_keyword_is_case_insensitive():
    with pytest.raises(CypherValidationError, match="forbidden"):
        validate_cypher("MATCH (n:Service) dEtAcH dElEtE n")


# --- adversarial: disguising forbidden keywords in strings/comments ------------------------


def test_forbidden_word_inside_a_properly_closed_string_is_inert_and_allowed():
    query = 'MATCH (n:Service) WHERE n.name = "please DROP this" RETURN n.id'
    validate_cypher(query)  # inert string data - Neo4j would treat it the same way


def test_forbidden_word_inside_a_properly_closed_comment_is_inert_and_allowed():
    query = "MATCH (n:Service) RETURN n.id // DROP everything"
    validate_cypher(query)  # inert comment - Neo4j would treat it the same way


def test_forbidden_word_in_unterminated_block_comment_is_still_caught():
    # No closing */, so the stripper can't treat this as a real comment - and neither would Neo4j.
    query = "MATCH (n:Service) RETURN n.id /* DROP DATABASE neo4j"
    with pytest.raises(CypherValidationError, match="forbidden"):
        validate_cypher(query)


def test_forbidden_word_in_unterminated_string_is_still_caught():
    query = "MATCH (n:Service) WHERE n.name = 'unterminated RETURN n.id DROP DATABASE neo4j"
    with pytest.raises(CypherValidationError, match="forbidden"):
        validate_cypher(query)


# --- unknown labels / relationship types ----------------------------------------------------


def test_unknown_node_label_rejected():
    with pytest.raises(CypherValidationError, match="unknown node label"):
        validate_cypher("MATCH (x:Hacker) RETURN x")


def test_unknown_relationship_type_rejected():
    with pytest.raises(CypherValidationError, match="unknown relationship type"):
        validate_cypher("MATCH (a:Service)-[:EVIL]->(b:Operation) RETURN a")


def test_unknown_type_in_alternation_rejected():
    with pytest.raises(CypherValidationError, match="unknown relationship type"):
        validate_cypher("MATCH (a:Service)-[:SENDS|EVIL]->(b) RETURN a")


# --- traversal depth (spec §15.4, default max_depth=5) --------------------------------------


def test_variable_length_within_max_depth_passes():
    query = "MATCH (a:Service)-[:CALLS*1..3]->(b:Operation) RETURN a.id"
    validate_cypher(query)  # must not raise


def test_variable_length_exceeding_max_depth_rejected():
    query = "MATCH (a:Service)-[:CALLS*1..10]->(b:Operation) RETURN a.id"
    with pytest.raises(CypherValidationError, match="exceeds max_depth"):
        validate_cypher(query)


def test_variable_length_respects_custom_max_depth():
    query = "MATCH (a:Service)-[:CALLS*1..3]->(b:Operation) RETURN a.id"
    with pytest.raises(CypherValidationError, match="exceeds max_depth"):
        validate_cypher(query, max_depth=2)


def test_fully_unbounded_variable_length_rejected():
    query = "MATCH (a:Service)-[:CALLS*]->(b:Operation) RETURN a.id"
    with pytest.raises(CypherValidationError, match="unbounded"):
        validate_cypher(query)


def test_unbounded_upper_variable_length_rejected():
    query = "MATCH (a:Service)-[:CALLS*2..]->(b:Operation) RETURN a.id"
    with pytest.raises(CypherValidationError, match="unbounded"):
        validate_cypher(query)


def test_single_number_variable_length_within_bound_passes():
    query = "MATCH (a:Service)-[:CALLS*3]->(b:Operation) RETURN a.id"
    validate_cypher(query)  # must not raise


def test_single_number_variable_length_exceeding_bound_rejected():
    query = "MATCH (a:Service)-[:CALLS*9]->(b:Operation) RETURN a.id"
    with pytest.raises(CypherValidationError, match="exceeds max_depth"):
        validate_cypher(query)
