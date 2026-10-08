import io
import json
import subprocess
import sys
import threading

import pytest

from dolphin_memory import hook
from dolphin_memory.daemon import DaemonServer, MemoryService, _write_state
from dolphin_memory.extraction import TripleExtractor, looks_like_secret
from dolphin_memory.config import DolphinConfig
from dolphin_memory.scopes import USER_SCOPE, _normalize_remote, project_scope, resolve_scope


# -----------------------------------------------------------------------------
# Scopes
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "git@github.com:DewashishCodes/Dolphin.git",
    "https://github.com/DewashishCodes/dolphin",
    "https://github.com/DewashishCodes/dolphin.git/",
    "ssh://git@github.com/DewashishCodes/dolphin.git",
])
def test_remote_forms_normalize_to_one_scope(url):
    assert _normalize_remote(url) == "github.com/dewashishcodes/dolphin"


def test_project_scope_uses_git_remote(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "remote", "add", "origin", "git@github.com:acme/api.git"],
        check=True,
    )
    sub = tmp_path / "src"
    sub.mkdir()
    assert project_scope(str(sub)) == "project:github.com/acme/api"


def test_project_scope_without_git_is_stable_per_directory(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert project_scope(str(a)) == project_scope(str(a))
    assert project_scope(str(a)) != project_scope(str(b))
    assert project_scope(str(a)).startswith("project:a-")


def test_resolve_scope(tmp_path, monkeypatch):
    monkeypatch.delenv("DOLPHIN_SCOPE", raising=False)
    assert resolve_scope("user") == USER_SCOPE
    assert resolve_scope("team:payments") == "team:payments"
    assert resolve_scope(None, str(tmp_path)) == project_scope(str(tmp_path))


# -----------------------------------------------------------------------------
# Distillation
# -----------------------------------------------------------------------------

def test_parse_facts_accepts_array_and_wrapped_object():
    extractor = TripleExtractor(DolphinConfig())
    fact = "Releases are cut with tools/release.py."
    assert extractor._parse_facts(json.dumps([fact])) == [fact]
    assert extractor._parse_facts(json.dumps({"facts": [fact]})) == [fact]
    assert extractor._parse_facts("Sure! Here you go: " + json.dumps([fact])) == [fact]
    assert extractor._parse_facts("nothing to keep") == []
    assert extractor._parse_facts("[]") == []


def test_distill_drops_secrets():
    extractor = TripleExtractor(DolphinConfig())
    extractor._complete = lambda system, user, parses: json.dumps([
        "The staging API key is sk-abcdefghijklmnopqrstuvwx.",
        "Staging deploys run from the release branch.",
    ])
    assert extractor.distill("...") == ["Staging deploys run from the release branch."]


@pytest.mark.parametrize("text", [
    "token: ghp_abcdefghijklmnopqrstuvwxyz0123",
    "AWS key AKIAIOSFODNN7EXAMPLE",
    "password = hunter2hunter2",
])
def test_looks_like_secret(text):
    assert looks_like_secret(text)


def test_ordinary_text_is_not_a_secret():
    assert not looks_like_secret("The token bucket refills at 100 requests per minute.")


def test_capture_stores_each_distilled_fact(memory):
    memory._extractor.distill = lambda exchange: [
        "Releases are cut with tools/release.py, never by pushing to main.",
        "The developer prefers pytest over unittest.",
    ]
    stored = memory.capture("Developer: ...\n\nAgent: ...", scope="project:x",
                            metadata={"source": "claude-code"})
    assert [s["status"] for s in stored] == ["created", "created"]

    saved = memory.get_all_memories(scope="project:x")
    assert len(saved) == 2
    assert saved[0]["content"]["source"] == "claude-code"


# -----------------------------------------------------------------------------
# Daemon + hooks
# -----------------------------------------------------------------------------

SCOPE = "project:github.com/acme/api"


@pytest.fixture
def daemon(memory, tmp_path, monkeypatch):
    """A daemon on a free port, with hook state pointing at it."""
    home = tmp_path / "home"
    monkeypatch.setattr("dolphin_memory.daemon.HOME", str(home))
    monkeypatch.setattr("dolphin_memory.daemon.STATE_FILE", str(home / "daemon.json"))
    monkeypatch.setattr(hook, "STATE_FILE", str(home / "daemon.json"))
    monkeypatch.setattr(hook, "project_scope", lambda cwd=None: SCOPE)

    service = MemoryService(memory)
    server = DaemonServer(0, service)
    _write_state(server)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield service
    server.shutdown()
    server.server_close()
    service._capture_pool.shutdown(wait=True)


def run_hook(event_name, event, monkeypatch, capsys):
    stdin = io.TextIOWrapper(io.BytesIO(json.dumps(event).encode("utf-8")), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", stdin)
    assert hook.main([event_name]) == 0
    return capsys.readouterr().out


def test_health_and_token(daemon):
    assert hook.health()["ok"] is True

    state = hook.read_state()
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        f"http://127.0.0.1:{state['port']}/recall",
        data=b'{"query": "x", "scope": "y"}',
        headers={"X-Dolphin-Token": "wrong"},
    )
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req, timeout=2)
    assert err.value.code == 403


def test_prompt_hook_recalls_what_another_session_stored(daemon, memory, monkeypatch, capsys):
    memory.add("Releases are cut with tools/release.py, never by pushing to main.", scope=SCOPE)
    memory.add("The developer prefers tabs over spaces in release notes.", scope=USER_SCOPE)
    memory.add("Unrelated note about database migrations.", scope="project:other")

    out = run_hook(
        "user-prompt-submit",
        {"prompt": "how are releases cut in this repo?", "session_id": "s2", "cwd": "."},
        monkeypatch, capsys,
    )
    assert "Project memory:" in out
    assert "tools/release.py" in out
    assert "database migrations" not in out


def test_prompt_hook_prints_nothing_when_nothing_relates(daemon, memory, monkeypatch, capsys):
    memory.add("Releases are cut with tools/release.py.", scope=SCOPE)
    out = run_hook(
        "user-prompt-submit",
        {"prompt": "rename the variable in parser module", "session_id": "s", "cwd": "."},
        monkeypatch, capsys,
    )
    assert out == ""


def test_short_prompts_and_commands_are_skipped(daemon, memory, monkeypatch, capsys):
    memory.add("continue continue continue", scope=SCOPE)
    assert run_hook("user-prompt-submit", {"prompt": "continue"}, monkeypatch, capsys) == ""
    assert run_hook("user-prompt-submit", {"prompt": "/clear the release notes"},
                    monkeypatch, capsys) == ""


def test_session_start_brief(daemon, memory, monkeypatch, capsys):
    assert run_hook("session-start", {"cwd": "."}, monkeypatch, capsys) == ""

    memory.add("Releases are cut with tools/release.py.", scope=SCOPE)
    out = run_hook("session-start", {"cwd": "."}, monkeypatch, capsys)
    assert "Most recent project memories" in out
    assert "tools/release.py" in out


def test_stop_hook_captures_the_exchange(daemon, memory, monkeypatch, capsys):
    seen = []

    def distill(exchange):
        seen.append(exchange)
        return ["The flaky checkout test is caused by a shared Redis key."]

    memory._extractor.distill = distill

    run_hook("user-prompt-submit",
             {"prompt": "why is the checkout test flaky?", "session_id": "s1", "cwd": "."},
             monkeypatch, capsys)
    run_hook("stop",
             {"last_assistant_message": "Root cause: both workers write the same Redis key.",
              "session_id": "s1", "cwd": "."},
             monkeypatch, capsys)
    daemon._capture_pool.shutdown(wait=True)

    assert "Developer: why is the checkout test flaky?" in seen[0]
    assert "Agent: Root cause" in seen[0]
    saved = memory.get_all_memories(scope=SCOPE)
    assert saved[0]["content"]["value"] == "The flaky checkout test is caused by a shared Redis key."
    assert saved[0]["content"]["session"] == "s1"


def test_stop_hook_respects_capture_opt_out(daemon, memory, monkeypatch, capsys):
    memory._extractor.distill = lambda exchange: ["This should never be stored at all."]
    monkeypatch.setenv("DOLPHIN_CAPTURE", "0")

    run_hook("user-prompt-submit",
             {"prompt": "why is the checkout test flaky?", "session_id": "s1"},
             monkeypatch, capsys)
    run_hook("stop", {"last_assistant_message": "Because of Redis.", "session_id": "s1"},
             monkeypatch, capsys)
    daemon._capture_pool.shutdown(wait=True)
    assert memory.get_all_memories(scope=SCOPE) == []


def test_hooks_are_silent_without_a_daemon(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hook, "STATE_FILE", str(tmp_path / "missing.json"))
    monkeypatch.setattr(hook, "spawn_daemon", lambda: None)
    for name in ("session-start", "user-prompt-submit", "stop"):
        event = {"prompt": "how are releases cut in this repo?", "last_assistant_message": "x"}
        monkeypatch.setattr(hook, "ensure_daemon", lambda wait=0: False)
        assert run_hook(name, event, monkeypatch, capsys) == ""


def test_hook_survives_garbage_input(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"not json")))
    assert hook.main(["user-prompt-submit"]) == 0
    assert hook.main(["no-such-event"]) == 0
    assert hook.main([]) == 0
