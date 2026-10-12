import logging
import os
import sqlite3
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator

# Configure Logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("food-ordering-service")

# In-memory log buffer for /logs endpoint
log_buffer = deque(maxlen=200)

class BufferLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            log_buffer.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage()
            })
        except Exception:
            pass

buffer_handler = BufferLogHandler()
buffer_handler.setFormatter(logging.Formatter(LOG_FORMAT))
logger.addHandler(buffer_handler)
logging.getLogger("uvicorn.access").addHandler(buffer_handler)

# Database Setup
DB_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).with_name("food_ordering.db")))

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    logger.info("Initializing database schema...")
    with db() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS restaurants(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                address TEXT NOT NULL,
                phone TEXT NOT NULL,
                cuisine TEXT DEFAULT 'General',
                rating REAL DEFAULT 4.5
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS menu(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL,
                category TEXT DEFAULT 'Main Course',
                available INTEGER NOT NULL DEFAULT 1
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS orders(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER NOT NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                item_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                total_price REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        # Backward-compatible column migration if table already existed
        cols_rest = [row[1] for row in c.execute("PRAGMA table_info(restaurants)").fetchall()]
        if "cuisine" not in cols_rest:
            c.execute("ALTER TABLE restaurants ADD COLUMN cuisine TEXT DEFAULT 'General'")
        if "rating" not in cols_rest:
            c.execute("ALTER TABLE restaurants ADD COLUMN rating REAL DEFAULT 4.5")
        cols_menu = [row[1] for row in c.execute("PRAGMA table_info(menu)").fetchall()]
        if "category" not in cols_menu:
            c.execute("ALTER TABLE menu ADD COLUMN category TEXT DEFAULT 'Main Course'")
        c.commit()
    logger.info("Database initialized successfully at %s", DB_PATH)

APP_VERSION = "1.0.0"

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Food Ordering Service started successfully (v%s)", APP_VERSION)
    yield
    logger.info("Food Ordering Service shutting down...")

app = FastAPI(
    title="Online Food Ordering System",
    description="Microservice API for Restaurant, Menu, and Order Management with Prometheus Metrics and Structured Logging.",
    version=APP_VERSION,
    lifespan=lifespan
)

# Instrument Prometheus metrics
Instrumentator().instrument(app).expose(app)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000.0
    logger.info(
        "%s %s -> status=%d duration=%.2fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms
    )
    return response

# Pydantic Models
class Restaurant(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=250)
    phone: str = Field(min_length=5, max_length=30)
    cuisine: Optional[str] = "General"
    rating: Optional[float] = Field(default=4.5, ge=0.0, le=5.0)

class MenuItem(BaseModel):
    restaurant_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = ""
    price: float = Field(gt=0)
    category: Optional[str] = "Main Course"
    available: Optional[bool] = True

class Order(BaseModel):
    restaurant_id: int = Field(gt=0)
    customer_name: str = Field(min_length=1, max_length=100)
    customer_phone: str = Field(min_length=5, max_length=30)
    item_name: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0, le=100)
    total_price: float = Field(gt=0)

class Status(BaseModel):
    status: str = Field(pattern="^(PLACED|CONFIRMED|PREPARING|OUT_FOR_DELIVERY|DELIVERED|CANCELLED)$")

# ==================== Core / Health Endpoints ====================

@app.get("/")
def root():
    return {
        "service": "online-food-ordering",
        "version": APP_VERSION,
        "status": "online",
        "docs_url": "/docs",
        "endpoints": {
            "restaurants": "/restaurants",
            "menu": "/menu",
            "orders": "/orders",
            "health": "/health",
            "version": "/version",
            "logs": "/logs",
            "metrics": "/metrics"
        }
    }

@app.get("/health")
def health():
    try:
        with db() as c:
            c.execute("SELECT 1").fetchone()
        db_status = "connected"
    except Exception as e:
        logger.error("Health check database failure: %s", str(e))
        db_status = f"error: {str(e)}"
        raise HTTPException(status_code=503, detail="Database unhealthy")
    
    return {
        "status": "healthy",
        "service": "online-food-ordering",
        "version": APP_VERSION,
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/version")
def version():
    return {
        "service": "online-food-ordering",
        "version": APP_VERSION,
        "environment": os.getenv("ENVIRONMENT", "production")
    }

@app.get("/logs")
def get_logs(limit: int = Query(50, ge=1, le=200)):
    items = list(log_buffer)[-limit:]
    return {
        "service": "online-food-ordering",
        "count": len(items),
        "logs": items
    }

# ==================== Restaurant Management ====================

@app.get("/restaurants")
def get_restaurants():
    with db() as c:
        rows = c.execute("SELECT * FROM restaurants ORDER BY id").fetchall()
        return [dict(x) for x in rows]

@app.post("/restaurants", status_code=201)
def add_restaurant(x: Restaurant):
    with db() as c:
        r = c.execute(
            "INSERT INTO restaurants(name, address, phone, cuisine, rating) VALUES(?, ?, ?, ?, ?)",
            (x.name, x.address, x.phone, x.cuisine or "General", x.rating or 4.5)
        )
        c.commit()
        rid = r.lastrowid
        logger.info("Created restaurant id=%d name='%s'", rid, x.name)
        return {"id": rid, **x.model_dump()}

@app.get("/restaurants/{rid}")
def get_restaurant(rid: int):
    with db() as c:
        r = c.execute("SELECT * FROM restaurants WHERE id=?", (rid,)).fetchone()
    if not r:
        logger.warning("Restaurant not found id=%d", rid)
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return dict(r)

@app.put("/restaurants/{rid}")
def update_restaurant(rid: int, x: Restaurant):
    with db() as c:
        r = c.execute(
            "UPDATE restaurants SET name=?, address=?, phone=?, cuisine=?, rating=? WHERE id=?",
            (x.name, x.address, x.phone, x.cuisine or "General", x.rating or 4.5, rid)
        )
        c.commit()
        if r.rowcount == 0:
            raise HTTPException(status_code=404, detail="Restaurant not found")
        logger.info("Updated restaurant id=%d", rid)
        return {"id": rid, **x.model_dump()}

@app.delete("/restaurants/{rid}")
def delete_restaurant(rid: int):
    with db() as c:
        r = c.execute("DELETE FROM restaurants WHERE id=?", (rid,))
        c.commit()
        if r.rowcount == 0:
            raise HTTPException(status_code=404, detail="Restaurant not found")
        logger.info("Deleted restaurant id=%d", rid)
        return {"id": rid, "message": "Restaurant deleted successfully"}

# ==================== Menu Management ====================

@app.get("/menu")
def get_menu(restaurant_id: Optional[int] = Query(None), category: Optional[str] = Query(None)):
    with db() as c:
        query = "SELECT * FROM menu WHERE 1=1"
        params = []
        if restaurant_id is not None:
            query += " AND restaurant_id=?"
            params.append(restaurant_id)
        if category is not None:
            query += " AND category=?"
            params.append(category)
        query += " ORDER BY id"
        rows = c.execute(query, tuple(params)).fetchall()
        return [dict(x) for x in rows]

@app.post("/menu", status_code=201)
def add_menu(x: MenuItem):
    with db() as c:
        rest = c.execute("SELECT id FROM restaurants WHERE id=?", (x.restaurant_id,)).fetchone()
        if not rest:
            logger.warning("Cannot add menu: Restaurant not found id=%d", x.restaurant_id)
            raise HTTPException(status_code=404, detail="Restaurant not found")
        r = c.execute(
            "INSERT INTO menu(restaurant_id, name, description, price, category, available) VALUES(?, ?, ?, ?, ?, ?)",
            (x.restaurant_id, x.name, x.description or "", x.price, x.category or "Main Course", int(bool(x.available)))
        )
        c.commit()
        mid = r.lastrowid
        logger.info("Added menu item id=%d '%s' to restaurant id=%d", mid, x.name, x.restaurant_id)
        return {"id": mid, **x.model_dump()}

@app.get("/menu/{mid}")
def get_menu_item(mid: int):
    with db() as c:
        r = c.execute("SELECT * FROM menu WHERE id=?", (mid,)).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return dict(r)

@app.put("/menu/{mid}")
def update_menu_item(mid: int, x: MenuItem):
    with db() as c:
        rest = c.execute("SELECT id FROM restaurants WHERE id=?", (x.restaurant_id,)).fetchone()
        if not rest:
            raise HTTPException(status_code=404, detail="Restaurant not found")
        r = c.execute(
            "UPDATE menu SET restaurant_id=?, name=?, description=?, price=?, category=?, available=? WHERE id=?",
            (x.restaurant_id, x.name, x.description or "", x.price, x.category or "Main Course", int(bool(x.available)), mid)
        )
        c.commit()
        if r.rowcount == 0:
            raise HTTPException(status_code=404, detail="Menu item not found")
        logger.info("Updated menu item id=%d", mid)
        return {"id": mid, **x.model_dump()}

@app.delete("/menu/{mid}")
def delete_menu_item(mid: int):
    with db() as c:
        r = c.execute("DELETE FROM menu WHERE id=?", (mid,))
        c.commit()
        if r.rowcount == 0:
            raise HTTPException(status_code=404, detail="Menu item not found")
        logger.info("Deleted menu item id=%d", mid)
        return {"id": mid, "message": "Menu item deleted successfully"}

# ==================== Order Management ====================

@app.get("/orders")
def get_orders(restaurant_id: Optional[int] = Query(None), status: Optional[str] = Query(None)):
    with db() as c:
        query = "SELECT * FROM orders WHERE 1=1"
        params = []
        if restaurant_id is not None:
            query += " AND restaurant_id=?"
            params.append(restaurant_id)
        if status is not None:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY id"
        rows = c.execute(query, tuple(params)).fetchall()
        return [dict(x) for x in rows]

@app.post("/orders", status_code=201)
def add_order(x: Order):
    with db() as c:
        rest = c.execute("SELECT id FROM restaurants WHERE id=?", (x.restaurant_id,)).fetchone()
        if not rest:
            logger.warning("Order placement failed: Restaurant id=%d not found", x.restaurant_id)
            raise HTTPException(status_code=404, detail="Restaurant not found")
        now_ts = datetime.now(timezone.utc).isoformat()
        r = c.execute(
            "INSERT INTO orders(restaurant_id, customer_name, customer_phone, item_name, quantity, total_price, status, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (x.restaurant_id, x.customer_name, x.customer_phone, x.item_name, x.quantity, x.total_price, "PLACED", now_ts)
        )
        c.commit()
        oid = r.lastrowid
        logger.info("Created order id=%d for '%s' item='%s' amount=%.2f", oid, x.customer_name, x.item_name, x.total_price)
        return {"id": oid, **x.model_dump(), "status": "PLACED", "created_at": now_ts}

@app.get("/orders/{oid}")
def get_order(oid: int):
    with db() as c:
        r = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not r:
        logger.warning("Order not found id=%d", oid)
        raise HTTPException(status_code=404, detail="Order not found")
    return dict(r)

@app.patch("/orders/{oid}/status")
def order_status(oid: int, x: Status):
    with db() as c:
        r = c.execute("UPDATE orders SET status=? WHERE id=?", (x.status, oid))
        c.commit()
        if r.rowcount == 0:
            logger.warning("Order update status failed: id=%d not found", oid)
            raise HTTPException(status_code=404, detail="Order not found")
    logger.info("Order id=%d status changed to %s", oid, x.status)
    return {"id": oid, "status": x.status}

@app.delete("/orders/{oid}")
def delete_order(oid: int):
    with db() as c:
        r = c.execute("DELETE FROM orders WHERE id=?", (oid,))
        c.commit()
        if r.rowcount == 0:
            raise HTTPException(status_code=404, detail="Order not found")
    logger.info("Order id=%d deleted/cancelled", oid)
    return {"id": oid, "message": "Order deleted successfully"}
