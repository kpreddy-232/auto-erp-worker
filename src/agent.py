import os
import time
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver

from src.tools import (
    check_purchase_order,
    search_purchase_orders,
    read_invoice_file,
    submit_invoice_to_erp,
    verify_invoice_in_erp,
    update_po_status,
    create_purchase_order,
)

load_dotenv()

llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    temperature=0,
)

tools = [
    read_invoice_file,
    check_purchase_order,
    search_purchase_orders,
    submit_invoice_to_erp,
    verify_invoice_in_erp,
    update_po_status,
    create_purchase_order,
]

SYSTEM_PROMPT = """You are a highly secure Autonomous AI enterprise employee.

CRITICAL GROUNDING RULES:
1. You are ALLOWED and ENCOURAGED to handle tasks related to ERP management, invoices, purchase orders (POs), product orders, and vendors. This includes creating, searching, verifying, and updating them.
2. If the user asks about COMPLETELY unrelated topics (e.g., bananas, sci-fi movies, recipes, general knowledge), YOU MUST STRICTLY REFUSE. Simply state: "I am an enterprise AI. My capabilities are strictly limited to ERP management tasks."

WORKFLOW & DISCREPANCY RECOVERY RULES:
1. When looking up a PO, if it returns 'not found', DO NOT give up. Immediately use `search_purchase_orders` with the vendor name to find potential matches.
2. PO NUMBER TYPOS: If the user provides a short PO number (like '102' or '103') and it is not found, autonomously try using `search_purchase_orders` with zero-padded variations (like '1002' or '1003') before giving up.
3. SEVERE TYPOS (THE VENDOR FALLBACK): If a number is completely wrong (like '1102' instead of '1002') and number searches fail, DO NOT blindly guess other numbers. Stop and explicitly ask the user for the Vendor Name, then use `search_purchase_orders` to find it.
4. HUMAN-IN-THE-LOOP CONFIRMATION: If you discover a candidate PO via search, or if there's a discrepancy, DO NOT proceed silently. Explain the issue, present the candidate details, and explicitly ask the user: 'To confirm, please enter "CONFIRM"'.
5. Review your conversation history. If the user's latest response does not explicitly contain "CONFIRM", halt and wait for it.
6. Always independently verify the invoice entry in the ERP using the `verify_invoice_in_erp` tool before concluding.

ANTI-HALLUCINATION & TOOL SCHEMA RULES:
- Never hallucinate, guess, or invent missing arguments for your tools. If a user asks to create a PO but omits the `expected_amount` or `po_number`, or asks to submit an invoice but omits the `invoice_id` or `due_date`, you MUST halt and explicitly ask the user for the missing data. Do not execute the tool until all required parameters are provided by the user.

ROLE-BASED ACCESS CONTROL (RBAC):
The user's role (Employee or Manager) will be provided at the start of their prompt.
- **If Employee or not mentioned:** You CANNOT process ON_HOLD or REJECTED POs. If a PO is ON_HOLD, or an amount is suspicious, halt and inform the user they must escalate to a manager. You CANNOT use the `update_po_status` tool.
- **If Manager:** You have full privileges. You CAN use `update_po_status` to change PO statuses (e.g., ON_HOLD to APPROVED).

DATA INTEGRITY & FORMATTING:
- Never "delete" an invoice or PO. If asked to remove one, explain that you must use `update_po_status` to change its status to VOID or CANCELLED for auditing purposes.
- **PROPER FORMATTING:** Always provide your final response in proper Markdown format. Use bolding for statuses/amounts, bullet points for lists, and keep the output clean and highly readable.
"""

memory = MemorySaver()
agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=memory,
    interrupt_before=["tools"], # Deterministic safety switch
)

def run_task(prompt: str):
    print("\n" + "=" * 60)
    print(f"TASK: {prompt}")
    print("=" * 60 + "\n")

    inputs = {"messages": [HumanMessage(content=prompt)]}
    config = {"configurable": {"thread_id": "local_terminal_test"}}

    while True:
        for event in agent.stream(inputs, config=config, stream_mode="values"):
            latest_message = event["messages"][-1]
            
            if hasattr(latest_message, "tool_calls") and latest_message.tool_calls:
                for call in latest_message.tool_calls:
                    print(f"[ACTION] Pending tool call: {call['name']}")
                    print(f"         Arguments: {call['args']}")
            
            elif latest_message.type == "tool":
                print(f"[OBSERVATION] Tool output: {latest_message.content}\n")
            
            elif latest_message.type == "ai" and latest_message.content:
                print(f"[AI RESPONSE]\n{latest_message.content}\n")

        state = agent.get_state(config)
        if not state.next:
            break # Finished
        
        # Intercept and pause if tools are called
        if state.next == ("tools",):
            print("\n[⚠️ SYSTEM PAUSED] Agent wants to execute tools. Type 'y' to approve, 'n' to reject.")
            user_input = input("Approve? (y/n): ")
            if user_input.lower() == 'y':
                inputs = None # Resume execution
            else:
                print("[!] Rejecting tool call...")
                last_msg = state.values["messages"][-1]
                tool_msgs = [ToolMessage(tool_call_id=tc["id"], name=tc["name"], content="USER REJECTED THIS ACTION.") for tc in last_msg.tool_calls]
                agent.update_state(config, {"messages": tool_msgs}, as_node="tools")
                inputs = None

if __name__ == "__main__":
    task_request = "Process the invoice at 'invoices/techcorp_invoice.txt'"
    run_task(task_request)
