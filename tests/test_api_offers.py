"""Integration tests for offer endpoints."""


def _customer_with_purchase(client, ref: str = "anon-offer-001", price: float = 4000):
    created = client.post("/api/v1/customers", json={"external_ref": ref}).json()
    client.post(f"/api/v1/customers/{created['id']}/purchases",
                json={"price": price, "quantity": 1, "had_discount": False, "category": "home"})
    return created["id"]


def test_generate_offers_returns_ranked_list(client):
    customer_id = _customer_with_purchase(client)
    response = client.get(f"/api/v1/offers/generate/{customer_id}?cart_total=4000")
    assert response.status_code == 200
    offers = response.json()["offers"]
    assert 1 <= len(offers) <= 3
    assert offers == sorted(offers, key=lambda o: o["score"], reverse=True)


def test_generate_offers_for_unknown_customer_returns_404(client):
    assert client.get("/api/v1/offers/generate/999999").status_code == 404


def test_apply_offer_marks_it_as_applied(client):
    customer_id = _customer_with_purchase(client, ref="anon-offer-002")
    offer_uid = client.get(f"/api/v1/offers/generate/{customer_id}").json()["offers"][0]["offer_uid"]
    response = client.post(f"/api/v1/offers/apply/{offer_uid}", json={"order_reference": "order-1", "converted": True})
    assert response.status_code == 200
    assert response.json()["status"] == "applied"


def test_applying_same_offer_twice_is_rejected(client):
    customer_id = _customer_with_purchase(client, ref="anon-offer-003")
    offer_uid = client.get(f"/api/v1/offers/generate/{customer_id}").json()["offers"][0]["offer_uid"]
    client.post(f"/api/v1/offers/apply/{offer_uid}", json={"converted": True})
    response = client.post(f"/api/v1/offers/apply/{offer_uid}", json={"converted": True})
    assert response.status_code == 409


def test_customer_offer_analytics_counts_applied_offers(client):
    customer_id = _customer_with_purchase(client, ref="anon-offer-004")
    offers = client.get(f"/api/v1/offers/generate/{customer_id}").json()["offers"]
    client.post(f"/api/v1/offers/apply/{offers[0]['offer_uid']}", json={"converted": True})
    body = client.get(f"/api/v1/offers/analytics/{customer_id}").json()
    assert body["total_offers_generated"] == len(offers)
    assert body["total_offers_applied"] == 1
