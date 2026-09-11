"""Integration tests for the customers API."""


def test_create_customer(client):
    response = client.post("/api/v1/customers", json={"external_ref": "anon-test-001"})
    assert response.status_code == 201
    body = response.json()
    assert body["external_ref"] == "anon-test-001"
    assert body["segment"] == "new_user"


def test_duplicate_customer_returns_409(client):
    payload = {"external_ref": "anon-dup-001"}
    client.post("/api/v1/customers", json=payload)
    assert client.post("/api/v1/customers", json=payload).status_code == 409


def test_get_nonexistent_customer_returns_404(client):
    assert client.get("/api/v1/customers/99999").status_code == 404


def test_invalid_external_ref_rejected(client):
    assert client.post("/api/v1/customers", json={"external_ref": "invalid ref!"}).status_code == 422


def test_add_purchase_updates_profile(client):
    customer_id = client.post("/api/v1/customers", json={"external_ref": "anon-purchase-001"}).json()["id"]
    purchase_resp = client.post(f"/api/v1/customers/{customer_id}/purchases", json={"price": 100.0, "quantity": 2, "had_discount": False})
    assert purchase_resp.status_code == 201
    body = purchase_resp.json()
    assert body["total_orders"] == 1
    assert body["total_revenue"] == 200.0
    assert body["segment"] == "repeat_buyer"
