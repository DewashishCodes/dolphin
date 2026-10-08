import json
import threading
import urllib.error
import urllib.request

import pytest

from dolphin_memory.viewer import Store, ViewerServer


@pytest.fixture
def viewer(make_memory, db_path):
    memory = make_memory(triples=[
        {"s": "Project", "p": "USES", "o": "SQLite", "ol": "Tool"},
    ])
    memory.add("The project uses SQLite for its cache", scope="project:acme/app")
    memory._graph._extractor.extract = lambda text: []
    memory.add("Prefers tabs over spaces", scope="user:global")

    server = ViewerServer(0, Store(db_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _get(server, path, host=None):
    port = server.server_address[1]
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if host:
        request.add_header("Host", host)
    with urllib.request.urlopen(request) as response:
        return response.status, response.read()


def test_scopes_lists_every_namespace_with_counts(viewer):
    status, body = _get(viewer, "/api/scopes")
    scopes = {s["scope"]: s for s in json.loads(body)}

    assert status == 200
    assert scopes["project:acme/app"]["memories"] == 1
    assert scopes["user:global"]["memories"] == 1


def test_graph_returns_memories_for_one_scope_only(viewer):
    _, body = _get(viewer, "/api/graph?scope=project%3Aacme%2Fapp")
    data = json.loads(body)

    assert [m["text"] for m in data["memories"]] == ["The project uses SQLite for its cache"]
    assert {"Project", "SQLite"} <= {n["name"] for n in data["nodes"]}
    node_ids = {n["id"] for n in data["nodes"]}
    assert "USES" in [l["relationship"] for l in data["links"]]
    assert all(l["source"] in node_ids and l["target"] in node_ids for l in data["links"])

    _, other = _get(viewer, "/api/graph?scope=user%3Aglobal")
    assert json.loads(other)["nodes"] == []


def test_graph_requires_a_scope(viewer):
    with pytest.raises(urllib.error.HTTPError) as err:
        _get(viewer, "/api/graph")
    assert err.value.code == 400


def test_rejects_foreign_host_header(viewer):
    with pytest.raises(urllib.error.HTTPError) as err:
        _get(viewer, "/api/scopes", host="evil.example.com")
    assert err.value.code == 403


def test_serves_the_page(viewer):
    status, body = _get(viewer, "/")
    assert status == 200
    assert b"Dolphin Graph" in body


def test_missing_database_is_empty_and_not_created(tmp_path):
    path = tmp_path / "nope" / "dolphin.db"
    store = Store(str(path))

    assert store.scopes() == []
    assert store.graph("anything") == {"nodes": [], "links": [], "memories": []}
    assert not path.exists()
