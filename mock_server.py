import sqlite3
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Mock ERP System")
DB_FILE = "erp.db"
failure_counter = {"POST_attempts": 0}

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_number TEXT PRIMARY KEY,
            vendor_name TEXT NOT NULL,
            expected_amount REAL NOT NULL,
            status TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_id TEXT PRIMARY KEY,
            po_number TEXT NOT NULL,
            vendor_name TEXT NOT NULL,
            amount REAL NOT NULL,
            due_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM purchase_orders")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("INSERT INTO purchase_orders VALUES (?, ?, ?, ?)", [
            ("PO-1001", "TechCorp Solutions", 1500.00, "APPROVED"),
            ("PO-1002", "OfficeSupplies Co", 420.50, "APPROVED"),
            ("PO-1003", "CloudServe Inc", 3000.00, "ON_HOLD"),
            ("PO-2050", "Apex Innovations", 8500.00, "APPROVED"),
        ])
        conn.commit()
    conn.close()

init_db()

class InvoicePayload(BaseModel):
    invoice_id: str
    po_number: str
    vendor_name: str
    amount: float
    due_date: str

class POPayload(BaseModel):
    po_number: str
    vendor_name: str
    expected_amount: float
    status: str = "APPROVED"

class POStatusUpdate(BaseModel):
    status: str

@app.post("/api/pos")
def create_purchase_order(payload: POPayload):
    """Creates a new Purchase Order in the ERP system."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO purchase_orders VALUES (?, ?, ?, ?)",
            (payload.po_number, payload.vendor_name, payload.expected_amount, payload.status))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail=f"PO '{payload.po_number}' already exists.")
    finally:
        conn.close()
    return {"message": f"Purchase Order {payload.po_number} successfully created.", "po_number": payload.po_number}

@app.get("/api/pos/{po_number}")
def get_purchase_order(po_number: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM purchase_orders WHERE po_number = ?", (po_number,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"PO '{po_number}' not found.")
    return {"po_number": row[0], "vendor_name": row[1], "expected_amount": row[2], "status": row[3]}

@app.put("/api/pos/{po_number}/status")
def update_po_status(po_number: str, payload: POStatusUpdate):
    """Updates a purchase order's status (e.g., APPROVED, ON_HOLD, VOID)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE purchase_orders SET status = ? WHERE po_number = ?", (payload.status, po_number))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail=f"PO '{po_number}' not found.")
    conn.commit()
    conn.close()
    return {"message": f"Purchase Order {po_number} status updated to {payload.status}.", "status": payload.status}

@app.get("/purchase_orders/search")
def search_purchase_orders(query: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    search_term = f"%{query.strip()}%"
    cursor.execute("SELECT * FROM purchase_orders WHERE vendor_name LIKE ? OR po_number LIKE ?", (search_term, search_term))
    rows = cursor.fetchall()
    conn.close()
    return {"matches": [{"po_number": r[0], "vendor_name": r[1], "expected_amount": r[2], "status": r[3]} for r in rows]}

@app.post("/api/invoices")
def submit_invoice(payload: InvoicePayload, simulate_flake: bool = True):
    # This flake tests the agent's ability to observe a 500 error and retry
    if simulate_flake:
        failure_counter["POST_attempts"] += 1
        if failure_counter["POST_attempts"] % 2 == 1:
            raise HTTPException(status_code=500, detail="Database connection pool timeout. Please retry the transaction.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?)",
            (payload.invoice_id, payload.po_number, payload.vendor_name, payload.amount, payload.due_date, datetime.utcnow().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Invoice already processed.")
    finally:
        conn.close()
    return {"status": "SUCCESS", "invoice_id": payload.invoice_id}

@app.get("/api/invoices/{invoice_id}")
def verify_invoice(invoice_id: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE invoice_id = ?", (invoice_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Verification failed: Not found.")
    return {"invoice_id": row[0], "amount": row[3]}