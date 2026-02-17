"""Pydantic models for the dataset generator data contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    input_file: str
    line_start: int
    line_end: int
    quote: str


class UseCase(BaseModel):
    id: str = Field(pattern=r"^uc_")
    case: Literal["support_bot", "operator_quality"]
    name: str
    description: str
    evidence: list[Evidence] = Field(min_length=1)


class Policy(BaseModel):
    id: str = Field(pattern=r"^pol_")
    type: Literal["must", "must_not", "escalate", "style", "format"]
    case: Literal["support_bot", "operator_quality"]
    statement: str
    evidence: list[Evidence] = Field(min_length=1)


class TestCase(BaseModel):
    id: str = Field(pattern=r"^tc_")
    case: Literal["support_bot", "operator_quality"]
    use_case_id: str = Field(pattern=r"^uc_")
    parameters: dict[str, Any]
    policy_ids: list[str]


class Message(BaseModel):
    role: Literal["user", "operator", "assistant", "system"]
    content: str


class DatasetExample(BaseModel):
    id: str = Field(pattern=r"^ex_")
    case: Literal["support_bot", "operator_quality"]
    format: Literal[
        "single_turn_qa",
        "single_utterance_correction",
        "dialog_last_turn_correction",
    ]
    use_case_id: str = Field(pattern=r"^uc_")
    test_case_id: str = Field(pattern=r"^tc_")
    input: dict[str, Any]
    expected_output: str
    evaluation_criteria: list[str] = Field(min_length=3)
    policy_ids: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)


# Wrapper models matching Data Contract root structure
class UseCasesFile(BaseModel):
    use_cases: list[UseCase]


class PoliciesFile(BaseModel):
    policies: list[Policy]


class TestCasesFile(BaseModel):
    test_cases: list[TestCase]


class DatasetFile(BaseModel):
    examples: list[DatasetExample]


class LLMInfo(BaseModel):
    provider: str
    model: str
    temperature: float


class RunManifest(BaseModel):
    input_path: str
    out_path: str
    seed: int
    timestamp: str
    generator_version: str
    llm: LLMInfo
