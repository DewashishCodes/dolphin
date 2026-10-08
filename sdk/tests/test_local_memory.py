import pytest

from dolphin_memory import DolphinConfig, DolphinMemory

TRIPLES = [
    {"s": "User", "p": "LIVES_IN", "o": "Mumbai", "ol": "City"},
    {"s": "User", "p": "LIKES", "o": "Rock Climbing", "ol": "Skill"},
    {"s": "Mumbai", "p": "LOCATED_IN", "o": "India", "ol": "Country"},
]


def test_default_config_is_local_sqlite():
    config = DolphinConfig()
    config.validate()
    assert config.resolved_backend() == "sqlite"
    assert config.resolved_embedding()[0] == "fastembed"


def test_supabase_url_selects_supabase():
    config = DolphinConfig(supabase_url="https://x.supabase.co", supabase_key="k")
    config.validate()
    assert config.resolved_backend() == "supabase"
    assert config.resolved_embedding()[0] == "sentence-transformers"


def test_supabase_backend_requires_credentials():
    with pytest.raises(ValueError, match="supabase_url is required"):
        DolphinConfig(backend="supabase").validate()


def test_add_and_search(memory):
    result = memory.add("The deploy script lives in tools/release.py", user_id="u1")
    assert result["status"] == "created"
    memory.add("We use pytest for the test suite", user_id="u1")

    hits = memory.search("where is the deploy script", user_id="u1")
    assert hits[0]["id"] == result["memory_id"]
    assert hits[0]["content"]["value"] == "The deploy script lives in tools/release.py"
    assert 0 < hits[0]["similarity"] <= 1.0001


def test_namespaces_are_isolated(memory):
    memory.add("The deploy script lives in tools/release.py", user_id="u1")
    assert memory.search("deploy script", user_id="u2") == []
    assert memory.get_all_memories(user_id="u2") == []


def test_duplicate_is_reinforced_not_stored_twice(memory):
    first = memory.add("We use pytest for the test suite", user_id="u1")
    second = memory.add("We use pytest for the test suite", user_id="u1")
    assert second["status"] == "reinforced"
    assert second["memory_id"] == first["memory_id"]
    assert len(memory.get_all_memories(user_id="u1")) == 1


def test_delete_single_memory(memory):
    memory_id = memory.add("temporary note about the build", user_id="u1")["memory_id"]
    assert memory.delete(memory_id) is True
    assert memory.delete(memory_id) is False
    assert memory.get_all_memories(user_id="u1") == []


def test_graph_extraction_and_context(make_memory):
    memory = make_memory(triples=TRIPLES)
    memory.add("I live in Mumbai and love rock climbing", user_id="u1")

    # User, Mumbai, Rock Climbing, India
    assert memory.get_stats(user_id="u1") == {"nodes": 4, "edges": 3}

    context = memory.get_context("rock climbing in Mumbai", user_id="u1")
    assert "### RELEVANT MEMORIES" in context
    assert "User LIVES_IN Mumbai (City)" in context
    assert "Mumbai LOCATED_IN India (Country)" in context


def test_repeated_fact_reinforces_edge(make_memory):
    memory = make_memory(triples=TRIPLES, deduplicate=False)
    memory.add("I live in Mumbai", user_id="u1")
    memory.add("Still living in Mumbai", user_id="u1")

    assert memory.get_stats(user_id="u1") == {"nodes": 4, "edges": 3}
    row = memory._store.backend._query(
        "SELECT access_count, weight FROM graph_edges WHERE relationship = 'LIVES_IN'"
    )[0]
    assert row["access_count"] == 2
    assert row["weight"] == pytest.approx(1.1)


def test_merge_node_repoints_edges(make_memory):
    memory = make_memory(triples=[
        {"s": "User", "p": "WORKS_AT", "o": "Acme", "ol": "Company"},
        {"s": "User", "p": "WORKS_AT", "o": "Acme Corp", "ol": "Company"},
        {"s": "Acme Corp", "p": "LOCATED_IN", "o": "Pune", "ol": "City"},
    ])
    memory.add("I work at Acme Corp in Pune", user_id="u1")
    backend = memory._store.backend
    keep = backend.get_node_id("user_u1", "Acme")
    drop = backend.get_node_id("user_u1", "Acme Corp")

    backend.merge_node(keep, drop)

    assert backend.get_node_id("user_u1", "Acme Corp") is None
    # The duplicate User-WORKS_AT edge collapses; LOCATED_IN moves to the kept node
    assert memory.get_stats(user_id="u1") == {"nodes": 3, "edges": 2}
    assert backend.edges_from([keep], 10)[0]["target_name"] == "Pune"


def test_delete_user_removes_everything(make_memory):
    memory = make_memory(triples=TRIPLES)
    memory.add("I live in Mumbai", user_id="u1")
    counts = memory.delete_user("u1")
    assert counts == {"memories": 1, "edges": 3, "nodes": 4}
    assert memory.get_stats(user_id="u1") == {"nodes": 0, "edges": 0}


def test_two_clients_share_one_database(make_memory):
    """Two sessions on the same machine see each other's memories."""
    session_a = make_memory()
    session_b = make_memory()

    session_a.add("The API rate limit is 100 requests per minute", user_id="proj")

    hits = session_b.search("API rate limit", user_id="proj")
    assert hits and "100 requests per minute" in hits[0]["content"]["value"]


def test_database_refuses_a_different_embedding_model(db_path):
    DolphinMemory(db_path=db_path)._store.backend.close()
    with pytest.raises(ValueError, match="was created with embedding model"):
        DolphinMemory(db_path=db_path, embedding_model="BAAI/bge-small-en-v1.5")
