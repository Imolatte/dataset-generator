"""Step 1: Extract use cases and policies from markdown documents."""

from __future__ import annotations

import os
from pathlib import Path

from .config import Config
from .llm import LLMClient
from .models import Evidence, Policy, UseCase


def _read_numbered_lines(path: str) -> tuple[str, list[str]]:
    """Read file and return content with numbered lines and raw lines list."""
    with open(path, encoding="utf-8") as f:
        raw_lines = f.readlines()
    numbered = []
    for i, line in enumerate(raw_lines, 1):
        numbered.append(f"{i:4d} | {line.rstrip()}")
    return "\n".join(numbered), [l.rstrip() for l in raw_lines]


def _detect_case(content: str) -> str:
    """Detect case type from document content."""
    lower = content.lower()
    support_signals = ["faq", "тикет", "обращени", "заказ", "доставк", "возврат", "корзин"]
    quality_signals = ["качеств", "оператор", "проверк", "ошибк", "пунктуац", "медицин", "клиник"]
    support_score = sum(1 for s in support_signals if s in lower)
    quality_score = sum(1 for s in quality_signals if s in lower)
    return "support_bot" if support_score >= quality_score else "operator_quality"


def _validate_evidence(evidence_list: list[dict], raw_lines: list[str], input_file: str) -> list[Evidence]:
    """Validate and fix evidence entries against actual file content."""
    validated = []
    for ev in evidence_list:
        line_start = ev.get("line_start", 1)
        line_end = ev.get("line_end", line_start)
        quote = ev.get("quote", "")
        # Clamp to valid range
        line_start = max(1, min(line_start, len(raw_lines)))
        line_end = max(line_start, min(line_end, len(raw_lines)))
        # Use actual lines if quote doesn't match
        actual_text = "\n".join(raw_lines[line_start - 1 : line_end])
        if quote.strip() and quote.strip() in actual_text:
            final_quote = quote.strip()
        else:
            final_quote = actual_text.strip()
        validated.append(Evidence(
            input_file=input_file,
            line_start=line_start,
            line_end=line_end,
            quote=final_quote if final_quote else quote,
        ))
    return validated


def extract_use_cases(
    config: Config,
    llm: LLMClient,
    numbered_content: str,
    raw_lines: list[str],
    case_type: str,
) -> list[UseCase]:
    """Extract use cases from document content via LLM."""
    input_file = os.path.basename(config.input_path)

    system_prompt = (
        "You are an expert business analyst. You extract structured data from documents. "
        "Always respond with valid JSON only."
    )

    prompt = f"""Analyze the following business requirements document and extract all distinct business use cases (scenarios).
The document has numbered lines for reference.

Document type: {case_type}

DOCUMENT:
{numbered_content}

Extract exactly {config.n_use_cases} use cases. For each use case provide:
- id: sequential id in format "uc_1", "uc_2", etc.
- case: "{case_type}"
- name: short name of the use case
- description: detailed description of what the use case covers
- evidence: array of objects with:
  - input_file: "{input_file}"
  - line_start: starting line number in the document
  - line_end: ending line number
  - quote: exact quote from the document that supports this use case

Return a JSON object with key "use_cases" containing an array of use case objects.
"""

    result = llm.generate_json(prompt, system_prompt)
    use_cases_raw = result.get("use_cases", result) if isinstance(result, dict) else result
    if isinstance(use_cases_raw, dict):
        use_cases_raw = [use_cases_raw]

    use_cases = []
    for i, uc_data in enumerate(use_cases_raw[:config.n_use_cases], 1):
        evidence = _validate_evidence(
            uc_data.get("evidence", [{"line_start": 1, "line_end": 1, "quote": "N/A"}]),
            raw_lines,
            input_file,
        )
        if not evidence:
            evidence = [Evidence(input_file=input_file, line_start=1, line_end=1, quote="N/A")]
        use_cases.append(UseCase(
            id=f"uc_{i}",
            case=case_type,
            name=uc_data.get("name", f"Use Case {i}"),
            description=uc_data.get("description", ""),
            evidence=evidence,
        ))
    return use_cases


def extract_policies(
    config: Config,
    llm: LLMClient,
    numbered_content: str,
    raw_lines: list[str],
    case_type: str,
) -> list[Policy]:
    """Extract policies from document content via LLM."""
    input_file = os.path.basename(config.input_path)

    system_prompt = (
        "You are an expert business analyst. You extract structured data from documents. "
        "Always respond with valid JSON only."
    )

    prompt = f"""Analyze the following business requirements document and extract all constraints, rules, and policies.

Document type: {case_type}

DOCUMENT:
{numbered_content}

Extract at least 8 policies. For each policy provide:
- id: sequential id in format "pol_1", "pol_2", etc.
- type: one of "must", "must_not", "escalate", "style", "format"
  - "must": something the agent/operator MUST do
  - "must_not": something the agent/operator MUST NOT do
  - "escalate": conditions requiring escalation to human/supervisor
  - "style": tone, language, communication style requirements
  - "format": formatting, structure requirements for responses
- case: "{case_type}"
- statement: clear statement of the policy/rule
- evidence: array of objects with:
  - input_file: "{input_file}"
  - line_start: starting line number in the document
  - line_end: ending line number
  - quote: exact quote from the document

Return a JSON object with key "policies" containing an array of policy objects.
"""

    result = llm.generate_json(prompt, system_prompt)
    policies_raw = result.get("policies", result) if isinstance(result, dict) else result
    if isinstance(policies_raw, dict):
        policies_raw = [policies_raw]

    policies = []
    valid_types = {"must", "must_not", "escalate", "style", "format"}
    for i, pol_data in enumerate(policies_raw, 1):
        pol_type = pol_data.get("type", "must")
        if pol_type not in valid_types:
            pol_type = "must"
        evidence = _validate_evidence(
            pol_data.get("evidence", [{"line_start": 1, "line_end": 1, "quote": "N/A"}]),
            raw_lines,
            input_file,
        )
        if not evidence:
            evidence = [Evidence(input_file=input_file, line_start=1, line_end=1, quote="N/A")]
        policies.append(Policy(
            id=f"pol_{i}",
            type=pol_type,
            case=case_type,
            statement=pol_data.get("statement", ""),
            evidence=evidence,
        ))
    return policies


def run_extraction(config: Config, llm: LLMClient) -> tuple[list[UseCase], list[Policy]]:
    """Run full extraction pipeline."""
    print(f"Reading input: {config.input_path}")
    numbered_content, raw_lines = _read_numbered_lines(config.input_path)
    case_type = _detect_case(numbered_content)
    print(f"Detected case type: {case_type}")

    print("Extracting use cases...")
    use_cases = extract_use_cases(config, llm, numbered_content, raw_lines, case_type)
    print(f"  Extracted {len(use_cases)} use cases")

    print("Extracting policies...")
    policies = extract_policies(config, llm, numbered_content, raw_lines, case_type)
    print(f"  Extracted {len(policies)} policies")

    return use_cases, policies
