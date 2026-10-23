# Prompt Leak Checker

**CS4680 Prompt Engineering — Assignment 3** · Brandon Karimi

A web app that checks text *before* you paste it into an AI tool. It flags
personal data, secrets and confidential company information, gives you a
redacted safe version, and decides: **Allow**, **Redact & Send**, or
**Block & Escalate**.

## Problem

People paste customer emails, internal plans, API keys and SSNs into public AI
tools every day, usually by accident. Once the text is sent, the company can't
get it back. Enterprise data-loss tools exist, but they're built for IT teams,
not for an employee who wants a quick answer to three questions:

1. What in this text is risky, and why?
2. What would a safe version look like?
3. Should I send it, send the redacted version, or escalate it?

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

**The role of the AI:** the model acts as the governance analyst. It makes the
judgment a keyword filter can't. For example, the same product name can be
harmless in public marketing copy but confidential in an unreleased roadmap.
It also writes the redacted version and explains the policy behind its
decision, not just a yes/no.

| File | Purpose |
|---|---|
| `app.py` | Flask server: `/`, `GET /health`, `POST /api/check` |
| `llm_client.py` | Fills the prompt, calls the model, validates the JSON, demo fallback |
| `prompts/prompt_template.txt` | The prompt |
| `templates/index.html` | The web page |
| `tests/test_app.py` | pytest tests (run in demo mode) |

## Prompt engineering

`prompts/prompt_template.txt` uses three course patterns, each in its own
labeled section:

- **Persona:** the model plays an AI governance and data protection analyst.
  *Effect:* it's cautious about secrets, explains why something is risky,
  and writes in plain language for non-technical users, instead of giving a
  generic "is this safe?" answer.
- **Few-Shot:** three examples anchor the decisions: safe public copy →
  Allow; personal email and phone → Redact & Send; API key and SSNs → Block &
  Escalate. *Effect:* scores and decisions stay consistent, and borderline
  text is judged by context, not keywords.
- **Template:** the model must reply with a single JSON object in a fixed
  schema. *Effect:* the page can always render the result as a decision
  banner, findings and a copyable safe version. The server validates the JSON
  (`llm_client.normalize_result`), so a bad reply shows a clear error rather
  than a broken page.

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

## Impact and future work

Catching a leak before it's sent is much cheaper than handling it afterwards.
Next steps:

- A browser extension that checks text as you paste it into ChatGPT or Gemini
- Company policy packs: load an organization's own data rules into the prompt
- Anonymized audit logs so security teams can see leak trends

## Limitations

This tool reduces risk but can't guarantee text is safe, and it isn't legal
advice. Demo mode only uses patterns and keywords, so it's less accurate than
a live model. The example buttons use fake data only.
