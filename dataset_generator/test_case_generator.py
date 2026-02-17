"""Step 2: Generate test cases from use cases and policies."""

from __future__ import annotations

import json

from .config import Config
from .llm import LLMClient
from .models import Policy, TestCase, UseCase


VARIATION_AXES = {
    "support_bot": [
        "tone", "has_order_id", "requires_account", "language", "abuse", "garbage",
    ],
    "operator_quality": [
        "punctuation_errors", "slang", "medical_terms", "escalation_needed", "emoji",
    ],
}


def generate_test_cases(
    config: Config,
    llm: LLMClient,
    use_cases: list[UseCase],
    policies: list[Policy],
) -> list[TestCase]:
    """Generate test cases for all use cases."""
    case_type = use_cases[0].case if use_cases else "support_bot"
    axes = VARIATION_AXES.get(case_type, VARIATION_AXES["support_bot"])
    policy_ids = [p.id for p in policies]

    system_prompt = (
        "You are a QA engineer generating test cases for LLM agent testing. "
        "Always respond with valid JSON only."
    )

    all_test_cases: list[TestCase] = []
    tc_counter = 1

    for uc in use_cases:
        print(f"  Generating test cases for {uc.id}: {uc.name}...")

        prompt = f"""Generate exactly {config.n_test_cases_per_uc} test cases for the following use case.

Use Case:
- ID: {uc.id}
- Name: {uc.name}
- Description: {uc.description}
- Case type: {case_type}

Available variation axes: {json.dumps(axes)}

Available policy IDs: {json.dumps(policy_ids)}

For each test case:
- Assign unique parameter combinations using the variation axes
- Select 1-4 relevant policy_ids that this test case should verify
- Make test cases diverse — cover normal, edge, and adversarial scenarios

{"For support_bot axes:" if case_type == "support_bot" else "For operator_quality axes:"}
{_get_axes_description(case_type)}

Return a JSON object with key "test_cases" containing an array of objects:
- parameters: dict mapping axis names to values
- policy_ids: array of relevant policy IDs from the available list
"""

        result = llm.generate_json(prompt, system_prompt)
        tc_raw = result.get("test_cases", result) if isinstance(result, dict) else result
        if isinstance(tc_raw, dict):
            tc_raw = [tc_raw]

        for tc_data in tc_raw[:config.n_test_cases_per_uc]:
            params = tc_data.get("parameters", {})
            pids = tc_data.get("policy_ids", [])
            # Filter to only valid policy IDs
            pids = [p for p in pids if p in policy_ids]
            if not pids:
                pids = policy_ids[:2]

            all_test_cases.append(TestCase(
                id=f"tc_{tc_counter}",
                case=case_type,
                use_case_id=uc.id,
                parameters=params,
                policy_ids=pids,
            ))
            tc_counter += 1

    print(f"  Generated {len(all_test_cases)} test cases total")
    return all_test_cases


def _get_axes_description(case_type: str) -> str:
    if case_type == "support_bot":
        return """- tone: "polite", "neutral", "angry", "confused"
- has_order_id: true/false — whether the user provides an order ID
- requires_account: true/false — whether the scenario requires account access
- language: "ru", "mixed_ru_en" — language of user message
- abuse: true/false — whether the user uses abusive language
- garbage: true/false — whether the input is nonsensical/random text"""
    return """- punctuation_errors: "none", "minor", "major" — level of punctuation errors in operator text
- slang: true/false — whether operator uses informal/slang language
- medical_terms: "correct", "incorrect", "missing" — accuracy of medical terminology
- escalation_needed: true/false — whether the situation requires escalation
- emoji: "none", "appropriate", "excessive" — emoji usage level"""
