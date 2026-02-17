"""Step 3: Generate dataset examples from test cases."""

from __future__ import annotations

import json
import os

from .config import Config
from .llm import LLMClient
from .models import DatasetExample, Policy, TestCase, UseCase


def _get_format_for_case(case_type: str, tc_index: int) -> str:
    """Determine format based on case type and variation."""
    if case_type == "support_bot":
        return "single_turn_qa"
    # Alternate between formats for operator_quality
    if tc_index % 2 == 0:
        return "single_utterance_correction"
    return "dialog_last_turn_correction"


def _get_source_for_support(ex_index: int) -> str:
    """Rotate through sources for support_bot."""
    sources = ["tickets", "faq_paraphrase", "corner"]
    return sources[ex_index % len(sources)]


def generate_dataset(
    config: Config,
    llm: LLMClient,
    use_cases: list[UseCase],
    policies: list[Policy],
    test_cases: list[TestCase],
    save_path: str = "",
) -> list[DatasetExample]:
    """Generate dataset examples for all test cases with incremental saving."""
    uc_map = {uc.id: uc for uc in use_cases}
    pol_map = {p.id: p for p in policies}

    system_prompt = (
        "You are a dataset generator creating realistic test examples for LLM agent evaluation. "
        "Always respond with valid JSON only. Generate examples in Russian."
    )

    # Load existing partial results if any
    all_examples: list[DatasetExample] = []
    completed_tc_ids: set[str] = set()
    if save_path and os.path.exists(save_path):
        with open(save_path, encoding="utf-8") as f:
            existing = json.load(f)
        # Handle wrapper format {"examples": [...]} or bare [...]
        if isinstance(existing, dict) and "examples" in existing:
            existing = existing["examples"]
        if isinstance(existing, list) and existing:
            for ex_data in existing:
                try:
                    all_examples.append(DatasetExample(**ex_data))
                    completed_tc_ids.add(ex_data["test_case_id"])
                except Exception:
                    pass
            if all_examples:
                print(f"  Resuming: loaded {len(all_examples)} existing examples ({len(completed_tc_ids)} test cases done)")

    ex_counter = len(all_examples) + 1

    for tc_idx, tc in enumerate(test_cases):
        if tc.id in completed_tc_ids:
            continue

        uc = uc_map.get(tc.use_case_id)
        if not uc:
            continue

        fmt = _get_format_for_case(tc.case, tc_idx)
        relevant_policies = [pol_map[pid] for pid in tc.policy_ids if pid in pol_map]
        policy_statements = [f"- {p.id}: {p.statement}" for p in relevant_policies]

        print(f"  Generating examples for {tc.id} ({fmt})...")

        prompt = _build_prompt(config, uc, tc, fmt, policy_statements)

        try:
            result = llm.generate_json(prompt, system_prompt)
        except Exception as e:
            print(f"  Failed to generate for {tc.id}: {e}")
            # Save partial progress and re-raise
            if save_path:
                _save_partial(save_path, all_examples)
            raise

        examples_raw = result.get("examples", result) if isinstance(result, dict) else result
        if isinstance(examples_raw, dict):
            examples_raw = [examples_raw]

        for ex_idx, ex_data in enumerate(examples_raw[:config.n_examples_per_tc]):
            input_data = ex_data.get("input", {})
            if "messages" in input_data:
                messages = []
                for msg in input_data["messages"]:
                    messages.append({
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", ""),
                    })
                input_data["messages"] = messages

            expected_output = ex_data.get("expected_output", "")
            eval_criteria = ex_data.get("evaluation_criteria", [])
            if len(eval_criteria) < 3:
                eval_criteria.extend(["Response is relevant", "Response follows policies", "Response is in Russian"][:3 - len(eval_criteria)])

            metadata = ex_data.get("metadata", {})
            if tc.case == "support_bot":
                metadata["source"] = _get_source_for_support(ex_idx)
            metadata["split"] = "test"

            # target_message_index goes inside input per Data Contract
            if fmt == "single_utterance_correction":
                input_data["target_message_index"] = 0
            elif fmt == "dialog_last_turn_correction" and "messages" in input_data:
                input_data["target_message_index"] = len(input_data["messages"]) - 1

            all_examples.append(DatasetExample(
                id=f"ex_{ex_counter}",
                case=tc.case,
                format=fmt,
                use_case_id=tc.use_case_id,
                test_case_id=tc.id,
                input=input_data,
                expected_output=expected_output,
                evaluation_criteria=eval_criteria,
                policy_ids=tc.policy_ids,
                metadata=metadata,
            ))
            ex_counter += 1

        # Save after each test case for resilience
        if save_path:
            _save_partial(save_path, all_examples)

    print(f"  Generated {len(all_examples)} examples total")
    return all_examples


def _save_partial(path: str, examples: list[DatasetExample]) -> None:
    """Save partial results to disk in wrapper format."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"examples": [ex.model_dump() for ex in examples]}, f, ensure_ascii=False, indent=2)


def _build_prompt(
    config: Config,
    uc: UseCase,
    tc: TestCase,
    fmt: str,
    policy_statements: list[str],
) -> str:
    """Build the generation prompt based on format type."""
    base = f"""Generate exactly {config.n_examples_per_tc} realistic test examples for LLM agent evaluation.

Use Case: {uc.name}
Description: {uc.description}
Case type: {tc.case}
Format: {fmt}

Test parameters:
{json.dumps(tc.parameters, ensure_ascii=False, indent=2)}

Relevant policies:
{chr(10).join(policy_statements)}
"""

    if fmt == "single_turn_qa":
        base += """
Each example should have:
- input: object with "messages" array containing a single message with role "user" and content (a user question/request in Russian)
- expected_output: the ideal assistant response in Russian
- evaluation_criteria: array of 3+ specific criteria to evaluate the response quality
- metadata: object (can be empty)

The user messages should be realistic — with typos, informal language, or varying levels of detail based on the test parameters.
"""
    elif fmt == "single_utterance_correction":
        base += """
Each example should have:
- input: object with "messages" array containing a single message with role "operator" and content (an operator message that may contain errors)
- expected_output: the corrected version of the operator's message
- evaluation_criteria: array of 3+ specific criteria for evaluating the correction
- metadata: object (can be empty)

The operator messages should reflect the test parameters (punctuation errors, slang, etc.).
"""
    elif fmt == "dialog_last_turn_correction":
        base += """
Each example should have:
- input: object with "messages" array containing 3-5 messages alternating between "user" and "operator" roles, where the LAST message is from the operator and may contain errors
- expected_output: the corrected version of the LAST operator message only
- evaluation_criteria: array of 3+ specific criteria for evaluating the correction
- metadata: object (can be empty)

The dialog should be realistic and contextually coherent. Errors should be in the last operator message.
"""

    base += """
Return a JSON object with key "examples" containing an array of example objects.
All text content must be in Russian.
"""
    return base
