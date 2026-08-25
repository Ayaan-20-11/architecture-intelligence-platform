import re

from app.graph.importer import NODE_LABELS
from app.graph.reconciliation import KNOWN_RELATION_TYPES

DEFAULT_MAX_DEPTH = 5
DEFAULT_MAX_RESULT_ROWS = 100

KNOWN_NODE_LABELS = set(NODE_LABELS.values())

# Spec §15.3 explicit forbidden list, plus other Cypher clause/admin keywords not in the §15.2
# allowlist (MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY, LIMIT) - together these give
# allowlist-equivalent coverage for realistic Cypher without a full grammar/AST parser.
FORBIDDEN_KEYWORDS = {
    "CREATE",
    "DELETE",
    "DETACH",
    "SET",
    "REMOVE",
    "MERGE",
    "DROP",
    "LOAD",
    "CALL",
    "UNWIND",
    "FOREACH",
    "UNION",
    "START",
    "USE",
    "SHOW",
    "EXPLAIN",
    "PROFILE",
    "GRANT",
    "DENY",
    "REVOKE",
    "TERMINATE",
    "INDEX",
    "CONSTRAINT",
    "ALTER",
    "RENAME",
    "DBMS",
}

_STRING_OR_COMMENT_RE = re.compile(
    r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|//[^\n]*|/\*.*?\*/", re.DOTALL
)
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NODE_LABEL_RE = re.compile(r"\(\s*\w*\s*:\s*([A-Za-z_][A-Za-z0-9_:]*)")
_REL_TYPE_RE = re.compile(r"\[\s*\w*\s*:\s*([A-Za-z_][A-Za-z0-9_|]*)")
_VAR_LENGTH_RE = re.compile(r"\[[^\]]*\]")
_STAR_DEPTH_RE = re.compile(r"\*\s*(\d+)?\s*(\.\.)?\s*(\d+)?")
_LIMIT_RE = re.compile(r"\bLIMIT\s+(\d+)\b", re.IGNORECASE)


class CypherValidationError(ValueError):
    pass


def _strip_strings_and_comments(cypher: str) -> str:
    return _STRING_OR_COMMENT_RE.sub(" ", cypher)


def _check_forbidden_keywords(code_only: str) -> None:
    tokens = {t.upper() for t in _TOKEN_RE.findall(code_only)}
    forbidden_found = tokens & FORBIDDEN_KEYWORDS
    if forbidden_found:
        raise CypherValidationError(
            f"forbidden Cypher construct(s): {', '.join(sorted(forbidden_found))}"
        )


def _check_requires_return(code_only: str) -> None:
    if "RETURN" not in {t.upper() for t in _TOKEN_RE.findall(code_only)}:
        raise CypherValidationError("query must contain a RETURN clause")


def _check_known_labels_and_relation_types(code_only: str) -> None:
    for match in _NODE_LABEL_RE.finditer(code_only):
        for label in match.group(1).split(":"):
            if label and label not in KNOWN_NODE_LABELS:
                raise CypherValidationError(f"unknown node label: {label}")
    for match in _REL_TYPE_RE.finditer(code_only):
        for rel_type in match.group(1).split("|"):
            if rel_type and rel_type not in KNOWN_RELATION_TYPES:
                raise CypherValidationError(f"unknown relationship type: {rel_type}")


def _check_traversal_depth(code_only: str, max_depth: int) -> None:
    for bracket_match in _VAR_LENGTH_RE.finditer(code_only):
        pattern = bracket_match.group(0)
        star_match = _STAR_DEPTH_RE.search(pattern)
        if star_match is None:
            continue
        min_str, has_range, max_str = star_match.groups()
        if has_range:
            if not max_str:
                raise CypherValidationError("unbounded variable-length traversal is not allowed")
            depth = int(max_str)
        elif min_str:
            depth = int(min_str)
        else:
            raise CypherValidationError("unbounded variable-length traversal is not allowed")
        if depth > max_depth:
            raise CypherValidationError(f"traversal depth {depth} exceeds max_depth {max_depth}")


def _reject_multiple_statements(code_only: str) -> None:
    if ";" in code_only:
        raise CypherValidationError("multiple statements are not allowed")


def _enforce_result_row_limit(cypher: str, max_result_rows: int) -> str:
    match = _LIMIT_RE.search(cypher)
    if match is None:
        return f"{cypher.rstrip()} LIMIT {max_result_rows}"
    existing = int(match.group(1))
    if existing <= max_result_rows:
        return cypher
    return cypher[: match.start(1)] + str(max_result_rows) + cypher[match.end(1) :]


def validate_cypher(
    cypher: str,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_result_rows: int = DEFAULT_MAX_RESULT_ROWS,
) -> str:
    """Enforces spec §15.2-§15.4: allowlisted read-only constructs, known labels/relation types, bounded traversal depth, and a row limit. Returns the query with LIMIT clamped/appended."""
    cypher = cypher.strip().rstrip(";").strip()
    if not cypher:
        raise CypherValidationError("empty query")

    code_only = _strip_strings_and_comments(cypher)
    _reject_multiple_statements(code_only)
    _check_forbidden_keywords(code_only)
    _check_requires_return(code_only)
    _check_known_labels_and_relation_types(code_only)
    _check_traversal_depth(code_only, max_depth)

    return _enforce_result_row_limit(cypher, max_result_rows)
