"""Integration tests for analytics endpoints."""


def test_health_check_reports_status(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"


def test_dashboard_summary_has_expected_keys(client):
    body = client.get("/api/v1/analytics/dashboard").json()
    for key in ("total_customers", "total_offers_generated", "overall_conversion_rate", "segment_distribution"):
        assert key in body


def test_ab_test_includes_methodology_note(client):
    body = client.get("/api/v1/analytics/ab-test").json()
    assert "синтетическом" in body["note"]
    assert body["personalized"]["group"] == "personalized"


def test_root_redirects_to_dashboard(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (307, 308)
    assert response.headers["location"] == "/app/"
