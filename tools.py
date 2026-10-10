import os
import requests
from langchain_core.tools import tool

BASE_URL = "http://127.0.0.1:8000"

@tool
def read_invoice_file(file_path: str) -> str:
    """Reads the raw text content of an invoice file from the local filesystem.

    Args:
        file_path: Path to the invoice file (e.g., 'invoices/techcorp_invoice.txt').
    """
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' does not exist."

    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

@tool
def check_purchase_order(po_number: str) -> str:
    """Queries the ERP system to verify if a Purchase Order (PO) exists,
    its approval status, and the authorized expected amount.
    
    Args:
        po_number: The PO identifier (e.g., 'PO-1001').
    """
    try:
        response = requests.get(f"{BASE_URL}/api/pos/{po_number}", timeout=5)
        if response.status_code == 200:
            return str(response.json())
        elif response.status_code == 404:
            return f"PO Not Found: {response.json().get('detail')}"
        else:
            return f"ERP Error: HTTP {response.status_code} - {response.text}"
    except Exception as e:
        return f"Network Error checking PO: {str(e)}"

@tool
def submit_invoice_to_erp(
    invoice_id: str,
    po_number: str,
    vendor_name: str,
    amount: float,
    due_date: str,
) -> str:
    """Submits a validated invoice record into the ERP system.

    Args:
        invoice_id: Unique invoice identifier (e.g., 'INV-2024-001').
        po_number: Matching purchase order identifier (e.g., 'PO-1001').
        vendor_name: Name of the vendor.
        amount: Total billed amount as a float (e.g., 1500.00).
        due_date: Payment due date formatted as YYYY-MM-DD.
    """
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
            # Captures intentional 500 errors so the agent can inspect and retry
            return f"Submission Failed with HTTP {response.status_code}: {response.text}"
    except Exception as e:
        return f"Network Error during submission: {str(e)}"

@tool
def verify_invoice_in_erp(invoice_id: str) -> str:
    """Queries the ERP database to independently verify that an invoice
    was successfully stored and matches ground truth.

    Args:
        invoice_id: Unique invoice identifier to look up.
    """
    try:
        response = requests.get(
            f"{BASE_URL}/api/invoices/{invoice_id}", timeout=5
        )
        if response.status_code == 200:
            return f"Verification Confirmed: {response.json()}"
        else:
            return f"Verification Failed: {response.text}"
    except Exception as e:
        return f"Network Error during verification: {str(e)}"