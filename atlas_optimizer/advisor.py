"""Claude explanation boundary for ATLAS; deterministic decisions stay outside the LLM."""

import json
import os

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from shared.config import CLAUDE_MODEL


class AtlasAdvisorRequest(BaseModel):
    evidence: dict
    question: str | None = None


def fallback_explanation(request: AtlasAdvisorRequest) -> str:
    calculation = request.evidence.get("calculation", {})
    requested = calculation.get("requestedQuantity", "the requested")
    recommended = calculation.get("optimizerRecommendedQuantity", "the feasible")
    base = (
        f"ATLAS calculated a {requested}-unit request from validated forecast, inventory, "
        f"in-transit, and safety-stock data; the optimizer found {recommended} feasible units. "
        "No inventory or transportation is committed until every affected organization approves."
    )
    if request.question:
        return f"{base} The available evidence does not support assumptions beyond those inputs."
    return base


def explain(request: AtlasAdvisorRequest) -> str:
    """Explain validated evidence; never calculate quantities or determine approvals."""
    fallback = fallback_explanation(request)
    if not os.getenv("ANTHROPIC_API_KEY"):
        return fallback
    prompt = (
        "You are the ReliefLink ATLAS operations explainer. Use only the validated JSON "
        "evidence below. Explain recommendations or answer the director's question in at "
        "most four sentences. Never change quantities, infer permissions, claim a commitment, "
        "or invent facts. Explicitly mention pending human authority when relevant.\n\n"
        f"Evidence: {json.dumps(request.evidence)}\nQuestion: {request.question or 'Why this plan?'}"
    )
    message = ChatAnthropic(model=CLAUDE_MODEL).invoke(prompt)
    if isinstance(message.content, str):
        return message.content or fallback
    text = "\n".join(
        block.get("text", "")
        for block in message.content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()
    return text or fallback
