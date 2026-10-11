import os
import requests
from langchain_core.tools import tool

BASE_URL = "http://127.0.0.1:8000"

@tool
def read_invoice_file(file_path: str) -> str:
    """Reads the raw text content of an invoice file from the local filesystem."""
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' does not exist."
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

@tool
def check_purchase_order(po_number: str) -> str:
    """Queries the ERP system to verify if a Purchase Order (PO) exists, its approval status, and the authorized expected amount."""
    try:
        response = requests.get(f"{BASE_URL}/api/pos/{po_number.strip()}", timeout=5)
        if response.status_code == 200:
            return str(response.json())
        elif response.status_code == 404:
            return f"PO Not Found: {response.json().get('detail', 'Not found')}"
        else:
            return f"ERP Error: HTTP {response.status_code} {response.text}"
    except Exception as e:
        return f"Network Error checking PO: {str(e)}"

@tool
def update_po_status(po_number: str, status: str) -> str:
    """Updates the status of a Purchase Order (e.g., from ON_HOLD to APPROVED, or VOID)."""
    try:
        response = requests.put(f"{BASE_URL}/api/pos/{po_number.strip()}/status", json={"status": status}, timeout=5)
        if response.status_code == 200:
            return str(response.json())
        elif response.status_code == 404:
            return f"PO Not Found: {response.json().get('detail', 'Not found')}"
        else:
            return f"ERP Error: HTTP {response.status_code} {response.text}"
    except Exception as e:
        return f"Network Error during PO status update: {str(e)}"

@tool
def create_purchase_order(po_number: str, vendor_name: str, expected_amount: float, status: str = "APPROVED") -> str:
    """Creates a new Purchase Order (PO) dynamically in the ERP system."""
    payload = {
        "po_number": po_number,
        "vendor_name": vendor_name,
        "expected_amount": expected_amount,
        "status": status,
    }
    try:
        response = requests.post(
            f"{BASE_URL}/api/pos", json=payload, timeout=5
        )
        if response.status_code == 200:
            return f"PO Creation Successful: {response.json()}"
        else:
            return f"PO Creation Failed with HTTP {response.status_code}: {response.text}"
    except Exception as e:
        return f"Network Error during PO creation: {str(e)}"

@tool
def search_purchase_orders(query: str) -> str:
    """Search purchase orders by vendor name (e.g. 'OfficeSupplies', 'TechCorp') or partial PO number."""
    try:
        response = requests.get(f"{BASE_URL}/purchase_orders/search", params={"query": query.strip()}, timeout=5)
        if response.status_code == 200:
            return str(response.json())
        return f"Search failed with status {response.status_code}: {response.text}"
    except Exception as e:
        return f"Network Error during search: {str(e)}"

@tool
def submit_invoice_to_erp(invoice_id: str, po_number: str, vendor_name: str, amount: float, due_date: str) -> str:
    """Submits a validated invoice record into the ERP system."""
    payload = {
        "invoice_id": invoice_id,
        "po_number": po_number,
        "vendor_name": vendor_name,
        "amount": amount,
        "due_date": due_date,
    }
    try:
        response = requests.post(
            f"{BASE_URL}/api/invoices", json=payload, timeout=5
        )
        if response.status_code == 200:
            return f"Submission Successful: {response.json()}"
        else:
            return f"Submission Failed with HTTP {response.status_code}: {response.text}"
    except Exception as e:
        return f"Network Error during submission: {str(e)}"

@tool
def verify_invoice_in_erp(invoice_id: str) -> str:
    """Queries the ERP database to independently verify that an invoice was successfully stored and matches ground truth."""
    try:
        response = requests.get(
            f"{BASE_URL}/api/invoices/{invoice_id.strip()}", timeout=5
        )
        if response.status_code == 200:
            return f"Verification Confirmed: {response.json()}"
        else:
            return f"Verification Failed: {response.text}"
    except Exception as e:
        return f"Network Error during verification: {str(e)}"