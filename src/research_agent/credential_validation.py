from __future__ import annotations

import re


PLACEHOLDER_SECRET_VALUES = {
    "...",
    "<api-key>",
    "<openai-api-key>",
    "<real-key>",
    "<your-api-key>",
    "<your-real-key>",
    "changeme",
    "replace-for-real-run",
    "replace-me",
    "todo",
}

EXAMPLE_CONTACT_DOMAINS = {"example.com", "example.org", "example.net", "localhost", "local"}


def placeholder_secret(value: str) -> bool:
    return str(value or "").strip().lower() in PLACEHOLDER_SECRET_VALUES


def valid_contact_email(value: str) -> bool:
    text = str(value or "").strip()
    if not re.match(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$", text):
        return False
    domain = text.rsplit("@", 1)[-1].lower()
    return domain not in EXAMPLE_CONTACT_DOMAINS and not domain.endswith(".example")
