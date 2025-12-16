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
        from cloudinary_cli.modules.settings.utils.pick import parse_picks, SMD_PICK_ALL_SENTINEL

        selected_components, smd_fields, smd_rules = parse_picks([
            ("smd", "field", "all"),
            ("smd", "rule", "*"),
        ])

        self.assertEqual(["smd"], selected_components)
        self.assertEqual([SMD_PICK_ALL_SENTINEL], smd_fields)
        self.assertEqual([SMD_PICK_ALL_SENTINEL], smd_rules)

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
                result = self.runner.invoke(cli, ["settings", "save", "--out", "out.json", "-F"])

            self.assertEqual(0, result.exit_code, msg=result.output)
            self.assertTrue(os.path.exists("out.json"))

            with open("out.json", "r", encoding="utf-8") as f:
                raw = f.read()
            # Pretty JSON should contain newlines and indentation.
            self.assertTrue(raw.startswith("{\n"))
            self.assertIn('\n  "schema_version":', raw)

            parsed = json.loads(raw)
            self.assertEqual("demo-cloud", parsed["source"]["cloud_name"])

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
