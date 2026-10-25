"""Check Groq credentials/model access without printing secrets or generating tokens."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
key = os.getenv("GROQ_API_KEY", "").strip()
if not key:
    raise SystemExit("GROQ_API_KEY is missing. Add it to the local .env file.")

client = OpenAI(
    api_key=key,
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1"),
)
models = client.models.list()
available = {item.id for item in models.data}
model = os.getenv("CHAT_MODEL", "openai/gpt-oss-20b")
if model not in available:
    print(f"Groq key is valid, but configured model {model!r} is not in the account's model list.")
    print("Available model IDs:")
    for item in sorted(available):
        print(f"  {item}")
else:
    print(f"Groq connection OK; configured model {model} is available.")

