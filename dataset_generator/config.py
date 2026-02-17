"""Configuration for the dataset generator."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    input_path: str = ""
    out_path: str = ""
    seed: int = 42
    n_use_cases: int = 8
    n_test_cases_per_uc: int = 5
    n_examples_per_tc: int = 2
    model: str = "gemini-2.0-flash"
    temperature: float = 0.7
    api_key: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = os.environ.get("GOOGLE_API_KEY", "")
            if not self.api_key:
                env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
                if os.path.exists(env_file):
                    with open(env_file) as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("GOOGLE_API_KEY="):
                                self.api_key = line.split("=", 1)[1].strip()
                                break
