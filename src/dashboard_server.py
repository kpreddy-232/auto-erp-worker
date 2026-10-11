import sqlite3
import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from langchain_core.messages import HumanMessage, ToolMessage

from src.agent import agent

app = FastAPI(title="ERP Manangement ReAct Agent - Dashboard")
DB_FILE = "chat_history.db"

def init_chat_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_chat_db()

@app.get("/")
async def get_dashboard():
    with open("dashboard.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    current_session_id = "demo_session_1"
    config = {"configurable": {"thread_id": current_session_id}}
    sent_message_ids = set()

    async def load_history(session_id):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,))
        for row in cursor.fetchall():
            await websocket.send_json({"type": "history", "role": row[0], "content": row[1]})
        conn.close()

    async def save_message(role, content):
        conn = sqlite3.connect(DB_FILE)
        conn.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", 
                     (current_session_id, role, content))
        conn.commit()
        conn.close()

    async def process_agent_stream(inputs):
        try:
            while True:
                async for event in agent.astream(inputs, config=config, stream_mode="values"):
                    latest_message = event["messages"][-1]
                    
                    if hasattr(latest_message, "id") and latest_message.id in sent_message_ids:
                        continue
                    if hasattr(latest_message, "id"):
                        sent_message_ids.add(latest_message.id)

                    has_text = False
                    
                    if latest_message.type == "ai" and latest_message.content:
                        raw_content = latest_message.content
                        final_response = " ".join([b.get("text", "") for b in raw_content if "text" in b]) if isinstance(raw_content, list) else str(raw_content)
                        if final_response.strip():
                            has_text = True
                            await websocket.send_json({"type": "ai_response", "content": final_response})
                            await save_message("agent", final_response)

                    if hasattr(latest_message, "tool_calls") and latest_message.tool_calls:
                        
                        # FALLBACK: Gemini often suppresses text when calling tools.
                        # If it's a high-stakes tool and the AI was silent, we generate a conversational summary for it!
                        if not has_text:
                            for call in latest_message.tool_calls:
                                if call['name'] == 'submit_invoice_to_erp':
                                    args = call.get('args', {})
                                    msg = f"I have verified the details. I am now ready to submit Invoice **{args.get('invoice_id', 'Unknown')}** for **${args.get('amount', '0')}** against PO **{args.get('po_number', 'Unknown')}**. Please approve the action below."
                                    await websocket.send_json({"type": "ai_response", "content": msg})
                                    await save_message("agent", msg)
                                elif call['name'] == 'update_po_status':
                                    args = call.get('args', {})
                                    msg = f"I am preparing to update Purchase Order **{args.get('po_number', 'Unknown')}** to status **{args.get('status', 'Unknown')}**. Please approve the action below."
                                    await websocket.send_json({"type": "ai_response", "content": msg})
                                    await save_message("agent", msg)
                                elif call['name'] == 'create_purchase_order':
                                    args = call.get('args', {})
                                    msg = f"I am preparing to create a new Purchase Order **{args.get('po_number', 'Unknown')}** for **{args.get('vendor_name', 'Unknown')}** valued at **${args.get('expected_amount', '0')}**. Please approve the action below."
                                    await websocket.send_json({"type": "ai_response", "content": msg})
                                    await save_message("agent", msg)

                        for call in latest_message.tool_calls:
                            await websocket.send_json({"type": "tool_call", "tool_name": call['name'], "args": call['args']})
                            await asyncio.sleep(0.1)
                            
                    elif latest_message.type == "tool":
                        await websocket.send_json({"type": "observation", "content": latest_message.content})
                        await asyncio.sleep(0.1)

                state = agent.get_state(config)
                if not state.next:
                    break 
                
                if state.next == ("tools",):
                    last_msg = state.values["messages"][-1]
                    tool_calls = getattr(last_msg, "tool_calls", [])
                    
                    # Intercept ALL high-stakes database mutations to trigger the UI Approval button
                    needs_approval = any(tc["name"] in ["submit_invoice_to_erp", "update_po_status", "create_purchase_order"] for tc in tool_calls)

                    if needs_approval:
                        await websocket.send_json({"type": "approval_required", "tool_calls": tool_calls})
                        break 
                    else:
                        inputs = None

        except Exception as e:
            await websocket.send_json({"type": "ai_response", "content": f"⚠️ Error: {str(e)}"})

    await load_history(current_session_id)

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            action = payload.get("action")

            if action == "set_session":
                current_session_id = payload.get("session_id")
                config = {"configurable": {"thread_id": current_session_id}}
                sent_message_ids.clear()
                await load_history(current_session_id)
                await websocket.send_json({"type": "session_confirmed", "session_id": current_session_id})

            elif action == "task":
                user_message = payload.get("task", "")
                user_role = payload.get("role", "Employee")
                
                # Secretly prepend the RBAC role context for the LLM
                context_message = f"[SYSTEM SECURITY CONTEXT: User Role is {user_role}]\n\n{user_message}"
                
                await save_message("user", user_message) # Save original to display to user
                await process_agent_stream({"messages": [HumanMessage(content=context_message)]})

            elif action == "approval_response":
                is_approved = payload.get("approved")
                if is_approved:
                    await websocket.send_json({"type": "observation", "content": "✅ Action Accepted by Human."})
                    await process_agent_stream(None) 
                else:
                    await websocket.send_json({"type": "observation", "content": "❌ Action Rejected by Human."})
                    state = agent.get_state(config)
                    last_msg = state.values["messages"][-1]
                    mock_tool_msgs = [ToolMessage(tool_call_id=tc["id"], name=tc["name"], content="Action REJECTED by user.") for tc in last_msg.tool_calls]
                    agent.update_state(config, {"messages": mock_tool_msgs}, as_node="tools")
                    await process_agent_stream(None) 

    except WebSocketDisconnect:
        print("Client disconnected.")