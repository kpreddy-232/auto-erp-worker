import sqlite3
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Mock ERP System")
DB_FILE = "erp.db"

# State tracking for deliberate transient failure demonstration
failure_counter = {"POST_attempts": 0}


# --- Database Initialization & Seeding ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Purchase Orders table (Source of Truth)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_number TEXT PRIMARY KEY,
            vendor_name TEXT NOT NULL,
            expected_amount REAL NOT NULL,
            status TEXT NOT NULL
        )
    """)

    # Invoices table (Entered records)
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

    # Seed baseline PO records if empty
    cursor.execute("SELECT COUNT(*) FROM purchase_orders")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO purchase_orders VALUES (?, ?, ?, ?)",
            [
                ("PO-1001", "TechCorp Solutions", 1500.00, "APPROVED"),
                ("PO-1002", "OfficeSupplies Co", 420.50, "APPROVED"),
                ("PO-1003", "CloudServe Inc", 3000.00, "ON_HOLD"),
            ],
        )
        conn.commit()
    conn.close()


init_db()


# --- Pydantic Schemas ---
class InvoicePayload(BaseModel):
    invoice_id: str = Field(..., description="Unique invoice ID (e.g., INV-2024-001)")
    po_number: str = Field(..., description="Associated PO number (e.g., PO-1001)")
    vendor_name: str = Field(..., description="Vendor name extracted from invoice")
    amount: float = Field(..., description="Total invoice amount")
    due_date: str = Field(..., description="Payment due date (YYYY-MM-DD)")


# --- API Routes ---
@app.get("/api/pos/{po_number}")
def get_purchase_order(po_number: str):
    """Allows the agent to verify if a PO exists and check its authorized amount."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT po_number, vendor_name, expected_amount, status FROM purchase_orders WHERE po_number = ?",
        (po_number,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"PO '{po_number}' not found.")

    return {
        "po_number": row[0],
        "vendor_name": row[1],
        "expected_amount": row[2],
        "status": row[3],
    }


@app.post("/api/invoices")
def submit_invoice(payload: InvoicePayload, simulate_flake: bool = True):
    """
    Submits an invoice. 
    Simulates a transient 500 error on the 1st attempt to test agent retry resilience.
    """
    if simulate_flake:
        failure_counter["POST_attempts"] += 1
        if failure_counter["POST_attempts"] % 2 == 1:
            raise HTTPException(
                status_code=500,
                detail="Database connection pool timeout. Please retry the transaction.",
            )

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?)",
            (
                payload.invoice_id,
                payload.po_number,
                payload.vendor_name,
                payload.amount,
                payload.due_date,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Invoice '{payload.invoice_id}' has already been processed.",
        )
    finally:
        conn.close()

    return {
        "status": "SUCCESS",
        "message": f"Invoice {payload.invoice_id} recorded in ERP.",
        "invoice_id": payload.invoice_id,
    }


@app.get("/api/invoices/{invoice_id}")
def verify_invoice(invoice_id: str):
    """Verification route: The agent must call this to confirm ground truth entry."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT invoice_id, po_number, amount, due_date FROM invoices WHERE invoice_id = ?",
        (invoice_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Verification failed: Invoice '{invoice_id}' does not exist.",
        )

    return {
        "verified": True,
        "invoice_id": row[0],
        "po_number": row[1],
        "amount": row[2],
        "due_date": row[3],
    }