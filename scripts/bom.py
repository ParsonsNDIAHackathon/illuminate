#!/usr/bin/env python3
"""Generate and validate Illuminate's product data and software BOM."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import runpy
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BOM_PATH = ROOT / "docs" / "bom.json"
DOC_PATH = ROOT / "docs" / "BOM.md"
AS_OF = "2026-09-08"

DATA_FIELDS = {
    "id", "name", "kind", "purpose", "coverage", "terms_reference",
    "license_or_terms", "attribution_redistribution", "access_credentials_rate_limits",
    "cost_model", "cost_as_of", "freshness_storage", "required", "omission_impact",
    "fallback", "review_status", "declaration_fingerprint", "declaration_summary",
}
SOFTWARE_FIELDS = {
    "id", "name", "version", "supplier", "classification", "license",
    "license_reference", "declared_license", "declared_license_reference",
    "conditions", "use_scope", "required", "cost_support", "omission_impact",
    "replacement", "review_status",
}

TERMS = {
    "usaspending.gov": "https://www.usaspending.gov/about/our-data",
    "nasa-firms": "https://www.earthdata.nasa.gov/data/tools/firms/faq",
    "nga-pirate-attacks": "https://msi.nga.mil/",
    "dod-budget-justification": "https://comptroller.defense.gov/Budget-Materials/",
    "deep-sea-minerals": "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits",
    "fema-climate-resilience": "https://www.fema.gov/about/website-information",
    "ibtracs": "https://www.ncei.noaa.gov/products/international-best-track-archive",
    "sam-entity-management": "https://sam.gov/content/terms-and-conditions",
    "world-port-index": "https://msi.nga.mil/",
    "nasa-earthdata": "https://www.earthdata.nasa.gov/engage/open-data-services-and-software/data-and-information-policy",
    "noaa-climate-normals": "https://www.noaa.gov/disclaimer",
    "gdelt-2.x": "https://www.gdeltproject.org/about.html",
    "acled": "https://acleddata.com/terms-of-use",
    "noaa-marine-cadastre-ais": "https://coast.noaa.gov/disclaimer/",
    "overture-maps": "https://docs.overturemaps.org/attribution/",
    "openstreetmap": "https://www.openstreetmap.org/copyright",
    "ecfr-title-48": "https://www.ecfr.gov/reader-aids/government-policy-and-ofr-procedures/developer-resources",
    "first-epss": "https://www.first.org/epss/model",
    "sam-exclusions-public-extract": "https://sam.gov/content/terms-and-conditions",
    "gleif-lei": "https://www.gleif.org/en/lei-data/gleif-data-terms-of-use",
    "sec-edgar": "https://www.sec.gov/about/privacy-information#security",
    "ofac-sdn": "https://ofac.treasury.gov/ofac-list-service",
    "opencorporates": "https://opencorporates.com/info/licence",
    "littlesis": "https://littlesis.org/about",
    "finnhub": "https://finnhub.io/terms-of-service",
    "openai": "https://openai.com/policies/service-terms/",
    "websearch": "https://openai.com/policies/service-terms/",
    "fixture-bundle": "api/illuminate/seed/fixtures/",
}

LICENSE_URLS = {
    "MIT": "https://spdx.org/licenses/MIT.html",
    "Apache-2.0": "https://spdx.org/licenses/Apache-2.0.html",
    "BSD-3-Clause": "https://spdx.org/licenses/BSD-3-Clause.html",
    "BSD-2-Clause": "https://spdx.org/licenses/BSD-2-Clause.html",
    "ISC": "https://spdx.org/licenses/ISC.html",
    "MPL-2.0": "https://spdx.org/licenses/MPL-2.0.html",
    "Python-2.0": "https://spdx.org/licenses/Python-2.0.html",
}


def _normal_name(requirement: str) -> str:
    return re.split(r"[\[<>=!~ ;]", requirement, maxsplit=1)[0].strip().lower().replace("_", "-")


def _requirement_shape(requirement: str) -> tuple[str, tuple[str, ...], str, str]:
    match = re.fullmatch(
        r"\s*([A-Za-z0-9_.-]+)(?:\[([^\]]+)\])?\s*([^;]*?)(?:\s*;\s*(.+))?\s*",
        requirement,
    )
    if not match:
        raise ValueError(f"unsupported Python requirement syntax {requirement!r}")
    name, extras, specifier, marker = match.groups()
    return (
        _normal_name(name),
        tuple(sorted(part.strip() for part in (extras or "").split(",") if part.strip())),
        re.sub(r"\s+", "", specifier or ""),
        (marker or "").strip(),
    )


def registry_connector_names(root: Path = ROOT) -> set[str]:
    registry_tree = ast.parse((root / "api/illuminate/connectors/registry.py").read_text())
    class_names: dict[str, str] = {}
    for path in (root / "api/illuminate/connectors").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if (isinstance(item, ast.Assign) and len(item.targets) == 1
                            and isinstance(item.targets[0], ast.Name) and item.targets[0].id == "name"
                            and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str)):
                        class_names[node.name] = item.value.value
    registry_classes: list[str] = []
    for node in registry_tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == "REGISTRY" for t in targets):
            registry_classes = [
                elt.func.id for elt in node.value.elts
                if isinstance(elt, ast.Call) and isinstance(elt.func, ast.Name)
            ]
    return {class_names[name] for name in registry_classes}


def validate_registry_coverage(sources: list[dict[str, Any]], registry_names: set[str]) -> None:
    covered = {item["adapter"] for item in sources if item["adapter"]}
    missing_registry = covered - registry_names
    if missing_registry:
        raise ValueError(f"source adapters absent from REGISTRY: {sorted(missing_registry)}")
    undocumented = registry_names - covered - {"openai", "websearch"}
    if undocumented:
        raise ValueError(f"connectors have no source coverage contract: {sorted(undocumented)}")


def source_inventory(root: Path = ROOT) -> list[dict[str, Any]]:
    namespace = runpy.run_path(str(root / "api/illuminate/connectors/source_contract.py"))
    sources = [dict(item) for item in namespace["SOURCE_COVERAGE"]]
    registry_names = registry_connector_names(root)
    covered = {item["adapter"] for item in sources if item["adapter"]}
    validate_registry_coverage(sources, registry_names)
    for name in sorted(registry_names - covered):
        sources.append({
            "source_id": name, "label": "OpenAI API" if name == "openai" else "OpenAI-backed web search",
            "adapter": name, "policy_status": "credential_required",
            "endpoint": "https://api.openai.com/", "access": "user-owned API account",
            "credentials": "OpenAI API key", "freshness": "request time",
            "categories": ["model"] if name == "openai" else ["web_search"],
            "limitations": "Optional model output is non-authoritative and usage is account-billed.",
            "action": "Configure an OpenAI key; deterministic workflows remain available.",
        })
    fixture_root = root / "api/illuminate/seed/fixtures"
    fixture_paths = sorted(path for path in fixture_root.iterdir() if path.is_file())
    fixture_hash = hashlib.sha256()
    for path in fixture_paths:
        fixture_hash.update(path.name.encode())
        fixture_hash.update(b"\0")
        fixture_hash.update(path.read_bytes())
        fixture_hash.update(b"\0")
    catalog = json.loads((fixture_root / "catalog_lineage.json").read_text())
    adapters = {item["adapter"] for item in sources if item.get("adapter")}
    for record in catalog["records"]:
        if record["connector"] not in adapters:
            raise ValueError(f"catalog fixture source {record['connector']!r} has no registered source")
        if not (fixture_root / record["cache_fixture"]).is_file():
            raise ValueError(f"catalog fixture references missing file {record['cache_fixture']!r}")
    sources.append({
        "source_id": "fixture-bundle", "label": "Committed offline fixture bundle",
        "adapter": None, "policy_status": "available",
        "endpoint": "api/illuminate/seed/fixtures/", "access": "bundled with source checkout",
        "credentials": "none", "freshness": "point-in-time retrieval timestamps in fixture records",
        "categories": ["fixture", "offline_demo"],
        "limitations": "Snapshots become stale and cover only the deterministic demonstration path.",
        "action": "Refresh through reviewed connectors and preserve provenance before replacing snapshots.",
        "fixture_count": len(fixture_paths),
        "fixture_types": sorted({path.suffix or "(none)" for path in fixture_paths}),
        "fixture_sha256": fixture_hash.hexdigest(),
    })
    for source in sources:
        declaration = {
            key: value for key, value in source.items()
            if key not in {"label"} and value is not None
        }
        source["_declaration_fingerprint"] = hashlib.sha256(
            json.dumps(declaration, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    return sources


def python_inventory(root: Path = ROOT) -> list[dict[str, Any]]:
    lock = tomllib.loads((root / "api/uv.lock").read_text())
    project = tomllib.loads((root / "api/pyproject.toml").read_text())["project"]
    direct = {_normal_name(x) for x in project["dependencies"]}
    dev = {_normal_name(x) for x in project.get("optional-dependencies", {}).get("dev", [])}
    packages = {package["name"]: package for package in lock["package"]}
    locked_project = packages.get(project["name"])
    if not locked_project:
        raise ValueError(f"api/uv.lock has no project entry for {project['name']!r}")
    locked_direct = {item["name"] for item in locked_project.get("dependencies", [])}
    locked_dev = {
        item["name"] for item in locked_project.get("optional-dependencies", {}).get("dev", [])
    }
    if direct != locked_direct or dev != locked_dev:
        raise ValueError(
            "api/pyproject.toml and api/uv.lock dependency declarations differ: "
            f"production missing-from-lock={sorted(direct-locked_direct)}, stale-in-lock={sorted(locked_direct-direct)}; "
            f"dev missing-from-lock={sorted(dev-locked_dev)}, stale-in-lock={sorted(locked_dev-dev)}"
        )
    expected_requirements = {
        ("production", *_requirement_shape(requirement))
        for requirement in project["dependencies"]
    } | {
        ("dev", *_requirement_shape(requirement))
        for requirement in project.get("optional-dependencies", {}).get("dev", [])
    }
    locked_requirements = set()
    for requirement in locked_project.get("metadata", {}).get("requires-dist", []):
        marker = requirement.get("marker", "")
        group = "dev" if marker == "extra == 'dev'" else "production"
        locked_requirements.add((
            group,
            _normal_name(requirement["name"]),
            tuple(sorted(requirement.get("extras", []))),
            re.sub(r"\s+", "", requirement.get("specifier", "")),
            "" if group == "dev" else marker,
        ))
    if expected_requirements != locked_requirements:
        raise ValueError(
            "api/pyproject.toml requirements (names, versions, extras, or markers) do not match "
            "api/uv.lock project metadata; run uv lock and review the BOM. "
            f"manifest-only={sorted(expected_requirements-locked_requirements)!r}, "
            f"lock-only={sorted(locked_requirements-expected_requirements)!r}"
        )

    marker_values = {
        "implementation_name": "cpython",
        "platform_python_implementation": "CPython",
        "python_full_version": "3.12.0",
        "sys_platform": "linux",
    }

    def marker_clause_applies(marker: str) -> bool:
        match = re.fullmatch(r"([a-z_]+)\s*(==|!=|<|<=|>|>=)\s*'([^']+)'", marker.strip())
        if not match or match.group(1) not in marker_values:
            raise ValueError(f"unsupported Python dependency marker clause {marker!r}; extend BOM marker evaluation")
        variable, operator, expected = match.groups()
        actual = marker_values[variable]
        if variable == "python_full_version":
            actual_value: Any = tuple(int(part) for part in actual.split("."))
            expected_value: Any = tuple(int(part) for part in expected.split("."))
        else:
            actual_value, expected_value = actual, expected
        return {
            "==": actual_value == expected_value, "!=": actual_value != expected_value,
            "<": actual_value < expected_value, "<=": actual_value <= expected_value,
            ">": actual_value > expected_value, ">=": actual_value >= expected_value,
        }[operator]

    def marker_applies(marker: str | None) -> bool:
        if not marker:
            return True
        return any(
            all(marker_clause_applies(clause) for clause in disjunction.split(" and "))
            for disjunction in marker.split(" or ")
        )

    def dependency_target(dependency: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
        extras = dependency.get("extra") or dependency.get("extras") or []
        return dependency["name"], tuple(extras)

    def reachable(starts: list[tuple[str, tuple[str, ...]]]) -> set[str]:
        reached: set[str] = set()
        pending = list(starts)
        while pending:
            name, selected_extras = pending.pop()
            if name in reached:
                continue
            reached.add(name)
            package_dependencies = list(packages.get(name, {}).get("dependencies", []))
            optional = packages.get(name, {}).get("optional-dependencies", {})
            for extra in selected_extras:
                package_dependencies.extend(optional.get(extra, []))
            for dependency in package_dependencies:
                if marker_applies(dependency.get("marker")):
                    pending.append(dependency_target(dependency))
        return reached

    prod_reachable = reachable([dependency_target(item) for item in locked_project.get("dependencies", [])])
    dev_reachable = reachable([
        dependency_target(item)
        for item in locked_project.get("optional-dependencies", {}).get("dev", [])
    ])
    incoming_markers: dict[str, set[str]] = {}
    for package in lock["package"]:
        for dependency in package.get("dependencies", []):
            if dependency.get("marker"):
                incoming_markers.setdefault(dependency["name"], set()).add(dependency["marker"])
    rows = []
    for package in lock["package"]:
        name = package["name"]
        if name == project["name"]:
            continue
        if name in direct:
            classification = "direct"
        elif name in prod_reachable:
            classification = "transitive"
        elif name in dev_reachable:
            classification = "development-only"
        else:
            classification = "optional"
        rows.append({
            "id": f"pypi:{name}", "name": name, "version": package["version"],
            "classification": classification, "declared_license": "REVIEW_REQUIRED",
            "declared_license_reference": f"https://pypi.org/project/{name}/{package['version']}/",
            "conditions": "; ".join(sorted(incoming_markers.get(name, []))) or "all supported runtime profiles",
        })
    return rows


def npm_inventory(root: Path = ROOT) -> list[dict[str, Any]]:
    lock = json.loads((root / "web/package-lock.json").read_text())
    manifest = json.loads((root / "web/package.json").read_text())
    root_package = lock["packages"][""]
    for section in ("dependencies", "devDependencies"):
        declared = manifest.get(section, {})
        locked = root_package.get(section, {})
        if declared != locked:
            raise ValueError(
                f"web/package.json and web/package-lock.json {section} differ: "
                f"manifest-only={sorted(declared.keys()-locked.keys())}, lock-only={sorted(locked.keys()-declared.keys())}, "
                f"changed={sorted(name for name in declared.keys() & locked.keys() if declared[name] != locked[name])}"
            )
    direct = set(root_package.get("dependencies", {}))
    dev = set(root_package.get("devDependencies", {}))
    rows = []
    for path, package in sorted(lock["packages"].items()):
        if not path:
            continue
        name = path.rsplit("node_modules/", 1)[-1]
        classification = "direct" if name in direct else "development-only" if name in dev or package.get("dev") else "transitive"
        if (package.get("optional") or package.get("devOptional")) and name not in direct and name not in dev:
            classification = "optional"
        if name == "@mdi/font":
            classification = "frontend-asset"
        license_name = package.get("license", "REVIEW_REQUIRED")
        clean_license = license_name.strip("()").split(" OR ")[0].split(" AND ")[0]
        rows.append({
            "id": f"npm:{name}@{package['version']}", "name": name, "version": package["version"],
            "classification": classification, "declared_license": license_name,
            "declared_license_reference": LICENSE_URLS.get(clean_license, f"https://www.npmjs.com/package/{name}/v/{package['version']}"),
            "conditions": "platform-selected" if package.get("optional") else "all supported runtime profiles",
        })
    return rows


def runtime_inventory(root: Path = ROOT) -> list[dict[str, Any]]:
    texts = {
        "compose": (root / "docker-compose.yml").read_text(),
        "api": (root / "api/Dockerfile").read_text(),
        "web": (root / "web/Dockerfile").read_text(),
        "production": (root / "scripts/replit-production.sh").read_text(),
    }
    images = sorted(set(re.findall(r"(?m)^\s*(?:image:|FROM)\s+([^\s]+)", "\n".join(texts.values()))))
    known_images = {
        "python:3.12-alpine": ("python", "3.12-alpine", "container-image", "Python Software Foundation License"),
        "python:3.12-slim": ("python", "3.12-slim", "container-image", "Python Software Foundation License"),
        "node:22-alpine": ("node", "22-alpine", "container-image", "MIT"),
        "nginx:alpine": ("nginx", "alpine", "container-image", "BSD-2-Clause"),
        "neo4j:5": ("neo4j", "5", "database", "GPL-3.0-only / commercial terms REVIEW_REQUIRED"),
    }
    result = []
    for image in images:
        tagged_name, separator, digest = image.partition("@")
        name, tag_version, classification, _project_license = known_images.get(
            tagged_name, (tagged_name.split(":", 1)[0], tagged_name.split(":", 1)[-1], "container-image", "REVIEW_REQUIRED")
        )
        result.append({
            "id": f"image:{image}", "name": name,
            "version": f"{tag_version}@{digest}" if separator else f"{tag_version}; mutable tag REVIEW_REQUIRED",
            "classification": classification, "declared_license": "Composite container contents; REVIEW_REQUIRED",
            "declared_license_reference": "https://hub.docker.com/_/" + name.lower(),
            "conditions": "declared container runtime",
        })
    plugins: set[str] = set()
    for raw in re.findall(r"NEO4J_PLUGINS:\s*'([^']+)'", texts["compose"]):
        parsed = json.loads(raw)
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError("NEO4J_PLUGINS must be a JSON string list")
        plugins.update(parsed)
    for plugin in sorted(plugins):
        known = plugin == "apoc"
        neo4j_image = next((image for image in images if image.startswith("neo4j:")), "neo4j image REVIEW_REQUIRED")
        result.append({
            "id": f"plugin:{plugin}",
            "name": "Neo4j APOC Core" if known else plugin,
            "version": f"image-managed by {neo4j_image}" if known else "REVIEW_REQUIRED",
            "classification": "database-plugin",
            "declared_license": "Apache-2.0" if known else "REVIEW_REQUIRED",
            "declared_license_reference": "https://github.com/neo4j/apoc/blob/5.26/LICENSE.txt" if known else "REVIEW_REQUIRED",
            "conditions": "Neo4j graph traversal runtime",
        })
    compose_services = re.findall(r"(?m)^  ([a-zA-Z0-9_-]+):\s*$", texts["compose"])
    for service in compose_services:
        if service == "neo4j-data":
            continue
        result.append({
            "id": f"service:{service}", "name": f"Illuminate {service} service",
            "version": "repository revision",
            "classification": "runtime-tool" if service == "backup" else "runtime-service",
            "declared_license": "Project source license not declared; REVIEW_REQUIRED",
            "declared_license_reference": "REVIEW_REQUIRED",
            "conditions": "tools profile" if service == "backup" else "default Compose profile",
        })
    if "neo4j console" in texts["production"]:
        result.append({
            "id": "runtime:neo4j-native", "name": "Neo4j native Replit runtime",
            "version": "5.x Nix package; exact deployment derivation REVIEW_REQUIRED",
            "classification": "database", "declared_license": "GPL-3.0-only / commercial terms REVIEW_REQUIRED",
            "declared_license_reference": "https://neo4j.com/licensing/",
            "conditions": "Replit development and production launchers",
        })
    uv_matches = re.findall(r"pip install --no-cache-dir uv==([0-9.]+)", texts["api"])
    if uv_matches:
        result.append({
            "id": "pypi:uv-build-tool", "name": "uv", "version": uv_matches[0],
            "classification": "build-tool", "declared_license": "Apache-2.0 OR MIT",
            "declared_license_reference": "https://github.com/astral-sh/uv/tree/0.9.24#license",
            "conditions": "API container build",
        })
    return result


def software_inventory(root: Path = ROOT) -> list[dict[str, Any]]:
    return python_inventory(root) + npm_inventory(root) + runtime_inventory(root)


def _data_entry(source: dict[str, Any]) -> dict[str, Any]:
    sid = source["source_id"]
    required = sid == "fixture-bundle"
    unavailable = source["policy_status"] in {"unavailable", "not_applicable"}
    access = f"{source.get('access', 'unknown')}; credentials/rate limits: {source.get('credentials', 'unknown')}"
    if source.get("policy_status") == "credential_required":
        access += "; provider/account limits apply and must be reviewed"
    return {
        "id": sid, "name": source["label"],
        "kind": "bundled/fixture" if sid == "fixture-bundle" else ("model/API" if sid in {"openai", "websearch"} else "external-data"),
        "purpose": "Deterministic offline startup and judged demonstration" if required else
                   f"Optional evidence capability for {', '.join(source.get('categories', [])) or 'documented coverage'}",
        "coverage": source.get("limitations") or "REVIEW_REQUIRED",
        "terms_reference": TERMS.get(sid, source.get("endpoint", "REVIEW_REQUIRED")),
        "license_or_terms": ("Bundled snapshots retain each upstream source's terms and attribution; review before redistribution"
                             if required else "Provider terms apply; REVIEW_REQUIRED before new redistribution or production use"),
        "attribution_redistribution": "Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED",
        "access_credentials_rate_limits": access,
        "cost_model": "Bundled; no per-request fee" if required else
                      ("Unavailable/not integrated; future provider cost REVIEW_REQUIRED" if unavailable else
                       "Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED"),
        "cost_as_of": AS_OF,
        "freshness_storage": f"{source.get('freshness', 'unknown')}; cached records retain provenance; storage/retention terms REVIEW_REQUIRED",
        "required": required,
        "omission_impact": "Offline deterministic mission data and startup readiness are unavailable" if required else
                           f"{source['label']} evidence/enrichment is unavailable; core deterministic graph remains usable",
        "fallback": source.get("action") or "Continue without this optional source and show coverage limitations",
        "review_status": "review_required",
        "declaration_fingerprint": source["_declaration_fingerprint"],
        "declaration_summary": (
            f"{source['fixture_count']} committed files ({', '.join(source['fixture_types'])})"
            if sid == "fixture-bundle" else
            f"{source.get('policy_status', 'unknown')} via {source.get('adapter') or 'no adapter'} at {source.get('endpoint')}"
        ),
    }


def _software_entry(item: dict[str, Any]) -> dict[str, Any]:
    classification = item["classification"]
    required = classification not in {"development-only", "optional", "runtime-tool"}
    ecosystem = item["id"].split(":", 1)[0]
    return {
        **item,
        "license": item["declared_license"],
        "license_reference": item["declared_license_reference"],
        "supplier": "PyPI project maintainers" if ecosystem == "pypi" else
                    "npm package maintainers" if ecosystem == "npm" else
                    ("Illuminate project" if ecosystem == "service" else
                     "Neo4j, Inc." if "neo4j" in item["id"] or "apoc" in item["id"] else "Official container image maintainers"),
        "use_scope": f"{classification} {ecosystem} component resolved from repository declarations",
        "required": required,
        "cost_support": "Open-source/community component; no support entitlement bundled; hosting and support costs are operator-dependent",
        "omission_impact": ("Development/build checks may be unavailable" if classification == "development-only" else
                            "Only the platform-specific optional installation is affected" if classification == "optional" else
                            "Manual portable backup creation is unavailable; normal application runtime is unaffected" if classification == "runtime-tool" else
                            "Application build or the dependent runtime capability fails"),
        "replacement": "Remove or replace the depending feature and regenerate the lockfile and BOM in the same change",
        "review_status": (
            "review_required" if "REVIEW_REQUIRED" in item["declared_license"]
            else "lockfile_reviewed" if ecosystem in {"pypi", "npm"} and classification != "build-tool"
            else "curated_reviewed"
        ),
    }


def build_bom(root: Path = ROOT) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "inventory_as_of": AS_OF,
        "supported_runtime_profile": "Linux CPython 3.12+ and Node.js 20+; conditional requiredness is evaluated for Linux CPython 3.12",
        "disclaimer": "Inventory information only, not legal advice. Verify upstream terms and pricing for the intended use.",
        "data_sources": [_data_entry(x) for x in source_inventory(root)],
        "software_components": [_software_entry(x) for x in software_inventory(root)],
    }


def validate_bom(bom: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for top in ("schema_version", "inventory_as_of", "supported_runtime_profile", "disclaimer", "data_sources", "software_components"):
        if top not in bom:
            errors.append(f"BOM missing top-level field: {top}")
    for section, fields in (("data_sources", DATA_FIELDS), ("software_components", SOFTWARE_FIELDS)):
        seen: set[str] = set()
        for index, entry in enumerate(bom.get(section, [])):
            ident = entry.get("id", f"index {index}")
            missing = sorted(field for field in fields if field not in entry or entry[field] in (None, ""))
            if missing:
                errors.append(f"{section} entry {ident!r} missing required fields: {', '.join(missing)}")
            if ident in seen:
                errors.append(f"{section} has duplicate id: {ident}")
            seen.add(ident)
            review_status = entry.get("review_status")
            allowed = {"review_required", "reviewed"} if section == "data_sources" else {
                "review_required", "lockfile_reviewed", "curated_reviewed"
            }
            if review_status not in allowed:
                errors.append(f"{section} entry {ident!r} has invalid review_status: {review_status!r}")
            review_values = [
                entry.get("license_or_terms", ""), entry.get("cost_model", ""),
                entry.get("license", ""), entry.get("license_reference", ""),
            ]
            if any("REVIEW_REQUIRED" in str(value) for value in review_values) and review_status != "review_required":
                errors.append(f"{section} entry {ident!r} contains REVIEW_REQUIRED facts but is marked {review_status!r}")
    try:
        expected_data = {x["source_id"] for x in source_inventory(root)}
        expected_data_rows = {x["source_id"]: x for x in source_inventory(root)}
        actual_data = {x.get("id") for x in bom.get("data_sources", [])}
        for ident in sorted(expected_data - actual_data):
            errors.append(f"unrecorded data source {ident!r}; add it to docs/bom.json")
        for ident in sorted(actual_data - expected_data):
            errors.append(f"stale BOM data source {ident!r}; remove it or restore its declaration")
        actual_data_rows = {x.get("id"): x for x in bom.get("data_sources", [])}
        for ident in sorted(expected_data & actual_data):
            expected_fingerprint = expected_data_rows[ident]["_declaration_fingerprint"]
            actual_fingerprint = actual_data_rows[ident].get("declaration_fingerprint")
            if expected_fingerprint != actual_fingerprint:
                errors.append(
                    f"data source {ident!r} declaration drifted; regenerate docs/bom.json and review terms, cost, and impact"
                )
        expected_software = {
            x["id"]: (x["version"], x["classification"], x["declared_license"], x["declared_license_reference"], x["conditions"])
            for x in software_inventory(root)
        }
        actual_software = {
            x.get("id"): (
                x.get("version"), x.get("classification"), x.get("declared_license"),
                x.get("declared_license_reference"), x.get("conditions"),
            )
            for x in bom.get("software_components", [])
        }
        for ident in sorted(expected_software.keys() - actual_software.keys()):
            errors.append(f"unrecorded software component {ident!r}; regenerate and review docs/bom.json")
        for ident in sorted(actual_software.keys() - expected_software.keys()):
            errors.append(f"stale BOM software component {ident!r}; remove it or restore its declaration")
        for ident in sorted(expected_software.keys() & actual_software.keys()):
            if expected_software[ident] != actual_software[ident]:
                errors.append(
                    f"software component {ident!r} drifted: declared version/class/license={expected_software[ident]!r}, "
                    f"BOM={actual_software[ident]!r}"
                )
    except Exception as exc:
        errors.append(f"could not derive declared inventory: {exc}")
    return errors


def render_markdown(bom: dict[str, Any]) -> str:
    lines = [
        "# Product Data and Software Bill of Materials", "",
        f"Inventory as of **{bom['inventory_as_of']}**. {bom['disclaimer']}", "",
        f"**Supported runtime profile:** {bom['supported_runtime_profile']}.", "",
        "The JSON contract at [`docs/bom.json`](bom.json) is authoritative. Generated facts (IDs, resolved",
        "versions, dependency class, and declaration membership) come from lockfiles and runtime/source",
        "declarations. Licensing, costs, operational impacts, and mitigations are curated assessments.",
        "Values marked `REVIEW_REQUIRED`, variable, or custom-contract are deliberately unresolved.", "",
        "Validate with `make validate-bom`; regenerate this view with `make generate-bom`.", "",
        "## Data sources", "",
    ]
    for item in bom["data_sources"]:
        lines += [
            f"### {item['name']} (`{item['id']}`)", "",
            f"- **Class / required:** {item['kind']}; {'required' if item['required'] else 'optional'}",
            f"- **Purpose:** {item['purpose']}",
            f"- **Coverage / limits:** {item['coverage']}",
            f"- **Terms/license:** [{item['license_or_terms']}]({item['terms_reference']})",
            f"- **Attribution/redistribution:** {item['attribution_redistribution']}",
            f"- **Access:** {item['access_credentials_rate_limits']}",
            f"- **Cost ({item['cost_as_of']}):** {item['cost_model']}",
            f"- **Freshness/storage:** {item['freshness_storage']}",
            f"- **If omitted:** {item['omission_impact']}",
            f"- **Fallback:** {item['fallback']}",
            f"- **Review:** `{item['review_status']}`", "",
        ]
    lines += ["## Software components", "",
              "| Component | Resolved version | Supplier | Class | License | Required | Review | Scope / omission path |",
              "|---|---:|---|---|---|:---:|---|---|"]
    for item in bom["software_components"]:
        license_cell = f"[{item['license']}]({item['license_reference']})"
        impact = f"{item['use_scope']}. {item['omission_impact']} Replacement: {item['replacement']}"
        lines.append(
            f"| `{item['id']}` | `{item['version']}` | {item['supplier']} | {item['classification']} | "
            f"{license_cell} | {'yes' if item['required'] else 'no'} | `{item['review_status']}` | {impact} |"
        )
    lines += ["", "### Software cost and support", "",
              "Each software row records: " + bom["software_components"][0]["cost_support"] + ".",
              "Supplier/project and review status remain available in the machine-readable JSON.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--initialize", action="store_true", help="replace the BOM from current declarations")
    parser.add_argument("--generate", action="store_true", help="regenerate docs/BOM.md from the checked JSON")
    args = parser.parse_args(argv)
    if args.initialize:
        BOM_PATH.write_text(json.dumps(build_bom(), indent=2) + "\n")
    if not BOM_PATH.exists():
        print("BOM validation failed: docs/bom.json is missing; run scripts/bom.py --initialize and review it", file=sys.stderr)
        return 1
    bom = json.loads(BOM_PATH.read_text())
    errors = validate_bom(bom)
    if errors:
        print("BOM validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    rendered = render_markdown(bom)
    if args.initialize or args.generate:
        DOC_PATH.write_text(rendered)
    elif not DOC_PATH.exists() or DOC_PATH.read_text() != rendered:
        print("BOM validation failed: docs/BOM.md is stale; run make generate-bom", file=sys.stderr)
        return 1
    print(f"BOM valid: {len(bom['data_sources'])} data sources, {len(bom['software_components'])} software components")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())