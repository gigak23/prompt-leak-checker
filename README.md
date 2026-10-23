# Prompt Leak Checker

**CS4680 Prompt Engineering — Assignment 3** · Brandon Karimi

A web app that checks text *before* you paste it into an AI tool. It flags
personal data, secrets and confidential company information, gives you a
redacted safe version, and decides: **Allow**, **Redact & Send**, or
**Block & Escalate**.

## How it works

1. Paste your text, choose where it's going (**Public AI tool** or
   **Company-approved AI tool**), and optionally add context.
2. `llm_client.py` fills `prompts/prompt_template.txt` with
   `{prompt_text}`, `{destination_tool}` and `{data_context}`, then calls
   Gemini (or OpenAI).
3. The model returns JSON. The page shows the decision and what to do, the
   risk score, the safe version and each finding.

With no API key, a local rule-based **demo mode** returns the same JSON, so
the app always works.

| File | Purpose |
|---|---|
| `app.py` | Flask server: `/`, `GET /health`, `POST /api/check` |
| `llm_client.py` | Fills the prompt, calls the model, validates the JSON, demo fallback |
| `prompts/prompt_template.txt` | The prompt |
| `templates/index.html` | The web page |
| `tests/test_app.py` | pytest tests (run in demo mode) |

## Prompt engineering

The template uses three patterns:

- **Persona:** the model acts as an AI governance / data protection analyst.
- **Few-Shot:** three examples (safe → Allow, email + phone → Redact & Send,
  API key + SSNs → Block & Escalate) teach it to judge by context, not
  keywords.
- **Template:** the model must reply with a single JSON object in a fixed
  schema, which the server validates before the page displays it.

## Run it

Requires Python 3.10+.

```bash
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000.

To use a live model, create a `.env` file (it is git-ignored):

```
GEMINI_API_KEY=your-key          # used first if set
GEMINI_MODEL=gemini-3.8-flash    # optional
OPENAI_API_KEY=your-key          # optional alternative
OPENAI_MODEL=gpt-4o-mini         # optional
PORT=5000                        # optional
```

If there's no key, the app runs in demo mode. A 503 from the provider means it's
busy, so click **Try again**.

## API

`POST /api/check`

```json
{ "prompt_text": "...", "destination_tool": "Public AI tool (e.g. ChatGPT, Gemini)", "data_context": "Customer data" }
```

Returns:

```json
{
  "decision": "Allow | Redact & Send | Block & Escalate",
  "risk_score": 0,
  "risk_level": "Low | Medium | High | Critical",
  "summary": "...",
  "findings": [
    { "category": "PII | Secret/Credential | Confidential Company Information",
      "severity": "Low | Medium | High | Critical",
      "snippet": "...", "explanation": "...", "recommendation": "..." }
  ],
  "redacted_text": "...",
  "policy_reason": "...",
  "mode": "demo | openai | gemini"
}
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

## Limitations

This tool reduces risk but can't guarantee text is safe, and it isn't legal
advice. Demo mode only uses patterns and keywords, so it's less accurate than
a live model. The example buttons use fake data only.
