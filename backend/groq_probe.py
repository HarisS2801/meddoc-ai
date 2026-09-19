"""One-shot live Groq probe (non-medical, key never printed).

Purpose: report the ACTUAL HTTP status and classified error kind from one
minimal Groq call using the app's real settings. Never prints the API key,
the raw provider body, or any patient content.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import get_settings
from app.services.groq_service import (
    classify_groq_error,
    GROQ_BASE_URL,
    GroqChatClient,
)

settings = get_settings()

print("key present?    :", bool(settings.groq_api_key))
print("model (env)     :", settings.groq_model)
print("ai_provider     :", settings.ai_provider)
print("timeout         :", settings.groq_timeout_seconds)
if not settings.groq_api_key:
    print("NO KEY -> controlled 503 GROQ_UNAVAILABLE (no live call made).")
    sys.exit(0)

client = GroqChatClient(
    api_key=settings.groq_api_key,
    model=settings.groq_model,
    base_url=GROQ_BASE_URL,
    timeout=min(30, int(settings.groq_timeout_seconds or 30)),
    max_tokens=24,
)

try:
    text = client.complete(
        messages=[
            {"role": "user", "content": 'Reply with exactly the words: MedDoc AI connection test'}
        ]
    )
    print("LIVE 200 OK -> model answered; sanitized text:", repr(text.strip()[:40]))
    sys.exit(0)
except Exception as exc:
    kind = classify_groq_error(exc)
    http = getattr(exc, "status_code", None)
    print("LIVE FAILED -> kind =", kind.kind, "| http_status =", http)
