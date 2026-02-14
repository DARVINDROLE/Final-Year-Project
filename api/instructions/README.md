# Agent Instructions Directory

Each runtime agent must have an instruction file under `api/instructions/` and must load it at startup.

Expected files:
- `perception.md`
- `intelligence.md`
- `decision.md`
- `action.md`

Rules:
- Agent code must refuse to run if its instruction file is missing.
- Instruction text should be logged at startup in a safe/redacted way.
- These files are human-readable policy and behavior contracts for each agent.
