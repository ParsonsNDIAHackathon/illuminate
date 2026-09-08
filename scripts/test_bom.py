#!/usr/bin/env python3
import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bom", ROOT / "scripts/bom.py")
bom = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(bom)


class BomValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.valid = bom.build_bom(ROOT)

    def test_current_inventory_is_complete(self):
        self.assertEqual([], bom.validate_bom(self.valid, ROOT))
        source_ids = {item["id"] for item in self.valid["data_sources"]}
        self.assertIn("openai", source_ids)
        self.assertIn("websearch", source_ids)

    def test_missing_required_metadata_is_actionable(self):
        candidate = copy.deepcopy(self.valid)
        del candidate["data_sources"][0]["cost_as_of"]
        errors = bom.validate_bom(candidate, ROOT)
        self.assertTrue(any("cost_as_of" in error and candidate["data_sources"][0]["id"] in error for error in errors))

    def test_unlisted_dependency_is_actionable(self):
        candidate = copy.deepcopy(self.valid)
        removed = candidate["software_components"].pop()
        errors = bom.validate_bom(candidate, ROOT)
        self.assertTrue(any("unrecorded software component" in error and removed["id"] in error for error in errors))

    def test_unlisted_source_is_actionable(self):
        candidate = copy.deepcopy(self.valid)
        removed = candidate["data_sources"].pop()
        errors = bom.validate_bom(candidate, ROOT)
        self.assertTrue(any("unrecorded data source" in error and removed["id"] in error for error in errors))

    def test_source_declaration_drift_is_actionable(self):
        candidate = copy.deepcopy(self.valid)
        candidate["data_sources"][0]["declaration_fingerprint"] = "changed"
        errors = bom.validate_bom(candidate, ROOT)
        self.assertTrue(any("declaration drifted" in error for error in errors))

    def test_unresolved_facts_cannot_be_marked_reviewed(self):
        candidate = copy.deepcopy(self.valid)
        candidate["data_sources"][0]["review_status"] = "reviewed"
        errors = bom.validate_bom(candidate, ROOT)
        self.assertTrue(any("contains REVIEW_REQUIRED facts" in error for error in errors))

    def test_python_dependency_reachability_classifies_dev_and_platform_packages(self):
        inventory = {item["name"]: item["classification"] for item in bom.python_inventory(ROOT)}
        self.assertEqual("development-only", inventory["iniconfig"])
        self.assertEqual("development-only", inventory["pluggy"])
        self.assertEqual("optional", inventory["pywin32"])
        self.assertEqual("transitive", inventory["cffi"])
        self.assertEqual("transitive", inventory["pycparser"])
        self.assertEqual("transitive", inventory["uvloop"])
        self.assertEqual("transitive", inventory["watchfiles"])

    def test_npm_dev_optional_packages_are_not_required(self):
        entries = [item for item in bom.npm_inventory(ROOT) if item["name"] == "@bufbuild/protobuf"]
        self.assertTrue(entries)
        self.assertTrue(all(item["classification"] == "optional" for item in entries))
        inventory = {item["name"]: item["classification"] for item in bom.npm_inventory(ROOT)}
        self.assertEqual("development-only", inventory["vite"])

    def test_software_license_drift_is_actionable(self):
        candidate = copy.deepcopy(self.valid)
        python_entry = next(item for item in candidate["software_components"] if item["id"].startswith("pypi:"))
        python_entry["declared_license"] = "MIT"
        errors = bom.validate_bom(candidate, ROOT)
        self.assertTrue(any("version/class/license" in error and python_entry["id"] in error for error in errors))

    def test_curated_python_license_review_can_replace_unknown_evidence(self):
        candidate = copy.deepcopy(self.valid)
        python_entry = next(item for item in candidate["software_components"] if item["id"].startswith("pypi:"))
        python_entry["license"] = "MIT"
        python_entry["license_reference"] = "https://example.test/upstream-license"
        python_entry["review_status"] = "curated_reviewed"
        self.assertEqual([], bom.validate_bom(candidate, ROOT))

    def test_runtime_images_are_digest_pinned_and_container_licenses_require_review(self):
        images = [item for item in self.valid["software_components"] if item["classification"] == "container-image"]
        self.assertTrue(images)
        self.assertTrue(all("@sha256:" in item["id"] for item in images))
        self.assertTrue(all(item["review_status"] == "review_required" for item in images))

    def test_profile_only_backup_service_is_optional(self):
        backup = next(item for item in self.valid["software_components"] if item["id"] == "service:backup")
        self.assertEqual("runtime-tool", backup["classification"])
        self.assertFalse(backup["required"])

    def test_npm_manifest_without_lock_update_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "web").mkdir()
            shutil.copy(ROOT / "web/package.json", root / "web/package.json")
            shutil.copy(ROOT / "web/package-lock.json", root / "web/package-lock.json")
            manifest = json.loads((root / "web/package.json").read_text())
            manifest["dependencies"]["unlocked-example"] = "1.0.0"
            (root / "web/package.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "manifest-only=.*unlocked-example"):
                bom.npm_inventory(root)

    def test_python_manifest_without_lock_update_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "api").mkdir()
            shutil.copy(ROOT / "api/pyproject.toml", root / "api/pyproject.toml")
            shutil.copy(ROOT / "api/uv.lock", root / "api/uv.lock")
            manifest_path = root / "api/pyproject.toml"
            manifest_path.write_text(
                manifest_path.read_text().replace(
                    '  "fastapi>=0.115",', '  "fastapi>=0.115",\n  "unlocked-example>=1",'
                )
            )
            with self.assertRaisesRegex(ValueError, "missing-from-lock=.*unlocked-example"):
                bom.python_inventory(root)

    def test_python_version_constraint_without_lock_update_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "api").mkdir()
            shutil.copy(ROOT / "api/pyproject.toml", root / "api/pyproject.toml")
            shutil.copy(ROOT / "api/uv.lock", root / "api/uv.lock")
            manifest_path = root / "api/pyproject.toml"
            manifest_path.write_text(manifest_path.read_text().replace("fastapi>=0.115", "fastapi>=999"))
            with self.assertRaisesRegex(ValueError, "versions, extras, or markers"):
                bom.python_inventory(root)

    def test_python_selected_extra_without_lock_update_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "api").mkdir()
            shutil.copy(ROOT / "api/pyproject.toml", root / "api/pyproject.toml")
            shutil.copy(ROOT / "api/uv.lock", root / "api/uv.lock")
            manifest_path = root / "api/pyproject.toml"
            manifest_path.write_text(manifest_path.read_text().replace("uvicorn[standard]>=0.30", "uvicorn>=0.30"))
            with self.assertRaisesRegex(ValueError, "versions, extras, or markers"):
                bom.python_inventory(root)

    def test_registry_removal_fails_coverage_reconciliation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            destination = root / "api/illuminate/connectors"
            destination.parent.mkdir(parents=True)
            shutil.copytree(ROOT / "api/illuminate/connectors", destination)
            registry = destination / "registry.py"
            registry.write_text(registry.read_text().replace("SAMConnector(),", ""))
            names = bom.registry_connector_names(root)
            sources = [
                dict(item) for item in
                bom.runpy.run_path(str(ROOT / "api/illuminate/connectors/source_contract.py"))["SOURCE_COVERAGE"]
            ]
            with self.assertRaisesRegex(ValueError, "source adapters absent from REGISTRY.*sam"):
                bom.validate_registry_coverage(sources, names)


if __name__ == "__main__":
    unittest.main()