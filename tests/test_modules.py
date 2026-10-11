"""system.modules — the extensibility framework behind the MODULES tab.

Covers: manifest schema validation, the shipped starter library, install
from folder/zip (incl. zip-slip and size guards), activation with real
skill registration + rollback, MCP server wiring, failed states, update
status, boot wiring, and the /api/modules routes.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from system import modules as modsys

_ROOT = Path(modsys.__file__).resolve().parent.parent

SKILL_SRC = '''"""Demo skill module."""
from skills.registry import register


@register("demo_mod_skill", [
    r"^demo\\s+module\\s+go[\\.\\?\\!]?$",
], "Demo skill")
def skill_demo(text, match):
    return "demo ok"
'''

OTHER_SRC = '''"""Registers a skill OTHER than the declared one."""
from skills.registry import register


@register("other_mod_skill", [
    r"^other\\s+module\\s+go[\\.\\?\\!]?$",
], "Other skill")
def skill_other(text, match):
    return "other ok"
'''

CRASH_SRC = '''"""Valid skill, then a crash at import time."""
from skills.registry import register


@register("demo_mod_skill", [
    r"^demo\\s+module\\s+go[\\.\\?\\!]?$",
], "Demo skill")
def skill_demo(text, match):
    return "demo ok"


raise RuntimeError("kaput at import")
'''

EVAL_SRC = '''"""Cheating module: tries to eval."""
from skills.registry import register


@register("demo_mod_skill", [
    r"^demo\\s+module\\s+go$",
], "Demo skill")
def skill_demo(text, match):
    return eval("1 + 1")
'''


def _manifest(**over):
    base = {"schema": 1, "id": "demo_mod", "name": "Demo Module",
            "version": "1.0.0", "description": "A demo module for tests.",
            "entry": "skill.py", "skills": ["demo_mod_skill"],
            "capabilities": ["do demo things"], "permissions": ["none"],
            "examples": [{"phrase": "demo module go", "reply": "demo ok"}]}
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


def _write_module(root: Path, manifest: dict, src=SKILL_SRC):
    d = root / manifest["id"]
    d.mkdir(parents=True)
    (d / "module.json").write_text(json.dumps(manifest), encoding="utf-8")
    if src is not None:
        (d / (manifest.get("entry") or "skill.py")).write_text(
            src, encoding="utf-8")
    (d / "README.md").write_text("# Demo\n\ndocs live here\n",
                                 encoding="utf-8")
    return d


def _shipped_dirs():
    root = _ROOT / "modules"
    return [c for c in sorted(root.iterdir())
            if c.is_dir() and not c.name.startswith(("_", "."))]


class _TempRoot(unittest.TestCase):
    """Points ROOT/STATE/CATALOG at a throwaway folder for the test."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="jarvis_mods_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for name, val in (("_ROOT", self.tmp),
                          ("_STATE", self.tmp / "state.json"),
                          ("_CATALOG", self.tmp / "catalog.json")):
            patcher = mock.patch.object(modsys, name, val)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        # A registered test skill must never leak into the shared
        # registry (other suites count and dispatch skills).
        from skills import registry
        for n in ("demo_mod_skill", "other_mod_skill"):
            registry.unregister(n)
        sys.modules.pop("jarvis_module_demo_mod", None)
        sys.modules.pop("jarvis_module_demo_mcp", None)


class ManifestSchemaTests(unittest.TestCase):
    def test_valid_manifest_derives_kind(self):
        m = modsys.validate_manifest(_manifest())
        self.assertEqual(m["kind"], "skill")

    def test_missing_description_rejected(self):
        with self.assertRaises(modsys.ModuleError) as ctx:
            modsys.validate_manifest(_manifest(description=""))
        self.assertIn("description", str(ctx.exception))

    def test_bad_id_rejected(self):
        with self.assertRaises(modsys.ModuleError):
            modsys.validate_manifest(_manifest(id="Bad Name!"))

    def test_non_semver_rejected(self):
        with self.assertRaises(modsys.ModuleError):
            modsys.validate_manifest(_manifest(version="v1"))

    def test_unknown_permission_rejected(self):
        with self.assertRaises(modsys.ModuleError) as ctx:
            modsys.validate_manifest(_manifest(permissions=["root"]))
        self.assertIn("unknown permission", str(ctx.exception))

    def test_none_cannot_mix_with_other_permissions(self):
        with self.assertRaises(modsys.ModuleError):
            modsys.validate_manifest(
                _manifest(permissions=["none", "network"]))

    def test_skill_module_requires_entry(self):
        with self.assertRaises(modsys.ModuleError):
            modsys.validate_manifest(_manifest(entry=None))

    def test_entry_must_be_plain_file_name(self):
        with self.assertRaises(modsys.ModuleError):
            modsys.validate_manifest(_manifest(entry="../evil.py"))

    def test_mcp_module_requires_command(self):
        with self.assertRaises(modsys.ModuleError):
            modsys.validate_manifest(_manifest(
                kind="mcp", entry=None,
                mcp={"name": "srv", "args": []}))

    def test_mcp_command_shell_metachars_rejected(self):
        with self.assertRaises(modsys.ModuleError) as ctx:
            modsys.validate_manifest(_manifest(
                kind="mcp", entry=None,
                mcp={"name": "srv", "command": "npx; rm -rf ~"}))
        self.assertIn("unsafe", str(ctx.exception))

    def test_every_permission_is_documented(self):
        for perm in modsys.PERMISSIONS.values():
            self.assertTrue(perm)


class StarterLibraryTests(unittest.TestCase):
    """The shipped library must be real: working code, docs, declared
    permissions — no placeholders."""

    def kinds(self):
        out = {}
        for d in _shipped_dirs():
            m = json.loads((d / "module.json").read_text(encoding="utf-8"))
            out[d.name] = m
        return out

    def test_starter_library_has_real_depth(self):
        kinds = [m.get("kind") or ("mcp" if m.get("mcp") else "skill")
                 for m in self.kinds().values()]
        self.assertGreaterEqual(kinds.count("skill"), 5)
        self.assertGreaterEqual(kinds.count("mcp"), 3)

    def test_every_starter_declares_docs_examples_and_permissions(self):
        for name, m in self.kinds().items():
            docs = m.get("docs", "README.md")
            self.assertTrue((_ROOT / "modules" / name / docs).is_file(),
                            f"{name} ships no docs")
            self.assertTrue(m.get("examples"), f"{name} has no examples")
            self.assertTrue(m.get("capabilities"), f"{name} has no caps")
            for p in m.get("permissions", []):
                self.assertIn(p, modsys.PERMISSIONS, f"{name}: {p}")

    def test_every_starter_skill_entry_passes_the_plugin_validator(self):
        from skills.auto_generator import _validate  # registry loads skills
        for d in _shipped_dirs():
            m = json.loads((d / "module.json").read_text(encoding="utf-8"))
            if m.get("mcp") or m.get("kind") == "mcp":
                continue
            info = _validate((d / m["entry"]).read_text(encoding="utf-8"))
            self.assertTrue(info["name"])

    def test_every_starter_folder_validates_clean(self):
        for d in _shipped_dirs():
            res = modsys.validate_module_dir(d)
            self.assertEqual(res["manifest"]["id"], d.name)

    def test_starter_mcp_specs_name_real_servers(self):
        for name, m in self.kinds().items():
            if not m.get("mcp") and m.get("kind") != "mcp":
                continue
            spec = m["mcp"]
            self.assertTrue(spec.get("command"), name)
            self.assertRegex(spec["command"], modsys._CMD_RE)
            self.assertTrue(spec.get("args"), name)

    def test_catalog_snapshot_matches_shipped_modules(self):
        cat = json.loads((_ROOT / "modules" / "catalog.json")
                         .read_text(encoding="utf-8"))
        listed = set(cat["modules"])
        shipped = set(self.kinds())
        self.assertEqual(listed, shipped)


class ScanStateTests(_TempRoot):
    def test_scan_seeds_shipped_default_enabled(self):
        _write_module(self.tmp, _manifest())
        mods = modsys.scan()
        self.assertEqual(len(mods), 1)
        self.assertTrue(mods[0]["enabled"])
        self.assertEqual(mods[0]["state"], "active")

    def test_scan_marks_broken_manifest_failed(self):
        d = self.tmp / "broken_mod"
        d.mkdir()
        (d / "module.json").write_text("{not json", encoding="utf-8")
        mods = modsys.scan()
        self.assertEqual(mods[0]["state"], "failed")
        self.assertIn("JSON", mods[0]["error"])

    def test_scan_skips_template_folders(self):
        _write_module(self.tmp, _manifest())
        (self.tmp / "_template_skill").mkdir()
        self.assertEqual(len(modsys.scan()), 1)

    def test_folder_id_mismatch_is_failed_with_reason(self):
        d = self.tmp / "wrong_name"
        d.mkdir()
        (d / "module.json").write_text(json.dumps(_manifest()),
                                      encoding="utf-8")
        mods = modsys.scan()
        self.assertEqual(mods[0]["state"], "failed")
        self.assertIn("match the folder", mods[0]["error"])


class InstallTests(_TempRoot):
    def test_install_from_folder_activates_and_registers(self):
        src = Path(tempfile.mkdtemp(prefix="jarvis_mod_src_"))
        self.addCleanup(shutil.rmtree, src, True)
        _write_module(src, _manifest())
        res = modsys.install(str(src / "demo_mod"))
        self.assertTrue(res["ok"])
        self.assertEqual(res["state"], "active")
        self.assertIn("demo_mod_skill", res["skills"])
        self.assertTrue((self.tmp / "demo_mod").is_dir())
        from skills import registry
        self.assertIsNotNone(registry.get_skill("demo_mod_skill"))

    def test_install_rejects_invalid_manifest_before_copying(self):
        src = Path(tempfile.mkdtemp(prefix="jarvis_mod_src_"))
        self.addCleanup(shutil.rmtree, src, True)
        bad = _write_module(src, _manifest(permissions=["root"]))
        with self.assertRaises(modsys.ModuleError):
            modsys.install(str(bad))
        self.assertFalse((self.tmp / "demo_mod").exists())
        self.assertEqual(modsys.scan(), [])

    def test_install_rejects_code_with_blocked_calls(self):
        src = Path(tempfile.mkdtemp(prefix="jarvis_mod_src_"))
        self.addCleanup(shutil.rmtree, src, True)
        bad = _write_module(src, _manifest(), src=EVAL_SRC)
        with self.assertRaises(modsys.ModuleError) as ctx:
            modsys.install(str(bad))
        self.assertIn("rejected", str(ctx.exception))
        self.assertFalse((self.tmp / "demo_mod").exists())

    def test_install_duplicate_rejected(self):
        src = Path(tempfile.mkdtemp(prefix="jarvis_mod_src_"))
        self.addCleanup(shutil.rmtree, src, True)
        _write_module(src, _manifest())
        modsys.install(str(src / "demo_mod"), activate_now=False)
        with self.assertRaises(modsys.ModuleError):
            modsys.install(str(src / "demo_mod"))

    def test_install_from_zip_roundtrip(self):
        src = Path(tempfile.mkdtemp(prefix="jarvis_mod_src_"))
        self.addCleanup(shutil.rmtree, src, True)
        folder = _write_module(src, _manifest())
        zpath = src / "demo_mod.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            for f in folder.rglob("*"):
                if f.is_file():
                    z.write(f, f.relative_to(folder))
        res = modsys.install(str(zpath))
        self.assertTrue(res["ok"])
        self.assertEqual(res["state"], "active")

    def test_zip_slip_rejected(self):
        zpath = self.tmp / "evil.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("../evil.py", "print('nope')")
            z.writestr("module.json", json.dumps(_manifest()))
        with self.assertRaises(modsys.ModuleError) as ctx:
            modsys.install(str(zpath))
        self.assertIn("unsafe path", str(ctx.exception))
        self.assertFalse((self.tmp.parent / "evil.py").exists())

    def test_zip_without_manifest_rejected(self):
        zpath = self.tmp / "empty.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("readme.txt", "nothing here")
        with self.assertRaises(modsys.ModuleError):
            modsys.install(str(zpath))

    def test_install_nonexistent_path_rejected(self):
        with self.assertRaises(modsys.ModuleError):
            modsys.install(str(self.tmp / "nope"))


class ActivationTests(_TempRoot):
    def test_activate_then_deactivate_leaves_no_skill_behind(self):
        _write_module(self.tmp, _manifest())
        from skills import registry
        res = modsys.activate("demo_mod")
        self.assertTrue(res["ok"])
        self.assertIsNotNone(registry.get_skill("demo_mod_skill"))
        off = modsys.deactivate("demo_mod")
        self.assertEqual(off["state"], "inactive")
        self.assertIsNone(registry.get_skill("demo_mod_skill"))
        self.assertNotIn("jarvis_module_demo_mod", sys.modules)

    def test_activation_crash_recorded_as_failed(self):
        _write_module(self.tmp, _manifest(skills=None), src=CRASH_SRC)
        with self.assertRaises(modsys.ModuleError) as ctx:
            modsys.activate("demo_mod")
        self.assertIn("kaput", str(ctx.exception))
        mods = modsys.scan()
        self.assertEqual(mods[0]["state"], "failed")
        self.assertIn("kaput", mods[0]["error"])
        from skills import registry
        self.assertIsNone(registry.get_skill("demo_mod_skill"))

    def test_declared_skills_must_register(self):
        _write_module(self.tmp, _manifest(), src=OTHER_SRC)
        with self.assertRaises(modsys.ModuleError) as ctx:
            modsys.activate("demo_mod")
        self.assertIn("did not register", str(ctx.exception))
        from skills import registry
        self.assertIsNone(registry.get_skill("other_mod_skill"))

    def test_activate_unknown_module_raises(self):
        with self.assertRaises(modsys.ModuleError):
            modsys.activate("ghost")

    def test_deactivate_unknown_module_raises(self):
        with self.assertRaises(modsys.ModuleError):
            modsys.deactivate("ghost")

    def test_activate_idempotent_no_duplicates(self):
        _write_module(self.tmp, _manifest())
        modsys.activate("demo_mod")
        res = modsys.activate("demo_mod")
        self.assertTrue(res.get("already"))
        from skills import registry
        hits = [s for s in registry.all_skills()
                if s.name == "demo_mod_skill"]
        self.assertEqual(len(hits), 1)


class McpActivationTests(_TempRoot):
    def _mcp_module(self):
        return _write_module(self.tmp, _manifest(
            id="demo_mcp", name="Demo MCP", kind="mcp", entry=None,
            skills=None,
            mcp={"name": "demo-srv", "command": "uvx",
                 "args": ["demo-server"], "auto_start": True},
            permissions=["network"]), src=None)

    def test_activate_mcp_adds_declared_server(self):
        self._mcp_module()
        with mock.patch("mcp.manager.all_servers", return_value=[]), \
             mock.patch("mcp.manager.add_server",
                        return_value={"id": "s1", "name": "demo-srv"}
                        ) as add, \
             mock.patch("mcp.runtime.start_server", return_value=True):
            res = modsys.activate("demo_mcp")
        self.assertTrue(res["ok"])
        add.assert_called_once_with("demo-srv", "uvx", ["demo-server"],
                                    enabled=True)
        self.assertEqual(res["server"], "demo-srv")

    def test_mcp_needs_key_starts_nothing(self):
        _write_module(self.tmp, _manifest(
            id="demo_mcp", name="Demo MCP", kind="mcp", entry=None,
            skills=None,
            mcp={"name": "demo-srv", "command": "npx",
                 "args": ["-y", "demo"], "env": {"DEMO_API_KEY": ""},
                 "auto_start": True},
            permissions=["network"]), src=None)
        with mock.patch("mcp.manager.all_servers", return_value=[]), \
             mock.patch("mcp.manager.add_server",
                        return_value={"id": "s1", "name": "demo-srv"}), \
             mock.patch("mcp.runtime.start_server") as start:
            res = modsys.activate("demo_mcp")
        start.assert_not_called()
        self.assertTrue(res["needs_key"])

    def test_deactivate_mcp_removes_server(self):
        self._mcp_module()
        with mock.patch("mcp.manager.all_servers",
                        return_value=[{"id": "s1", "name": "demo-srv"}]), \
             mock.patch("mcp.manager.add_server",
                        return_value={"id": "s1", "name": "demo-srv"}), \
             mock.patch("mcp.manager.remove_server",
                        return_value=True) as rm, \
             mock.patch("mcp.runtime.start_server", return_value=True), \
             mock.patch("mcp.runtime.stop_server", return_value=True):
            modsys.activate("demo_mcp")
            modsys.deactivate("demo_mcp")
        rm.assert_called_once_with("s1")


class UninstallTests(_TempRoot):
    def test_uninstall_removes_folder_and_state(self):
        _write_module(self.tmp, _manifest())
        modsys.activate("demo_mod")
        res = modsys.uninstall("demo_mod")
        self.assertTrue(res["ok"])
        self.assertTrue(res["deleted"])
        self.assertFalse((self.tmp / "demo_mod").exists())
        self.assertEqual(modsys.scan(), [])

    def test_uninstall_unknown_module_raises(self):
        with self.assertRaises(modsys.ModuleError):
            modsys.uninstall("ghost")


class UpdateTests(_TempRoot):
    def test_update_flagged_when_catalog_newer(self):
        _write_module(self.tmp, _manifest())
        (self.tmp / "catalog.json").write_text(
            json.dumps({"modules": {"demo_mod": "2.0.0"}}),
            encoding="utf-8")
        mods = modsys.scan()
        self.assertTrue(mods[0]["update"]["available"])
        self.assertEqual(mods[0]["update"]["latest"], "2.0.0")

    def test_no_update_when_current(self):
        _write_module(self.tmp, _manifest())
        (self.tmp / "catalog.json").write_text(
            json.dumps({"modules": {"demo_mod": "1.0.0"}}),
            encoding="utf-8")
        self.assertFalse(modsys.scan()[0]["update"]["available"])


class BootTests(_TempRoot):
    def test_boot_load_counts_active_and_never_raises(self):
        _write_module(self.tmp, _manifest())
        broken = self.tmp / "broken_mod"
        broken.mkdir()
        (broken / "module.json").write_text("{oops", encoding="utf-8")
        summary = modsys.boot_load()
        self.assertIn("1 module(s) active", summary)
        self.assertIn("1 failed", summary)

    def test_boot_load_with_empty_root(self):
        self.assertEqual(modsys.boot_load(), "0 module(s) active")

    def test_modules_service_registered_in_both_modes(self):
        from system import services
        for mode in ("console", "desktop"):
            names = {s.name for s in services._specs(mode)}
            self.assertIn("modules", names, mode)


class ApiTests(_TempRoot):
    def setUp(self):
        super().setUp()
        _write_module(self.tmp, _manifest())
        from server import create_app
        app = create_app()
        app.testing = True
        self.client = app.test_client()

    def test_modules_list_shape(self):
        r = self.client.get("/api/modules")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["counts"]["total"], 1)
        self.assertEqual(data["counts"]["active"], 1)
        self.assertIn("none", data["permissions"])
        self.assertEqual(data["modules"][0]["id"], "demo_mod")

    def test_detail_includes_docs_text(self):
        r = self.client.get("/api/modules/demo_mod")
        self.assertEqual(r.status_code, 200)
        self.assertIn("docs", r.get_json()["docs_text"])

    def test_detail_unknown_module_is_400(self):
        r = self.client.get("/api/modules/ghost")
        self.assertEqual(r.status_code, 400)

    def test_toggle_missing_id_is_400(self):
        r = self.client.post("/api/modules/toggle", json={})
        self.assertEqual(r.status_code, 400)

    def test_toggle_off_then_on(self):
        r = self.client.post("/api/modules/toggle",
                             json={"id": "demo_mod", "enabled": False})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["state"], "inactive")
        r = self.client.post("/api/modules/toggle",
                             json={"id": "demo_mod", "enabled": True})
        self.assertEqual(r.get_json()["state"], "active")

    def test_install_missing_path_is_400(self):
        r = self.client.post("/api/modules/install", json={})
        self.assertEqual(r.status_code, 400)

    def test_install_invalid_path_is_400_with_reason(self):
        r = self.client.post("/api/modules/install",
                             json={"path": str(self.tmp / "nope")})
        self.assertEqual(r.status_code, 400)
        self.assertIn("no such path", r.get_json()["detail"])

    def test_validate_reports_rejection_without_installing(self):
        r = self.client.post("/api/modules/validate",
                             json={"path": str(self.tmp / "nope")})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("no such path", data["error"])
        self.assertEqual(len(modsys.scan()), 1)

    def test_uninstall_missing_id_is_400(self):
        r = self.client.post("/api/modules/uninstall", json={})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
