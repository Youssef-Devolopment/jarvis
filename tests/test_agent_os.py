"""v1.26.0 — disciplined Agent OS: one permission table, hardened
tools, staged subagents.

- ai.permissions is the single source of truth (tiers, capability
  vocabulary, destructive-shell rules); the legacy AUTO/CONFIRM sets
  are frozen views over it.
- The execute_tool choke point validates args against TOOL_SCHEMAS,
  and secrets are redacted before anything model-bound.
- Subagents: max 2 workers, truncated merge evidence, cancelled
  stragglers, audit events, flag default off.
"""
import contextlib
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


def _chunk(text=None, finish=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=text, reasoning_content=None,
                              tool_calls=tool_calls),
        finish_reason=finish)])


def _stream_of(*texts):
    for t in texts:
        yield _chunk(t)


def _tool_call_stream(name, args):
    yield _chunk(tool_calls=[SimpleNamespace(
        index=0, id="call_1",
        function=SimpleNamespace(name=name, arguments=args))])
    yield _chunk(finish="tool_calls")


class PermissionTableTests(unittest.TestCase):
    def test_legacy_sets_are_frozen_views(self):
        from ai import permissions as pm
        from ai.approvals import CONFIRM_TOOLS
        from ai.os_mode import AUTO_TOOLS
        self.assertEqual(set(AUTO_TOOLS), set(pm.auto_tools()))
        self.assertEqual(set(CONFIRM_TOOLS), set(pm.confirm_tools()))
        self.assertFalse(set(AUTO_TOOLS) & set(CONFIRM_TOOLS))

    def test_catalog_covers_every_schema_and_vice_versa(self):
        from ai import permissions as pm
        from ai.tool_schemas import TOOL_SCHEMAS
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        self.assertEqual(names, set(pm._CATALOG))
        for name, meta in pm._CATALOG.items():
            self.assertIn(meta["tier"], ("auto", "confirm"), name)
            self.assertTrue(isinstance(meta["caps"], set), name)
            self.assertIn(meta["timeout"], (None, 30, 60, 120), name)

    def test_toggle_list_has_no_phantom_tools(self):
        # Principle 6: every user-toggleable tool must resolve to a
        # real schema + dispatcher branch (web_search and
        # read_current_page were toggles for tools that never existed).
        from ai.tool_schemas import TOOL_SCHEMAS
        from ai.tools import execute_tool
        from tools import registry as reg
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        for n in reg._ALL:
            self.assertIn(n, names, n)
        out = execute_tool("web_search", {"q": "x"})
        self.assertIn("Unknown tool", out)

    def test_capability_vocabulary(self):
        from ai import permissions as pm
        self.assertEqual(pm.capabilities_of("fs_delete"), {"fs:delete"})
        self.assertEqual(pm.capabilities_of("term_run"), {"shell:exec"})
        self.assertEqual(pm.capabilities_of("mcp__x__y"), {"mcp:invoke"})
        self.assertEqual(pm.capabilities_of("deep_search"),
                         {"network:fetch"})
        self.assertEqual(pm.timeout_of("term_run"), 30)
        self.assertEqual(pm.timeout_of("mcp__x__y"), 60)
        self.assertIsNone(pm.timeout_of("fs_read"))

    def test_decide_matrix(self):
        from ai import permissions as pm
        self.assertEqual(pm.decide("fs_read", {}, "ask"), "run")
        self.assertEqual(pm.decide("fs_write", {}, "ask"), "park")
        self.assertEqual(pm.decide("fs_write", {}, "auto"), "run")
        self.assertEqual(pm.decide("mcp__s__t", {}, "ask"), "park")
        self.assertEqual(pm.decide("mcp__s__t", {}, "auto"), "run")
        # unknown names run free in both modes: the closed dispatcher
        # cannot execute them, so the "Unknown tool" result corrects
        # the model without involving the user.
        self.assertEqual(pm.decide("mystery_tool", {}, "ask"), "run")
        self.assertEqual(pm.decide("mystery_tool", {}, "auto"), "run")
        # destructive parks even in auto mode — auto never bypasses
        self.assertEqual(
            pm.decide("term_run", {"command": "rm -rf /"}, "auto"),
            "park")
        self.assertEqual(
            pm.decide("term_run", {"command": "dir"}, "auto"), "run")

    def test_destructive_patterns(self):
        from ai import permissions as pm
        bad = ["rm -rf /", "rm -rf /*", "sudo rm -Rf ~",
               "format C:", "FORMAT d:",
               "deltree /y c:\\x", "mkfs.ext4 /dev/sda",
               "dd if=/dev/zero of=/dev/sda", "diskpart",
               "bcdedit /delete x", "shutdown /s /t 0",
               "reg delete HKLM\\SW /f",
               "del /s /q C:\\Windows\\Temp\\x",
               "rmdir /s /q C:\\Windows\\old"]
        for cmd in bad:
            self.assertTrue(pm.is_destructive("term_run",
                                             {"command": cmd}), cmd)
        good = ["dir", "format the quarterly report",
                "rm notes.txt", "shutdown the debate early",
                "echo diskpart is a tool", "git status",
                "python -c 'print(1)'"]
        for cmd in good:
            self.assertFalse(pm.is_destructive("term_run",
                                              {"command": cmd}), cmd)
        self.assertFalse(pm.is_destructive(
            "term_python", {"code": "print('rm -rf /')"}))
        self.assertFalse(pm.is_destructive("fs_delete", {"path": "x"}))


class ArgValidationTests(unittest.TestCase):
    def test_missing_required_rejected(self):
        from ai.tool_dispatch import validate_tool_args
        ok, err = validate_tool_args("fs_write", {"path": "a.txt"})
        self.assertFalse(ok)
        self.assertIn("missing required 'content'", err)

    def test_wrong_type_rejected(self):
        from ai.tool_dispatch import validate_tool_args
        ok, err = validate_tool_args("term_run", {"command": 123})
        self.assertFalse(ok)
        self.assertIn("'command' must be string", err)

    def test_integer_coerced_from_string(self):
        from ai.tool_dispatch import validate_tool_args
        ok, args = validate_tool_args("term_run", {"command": "dir",
                                                   "timeout": "30"})
        self.assertTrue(ok)
        self.assertEqual(args["timeout"], 30)

    def test_garbage_integer_rejected(self):
        from ai.tool_dispatch import validate_tool_args
        ok, err = validate_tool_args("term_run", {"command": "dir",
                                                  "timeout": "soon"})
        self.assertFalse(ok)
        self.assertIn("must be integer", err)

    def test_valid_passes_through(self):
        from ai.tool_dispatch import validate_tool_args
        ok, args = validate_tool_args(
            "fs_replace", {"path": "a", "old": "x", "new": "y"})
        self.assertTrue(ok)
        self.assertEqual(args["new"], "y")

    def test_mcp_and_unknown_skip_strict_checks(self):
        from ai.tool_dispatch import validate_tool_args
        ok, _ = validate_tool_args("mcp__s__t", {"anything": 1})
        self.assertTrue(ok)
        ok, err = validate_tool_args("fs_write", "not-a-dict")
        self.assertFalse(ok)
        self.assertIn("not an object", err)

    def test_invalid_args_audited_as_fail(self):
        from system import audit as trail
        tmp = Path(tempfile.mkdtemp()) / "audit.log"
        with mock.patch.object(trail, "_FILE", tmp):
            from ai.tools import execute_tool
            out = execute_tool("fs_write", {"path": "a"})
        self.assertIn("invalid arguments", out)
        lines = tmp.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("FAIL", lines[0])
        self.assertIn("fs_write", lines[0])


class RedactionTests(unittest.TestCase):
    def setUp(self):
        import ai.client as ac
        self.ac = ac
        ac._cooling.clear()
        self.addCleanup(ac._cooling.clear)
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(
            ac, "pick_model", return_value="primary-model"))
        stack.enter_context(mock.patch.object(
            ac, "resolve_client", return_value=object()))
        stack.enter_context(mock.patch.object(
            ac, "extra_provider_names", return_value=[]))
        stack.enter_context(mock.patch.object(
            ac, "FALLBACK_CHAIN", ["backup-model"]))
        stack.enter_context(mock.patch.object(
            ac, "current_mood",
            return_value=SimpleNamespace(temperature=0.7, max_tokens=100,
                                         use_reasoner=False,
                                         prefer_fastest=False)))
        stack.enter_context(mock.patch("memory.get_pref",
                                       return_value="auto"))
        self.addCleanup(stack.close)

    def test_secrets_redacted_before_model_and_display(self):
        calls = []

        def open_stream(model, messages, schemas, mood, client=None):
            calls.append(list(messages))
            if len(calls) > 1:
                return _stream_of("done")
            return _tool_call_stream("outcome_stats", "{}")

        c = self.ac.AIClient.__new__(self.ac.AIClient)
        c._client = object()
        c._system_prompt = lambda: "system prompt"
        c._last_user_text = lambda msgs: msgs[-1]["content"]
        c._open_stream = open_stream
        leak = "token sk-abcdefgh1234 in result"
        with mock.patch.object(self.ac, "execute_tool",
                               return_value=leak):
            pieces = list(c.stream([{"role": "user", "content": "hi"}],
                                   tools=[{"dummy": True}]))
        tr = next(p for k, p in pieces if k == "tool_result")
        self.assertNotIn("sk-abcdefgh1234", tr["result"])
        self.assertIn("sk-***", tr["result"])
        tool_msgs = [m for m in calls[-1] if m.get("role") == "tool"]
        self.assertNotIn("sk-abcdefgh1234", tool_msgs[0]["content"])


class SubagentBoundsTests(unittest.TestCase):
    def test_pool_caps_workers_at_two(self):
        from ai.agent_pool import run_parallel
        live, peak = [], [0]
        lock = threading.Lock()

        def worker(t):
            with lock:
                live.append(1)
                peak[0] = max(peak[0], len(live))
            time.sleep(0.05)
            with lock:
                live.pop()
            return {"ok": True}

        out = run_parallel(["a", "b", "c", "d"], worker,
                           timeout_per_task=5, max_workers=2)
        self.assertEqual(len(out), 4)
        self.assertTrue(all(r["ok"] for r in out))
        self.assertLessEqual(peak[0], 2)

    def test_stragglers_become_timeouts_not_errors(self):
        from ai.agent_pool import run_parallel

        def stuck(t):
            time.sleep(13)  # outlasts the 11s backstop, then joined
            return {"ok": True}

        out = run_parallel(["x"], stuck, timeout_per_task=1)
        self.assertFalse(out[0]["ok"])
        self.assertEqual(out[0]["error"], "timeout")

    def test_merge_evidence_truncated(self):
        from ai import agents as ag
        seen = []

        class Cap:
            def create(self, **kw):
                seen.append(kw)
                return SimpleNamespace(
                    choices=[SimpleNamespace(
                        message=SimpleNamespace(
                            content="Combined."))])

        fake = SimpleNamespace(default_model="m",
                               _client=SimpleNamespace(
                                   chat=SimpleNamespace(completions=Cap())))
        results = [{"ok": True, "task": f"t{i}",
                    "answer": "w" * 3000} for i in range(3)]
        with mock.patch("ai.client.get_client", return_value=fake):
            out = ag._merge("compare three things", results)
        self.assertEqual(out, "Combined.")
        user = " ".join(m.get("content", "")
                        for m in seen[-1]["messages"])
        self.assertIn("[sub-agent evidence truncated]", user)
        self.assertLess(len(user), 6000)

    def test_agent_lifecycle_audited(self):
        from system import audit as trail
        tmp = Path(tempfile.mkdtemp()) / "audit.log"
        from ai import agents as ag
        with mock.patch.object(trail, "_FILE", tmp), \
                mock.patch.object(ag, "_plan_split", return_value=[]), \
                mock.patch.object(ag, "_run_one",
                                  return_value={"ok": True, "task": "t",
                                                "answer": "a"}):
            res = ag.run("compare apples and oranges in detail")
        self.assertTrue(res["ok"])
        text = tmp.read_text(encoding="utf-8")
        self.assertIn("subagent_spawned", text)
        self.assertIn("subagent_completed", text)


if __name__ == "__main__":
    unittest.main()
