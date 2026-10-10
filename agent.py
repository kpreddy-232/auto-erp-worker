import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from tools import (
    check_purchase_order,
    read_invoice_file,
    submit_invoice_to_erp,
    verify_invoice_in_erp,
)

# Load GEMINI API Key
load_dotenv()

# 1. Initialize Gemini
llm = ChatGoogleGenerativeAI(
    model="gemini-3.8-flash",
    temperature=0,  # Zero temperature for deterministic tool calling
)

# 2. Register tools
tools = [
    read_invoice_file,
    check_purchase_order,
    submit_invoice_to_erp,
    verify_invoice_in_erp,
]

# 3. System prompt enforcing autonomy, failure recovery, and verification
SYSTEM_PROMPT = """You are an autonomous AI enterprise employee responsible for invoice reconciliation and ERP data entry.

Your workflow rules:
1. Parse the invoice file provided in the task and extract all required metadata (Invoice ID, PO Number, Vendor Name, Amount, Due Date).
2. Query the ERP to check the PO status and ensure the invoice amount matches the expected amount. If there is a mismatch or the PO is on hold, stop and notify the user.
3. Submit the invoice to the ERP. If the server returns an error (such as a 500 Database timeout), observe the error and retry the submission.
4. Always independently verify the invoice entry in the ERP using the verification tool before concluding.
5. Provide a clear summary with concrete evidence (Transaction ID, PO Number, Status) of completion.
"""

# 4. Compile the Agent using the modern LangChain API
agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=SYSTEM_PROMPT, # FIXED: Changed 'prompt' to 'system_prompt'
)


def run_task(prompt: str):
    print("\n" + "=" * 60)
    print(f"TASK: {prompt}")
    print("=" * 60 + "\n")

    inputs = {"messages": [HumanMessage(content=prompt)]}

    # Stream agent execution step-by-step
    for event in agent.stream(inputs, stream_mode="values"):
        latest_message = event["messages"][-1]

        # Inspect tool calls made by the agent
        if (
            hasattr(latest_message, "tool_calls")
            and latest_message.tool_calls
        ):
            for call in latest_message.tool_calls:
                print(f"[ACTION] Calling tool: {call['name']}")
                print(f"         Arguments: {call['args']}")

        # Inspect tool responses returned back to the agent
        elif latest_message.type == "tool":
            print(f"[OBSERVATION] Tool output: {latest_message.content}\n")

        # Inspect final assistant response
        elif latest_message.type == "ai" and latest_message.content:
            print(f"[AI RESPONSE]\n{latest_message.content}\n")


if __name__ == "__main__":
    task_request = (
        "Process the invoice at 'invoices/techcorp_invoice.txt', "
        "verify the purchase order details, enter it into our ERP, "
        "and verify that it was successfully recorded."
    )
    run_task(task_request)