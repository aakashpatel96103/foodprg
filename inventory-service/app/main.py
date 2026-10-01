from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator

DB = Path(__file__).with_name("food_ordering.db")

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS restaurants(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,address TEXT NOT NULL,phone TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS menu(id INTEGER PRIMARY KEY AUTOINCREMENT,restaurant_id INTEGER NOT NULL,name TEXT NOT NULL,description TEXT,price REAL NOT NULL,available INTEGER NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,restaurant_id INTEGER NOT NULL,customer_name TEXT NOT NULL,customer_phone TEXT NOT NULL,item_name TEXT NOT NULL,quantity INTEGER NOT NULL,total_price REAL NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL)")
        c.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Online Food Ordering System", version="1.0.0", lifespan=lifespan)
Instrumentator().instrument(app).expose(app)

class Restaurant(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=250)
    phone: str = Field(min_length=5, max_length=30)

class MenuItem(BaseModel):
    restaurant_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    price: float = Field(gt=0)
    available: bool = True

class Order(BaseModel):
    restaurant_id: int = Field(gt=0)
    customer_name: str = Field(min_length=1, max_length=100)
    customer_phone: str = Field(min_length=5, max_length=30)
    item_name: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0, le=100)
    total_price: float = Field(gt=0)

class Status(BaseModel):
    status: str = Field(pattern="^(PLACED|CONFIRMED|PREPARING|OUT_FOR_DELIVERY|DELIVERED|CANCELLED)$")

@app.get("/")
def root(): return {"service":"online-food-ordering","version":"1.0.0"}

@app.get("/health")
def health(): return {"status":"healthy","service":"online-food-ordering","version":"1.0.0"}

@app.get("/restaurants")
def restaurants():
    with db() as c: return [dict(x) for x in c.execute("SELECT * FROM restaurants ORDER BY id")]

@app.post("/restaurants", status_code=201)
def add_restaurant(x: Restaurant):
    with db() as c:
        r=c.execute("INSERT INTO restaurants(name,address,phone) VALUES(?,?,?)",(x.name,x.address,x.phone))
        c.commit()
        return {"id":r.lastrowid,**x.model_dump()}

@app.get("/restaurants/{rid}")
def get_restaurant(rid:int):
    with db() as c: r=c.execute("SELECT * FROM restaurants WHERE id=?",(rid,)).fetchone()
    if not r: raise HTTPException(404,"Restaurant not found")
    return dict(r)

@app.get("/menu")
def menu(restaurant_id:Optional[int]=Query(None)):
    with db() as c:
        q="SELECT * FROM menu" if restaurant_id is None else "SELECT * FROM menu WHERE restaurant_id=?"
        rows=c.execute(q,() if restaurant_id is None else (restaurant_id,)).fetchall()
        return [dict(x) for x in rows]

@app.post("/menu", status_code=201)
def add_menu(x:MenuItem):
    with db() as c:
        if not c.execute("SELECT id FROM restaurants WHERE id=?",(x.restaurant_id,)).fetchone(): raise HTTPException(404,"Restaurant not found")
        r=c.execute("INSERT INTO menu(restaurant_id,name,description,price,available) VALUES(?,?,?,?,?)",(x.restaurant_id,x.name,x.description,x.price,int(x.available)))
        c.commit()
        return {"id":r.lastrowid,**x.model_dump()}

@app.get("/orders")
def orders():
    with db() as c: return [dict(x) for x in c.execute("SELECT * FROM orders ORDER BY id")]

@app.post("/orders", status_code=201)
def add_order(x:Order):
    with db() as c:
        if not c.execute("SELECT id FROM restaurants WHERE id=?",(x.restaurant_id,)).fetchone(): raise HTTPException(404,"Restaurant not found")
        t=datetime.now(timezone.utc).isoformat()
        r=c.execute("INSERT INTO orders(restaurant_id,customer_name,customer_phone,item_name,quantity,total_price,status,created_at) VALUES(?,?,?,?,?,?,?,?)",(x.restaurant_id,x.customer_name,x.customer_phone,x.item_name,x.quantity,x.total_price,"PLACED",t))
        c.commit()
        return {"id":r.lastrowid,**x.model_dump(),"status":"PLACED","created_at":t}

@app.get("/orders/{oid}")
def get_order(oid:int):
    with db() as c: r=c.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone()
    if not r: raise HTTPException(404,"Order not found")
    return dict(r)

@app.patch("/orders/{oid}/status")
def order_status(oid:int,x:Status):
    with db() as c:
        r=c.execute("UPDATE orders SET status=? WHERE id=?",(x.status,oid)); c.commit()
        if not r.rowcount: raise HTTPException(404,"Order not found")
    return {"id":oid,"status":x.status}
