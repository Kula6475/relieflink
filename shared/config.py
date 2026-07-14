"""Shared constants used by every section.

Import from anywhere with:  from shared.config import CATEGORIES, LEDGER_URL
(Always run modules from the repo root, e.g. `python -m vision_agent.agent`.)
"""

import os

from dotenv import load_dotenv

load_dotenv()

# Where the ledger API lives. Override in .env if you run it elsewhere.
LEDGER_URL = os.getenv("LEDGER_URL", "http://localhost:8000")

# Claude model for vision counting and plain-English explanations.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")

# The four inventory categories every section agrees on. Do not add or rename
# without updating docs/api-contract.md and telling the team.
CATEGORIES = ["canned_goods", "produce", "dairy", "dry_goods"]
