from atlas_optimizer.advisor import AtlasAdvisorRequest, explain


def test_atlas_advisor_has_key_free_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    answer = explain(
        AtlasAdvisorRequest(
            evidence={"calculation": {"requestedQuantity": 150, "optimizerRecommendedQuantity": 150}},
            question="Why not request more?",
        )
    )
    assert "150-unit request" in answer
    assert "every affected organization approves" in answer
