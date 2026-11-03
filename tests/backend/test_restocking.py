"""
Tests for restocking API endpoints (recommendations and submitted orders).
"""
import pytest

import mock_data


@pytest.fixture(autouse=True)
def clear_restocking_orders():
    """Submitted orders live in module-level state, so reset around every test."""
    mock_data.restocking_orders.clear()
    yield
    mock_data.restocking_orders.clear()


class TestRestockingRecommendations:
    """Test suite for GET /api/restocking/recommendations."""

    def test_zero_budget_recommends_nothing(self, client):
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert data["recommendations"] == []
        assert data["total_cost"] == 0
        assert data["remaining_budget"] == 0
        # Slider maximum must be available even when nothing is funded
        assert data["full_restock_cost"] > 0

    def test_negative_budget_rejected(self, client):
        response = client.get("/api/restocking/recommendations?budget=-1")
        assert response.status_code == 400

    def test_recommendation_structure(self, client):
        data = client.get("/api/restocking/recommendations?budget=1000000").json()
        assert len(data["recommendations"]) > 0

        rec = data["recommendations"][0]
        for field in ["sku", "name", "trend", "forecasted_demand", "quantity_on_hand",
                      "shortfall", "recommended_quantity", "unit_cost", "line_total",
                      "lead_time_days", "fully_funded"]:
            assert field in rec

    def test_budget_is_never_exceeded(self, client):
        for budget in [50, 500, 2500, 10000, 50000]:
            data = client.get(f"/api/restocking/recommendations?budget={budget}").json()
            assert data["total_cost"] <= budget
            assert data["remaining_budget"] >= 0
            assert abs(data["total_cost"] + data["remaining_budget"] - budget) < 0.01

    def test_large_budget_funds_every_shortfall(self, client):
        full_cost = client.get("/api/restocking/recommendations?budget=0").json()["full_restock_cost"]
        data = client.get(f"/api/restocking/recommendations?budget={full_cost}").json()

        assert all(r["fully_funded"] for r in data["recommendations"])
        assert all(r["recommended_quantity"] == r["shortfall"] for r in data["recommendations"])
        assert abs(data["total_cost"] - full_cost) < 0.01

    def test_sorted_by_largest_shortfall(self, client):
        data = client.get("/api/restocking/recommendations?budget=1000000").json()
        shortfalls = [r["shortfall"] for r in data["recommendations"]]
        assert shortfalls == sorted(shortfalls, reverse=True)

    def test_items_without_shortfall_are_excluded(self, client):
        """PSU-501 has more stock on hand than forecast demand."""
        data = client.get("/api/restocking/recommendations?budget=1000000").json()
        assert "PSU-501" not in [r["sku"] for r in data["recommendations"]]

    def test_small_budget_buys_partial_quantity(self, client):
        data = client.get("/api/restocking/recommendations?budget=100").json()
        assert len(data["recommendations"]) > 0
        assert any(not r["fully_funded"] for r in data["recommendations"])

    def test_line_total_matches_quantity_times_cost(self, client):
        data = client.get("/api/restocking/recommendations?budget=5000").json()
        for rec in data["recommendations"]:
            assert abs(rec["line_total"] - rec["recommended_quantity"] * rec["unit_cost"]) < 0.01


class TestRestockingOrders:
    """Test suite for POST/GET /api/restocking/orders."""

    def test_no_orders_initially(self, client):
        response = client.get("/api/restocking/orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_order(self, client):
        payload = {"items": [{"sku": "WDG-001", "quantity": 100}], "budget": 5000}
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        assert order["order_number"].startswith("RST-")
        assert order["status"] == "Submitted"
        assert order["total_cost"] == pytest.approx(100 * 14.50)
        assert order["lead_time_days"] == 7
        assert order["items"][0]["sku"] == "WDG-001"

    def test_cost_is_computed_server_side(self, client):
        """Client-supplied prices are ignored; only sku and quantity are accepted."""
        payload = {"items": [{"sku": "WDG-001", "quantity": 10, "unit_cost": 0.01}]}
        order = client.post("/api/restocking/orders", json=payload).json()
        assert order["total_cost"] == pytest.approx(145.0)

    def test_lead_time_is_longest_item(self, client):
        payload = {"items": [
            {"sku": "WDG-001", "quantity": 1},   # 7 days
            {"sku": "MTR-304", "quantity": 1},   # 28 days
        ]}
        order = client.post("/api/restocking/orders", json=payload).json()
        assert order["lead_time_days"] == 28

    def test_expected_delivery_follows_lead_time(self, client):
        from datetime import datetime
        order = client.post("/api/restocking/orders",
                            json={"items": [{"sku": "MTR-304", "quantity": 1}]}).json()
        submitted = datetime.fromisoformat(order["submitted_date"])
        expected = datetime.fromisoformat(order["expected_delivery"])
        assert (expected - submitted).days == order["lead_time_days"]

    def test_submitted_order_is_listed_newest_first(self, client):
        client.post("/api/restocking/orders", json={"items": [{"sku": "WDG-001", "quantity": 1}]})
        client.post("/api/restocking/orders", json={"items": [{"sku": "FLT-405", "quantity": 1}]})

        orders = client.get("/api/restocking/orders").json()
        assert len(orders) == 2
        assert orders[0]["items"][0]["sku"] == "FLT-405"
        assert orders[0]["order_number"] != orders[1]["order_number"]

    def test_empty_order_rejected(self, client):
        response = client.post("/api/restocking/orders", json={"items": []})
        assert response.status_code == 400

    def test_unknown_sku_returns_404(self, client):
        response = client.post("/api/restocking/orders",
                               json={"items": [{"sku": "NOPE-999", "quantity": 1}]})
        assert response.status_code == 404

    @pytest.mark.parametrize("quantity", [0, -5])
    def test_non_positive_quantity_rejected(self, client, quantity):
        response = client.post("/api/restocking/orders",
                               json={"items": [{"sku": "WDG-001", "quantity": quantity}]})
        assert response.status_code == 400

    def test_duplicate_sku_rejected(self, client):
        response = client.post("/api/restocking/orders", json={"items": [
            {"sku": "WDG-001", "quantity": 1}, {"sku": "WDG-001", "quantity": 2}]})
        assert response.status_code == 400

    def test_order_over_budget_rejected(self, client):
        response = client.post("/api/restocking/orders",
                               json={"items": [{"sku": "MTR-304", "quantity": 10}], "budget": 100})
        assert response.status_code == 400
        assert client.get("/api/restocking/orders").json() == []

    def test_recommendation_can_be_submitted_as_order(self, client):
        """End to end: recommended lines are accepted as an order within the same budget."""
        budget = 5000
        recs = client.get(f"/api/restocking/recommendations?budget={budget}").json()["recommendations"]
        items = [{"sku": r["sku"], "quantity": r["recommended_quantity"]} for r in recs]

        response = client.post("/api/restocking/orders", json={"items": items, "budget": budget})
        assert response.status_code == 201
        assert response.json()["total_cost"] <= budget
