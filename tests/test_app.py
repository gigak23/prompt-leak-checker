"""Tests for Prompt Leak Checker (demo mode - no API keys required).

Run from the project root:
    python -m pytest tests/ -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402

# FAKE example data only - invented for tests, no real person or credential.
LEAKY = (
    "Hi, can you draft a follow-up email for our customer John Doe? "
    "His SSN is 123-45-6789, email john.doe@example.com, phone (555) 123-4567. "
    "For reference our internal API key is sk-FAKE1234567890EXAMPLE - do not share it. "
    "This is for our confidential internal project codename Project Nightingale."
)
FAKE_SSN = "123-45-6789"
FAKE_KEY = "sk-FAKE1234567890EXAMPLE"

SAFE = (
    "Write a friendly social media post announcing our new public product "
    "launch event next Tuesday. All are welcome to attend and learn about "
    "the features we have already published on our website."
)

SCHEMA_KEYS = {
    "decision", "risk_score", "risk_level", "summary",
    "findings", "redacted_text", "policy_reason", "mode",
}
FINDING_KEYS = {"category", "severity", "snippet", "explanation", "recommendation"}


@pytest.fixture()
def client(monkeypatch):
    # Force demo mode regardless of the developer's environment.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


def check(client, text, destination="Public ChatGPT", context=""):
    return client.post("/api/check", json={
        "prompt_text": text,
        "destination_tool": destination,
        "data_context": context,
    })


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["mode"] == "demo"


def test_index_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Prompt Leak Checker" in resp.data


def test_leaky_example_schema_and_decision(client):
    resp = check(client, LEAKY, context="customer support follow-up")
    assert resp.status_code == 200
    data = resp.get_json()

    assert SCHEMA_KEYS <= set(data.keys())
    assert data["mode"] == "demo"
    assert data["decision"] in ("Redact & Send", "Block & Escalate")
    assert isinstance(data["risk_score"], int)
    assert 0 <= data["risk_score"] <= 100
    assert data["risk_level"] in ("Low", "Medium", "High", "Critical")
    assert data["findings"], "leaky example must produce findings"
    for finding in data["findings"]:
        assert FINDING_KEYS <= set(finding.keys())

    # The redacted version must not contain the fake SSN or the fake key.
    assert FAKE_SSN not in data["redacted_text"]
    assert FAKE_KEY not in data["redacted_text"]
    assert "john.doe@example.com" not in data["redacted_text"]


def test_safe_example_allows_low_risk(client):
    resp = check(client, SAFE, context="public marketing copy")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["decision"] == "Allow"
    assert data["risk_level"] == "Low"
    assert data["risk_score"] < 25
    assert data["redacted_text"] == SAFE


def test_leaky_scores_higher_than_safe(client):
    leaky_score = check(client, LEAKY).get_json()["risk_score"]
    safe_score = check(client, SAFE).get_json()["risk_score"]
    assert leaky_score > safe_score


def test_empty_input_returns_400(client):
    resp = check(client, "   ")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    assert data["error"]


def test_missing_prompt_text_returns_400(client):
    resp = client.post("/api/check", json={"destination_tool": "Public ChatGPT"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()
