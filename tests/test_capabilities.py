from app.api_docs import capabilities


def test_capabilities_contract():
    data = capabilities()
    assert data["service"].endswith("Trust Engine")
    assert "duplicate_detection" in data["capabilities"]
    assert data["decisions"] == ["verified", "review_required", "rejected"]
