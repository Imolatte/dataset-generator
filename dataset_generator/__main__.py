"""CLI entrypoint for the dataset generator."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from . import __version__
from .config import Config
from .models import RunManifest, LLMInfo, UseCase, Policy, TestCase
from .validator import run_validation


def _save_json(path: str, data: list | dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Saved: {path}")


def _load_json(path: str) -> list | dict | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _unwrap(data: dict | list | None, key: str) -> list | None:
    """Unwrap {"key": [...]} or bare [...] for resume loading."""
    if data is None:
        return None
    if isinstance(data, dict) and key in data:
        return data[key]
    if isinstance(data, list):
        return data
    return None


def cmd_generate(args: argparse.Namespace) -> int:
    """Run the full generation pipeline with resume support."""
    config = Config(
        input_path=os.path.abspath(args.input),
        out_path=os.path.abspath(args.out),
        seed=args.seed,
        n_use_cases=args.n_use_cases,
        n_test_cases_per_uc=args.n_test_cases_per_uc,
        n_examples_per_tc=args.n_examples_per_tc,
        model=args.model,
        temperature=args.temperature,
    )

    if not config.api_key:
        print("Error: GOOGLE_API_KEY not set. Set it via environment variable or .env file.")
        return 1

    if not os.path.exists(config.input_path):
        print(f"Error: Input file not found: {config.input_path}")
        return 1

    from .llm import LLMClient
    from .extractor import run_extraction
    from .test_case_generator import generate_test_cases
    from .dataset_generator import generate_dataset

    llm = LLMClient(config)
    os.makedirs(config.out_path, exist_ok=True)

    # Save run manifest
    manifest = RunManifest(
        input_path=config.input_path,
        out_path=config.out_path,
        seed=config.seed,
        timestamp=datetime.now(timezone.utc).isoformat(),
        generator_version=__version__,
        llm=LLMInfo(
            provider="google",
            model=config.model,
            temperature=config.temperature,
        ),
    )
    _save_json(os.path.join(config.out_path, "run_manifest.json"), manifest.model_dump())

    # Step 1: Extract use cases and policies (resume if already done)
    uc_path = os.path.join(config.out_path, "use_cases.json")
    pol_path = os.path.join(config.out_path, "policies.json")
    uc_list = _unwrap(_load_json(uc_path), "use_cases")
    pol_list = _unwrap(_load_json(pol_path), "policies")

    if uc_list and pol_list:
        print("\n=== Step 1: Extraction (resuming from saved files) ===")
        use_cases = [UseCase(**u) for u in uc_list]
        policies = [Policy(**p) for p in pol_list]
        print(f"  Loaded {len(use_cases)} use cases, {len(policies)} policies")
    else:
        print("\n=== Step 1: Extraction ===")
        use_cases, policies = run_extraction(config, llm)
        _save_json(uc_path, {"use_cases": [uc.model_dump() for uc in use_cases]})
        _save_json(pol_path, {"policies": [p.model_dump() for p in policies]})

    # Step 2: Generate test cases (resume if already done)
    tc_path = os.path.join(config.out_path, "test_cases.json")
    tc_list = _unwrap(_load_json(tc_path), "test_cases")

    if tc_list:
        print("\n=== Step 2: Test Case Generation (resuming from saved files) ===")
        test_cases = [TestCase(**tc) for tc in tc_list]
        print(f"  Loaded {len(test_cases)} test cases")
    else:
        print("\n=== Step 2: Test Case Generation ===")
        test_cases = generate_test_cases(config, llm, use_cases, policies)
        _save_json(tc_path, {"test_cases": [tc.model_dump() for tc in test_cases]})

    # Step 3: Generate dataset
    ds_path = os.path.join(config.out_path, "dataset.json")
    print("\n=== Step 3: Dataset Generation ===")
    examples = generate_dataset(config, llm, use_cases, policies, test_cases, ds_path)
    _save_json(ds_path, {"examples": [ex.model_dump() for ex in examples]})

    print(f"\n=== Generation complete ===")
    print(f"  Use cases: {len(use_cases)}")
    print(f"  Policies: {len(policies)}")
    print(f"  Test cases: {len(test_cases)}")
    print(f"  Examples: {len(examples)}")
    print(f"  Output: {config.out_path}")

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Run validation on generated artifacts."""
    out_path = os.path.abspath(args.out)
    if not os.path.isdir(out_path):
        print(f"Error: Output directory not found: {out_path}")
        return 1
    input_path = ""
    if hasattr(args, "input") and args.input:
        input_path = os.path.abspath(args.input)
    return run_validation(out_path, input_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="dataset_generator",
        description="Synthetic dataset generator for LLM agent testing",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate dataset from markdown")
    gen_parser.add_argument("--input", required=True, help="Path to markdown input file")
    gen_parser.add_argument("--out", required=True, help="Output directory")
    gen_parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    gen_parser.add_argument("--n-use-cases", type=int, default=8, help="Target number of use cases (default: 8)")
    gen_parser.add_argument("--n-test-cases-per-uc", type=int, default=5, help="Test cases per use case (default: 5)")
    gen_parser.add_argument("--n-examples-per-tc", type=int, default=2, help="Examples per test case (default: 2)")
    gen_parser.add_argument("--model", default="gemini-2.0-flash", help="Gemini model (default: gemini-2.0-flash)")
    gen_parser.add_argument("--temperature", type=float, default=0.7, help="Temperature (default: 0.7)")

    # Validate command
    val_parser = subparsers.add_parser("validate", help="Validate generated artifacts")
    val_parser.add_argument("--out", required=True, help="Output directory to validate")
    val_parser.add_argument("--input", default="", help="Path to input markdown (for evidence checking)")

    args = parser.parse_args()

    if args.command is None:
        if "--input" in sys.argv:
            args = gen_parser.parse_args(sys.argv[1:])
            return cmd_generate(args)
        parser.print_help()
        return 1

    if args.command == "generate":
        return cmd_generate(args)
    elif args.command == "validate":
        return cmd_validate(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
