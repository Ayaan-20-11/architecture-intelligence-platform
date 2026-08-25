from app.analysis.blast_radius import _traverse

# A -SYNC-> B -SYNC-> D -SYNC-> A (cycle)
# A -ASYNC-> C -ASYNC-> D          (diamond: D reachable via both B and C)
# E is isolated / unreachable from A
GRAPH = {
    "A": [("B", "B", "SYNC"), ("C", "C", "ASYNC")],
    "B": [("D", "D", "SYNC")],
    "C": [("D", "D", "ASYNC")],
    "D": [("A", "A", "SYNC")],
    "E": [],
}


def fetch(service_id: str):
    return GRAPH.get(service_id, [])


def test_traverse_visits_all_reachable_nodes_by_depth():
    results = _traverse(fetch, "A", max_depth=5)
    by_depth = {}
    for entry in results:
        by_depth.setdefault(entry.depth, set()).add(entry.service_id)

    assert by_depth[1] == {"B", "C"}
    assert by_depth[2] == {"D"}
    assert 3 not in by_depth  # cycle back to A must not produce further hops


def test_traverse_diamond_keeps_only_first_discovered_path():
    results = _traverse(fetch, "A", max_depth=5)
    d_entries = [e for e in results if e.service_id == "D"]
    assert len(d_entries) == 1
    assert d_entries[0].via == "SYNC"  # discovered through B, processed before C


def test_traverse_never_revisits_start_node():
    results = _traverse(fetch, "A", max_depth=5)
    assert all(entry.service_id != "A" for entry in results)


def test_traverse_respects_max_depth():
    results = _traverse(fetch, "A", max_depth=1)
    assert {e.service_id for e in results} == {"B", "C"}


def test_traverse_max_depth_zero_yields_nothing():
    assert _traverse(fetch, "A", max_depth=0) == []


def test_traverse_isolated_node_yields_nothing():
    assert _traverse(fetch, "E", max_depth=5) == []
