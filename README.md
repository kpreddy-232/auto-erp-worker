# Autonomous AI Task Worker - CentrAlign AI Internship Submission

This repository contains a prototype of an autonomous AI worker capable of extracting data from an invoice, querying an external ERP system, handling intentional API failures, and verifying its own work.

## 🛠️ Setup and Run Instructions

### 1. Prerequisites
- Python 3.10+
- A Google Gemini API Key

### 2. Installation
```powershell
# Create and activate a virtual environment
python -m venv agent-env
agent-env\Scripts\activate

# Install dependencies
pip install langgraph langchain-core langchain-google-genai fastapi uvicorn python-dotenv pydantic requests
```

### 3. Environment Variables
Create a `.env` file in the root directory and add your Gemini API key:
```env
GOOGLE_API_KEY="your_api_key_here"
```

### 4. Running the Prototype
This system requires two terminal windows to run simultaneously.

**Terminal 1: Start the Mock ERP Server**
```powershell
agent-env\Scripts\activate
uvicorn mock_server:app --reload --port 8000
```

**Terminal 2: Run the Autonomous Agent**
```powershell
agent-env\Scripts\activate
python agent.py
```

---

## 🧠 Architecture Overview
The system is built using **LangGraph** to implement a deterministic ReAct (Reasoning + Acting) execution loop, powered by the `gemini-3.8-flash` model.

**Components:**
1. **Mock ERP Server (`mock_server.py`):** A simulated backend using FastAPI and SQLite. It acts as the source of truth for Purchase Orders and the ledger for Invoices. It includes an intentional transient 500 error trap to test agent resilience.
2. **Tools (`tools.py`):** Deterministic Python functions bound to the LLM (File Reader, PO Lookup, Invoice Submission, Database Verification).
3. **State Machine (`agent.py`):** The LangGraph orchestrator that manages the agent's internal state, tool execution, and error observation.

---

## ⚙️ Technical & Design Decisions

- **Strict Tooling over Generation:** The agent is given a temperature of `0` to heavily prioritize deterministic tool-calling over creative generation.
- **SQLite Source of Truth:** Rather than mocking APIs in memory, I built a physical SQLite database. This forces the agent to actually verify ground-truth state changes, satisfying the "Verification" rubric requirement.
- **Intentional Failure Injection:** The `POST /api/invoices` endpoint is programmed to fail with a `500 Internal Server Error` on its first attempt. This tests the agent's autonomy and reliability, proving it can read error traces and retry rather than failing completely.

---

## ⚠️ Known Limitations

1. **The "ReAct Tax" (High Latency):** The system currently takes 15-40 seconds to complete a task. Because the ReAct loop executes sequentially, every tool call requires a full roundtrip to the Gemini API. 
2. **Brittle File Paths:** The file reading tool currently assumes the file is text-based and relies on exact or slightly fuzzy path matching.
3. **No Human-in-the-Loop (HITL):** If the agent hallucinates a drastically wrong invoice amount, it will still attempt to push it to the ERP without asking for permission.

---

## 🚀 What I Would Build Next

If given additional time to push this toward a production-grade AI employee, I would implement:
1. **Streaming Tool UX:** To solve the perceived latency issue, I would stream the agent's internal thoughts and intermediate steps to the frontend so the user isn't left waiting at a blank screen.
2. **Concurrent Tool Calling:** Allowing the agent to execute non-dependent tools (like looking up a PO and reading a secondary file) in parallel to cut down on API roundtrips.
3. **Human Approval Checkpoints:** Utilizing LangGraph's `interrupt_before` functionality to pause the graph state right before the `submit_invoice_to_erp` tool is called, requiring explicit human `y/n` input for amounts over a certain threshold.
4. **Multimodal Extraction:** Upgrading the file reader tool to use a Vision model to extract data directly from raw PDFs rather than relying on clean `.txt` files.