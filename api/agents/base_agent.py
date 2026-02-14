from __future__ import annotations

import logging
from pathlib import Path


class BaseAgent:
    def __init__(self, instruction_file: str) -> None:
        self.instruction_file = Path(instruction_file)
        self.agent_name = self.__class__.__name__
        self.logger = logging.getLogger(f"api.agents.{self.agent_name}")
        self.instructions_text = self._load_instructions()

    def _load_instructions(self) -> str:
        if not self.instruction_file.exists():
            raise FileNotFoundError(
                f"Missing required instruction file: {self.instruction_file.as_posix()}"
            )
        text = self.instruction_file.read_text(encoding="utf-8")
        # Log instruction loading at startup (redact to first 120 chars for safety)
        preview = text[:120].replace("\n", " ").strip()
        self.logger.info(
            "[%s] Loaded instruction file: %s (%d chars) — '%s…'",
            self.agent_name,
            self.instruction_file.as_posix(),
            len(text),
            preview,
        )
        return text
