"""Validate generated artifacts against the data contract."""

from __future__ import annotations

import json
import os

from pydantic import ValidationError

from .models import (
    DatasetExample,
    DatasetFile,
    PoliciesFile,
    Policy,
    RunManifest,
    TestCase,
    TestCasesFile,
    UseCase,
    UseCasesFile,
)


class ValidationReport:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.stats: dict[str, int | str] = {}

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def print_report(self) -> None:
        print("\n=== Validation Report ===")
        if self.stats:
            print("\nStats:")
            for key, val in sorted(self.stats.items()):
                print(f"  {key}: {val}")
        if self.warnings:
            print(f"\nWarnings ({len(self.warnings)}):")
            for w in self.warnings:
                print(f"  ! {w}")
        if self.errors:
            print(f"\nErrors ({len(self.errors)}):")
            for e in self.errors:
                print(f"  x {e}")
        if self.ok:
            print("\n  Validation passed")
        else:
            print(f"\n  Validation failed with {len(self.errors)} error(s)")


def _load_json(path: str) -> dict | list | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _read_input_lines(input_path: str) -> list[str] | None:
    """Read input file lines for evidence validation."""
    if not input_path or not os.path.exists(input_path):
        return None
    with open(input_path, encoding="utf-8") as f:
        return [line.rstrip("\n").rstrip("\r") for line in f.readlines()]


def _validate_evidence_quote(evidence: dict, input_lines: list[str] | None, report: ValidationReport, context: str) -> None:
    """Validate that evidence quote matches actual file content."""
    if input_lines is None:
        return
    line_start = evidence.get("line_start", 0)
    line_end = evidence.get("line_end", 0)
    quote = evidence.get("quote", "")
    if line_start < 1 or line_end < line_start or line_end > len(input_lines):
        report.warn(f"{context}: line range {line_start}-{line_end} out of bounds (file has {len(input_lines)} lines)")
        return
    actual = "\n".join(input_lines[line_start - 1 : line_end])
    normalized_quote = quote.strip()
    normalized_actual = actual.strip()
    if normalized_quote and normalized_quote not in normalized_actual:
        report.warn(f"{context}: evidence quote does not match lines {line_start}-{line_end}")


def validate(out_path: str, input_path: str = "") -> ValidationReport:
    """Validate all generated artifacts in the output directory."""
    report = ValidationReport()

    required_files = ["run_manifest.json", "use_cases.json", "policies.json", "test_cases.json", "dataset.json"]
    for fname in required_files:
        fpath = os.path.join(out_path, fname)
        if not os.path.exists(fpath):
            report.error(f"Missing required file: {fname}")

    if not report.ok:
        return report

    # Load input file for evidence checking
    input_lines = None
    if input_path:
        input_lines = _read_input_lines(input_path)

    # Validate run_manifest
    manifest_data = _load_json(os.path.join(out_path, "run_manifest.json"))
    if manifest_data:
        try:
            manifest = RunManifest(**manifest_data)
            if not input_path and manifest.input_path:
                input_lines = _read_input_lines(manifest.input_path)
        except ValidationError as e:
            report.error(f"run_manifest.json validation failed: {e}")

    # Validate use_cases (wrapper object)
    uc_raw = _load_json(os.path.join(out_path, "use_cases.json"))
    use_case_ids: set[str] = set()
    if isinstance(uc_raw, dict) and "use_cases" in uc_raw:
        uc_list = uc_raw["use_cases"]
    elif isinstance(uc_raw, list):
        uc_list = uc_raw
        report.warn("use_cases.json should be {\"use_cases\": [...]}, not a bare array")
    else:
        uc_list = []
        report.error("use_cases.json must be {\"use_cases\": [...]}")

    report.stats["use_cases"] = len(uc_list)
    if len(uc_list) < 5:
        report.error(f"Minimum 5 use cases required, found {len(uc_list)}")
    for i, uc in enumerate(uc_list):
        try:
            obj = UseCase(**uc)
            use_case_ids.add(obj.id)
            for ev in obj.evidence:
                _validate_evidence_quote(ev.model_dump(), input_lines, report, f"use_cases[{i}]")
        except ValidationError as e:
            report.error(f"use_cases[{i}] validation failed: {e}")

    # Validate policies (wrapper object)
    pol_raw = _load_json(os.path.join(out_path, "policies.json"))
    policy_ids: set[str] = set()
    if isinstance(pol_raw, dict) and "policies" in pol_raw:
        pol_list = pol_raw["policies"]
    elif isinstance(pol_raw, list):
        pol_list = pol_raw
        report.warn("policies.json should be {\"policies\": [...]}, not a bare array")
    else:
        pol_list = []
        report.error("policies.json must be {\"policies\": [...]}")

    report.stats["policies"] = len(pol_list)
    if len(pol_list) < 5:
        report.error(f"Minimum 5 policies required, found {len(pol_list)}")
    policy_types: set[str] = set()
    for i, pol in enumerate(pol_list):
        try:
            obj = Policy(**pol)
            policy_ids.add(obj.id)
            policy_types.add(obj.type)
            for ev in obj.evidence:
                _validate_evidence_quote(ev.model_dump(), input_lines, report, f"policies[{i}]")
        except ValidationError as e:
            report.error(f"policies[{i}] validation failed: {e}")
    if len(policy_types) < 2:
        report.error(f"Minimum 2 policy types required, found {len(policy_types)}: {policy_types}")

    # Validate test_cases (wrapper object)
    tc_raw = _load_json(os.path.join(out_path, "test_cases.json"))
    test_case_ids: set[str] = set()
    tc_per_uc: dict[str, int] = {}
    if isinstance(tc_raw, dict) and "test_cases" in tc_raw:
        tc_list = tc_raw["test_cases"]
    elif isinstance(tc_raw, list):
        tc_list = tc_raw
        report.warn("test_cases.json should be {\"test_cases\": [...]}, not a bare array")
    else:
        tc_list = []
        report.error("test_cases.json must be {\"test_cases\": [...]}")

    report.stats["test_cases"] = len(tc_list)
    for i, tc in enumerate(tc_list):
        try:
            obj = TestCase(**tc)
            test_case_ids.add(obj.id)
            tc_per_uc[obj.use_case_id] = tc_per_uc.get(obj.use_case_id, 0) + 1
            if obj.use_case_id not in use_case_ids:
                report.error(f"test_cases[{i}].use_case_id '{obj.use_case_id}' not found in use_cases")
            for pid in obj.policy_ids:
                if pid not in policy_ids:
                    report.error(f"test_cases[{i}].policy_ids contains '{pid}' not found in policies")
            if not obj.policy_ids:
                report.error(f"test_cases[{i}] must have at least 1 policy_id")
        except ValidationError as e:
            report.error(f"test_cases[{i}] validation failed: {e}")

    for uc_id, count in tc_per_uc.items():
        if count < 3:
            report.error(f"Use case {uc_id} has only {count} test case(s), minimum is 3")

    # Validate dataset (wrapper object)
    ds_raw = _load_json(os.path.join(out_path, "dataset.json"))
    if isinstance(ds_raw, dict) and "examples" in ds_raw:
        ds_list = ds_raw["examples"]
    elif isinstance(ds_raw, list):
        ds_list = ds_raw
        report.warn("dataset.json should be {\"examples\": [...]}, not a bare array")
    else:
        ds_list = []
        report.error("dataset.json must be {\"examples\": [...]}")

    ex_per_tc: dict[str, int] = {}
    formats_seen: set[str] = set()
    sources_seen: set[str] = set()
    report.stats["examples"] = len(ds_list)

    for i, ex in enumerate(ds_list):
        try:
            obj = DatasetExample(**ex)
            formats_seen.add(obj.format)
            ex_per_tc[obj.test_case_id] = ex_per_tc.get(obj.test_case_id, 0) + 1
            if obj.metadata.get("source"):
                sources_seen.add(obj.metadata["source"])

            # Referential integrity
            if obj.use_case_id not in use_case_ids:
                report.error(f"dataset[{i}].use_case_id '{obj.use_case_id}' not found in use_cases")
            if obj.test_case_id not in test_case_ids:
                report.error(f"dataset[{i}].test_case_id '{obj.test_case_id}' not found in test_cases")
            for pid in obj.policy_ids:
                if pid not in policy_ids:
                    report.error(f"dataset[{i}].policy_ids contains '{pid}' not found in policies")
            if not obj.policy_ids:
                report.error(f"dataset[{i}] must have at least 1 policy_id")

            # Check input.messages structure
            messages = obj.input.get("messages", [])
            if not messages:
                report.error(f"dataset[{i}] input.messages is empty")

            # Format-specific checks
            if obj.format == "single_utterance_correction":
                if len(messages) != 1:
                    report.warn(f"dataset[{i}] single_utterance_correction should have exactly 1 message, has {len(messages)}")
                if messages and messages[0].get("role") != "operator":
                    report.error(f"dataset[{i}] single_utterance_correction message must have role=operator")
                tmi = obj.input.get("target_message_index")
                if tmi is None:
                    report.warn(f"dataset[{i}] single_utterance_correction missing input.target_message_index")
                elif tmi != 0:
                    report.warn(f"dataset[{i}] single_utterance_correction target_message_index should be 0")

            elif obj.format == "dialog_last_turn_correction":
                if len(messages) < 2:
                    report.error(f"dataset[{i}] dialog_last_turn_correction must have >= 2 messages")
                if messages and messages[-1].get("role") != "operator":
                    report.error(f"dataset[{i}] dialog_last_turn_correction last message must have role=operator")
                tmi = obj.input.get("target_message_index")
                if tmi is None:
                    report.error(f"dataset[{i}] dialog_last_turn_correction missing input.target_message_index")
                elif tmi != len(messages) - 1:
                    report.error(f"dataset[{i}] target_message_index={tmi} but should be {len(messages) - 1}")

            # Check support_bot source coverage
            if obj.case == "support_bot" and not obj.metadata.get("source"):
                report.warn(f"dataset[{i}] support_bot example missing metadata.source")

        except ValidationError as e:
            report.error(f"dataset[{i}] validation failed: {e}")

    # Coverage checks
    for tc_id in test_case_ids:
        if tc_id not in ex_per_tc:
            report.error(f"Test case {tc_id} has no examples in dataset")

    report.stats["formats"] = len(formats_seen)
    report.stats["sources"] = len(sources_seen)
    if formats_seen:
        print(f"  Formats: {', '.join(sorted(formats_seen))}")
    if sources_seen:
        print(f"  Sources: {', '.join(sorted(sources_seen))}")

    # Check case-specific format coverage
    case_type = None
    if ds_list:
        case_type = ds_list[0].get("case")
    if case_type == "support_bot":
        required_sources = {"tickets", "faq_paraphrase", "corner"}
        missing = required_sources - sources_seen
        if missing:
            report.error(f"Support dataset missing required sources: {missing}")
    elif case_type == "operator_quality":
        required_formats = {"single_utterance_correction", "dialog_last_turn_correction"}
        missing = required_formats - formats_seen
        if missing:
            report.error(f"Operator dataset missing required formats: {missing}")

    return report


def run_validation(out_path: str, input_path: str = "") -> int:
    """Run validation and return exit code."""
    report = validate(out_path, input_path)
    report.print_report()
    return 0 if report.ok else 1
