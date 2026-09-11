"""Integration tests for customer endpoints."""


def test_create_customer_returns_profile(client):
    response = client.post("/api/v1/customers", json={"external_ref": "anon-test-001"})
    assert response.status_code == 201
    body = response.json()
    assert body["external_ref"] == "anon-test-001"
    assert body["segment"] == "new_user"


def test_duplicate_external_ref_is_rejected(client):
    client.post("/api/v1/customers", json={"external_ref": "anon-test-002"})
    response = client.post("/api/v1/customers", json={"external_ref": "anon-test-002"})
    assert response.status_code == 409


def test_unsafe_external_ref_is_rejected(client):
    response = client.post("/api/v1/customers", json={"external_ref": "<script>alert(1)</script>"})
    assert response.status_code == 422


def test_missing_customer_returns_not_found(client):
    assert client.get("/api/v1/customers/999999").status_code == 404


def test_purchase_updates_profile_metrics(client):
    created = client.post("/api/v1/customers", json={"external_ref": "anon-test-003"}).json()
    response = client.post(
        f"/api/v1/customers/{created['id']}/purchases",
        json={"price": 2500, "quantity": 2, "had_discount": False, "category": "home"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["total_orders"] == 1
    assert body["total_revenue"] == 5000.0
