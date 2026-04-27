import json
import os
import re
import unittest
import uuid
from unittest.mock import patch, MagicMock

import cloudinary
import cloudinary.api
from click.testing import CliRunner

from cloudinary_cli.cli import cli


class TestCLISettings(unittest.TestCase):
    runner = CliRunner()

    def test_parse_picks_all_sentinels(self):
        from cloudinary_cli.modules.settings.utils.pick import (
            parse_picks,
            SMD_PICK_ALL_SENTINEL,
            TRANSFORMATIONS_PICK_ALL_SENTINEL,
        )

        selected_components, smd_fields, smd_rules, transformation_names = parse_picks([
            ("smd", "field", "all"),
            ("smd", "rule", "*"),
            ("transformations", "name", "all"),
        ])

        self.assertEqual(["smd", "transformations"], selected_components)
        self.assertEqual([SMD_PICK_ALL_SENTINEL], smd_fields)
        self.assertEqual([SMD_PICK_ALL_SENTINEL], smd_rules)
        self.assertEqual([TRANSFORMATIONS_PICK_ALL_SENTINEL], transformation_names)

    def test_export_smd_bundle_all_rules_includes_referenced_fields(self):
        # All rules selected should include only referenced fields (metadata_field_id + controlling_ids)
        from cloudinary_cli.modules.settings.providers import smd as smd_provider

        mock_rules = [
            {"name": "r1", "metadata_field_id": "A", "controlling_ids": ["B"]},
            {"name": "r2", "metadata_field_id": "B", "controlling_ids": []},
        ]
        mock_fields = [
            {"external_id": "A", "type": "string", "label": "A"},
            {"external_id": "B", "type": "string", "label": "B"},
            {"external_id": "C", "type": "string", "label": "C"},
        ]

        def fake_call_api_with_pagination(func, kwargs=None, force=False):
            if func == smd_provider.cloudinary.api.list_metadata_fields:
                return {"metadata_fields": mock_fields}
            if func == smd_provider.cloudinary.api.list_metadata_rules:
                return {"metadata_rules": mock_rules}
            raise AssertionError("unexpected function passed to call_api_with_pagination")

        with patch.object(smd_provider, "call_api_with_pagination", side_effect=fake_call_api_with_pagination):
            bundle = smd_provider.export_smd_bundle(rule_names=["__ALL__"])

        field_ids = {f.get("external_id") for f in bundle["fields"]}
        self.assertEqual({"A", "B"}, field_ids)
        self.assertEqual(2, len(bundle["rules"]))

    def test_export_smd_bundle_rule_wildcard(self):
        from cloudinary_cli.modules.settings.providers import smd as smd_provider

        mock_rules = [
            {"name": "prefix one", "metadata_field_id": "A", "controlling_ids": []},
            {"name": "prefix two", "metadata_field_id": "B", "controlling_ids": []},
            {"name": "other", "metadata_field_id": "C", "controlling_ids": []},
        ]
        mock_fields = [
            {"external_id": "A", "type": "string", "label": "A"},
            {"external_id": "B", "type": "string", "label": "B"},
            {"external_id": "C", "type": "string", "label": "C"},
        ]

        def fake_call_api_with_pagination(func, kwargs=None, force=False):
            if func == smd_provider.cloudinary.api.list_metadata_fields:
                return {"metadata_fields": mock_fields}
            if func == smd_provider.cloudinary.api.list_metadata_rules:
                return {"metadata_rules": mock_rules}
            raise AssertionError("unexpected function passed to call_api_with_pagination")

        with patch.object(smd_provider, "call_api_with_pagination", side_effect=fake_call_api_with_pagination):
            bundle = smd_provider.export_smd_bundle(rule_names=["prefix*"])

        rule_names = {r.get("name") for r in bundle["rules"]}
        self.assertEqual({"prefix one", "prefix two"}, rule_names)

    def test_settings_save_out_file_is_pretty_and_file_only(self):
        # Ensure save --out writes pretty JSON and doesn't try to write to the store path.
        from cloudinary_cli.modules.settings import commands as settings_commands

        with self.runner.isolated_filesystem():
            fake_cloudinary_cfg = MagicMock()
            fake_cloudinary_cfg.cloud_name = "demo-cloud"

            with patch.object(settings_commands.cloudinary, "config", return_value=fake_cloudinary_cfg), \
                 patch.object(settings_commands, "export_smd_bundle", return_value={"fields": [], "rules": []}), \
                 patch.object(settings_commands, "ensure_settings_store_dirs", return_value=os.getcwd()), \
                 patch.object(settings_commands, "get_settings_store_snapshot_path", side_effect=AssertionError("store path should not be used when --out is set")):
                result = self.runner.invoke(cli, [
                    "settings", "save",
                    "--component", "smd",
                    "--out", "out.json",
                    "-F",
                ])

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertTrue(os.path.exists("out.json"))

            with open("out.json", "r", encoding="utf-8") as f:
                raw = f.read()
            # Pretty JSON should contain newlines and indentation.
            self.assertTrue(raw.startswith("{\n"))
            self.assertIn('\n  "schema_version":', raw)

            parsed = json.loads(raw)
            self.assertEqual("demo-cloud", parsed["source"]["cloud_name"])
            # v2 envelope additions
            self.assertEqual(2, parsed["schema_version"])
            self.assertIn("lineage", parsed)
            self.assertIn("serial", parsed)
            self.assertIn("writer", parsed)
            self.assertIn("checksum", parsed)
            self.assertIn("fingerprints", parsed)

    def test_settings_smd_delete_no_picks_deletes_all(self):
        # No --pick means delete all (rules first, then fields).
        from cloudinary_cli.modules.settings.providers import smd as smd_provider

        calls = []

        def record_rule(rule_external_id, _opts):
            calls.append(("rule", rule_external_id))

        def record_field(field_external_id, _opts):
            calls.append(("field", field_external_id))

        with patch.object(smd_provider, "_list_target_fields", return_value={"f1": {}, "f2": {}}), \
             patch.object(smd_provider, "_list_target_rules", return_value={"r1": {"external_id": "er1"}, "r2": {"external_id": "er2"}}), \
             patch.object(smd_provider, "_delete_rule", side_effect=record_rule), \
             patch.object(smd_provider, "_delete_field", side_effect=record_field):
            result = self.runner.invoke(cli, ["settings", "smd", "delete", "-F"])

        self.assertEqual(0, result.exit_code, msg=result.output)
        # Expect both rules deleted before any fields.
        self.assertEqual([("rule", "er1"), ("rule", "er2"), ("field", "f1"), ("field", "f2")], calls)

    # -------------------------------------------------------------------
    # P1+P2: pick parsing for new components
    # -------------------------------------------------------------------

    def test_parse_picks_new_components(self):
        from cloudinary_cli.modules.settings.utils.pick import (
            parse_picks,
            UPLOAD_PRESETS_PICK_ALL_SENTINEL,
            STREAMING_PROFILES_PICK_ALL_SENTINEL,
            UPLOAD_MAPPINGS_PICK_ALL_SENTINEL,
        )

        picks = parse_picks([
            ("upload_presets", "name", "all"),
            ("upload_presets", "name", "checkout-*"),
            ("streaming_profiles", "name", "*"),
            ("upload_mappings", "folder", "incoming/"),
        ])

        self.assertEqual(
            ["streaming_profiles", "upload_mappings", "upload_presets"],
            picks.selected_components,
        )
        self.assertEqual(
            [UPLOAD_PRESETS_PICK_ALL_SENTINEL, "checkout-*"],
            picks.upload_preset_names,
        )
        self.assertEqual([STREAMING_PROFILES_PICK_ALL_SENTINEL], picks.streaming_profile_names)
        self.assertEqual(["incoming/"], picks.upload_mapping_folders)
        self.assertEqual(UPLOAD_MAPPINGS_PICK_ALL_SENTINEL, "__ALL_UPLOAD_MAPPINGS__")

        # `for_component()` exposes the per-component lists.
        self.assertEqual(picks.upload_preset_names, picks.for_component("upload_presets"))
        self.assertEqual(picks.streaming_profile_names, picks.for_component("streaming_profiles"))
        self.assertEqual(picks.upload_mapping_folders, picks.for_component("upload_mappings"))

    def test_parse_picks_unsupported_group_raises(self):
        import click
        from cloudinary_cli.modules.settings.utils.pick import parse_picks

        with self.assertRaises(click.UsageError):
            parse_picks([("nonsense", "name", "x")])

    # -------------------------------------------------------------------
    # P2: snapshot envelope v2 + v1 backcompat
    # -------------------------------------------------------------------

    def test_envelope_v2_make_finalize_round_trip(self):
        from cloudinary_cli.modules.settings.utils import envelope as env_mod

        env = env_mod.make_envelope(
            name="alpha",
            cloud_name="demo",
            components=["smd", "transformations"],
            metadata={"notes": "hi", "tags": ["t1", "t2"]},
        )
        self.assertEqual(2, env["schema_version"])
        self.assertEqual("settings_snapshot", env["type"])
        self.assertEqual(["smd", "transformations"], env["components"])
        self.assertEqual(1, env["serial"])
        self.assertIn("lineage", env)
        self.assertIn("created_at", env)
        self.assertIn("writer", env)
        self.assertIn("cli_version", env["writer"])
        self.assertEqual({"notes": "hi", "tags": ["t1", "t2"]}, env["metadata"])

        env["smd"] = {"fields": [{"external_id": "x"}], "rules": []}
        env["transformations"] = {"transformations": []}
        env_mod.finalize_envelope(env, ["smd", "transformations"])

        self.assertIn("fingerprints", env)
        self.assertIn("checksum", env)
        self.assertTrue(env["checksum"].startswith("sha256:"))
        self.assertSetEqual({"smd", "transformations"}, set(env["fingerprints"].keys()))
        # Each component fingerprint is sha256 of its canonical bundle.
        self.assertTrue(env["fingerprints"]["smd"].startswith("sha256:"))

        # Mutating a component bundle must change its fingerprint and the checksum.
        prev_fp = env["fingerprints"]["smd"]
        prev_cs = env["checksum"]
        env["smd"]["fields"].append({"external_id": "y"})
        env_mod.finalize_envelope(env, ["smd", "transformations"])
        self.assertNotEqual(prev_fp, env["fingerprints"]["smd"])
        self.assertNotEqual(prev_cs, env["checksum"])

    def test_envelope_load_v1_snapshot_upgrades_in_memory(self):
        from cloudinary_cli.modules.settings.utils.envelope import load_snapshot

        v1 = {
            "schema_version": 1,
            "name": "old",
            "source": {"cloud_name": "legacy"},
            "smd": {"fields": [], "rules": []},
            "components": ["smd"],
        }
        upgraded = load_snapshot(v1)
        self.assertEqual(1, upgraded["schema_version"])  # preserved
        self.assertEqual("settings_snapshot", upgraded["type"])
        self.assertIsNone(upgraded["lineage"])
        self.assertIsNone(upgraded["serial"])
        self.assertIsNone(upgraded["writer"])
        self.assertEqual({"notes": None, "tags": []}, upgraded["metadata"])
        self.assertEqual({"components": ["smd"], "picks": []}, upgraded["selection"])

    def test_envelope_previous_serial_for_lineage(self):
        from cloudinary_cli.modules.settings.utils import envelope as env_mod

        with self.runner.isolated_filesystem():
            self.assertEqual((None, 0), env_mod.previous_serial_for_lineage("missing.json"))
            self.assertEqual((None, 0), env_mod.previous_serial_for_lineage(None))

            with open("snap.json", "w", encoding="utf-8") as f:
                json.dump({"lineage": "abc-123", "serial": 4}, f)
            self.assertEqual(("abc-123", 4), env_mod.previous_serial_for_lineage("snap.json"))

    # -------------------------------------------------------------------
    # P2: dirstore round-trip
    # -------------------------------------------------------------------

    def test_dirstore_round_trip(self):
        from cloudinary_cli.modules.settings.utils.dirstore import (
            read_snapshot_dir,
            write_snapshot_dir,
        )

        with self.runner.isolated_filesystem():
            snapshot = {
                "schema_version": 2,
                "name": "rt",
                "components": ["smd", "upload_presets"],
                "smd": {"fields": [{"external_id": "a"}], "rules": []},
                "upload_presets": {"presets": [{"name": "p1", "unsigned": False, "settings": {}}]},
            }
            write_snapshot_dir("d", snapshot, ["smd", "upload_presets", "transformations"])

            self.assertTrue(os.path.exists(os.path.join("d", "_index.json")))
            self.assertTrue(os.path.exists(os.path.join("d", "smd.json")))
            self.assertTrue(os.path.exists(os.path.join("d", "upload_presets.json")))
            # Missing components don't create empty files.
            self.assertFalse(os.path.exists(os.path.join("d", "transformations.json")))

            # Index has envelope only — never component bundles.
            with open(os.path.join("d", "_index.json"), "r", encoding="utf-8") as f:
                idx = json.load(f)
            self.assertNotIn("smd", idx)
            self.assertNotIn("upload_presets", idx)
            self.assertEqual("rt", idx["name"])

            recombined = read_snapshot_dir("d", ["smd", "upload_presets", "transformations"])
            self.assertEqual(snapshot["smd"], recombined["smd"])
            self.assertEqual(snapshot["upload_presets"], recombined["upload_presets"])
            self.assertNotIn("transformations", recombined)

    def test_dirstore_missing_index_raises(self):
        from cloudinary_cli.modules.settings.utils.dirstore import read_snapshot_dir

        with self.runner.isolated_filesystem():
            os.makedirs("empty", exist_ok=True)
            with self.assertRaises(FileNotFoundError):
                read_snapshot_dir("empty", ["smd"])

    # -------------------------------------------------------------------
    # P0/P1: provider registry
    # -------------------------------------------------------------------

    def test_provider_registry_shape(self):
        from cloudinary_cli.modules.settings import providers

        expected = {
            "smd",
            "transformations",
            "upload_presets",
            "streaming_profiles",
            "upload_mappings",
            "config",
        }
        self.assertSetEqual(expected, set(providers.PROVIDERS.keys()))
        self.assertSetEqual(expected, set(providers.ALL_COMPONENTS))
        self.assertSetEqual(expected, set(providers.DEFAULT_COMPONENTS))

        # APPLY_ORDER must contain every component exactly once and put SMD before
        # upload_presets, and upload_mappings before SMD/transformations (no
        # downstream deps).
        self.assertEqual(set(providers.APPLY_ORDER), expected)
        self.assertEqual(len(providers.APPLY_ORDER), len(expected))
        order = list(providers.APPLY_ORDER)
        self.assertLess(order.index("smd"), order.index("upload_presets"))
        self.assertLess(order.index("upload_mappings"), order.index("smd"))

        for comp in expected:
            p = providers.get_provider(comp)
            self.assertIsNotNone(p, comp)
            self.assertTrue(hasattr(p, "export_bundle"), comp)
            self.assertTrue(hasattr(p, "summarize_bundle"), comp)
            self.assertTrue(hasattr(p, "apply_bundle"), comp)
            self.assertEqual(comp, p.COMPONENT)

        rows = providers.list_components_status()
        self.assertEqual(len(expected), len(rows))
        config_row = next(r for r in rows if r["component"] == "config")
        self.assertFalse(config_row["applicable"])
        self.assertFalse(config_row["supports_delete"])
        smd_row = next(r for r in rows if r["component"] == "smd")
        self.assertTrue(smd_row["applicable"])
        self.assertTrue(smd_row["supports_delete"])

    # -------------------------------------------------------------------
    # P1: upload_presets normalization
    # -------------------------------------------------------------------

    def test_upload_presets_normalize_strips_noisy_and_sorts_lists(self):
        from cloudinary_cli.modules.settings.providers import upload_presets as up

        a = {
            "name": "p",
            "external_id": "ignore-me",
            "created_at": "2024-01-01",
            "unsigned": True,
            "settings": {"tags": "z,a,m", "allowed_formats": ["png", "jpg"]},
        }
        b = {
            "name": "p",
            "unsigned": True,
            "settings": {"tags": "a,m,z", "allowed_formats": "jpg,png"},
        }
        # Despite different insertion order and presence of server-noisy keys
        # in `a`, the two presets should be considered equivalent.
        self.assertFalse(up._needs_update(a, b))

        c = dict(b)
        c["settings"] = dict(b["settings"])
        c["settings"]["tags"] = "a,m,z,extra"
        self.assertTrue(up._needs_update(c, b))

    def test_upload_presets_export_filters_with_pattern(self):
        # Patch list+detail calls to avoid network and verify pattern filtering.
        from cloudinary_cli.modules.settings.providers import upload_presets as up

        listed = {"presets": [
            {"name": "checkout-image"},
            {"name": "checkout-video"},
            {"name": "marketing"},
        ]}

        def fake_call_api_with_pagination(func, kwargs=None, force=False):
            return listed

        def fake_detail(name):
            return {"name": name, "unsigned": False, "settings": {"resource_type": "image"}}

        with patch.object(up, "call_api_with_pagination", side_effect=fake_call_api_with_pagination), \
             patch.object(up.cloudinary.api, "upload_preset", side_effect=fake_detail):
            bundle = up.export_upload_presets(preset_names=["checkout-*"])

        names = [p["name"] for p in bundle["presets"]]
        self.assertEqual(["checkout-image", "checkout-video"], names)

    # -------------------------------------------------------------------
    # P1: streaming_profiles built-in detection
    # -------------------------------------------------------------------

    def test_streaming_profiles_overridden_builtin_detection(self):
        from cloudinary_cli.modules.settings.providers import streaming_profiles as sp

        default_hd = {
            "name": "hd",
            "predefined": True,
            "representations": [{"transformation": "sp_auto"}],
        }
        self.assertFalse(sp._is_overridden_builtin(default_hd))

        overridden_hd = {
            "name": "hd",
            "predefined": True,
            "representations": [{"transformation": "w_1280,h_720,c_fill"}],
        }
        self.assertTrue(sp._is_overridden_builtin(overridden_hd))

        # Custom (predefined=false) should never be classified as overridden built-in.
        custom = {"name": "mine", "predefined": False, "representations": []}
        self.assertFalse(sp._is_overridden_builtin(custom))

        # Unknown built-in (not in defaults table) → treated as overridden to be safe.
        unknown_builtin = {"name": "future_8k", "predefined": True, "representations": []}
        self.assertTrue(sp._is_overridden_builtin(unknown_builtin))

    def test_streaming_profiles_summarize_marks_builtin_overrides(self):
        from cloudinary_cli.modules.settings.providers import streaming_profiles as sp

        bundle = {
            "custom_profiles": [{"name": "mine"}, {"name": "yours"}],
            "overridden_builtins": [{"name": "hd"}],
        }
        summary = sp.summarize_streaming_profiles(bundle)
        self.assertIn("mine", summary)
        self.assertIn("yours", summary)
        self.assertIn("hd (built-in override)", summary)

    # -------------------------------------------------------------------
    # P1: upload_mappings normalization
    # -------------------------------------------------------------------

    def test_upload_mappings_needs_update(self):
        from cloudinary_cli.modules.settings.providers import upload_mappings as um

        a = {"folder": "f", "template": "https://x", "external_id": "ignored"}
        b = {"folder": "f", "template": "https://x"}
        self.assertFalse(um._needs_update(a, b))

        c = {"folder": "f", "template": "https://y"}
        self.assertTrue(um._needs_update(a, c))

    # -------------------------------------------------------------------
    # P2: config provider — apply refused, diff reports drift
    # -------------------------------------------------------------------

    def test_config_apply_bundle_refuses_with_warning(self):
        from cloudinary_cli.modules.settings.providers import config as cfg

        with patch.object(cfg.logger, "warning") as warn:
            ok = cfg.apply_bundle({"settings": {"settings": {"folder_mode": "fixed"}}})
        self.assertTrue(ok)  # contract: returns True (no-op success)
        self.assertTrue(warn.called)
        self.assertIn("captured for diffing only", warn.call_args[0][0].lower())

    def test_config_diff_bundle_detects_drift(self):
        from cloudinary_cli.modules.settings.providers import config as cfg

        bundle = {
            "settings": {
                "cloud_name": "demo",
                "settings": {"folder_mode": "fixed"},
            },
        }
        live = {
            "cloud_name": "demo",
            "settings": {"folder_mode": "dynamic"},
        }

        with patch.object(cfg.cloudinary.api, "config", return_value=live):
            ok = cfg.diff_config_bundle(bundle)
        self.assertFalse(ok, "drift between fixed/dynamic folder_mode should be reported")

        # No drift case.
        live_match = {
            "cloud_name": "demo",
            "settings": {"folder_mode": "fixed"},
        }
        with patch.object(cfg.cloudinary.api, "config", return_value=live_match):
            ok = cfg.diff_config_bundle(bundle)
        self.assertTrue(ok)

    # -------------------------------------------------------------------
    # `cld settings components` & `cld settings diff`
    # -------------------------------------------------------------------

    def test_settings_components_command_lists_all(self):
        result = self.runner.invoke(cli, ["settings", "components", "--json"])
        self.assertEqual(0, result.exit_code, msg=result.output)
        rows = json.loads(result.output)
        names = {r["component"] for r in rows}
        self.assertSetEqual(
            {"smd", "transformations", "upload_presets", "streaming_profiles", "upload_mappings", "config"},
            names,
        )

    def test_settings_diff_invokes_apply_dry_run_for_components(self):
        # `settings diff --in <path>` should run each provider's apply_bundle in
        # dry-run mode and (for config) call diff_config_bundle.
        from cloudinary_cli.modules.settings import commands as settings_commands
        from cloudinary_cli.modules.settings.providers import smd as smd_provider

        with self.runner.isolated_filesystem():
            snapshot = {
                "schema_version": 2,
                "type": "settings_snapshot",
                "name": "diff-test",
                "components": ["smd", "config"],
                "smd": {"fields": [], "rules": []},
                "config": {"settings": {"settings": {"folder_mode": "fixed"}}, "applicable": False},
            }
            with open("snap.json", "w", encoding="utf-8") as f:
                json.dump(snapshot, f)

            fake_cfg = MagicMock()
            fake_cfg.cloud_name = "demo"

            with patch.object(settings_commands.cloudinary, "config", return_value=fake_cfg), \
                 patch.object(smd_provider, "apply_bundle", return_value=True) as smd_apply, \
                 patch.object(settings_commands, "diff_config_bundle", return_value=True) as cfg_diff:
                result = self.runner.invoke(cli, ["settings", "diff", "--in", "snap.json"])

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertTrue(smd_apply.called)
            kwargs = smd_apply.call_args.kwargs
            self.assertTrue(kwargs.get("dry_run"))
            self.assertTrue(cfg_diff.called)


@unittest.skipUnless(cloudinary.config().api_secret and cloudinary.config().cloud_name, "Requires api_key/api_secret/cloud_name")
class TestCLISettingsIntegration(unittest.TestCase):
    """
    Live integration tests against the currently configured Cloudinary account.

    IMPORTANT:
    - Uses uniquely prefixed fields/rules and only operates on those.
    - Cleans up (rules first, then fields).
    """
    runner = CliRunner()

    def setUp(self):
        self.prefix = f"cli_settings_it_{uuid.uuid4().hex[:10]}"
        self.field_status = f"{self.prefix}_status"
        self.field_priority = f"{self.prefix}_priority"
        self.rule_name = f"{self.prefix} rule"

        self.status_values = [
            {"external_id": f"{self.prefix}_draft", "value": "Draft", "state": "active"},
            {"external_id": f"{self.prefix}_archived", "value": "Archived", "state": "active"},
        ]
        self.priority_values = [
            {"external_id": f"{self.prefix}_low", "value": "Low", "state": "active"},
            {"external_id": f"{self.prefix}_critical", "value": "Critical", "state": "active"},
        ]

        # Create fields
        cloudinary.api.add_metadata_field({
            "type": "enum",
            "external_id": self.field_status,
            "label": f"{self.prefix} Status",
            "mandatory": False,
            "default_value": None,
            "restrictions": {"readonly_ui": False},
            "datasource": {"values": self.status_values},
            "allow_dynamic_list_values": False,
        })

        cloudinary.api.add_metadata_field({
            "type": "enum",
            "external_id": self.field_priority,
            "label": f"{self.prefix} Priority",
            "mandatory": False,
            "default_value": None,
            "restrictions": {"readonly_ui": False},
            "datasource": {"values": self.priority_values},
            "allow_dynamic_list_values": False,
        })

        # Create rule: if priority == critical then set status to archived
        created = cloudinary.api.add_metadata_rule({
            "name": self.rule_name,
            "metadata_field_id": self.field_status,
            "condition": {"equals": f"{self.prefix}_critical", "metadata_field_id": self.field_priority},
            "result": {"apply_value": {"mode": "default", "value": f"{self.prefix}_archived"}, "enable": True},
            "state": "active",
        })
        self.rule_external_id = created.get("external_id")

    def tearDown(self):
        # Best-effort cleanup: rules first, then fields.
        try:
            rules = cloudinary.api.list_metadata_rules().get("metadata_rules", []) or []
            for r in rules:
                if r.get("name", "").startswith(self.prefix):
                    try:
                        cloudinary.api.delete_metadata_rule(r.get("external_id"))
                    except Exception:
                        pass
        finally:
            for fid in (self.field_status, self.field_priority):
                try:
                    cloudinary.api.delete_metadata_field(fid)
                except Exception:
                    pass

    def test_save_restore_roundtrip_prefixed_items(self):
        with self.runner.isolated_filesystem():
            # Save only our prefixed rule (and required fields) to file
            result = self.runner.invoke(cli, [
                "settings", "save",
                "--out", "bundle.json",
                "-F",
                "--pick", "smd", "rule", self.rule_name,
            ])
            self.assertEqual(0, result.exit_code, msg=result.output)
            with open("bundle.json", "r", encoding="utf-8") as f:
                bundle = json.load(f)
            self.assertIn("smd", bundle)

            # Mutate the cloud:
            # - Add an extra status option not in bundle (will be deactivated in sync)
            extra_opt = {"external_id": f"{self.prefix}_extra", "value": "Extra", "state": "active"}
            cloudinary.api.update_metadata_field_datasource(self.field_status, [extra_opt])
            # - Change rule to set status to Draft (will be restored back to Archived)
            cloudinary.api.update_metadata_rule(self.rule_external_id, {
                "result": {"apply_value": {"mode": "default", "value": f"{self.prefix}_draft"}, "enable": True},
            })

            # Restore from bundle with sync (should revert rule + deactivate extra option)
            result2 = self.runner.invoke(cli, [
                "settings", "restore",
                "--in", "bundle.json",
                "--mode", "sync",
                "-F",
            ])
            self.assertEqual(0, result2.exit_code, msg=result2.output)

        # Verify rule restored
        rules = cloudinary.api.list_metadata_rules().get("metadata_rules", []) or []
        rule = next((r for r in rules if r.get("name") == self.rule_name), None)
        self.assertIsNotNone(rule)
        self.assertEqual(f"{self.prefix}_archived", ((rule.get("result") or {}).get("apply_value") or {}).get("value"))

        # Verify extra datasource option is not active anymore
        fields = cloudinary.api.list_metadata_fields().get("metadata_fields", []) or []
        status_field = next((f for f in fields if f.get("external_id") == self.field_status), None)
        self.assertIsNotNone(status_field)
        ds_vals = ((status_field.get("datasource") or {}).get("values") or [])
        extra = next((v for v in ds_vals if v.get("external_id") == f"{self.prefix}_extra"), None)
        # Cloudinary may keep deleted options as inactive entries
        self.assertTrue(extra is None or (extra.get("state") == "inactive"))
