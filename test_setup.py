import os
import sqlite3
import langgraph
from dotenv import load_dotenv
from fastapi import FastAPI
from langchain_google_genai import ChatGoogleGenerativeAI

# Load variables from the .env file
load_dotenv()

def verify_setup():
    print("Testing imports...")
    app = FastAPI()
    print(f"SQLite version: {sqlite3.sqlite_version}")
    
    print("\nTesting Gemini API...")
    try:
        # Initialize the Gemini model
        llm = ChatGoogleGenerativeAI(model="gemini-3.8-flash", temperature=0)
        response = llm.invoke("Reply with exactly: 'Setup successful.'")
        print(f"Gemini Response: {response.content}")
    except Exception as e:
        print(f"API Error: {e}")

if __name__ == "__main__":
    verify_setup()