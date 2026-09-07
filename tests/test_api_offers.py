"""Integration tests for the offers API."""


def _create_customer(client, external_ref="anon-offer-001"):
    resp = client.post("/api/v1/customers", json={"external_ref": external_ref})
    return resp.json()["id"]


def test_generate_offers_for_existing_customer(client):
    customer_id = _create_customer(client)
    response = client.get(f"/api/v1/offers/generate/{customer_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["customer_id"] == customer_id
    assert len(body["offers"]) > 0
    assert all(0 <= o["score"] <= 1 for o in body["offers"])


def test_generate_offers_for_missing_customer_returns_404(client):
    response = client.get("/api/v1/offers/generate/99999")
    assert response.status_code == 404


def test_apply_offer_marks_it_as_applied(client):
    customer_id = _create_customer(client, "anon-offer-002")
    generate_resp = client.get(f"/api/v1/offers/generate/{customer_id}")
    offer_uid = generate_resp.json()["offers"][0]["offer_uid"]

    apply_resp = client.post(f"/api/v1/offers/apply/{offer_uid}", json={"order_reference": "order-123", "converted": True})
    assert apply_resp.status_code == 200
    assert apply_resp.json()["status"] == "applied"


def test_apply_nonexistent_offer_returns_404(client):
    response = client.post("/api/v1/offers/apply/does-not-exist", json={"converted": True})
    assert response.status_code == 404


def test_offer_analytics_reflects_generated_offers(client):
    customer_id = _create_customer(client, "anon-offer-003")
    client.get(f"/api/v1/offers/generate/{customer_id}")

    response = client.get(f"/api/v1/offers/analytics/{customer_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["total_offers_generated"] > 0
