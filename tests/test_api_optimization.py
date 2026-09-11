"""Integration tests for the optimization and campaign endpoints."""

from datetime import datetime, timedelta


def _customer(client, ref: str, price: float, quantity: int = 1, discount: bool = False):
    created = client.post("/api/v1/customers", json={"external_ref": ref}).json()
    for _ in range(3):
        client.post(f"/api/v1/customers/{created['id']}/purchases",
                    json={"price": price, "quantity": quantity, "had_discount": discount, "category": "home"})
    return created["id"]


def test_recommendations_include_channel_and_timing(client):
    customer_id = _customer(client, "anon-opt-001", 3000)
    response = client.get(f"/api/v1/offers/optimization/recommendations?customer_id={customer_id}&cart_total=3000")
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "rule_based_v1"
    assert body["overall_strategy"]
    for recommendation in body["recommendations"]:
        assert recommendation["channel"] in {"push", "email", "sms", "telegram"}
        assert recommendation["timing"] in {"immediate", "same_day_evening", "next_morning", "weekend"}
        assert recommendation["reasoning"]


def test_recommendations_for_unknown_customer_returns_404(client):
    assert client.get("/api/v1/offers/optimization/recommendations?customer_id=999999").status_code == 404


def test_schedule_campaign_returns_audience_size(client):
    _customer(client, "anon-camp-001", 2000)
    response = client.post("/api/v1/offers/campaign/schedule",
                           json={"segment": "new_user", "offer_type": "free_shipping", "channel": "email"})
    assert response.status_code == 201
    body = response.json()
    assert body["campaign_id"].startswith("camp-")
    assert body["status"] == "scheduled"
    assert body["target_audience_size"] >= 0


def test_schedule_campaign_rejects_unknown_segment(client):
    response = client.post("/api/v1/offers/campaign/schedule",
                           json={"segment": "not_a_segment", "offer_type": "gift"})
    assert response.status_code == 422


def test_campaign_performance_reports_conversion(client):
    customer_id = _customer(client, "anon-camp-002", 2500)
    offers = client.get(f"/api/v1/offers/generate/{customer_id}").json()["offers"]
    client.post(f"/api/v1/offers/apply/{offers[0]['offer_uid']}", json={"converted": True})

    campaign_id = client.post("/api/v1/offers/campaign/schedule",
                              json={"segment": "repeat_buyer", "offer_type": "bonus_points"}).json()["campaign_id"]
    response = client.get(f"/api/v1/offers/campaign/performance?campaign_id={campaign_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["offers_generated"] >= len(offers)
    assert 0.0 <= body["conversion_rate"] <= 1.0


def test_campaign_performance_rejects_inverted_period(client):
    end = datetime.utcnow()
    start = end + timedelta(days=5)
    response = client.get(
        f"/api/v1/offers/campaign/performance?campaign_id=camp-x"
        f"&start_date={start.isoformat()}&end_date={end.isoformat()}"
    )
    assert response.status_code == 422
