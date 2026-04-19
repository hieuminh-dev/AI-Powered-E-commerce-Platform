import os
import importlib
from dotenv import load_dotenv

# Load .env
load_dotenv()

api_key = os.getenv("PINECONE_API_KEY")
index_name = os.getenv("PINECONE_INDEX_NAME", "ecommerce-chatbot")

print("Checking Pinecone connection...\n")

if not api_key:
    print("[ERROR] PINECONE_API_KEY not found in environment variables")
    exit(1)

try:
    pinecone = importlib.import_module("pinecone")
    print("Pinecone module version:", getattr(pinecone, "__version__", "unknown"))
    print("Configured index:", index_name)

    if not hasattr(pinecone, "Pinecone"):
        print("[ERROR] Installed pinecone package does not support Pinecone class API (v3+ required)")
        raise SystemExit(1)

    pc = pinecone.Pinecone(api_key=api_key)
    li = pc.list_indexes()
    indexes = li.names() if hasattr(li, "names") else list(li)
    print("Using Pinecone class (new client)")
    print("Indexes discovered:", indexes)
    if index_name in indexes:
        print(f"[OK] Index exists: {index_name}")
    else:
        print(f"[ERROR] Index not found: {index_name}")
        print("Tip: update PINECONE_INDEX_NAME to one of:", indexes)
        raise SystemExit(2)

except Exception as e:
    print("[ERROR] Failed to import or check Pinecone:")
    print(e)