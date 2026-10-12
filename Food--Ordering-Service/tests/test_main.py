import sys
from pathlib import Path

# Ensure Food--Ordering-Service is in sys.path whether pytest is run from root or subfolder
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from app.main import app, init_db

init_db()
client = TestClient(app)

def test_root():
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "online-food-ordering"
    assert "endpoints" in data

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"

def test_version():
    r = client.get("/version")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == "1.0.0"

def test_logs():
    r = client.get("/logs")
    assert r.status_code == 200
    data = r.json()
    assert "logs" in data
    assert isinstance(data["logs"], list)

def test_metrics():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "http" in r.text or "python_info" in r.text

def test_restaurant_crud():
    # Create restaurant
    r = client.post("/restaurants", json={
        "name": "Spice Delight",
        "address": "123 Curry Lane, Mumbai",
        "phone": "+919876543210",
        "cuisine": "Indian",
        "rating": 4.8
    })
    assert r.status_code == 201
    rest_data = r.json()
    rid = rest_data["id"]
    assert rest_data["name"] == "Spice Delight"

    # List restaurants
    r = client.get("/restaurants")
    assert r.status_code == 200
    assert any(x["id"] == rid for x in r.json())

    # Get restaurant by ID
    r = client.get(f"/restaurants/{rid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Spice Delight"

    # Update restaurant
    r = client.put(f"/restaurants/{rid}", json={
        "name": "Spice Delight Grand",
        "address": "123 Curry Lane, Mumbai",
        "phone": "+919876543210",
        "cuisine": "Mughlai",
        "rating": 4.9
    })
    assert r.status_code == 200
    assert r.json()["name"] == "Spice Delight Grand"
    assert r.json()["cuisine"] == "Mughlai"

    # Get non-existent restaurant
    r = client.get("/restaurants/999999")
    assert r.status_code == 404

    # Delete restaurant
    r = client.delete(f"/restaurants/{rid}")
    assert r.status_code == 200

    # Verify deleted
    r = client.get(f"/restaurants/{rid}")
    assert r.status_code == 404

def test_menu_crud():
    # Create restaurant first
    r = client.post("/restaurants", json={
        "name": "Bella Italia",
        "address": "45 Roman Way, Delhi",
        "phone": "+919811223344",
        "cuisine": "Italian",
        "rating": 4.7
    })
    assert r.status_code == 201
    rid = r.json()["id"]

    # Try creating menu for non-existent restaurant
    r = client.post("/menu", json={
        "restaurant_id": 999999,
        "name": "Ghost Pizza",
        "price": 300,
        "available": True
    })
    assert r.status_code == 404

    # Create menu item
    r = client.post("/menu", json={
        "restaurant_id": rid,
        "name": "Margherita Pizza",
        "description": "Wood-fired with fresh basil and mozzarella",
        "price": 399.0,
        "category": "Pizza",
        "available": True
    })
    assert r.status_code == 201
    mid = r.json()["id"]

    # List menu filtered by restaurant_id
    r = client.get(f"/menu?restaurant_id={rid}")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert any(x["id"] == mid for x in items)

    # Get single menu item
    r = client.get(f"/menu/{mid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Margherita Pizza"

    # Update menu item
    r = client.put(f"/menu/{mid}", json={
        "restaurant_id": rid,
        "name": "Margherita Pizza Extra Cheese",
        "description": "Extra cheese and basil",
        "price": 449.0,
        "category": "Pizza",
        "available": True
    })
    assert r.status_code == 200
    assert r.json()["price"] == 449.0

    # Delete menu item
    r = client.delete(f"/menu/{mid}")
    assert r.status_code == 200

    # Verify deleted
    r = client.get(f"/menu/{mid}")
    assert r.status_code == 404

def test_order_management():
    # Create restaurant
    r = client.post("/restaurants", json={
        "name": "Burger Barn",
        "address": "88 Fast Food Blvd, Bangalore",
        "phone": "+919822334455",
        "cuisine": "American",
        "rating": 4.6
    })
    assert r.status_code == 201
    rid = r.json()["id"]

    # Create order with invalid restaurant
    r = client.post("/orders", json={
        "restaurant_id": 999999,
        "customer_name": "John Doe",
        "customer_phone": "+919123456789",
        "item_name": "Cheeseburger",
        "quantity": 2,
        "total_price": 500.0
    })
    assert r.status_code == 404

    # Create valid order
    r = client.post("/orders", json={
        "restaurant_id": rid,
        "customer_name": "Alice Smith",
        "customer_phone": "+919123456780",
        "item_name": "Smash Burger Meal",
        "quantity": 2,
        "total_price": 650.0
    })
    assert r.status_code == 201
    order_data = r.json()
    oid = order_data["id"]
    assert order_data["status"] == "PLACED"

    # List orders
    r = client.get("/orders")
    assert r.status_code == 200
    assert any(x["id"] == oid for x in r.json())

    # Get single order
    r = client.get(f"/orders/{oid}")
    assert r.status_code == 200
    assert r.json()["customer_name"] == "Alice Smith"

    # Update status to PREPARING
    r = client.patch(f"/orders/{oid}/status", json={"status": "PREPARING"})
    assert r.status_code == 200
    assert r.json()["status"] == "PREPARING"

    # Update status to DELIVERED
    r = client.patch(f"/orders/{oid}/status", json={"status": "DELIVERED"})
    assert r.status_code == 200
    assert r.json()["status"] == "DELIVERED"

    # Invalid status update fails validation
    r = client.patch(f"/orders/{oid}/status", json={"status": "INVALID_STATUS"})
    assert r.status_code == 422

    # Delete order
    r = client.delete(f"/orders/{oid}")
    assert r.status_code == 200

    # Verify deleted
    r = client.get(f"/orders/{oid}")
    assert r.status_code == 404
