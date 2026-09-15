"""Versioned report profiles and immutable Report Plan compiler."""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from . import contracts

CONFIG_SCHEMA_VERSION = 3
PLAN_SCHEMA_VERSION = 1
SUPPORTED_KINDS = frozenset({
    "editorial_items",
    "semantic_clusters",
    "producer_markdown",
    "semantic_synthesis",
    "project_board",
})
_COMMON_COMPONENT_FIELDS = {
    "id", "order", "title", "kind", "editorial_hint",
    "bindings", "health", "policy",
}
_KIND_POLICIES = {
    "editorial_items": {"selection_limit"},
    "semantic_clusters": {"max_items", "max_candidates_per_item", "coverage_target"},
    "producer_markdown": {"snapshot_key"},
    "semantic_synthesis": {"exact_items"},
    "project_board": {
        "fresh_snapshot_key", "categories_snapshot_key", "quality_snapshot_key",
        "max_projects_per_category", "fresh_title",
    },
}
_PROFILE_KINDS = {
    "news_digest": ("editorial_items",),
    "ecosystem_digest": (
        "semantic_clusters", "producer_markdown", "semantic_synthesis", "project_board",
    ),
}


def _nonnegative_integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise contracts.ContractError(f"{path} must be a non-negative integer")
    return value


def _positive_integer(value: Any, path: str) -> int:
    result = _nonnegative_integer(value, path)
    if result < 1:
        raise contracts.ContractError(f"{path} must be a positive integer")
    return result


def _selection_limit(value: Any, path: str) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != {"min", "max"}:
        raise contracts.ContractError(f"{path} must contain min and max")
    minimum = _nonnegative_integer(value["min"], f"{path}.min")
    maximum = _nonnegative_integer(value["max"], f"{path}.max")
    if maximum < minimum:
        raise contracts.ContractError(f"{path} must satisfy min <= max")
    return {"min": minimum, "max": maximum}


def validate_bundle(config: Any) -> None:
    """Validate the schema-v3 profile envelope, excluding source map internals."""
    if not isinstance(config, Mapping):
        raise contracts.ContractError("config must be an object")
    if set(config) != {"schema_version", "sources", "reports"}:
        raise contracts.ContractError("config must contain only schema_version, sources, and reports")
    if config.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise contracts.ContractError("config.schema_version must be 3")
    sources = config.get("sources")
    reports = config.get("reports")
    if not isinstance(sources, Mapping) or not sources:
        raise contracts.ContractError("config.sources must be a non-empty object")
    if not isinstance(reports, Mapping) or not reports:
        raise contracts.ContractError("config.reports must be a non-empty object")
    unsupported = set(reports) - {contracts.NOON_REPORT, contracts.AGENTS_REPORT}
    if unsupported:
        raise contracts.ContractError(f"config.reports contains unsupported reports: {sorted(unsupported)!r}")

    for report_id, report_value in reports.items():
        path = f"reports.{report_id}"
        if not isinstance(report_value, Mapping):
            raise contracts.ContractError(f"{path} must be an object")
        report = report_value
        if set(report) != {"profile_type", "title", "input", "features", "components"}:
            raise contracts.ContractError(f"{path} must contain profile_type, title, input, features, and components")
        profile_type = report.get("profile_type")
        expected_profile = "news_digest" if report_id == contracts.NOON_REPORT else "ecosystem_digest"
        if profile_type != expected_profile:
            raise contracts.ContractError(f"{path}.profile_type must be {expected_profile}")
        contracts.safe_text(report.get("title"), f"{path}.title")
        report_input = report.get("input")
        if not isinstance(report_input, Mapping) or set(report_input) != {"driver", "path"}:
            raise contracts.ContractError(f"{path}.input must contain driver and path")
        if report_input.get("driver") != "json_file" or not isinstance(report_input.get("path"), str) or not report_input["path"]:
            raise contracts.ContractError(f"{path}.input must be a json_file with a non-empty path")

        features = report.get("features")
        if not isinstance(features, Mapping):
            raise contracts.ContractError(f"{path}.features must be an object")
        if profile_type == "news_digest":
            if set(features) != {"top_points", "total_selection_limit"}:
                raise contracts.ContractError(f"{path}.features must contain top_points and total_selection_limit")
            top_points = features["top_points"]
            if not isinstance(top_points, Mapping) or set(top_points) not in (
                {"max"},
                {"max", "max_per_section"},
            ):
                raise contracts.ContractError(
                    f"{path}.features.top_points must contain max and optional max_per_section"
                )
            top_max = _nonnegative_integer(top_points["max"], f"{path}.features.top_points.max")
            if top_max > 5:
                raise contracts.ContractError(f"{path}.features.top_points.max must not exceed 5")
            top_section_max = _positive_integer(
                top_points.get("max_per_section", 2),
                f"{path}.features.top_points.max_per_section",
            )
            if top_section_max > max(1, top_max):
                raise contracts.ContractError(
                    f"{path}.features.top_points.max_per_section must not exceed max"
                )
            total = features["total_selection_limit"]
            if not isinstance(total, Mapping) or set(total) != {"max"}:
                raise contracts.ContractError(f"{path}.features.total_selection_limit must contain max")
            _nonnegative_integer(total["max"], f"{path}.features.total_selection_limit.max")
        elif features:
            raise contracts.ContractError(f"{path}.features must be empty for ecosystem_digest")

        components = report.get("components")
        if not isinstance(components, list) or not components:
            raise contracts.ContractError(f"{path}.components must be a non-empty array")
        ids: set[str] = set()
        orders: list[int] = []
        kinds: list[str] = []
        editorial_minimum_total = 0
        for index, component_value in enumerate(components):
            component_path = f"{path}.components[{index}]"
            if not isinstance(component_value, Mapping) or set(component_value) != _COMMON_COMPONENT_FIELDS:
                raise contracts.ContractError(f"{component_path} must contain the common component fields")
            component = component_value
            component_id = contracts.section_id(component.get("id"), f"{component_path}.id")
            if component_id in ids:
                raise contracts.ContractError(f"{component_path}.id is duplicated")
            ids.add(component_id)
            order = _positive_integer(component.get("order"), f"{component_path}.order")
            orders.append(order)
            contracts.safe_text(component.get("title"), f"{component_path}.title")
            contracts.safe_text(component.get("editorial_hint"), f"{component_path}.editorial_hint")
            kind = component.get("kind")
            if kind not in SUPPORTED_KINDS:
                raise contracts.ContractError(f"{component_path}.kind is unsupported")
            kinds.append(str(kind))
            bindings = component.get("bindings")
            if not isinstance(bindings, list) or not bindings:
                raise contracts.ContractError(f"{component_path}.bindings must be a non-empty array")
            for binding_index, binding in enumerate(bindings):
                binding_path = f"{component_path}.bindings[{binding_index}]"
                if not isinstance(binding, Mapping):
                    raise contracts.ContractError(f"{binding_path} must be an object")
                source_id = binding.get("source")
                if source_id not in sources:
                    raise contracts.ContractError(f"{binding_path}.source references unknown source")
            health = component.get("health")
            if not isinstance(health, Mapping) or set(health) != {"minimum_candidates"}:
                raise contracts.ContractError(f"{component_path}.health must contain minimum_candidates")
            _nonnegative_integer(health["minimum_candidates"], f"{component_path}.health.minimum_candidates")
            policy = component.get("policy")
            expected_policy = _KIND_POLICIES[str(kind)]
            if not isinstance(policy, Mapping) or set(policy) != expected_policy:
                raise contracts.ContractError(
                    f"{component_path}.policy must contain {sorted(expected_policy)!r} for kind {kind}"
                )
            if kind == "editorial_items":
                limit = _selection_limit(policy["selection_limit"], f"{component_path}.policy.selection_limit")
                editorial_minimum_total += limit["min"]
            elif kind == "semantic_clusters":
                maximum = _positive_integer(policy["max_items"], f"{component_path}.policy.max_items")
                per_item = _positive_integer(
                    policy["max_candidates_per_item"],
                    f"{component_path}.policy.max_candidates_per_item",
                )
                coverage = _nonnegative_integer(policy["coverage_target"], f"{component_path}.policy.coverage_target")
                if per_item > 3 or coverage > maximum * per_item:
                    raise contracts.ContractError(f"{component_path}.policy has an impossible cluster budget")
            elif kind == "producer_markdown":
                contracts.safe_text(policy["snapshot_key"], f"{component_path}.policy.snapshot_key")
            elif kind == "semantic_synthesis":
                _positive_integer(policy["exact_items"], f"{component_path}.policy.exact_items")
            elif kind == "project_board":
                for key in ("fresh_snapshot_key", "categories_snapshot_key", "quality_snapshot_key", "fresh_title"):
                    contracts.safe_text(policy[key], f"{component_path}.policy.{key}")
                _positive_integer(
                    policy["max_projects_per_category"],
                    f"{component_path}.policy.max_projects_per_category",
                )

        if orders != list(range(1, len(components) + 1)):
            raise contracts.ContractError(f"{path}.components.order must be contiguous and match list order")
        if profile_type == "news_digest":
            if set(kinds) != {"editorial_items"}:
                raise contracts.ContractError(f"{path}.components must all use editorial_items")
            if features["total_selection_limit"]["max"] < editorial_minimum_total:
                raise contracts.ContractError(
                    f"{path}.features.total_selection_limit.max cannot be below selection minimum total"
                )
        else:
            if sorted(kinds) != sorted(_PROFILE_KINDS["ecosystem_digest"]):
                raise contracts.ContractError(
                    f"{path}.components must contain exactly one supported ecosystem block kind"
                )


def _plan_digest(plan_without_hash: Mapping[str, Any]) -> str:
    encoded = json.dumps(plan_without_hash, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compile_report_plan(config: Mapping[str, Any], report_id: str) -> dict[str, Any]:
    """Compile one validated schema-v3 report into an immutable ordered plan."""
    validate_bundle(config)
    if report_id not in config["reports"]:
        raise contracts.ContractError(f"report {report_id!r} is not configured")
    report = config["reports"][report_id]
    components = copy.deepcopy(report["components"])
    source_ids: list[str] = []
    for component in components:
        for binding in component["bindings"]:
            source_id = binding["source"]
            if source_id not in source_ids:
                source_ids.append(source_id)
    base: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "config_schema_version": CONFIG_SCHEMA_VERSION,
        "report": report_id,
        "profile_type": report["profile_type"],
        "title": report["title"],
        "input": copy.deepcopy(report["input"]),
        "features": copy.deepcopy(report["features"]),
        "components": components,
        "source_ids": source_ids,
        "sources": {source_id: copy.deepcopy(config["sources"][source_id]) for source_id in source_ids},
    }
    base["plan_sha256"] = _plan_digest(base)
    return base


def validate_report_plan(plan: Any, report_id: str | None = None) -> tuple[str, ...]:
    """Validate an embedded plan and return ordered component IDs."""
    if not isinstance(plan, Mapping):
        raise contracts.ContractError("report_plan must be an object")
    if set(plan) != {
        "schema_version", "config_schema_version", "report", "profile_type", "title",
        "input", "features", "components", "source_ids", "sources", "plan_sha256",
    }:
        raise contracts.ContractError("report_plan has unexpected fields")
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION or plan.get("config_schema_version") != CONFIG_SCHEMA_VERSION:
        raise contracts.ContractError("report_plan schema version is unsupported")
    if report_id is not None and plan.get("report") != report_id:
        raise contracts.ContractError("report_plan report does not match")
    provided = plan.get("plan_sha256")
    if not isinstance(provided, str) or len(provided) != 64:
        raise contracts.ContractError("report_plan.plan_sha256 is invalid")
    unhashed = {key: copy.deepcopy(value) for key, value in plan.items() if key != "plan_sha256"}
    if _plan_digest(unhashed) != provided:
        raise contracts.ContractError("report_plan.plan_sha256 does not match its content")
    # Reuse bundle validation so plans and configs cannot drift semantically.
    synthetic = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "sources": copy.deepcopy(plan["sources"]),
        "reports": {
            plan["report"]: {
                "profile_type": plan["profile_type"],
                "title": plan["title"],
                "input": copy.deepcopy(plan["input"]),
                "features": copy.deepcopy(plan["features"]),
                "components": copy.deepcopy(plan["components"]),
            }
        },
    }
    validate_bundle(synthetic)
    source_ids = plan.get("source_ids")
    ordered_source_ids: list[str] = []
    for component in plan["components"]:
        for binding in component["bindings"]:
            source_id = binding["source"]
            if source_id not in ordered_source_ids:
                ordered_source_ids.append(source_id)
    if (
        not isinstance(source_ids, list)
        or source_ids != ordered_source_ids
        or set(source_ids) != set(plan["sources"])
    ):
        raise contracts.ContractError("report_plan.source_ids must match ordered component sources")
    return tuple(component["id"] for component in plan["components"])


def component_by_kind(plan: Mapping[str, Any], kind: str) -> Mapping[str, Any]:
    validate_report_plan(plan)
    matches = [component for component in plan["components"] if component["kind"] == kind]
    if len(matches) != 1:
        raise contracts.ContractError(f"report_plan must contain exactly one {kind} component")
    return matches[0]
