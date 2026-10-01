from fastapi.testclient import TestClient
from app.main import app, init_db
init_db()
client=TestClient(app)

def test_root():
    r=client.get("/")
    assert r.status_code==200

def test_health():
    r=client.get("/health")
    assert r.status_code==200
    assert r.json()["status"]=="healthy"

def test_metrics():
    r=client.get("/metrics")
    assert r.status_code==200
    assert "python_info" in r.text

def test_food_flow():
    r=client.post("/restaurants",json={"name":"Test Restaurant","address":"Mumbai","phone":"9999999999"})
    assert r.status_code==201
    rid=r.json()["id"]
    r=client.post("/menu",json={"restaurant_id":rid,"name":"Pizza","description":"Cheese","price":299,"available":True})
    assert r.status_code==201
    r=client.post("/orders",json={"restaurant_id":rid,"customer_name":"Test","customer_phone":"8888888888","item_name":"Pizza","quantity":2,"total_price":598})
    assert r.status_code==201
    assert r.json()["status"]=="PLACED"
