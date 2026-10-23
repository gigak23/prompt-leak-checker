# Prompt Leak Checker + Governance Decision

**CS4680 Prompt Engineering — Assignment 3: AI Assistant Project**
Author: Brandon Karimi

A web app that checks text *before* you paste it into an AI tool. It flags
personal data (PII), secrets/credentials, and confidential company information,
returns a risk score and a redacted safe version, and makes a governance
decision: **Allow**, **Redact & Send**, or **Block & Escalate** — with the
policy reason for that decision.

I built this as a complete, end-to-end AI application: **prompt template
file → Python call to a Generative API → Flask server → web UI served by
Flask that renders structured JSON.**

---

## 1. Problem / Market Need

Employees paste sensitive text into public AI tools every day: customer
emails, internal project details, support tickets — and sometimes API keys,
passwords, and personal identifiers like SSNs. Once text is sent to a public
tool it is outside company control. Most people do not do this maliciously;
they simply have no quick way to know what in their text is risky, what to
remove, or when the right answer is "do not send this at all."

Existing DLP (data loss prevention) tools are enterprise products aimed at IT
departments. There is a gap for a simple, end-user checker that answers three
questions in seconds, in plain language:

1. What in this text is risky, and why?
2. What would a safe version look like?
3. Should I send it, send the redacted version, or escalate it?

## 2. What the App Does

The user pastes the text they are about to send, picks the destination AI
tool (Public ChatGPT, Public Gemini, Company-approved AI tool, or Other
public AI tool), and optionally describes the data context. The app returns:

- **Governance decision** — Allow / Redact & Send / Block & Escalate
- **Risk score** (0–100) and **risk level** (Low / Medium / High / Critical)
- **Summary** in plain language
- **Findings** — each categorized (PII, Secret/Credential, or Confidential
  Company Information) with severity, the flagged snippet, an explanation,
  and a recommendation
- **Redacted safe version** of the text, with a Copy button
- **Policy reason** — the governance rule behind the decision
- **Mode** — whether the result came from a live model (`openai` / `gemini`)
  or the local `demo` analyzer

## 3. Interaction Flow

```
User pastes text + picks destination tool (+ optional context)
        |
        v
Web UI (Flask-served page)  --POST /api/check (JSON)-->  Flask server (app.py)
                                                              |
                                                              v
                                          llm_client.py fills prompts/prompt_template.txt
                                          with {prompt_text}, {destination_tool}, {data_context}
                                                              |
                                                              v
                                          Generative API call (OpenAI or Gemini)
                                          -- or demo fallback analyzer if no key is set --
                                                              |
                                                              v
                                          Structured JSON result (exact schema, Section 5)
                                                              |
                                                              v
                       UI renders: decision banner (green / amber / red), risk meter,
                       findings cards, redacted text with Copy button, policy reason
```

The role of the LLM is purposeful and narrow: it acts as the governance
analyst. It performs the semantic judgment a keyword filter cannot — for
example, telling public marketing copy apart from an unreleased internal
roadmap that mentions the same product — and it produces the redacted rewrite
and the policy reasoning, not just a block/allow flag.

## 4. Architecture

| Component | How I implemented it |
|---|---|
| Prompt template file with variables and JSON output | `prompts/prompt_template.txt` — variables `{prompt_text}`, `{destination_tool}`, `{data_context}` |
| Python script that calls the model API | `llm_client.py` — fills the template, calls OpenAI or Gemini via Python stdlib `urllib` (no SDK needed) |
| Flask server with health + generate endpoints | `app.py` — `GET /health`, `POST /api/check` |
| Web UI served by the same Flask app, rendering the JSON | `templates/index.html` — self-contained HTML/CSS/JS, no CDN dependencies, runs offline |
| Structured JSON between server and UI | Exact schema in Section 5, enforced/normalized in `llm_client.normalize_result` |

Project layout:

```
cs4680-assignment-3/
├── app.py                      # Flask server: /, /health, /api/check
├── llm_client.py               # Provider logic + demo fallback analyzer
├── prompts/
│   └── prompt_template.txt     # Persona + Few-Shot + Template patterns
├── templates/
│   └── index.html              # Web UI (inline CSS/JS, no external deps)
├── tests/
│   └── test_app.py             # pytest: health, schema, decisions, errors
├── requirements.txt            # Flask only
├── requirements-dev.txt        # + pytest
├── .env.example                # Key/model/port placeholders (no real secrets)
└── README.md
```

## 5. Output Schema

`POST /api/check` accepts:

```json
{ "prompt_text": "...", "destination_tool": "Public ChatGPT", "data_context": "customer support" }
```

and returns (this schema is identical in the prompt template, the code, the
tests, this README, and the UI rendering):

```json
{
  "decision": "Allow | Redact & Send | Block & Escalate",
  "risk_score": 0,
  "risk_level": "Low | Medium | High | Critical",
  "summary": "Plain-language summary.",
  "findings": [
    {
      "category": "PII | Secret/Credential | Confidential Company Information",
      "severity": "Low | Medium | High | Critical",
      "snippet": "flagged fragment",
      "explanation": "why it is a risk",
      "recommendation": "what to do about it"
    }
  ],
  "redacted_text": "text with [REDACTED ...] placeholders",
  "policy_reason": "governance reason for the decision",
  "mode": "demo | openai | gemini"
}
```

`mode` is added by the server so the UI (and the audience during a demo) can
always see whether a live model or the demo analyzer produced the result.

Risk mapping: 0–24 Low → Allow; 25–74 Medium/High → Redact & Send (when the
text is usable once redacted); 75–100 Critical, or any credential/government
ID → Block & Escalate.

## 6. Prompt Engineering Techniques

All three patterns live in `prompts/prompt_template.txt`, each in its own
clearly labeled section:

1. **Persona (Pattern 1 in the template).** The model is cast as "an AI
   governance and data protection analyst on a corporate AI security team"
   who reviews text the way a DLP analyst would. This changes the output
   style: conservative about secrets, specific about *why* something is
   risky, and written for a non-technical employee — instead of a generic
   "is this safe?" answer.

2. **Few-Shot (Pattern 2 in the template).** Three short examples anchor the
   classification boundaries:
   - Safe public copy → **Allow** (~5, Low)
   - A personal email + phone number in a legitimate task → **Redact & Send**
     (~45, Medium)
   - An API key plus a customer database excerpt with SSNs → **Block &
     Escalate** (~95, Critical)

   The examples matter most for borderline cases: the same product name can
   be harmless in public copy and confidential in an unreleased roadmap, and
   the examples teach the model to judge by context, not keywords alone.

3. **Template (Pattern 3 in the template).** The model must respond with
   *only* a single JSON object matching the exact schema in Section 5 — no
   markdown, no prose outside the JSON. `llm_client.parse_model_json` strips
   code fences defensively and `normalize_result` validates/coerces every
   field, and a parse failure returns a clear error JSON to the UI rather
   than a stack trace.

## 7. Setup and Run

Requirements: Python 3.10+.

```bash
cd cs4680-assignment-3
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 in a browser. (Port can be changed with the
`PORT` environment variable.)

### Demo mode (no API key — the default)

With no keys set, the app runs its **demo fallback analyzer** in
`llm_client.analyze_demo`: a local rule + heuristic analyzer (regex for SSNs,
emails, phone numbers, card-like numbers, `sk-` / AWS `AKIA` / GitHub token
patterns, `password=` assignments, plus keyword heuristics for
confidential/internal content) that returns the **same JSON schema** and
sensible decisions. Every response shows `"mode": "demo"`, and the UI labels
it clearly. This guarantees the live demo can never fail for lack of a key,
quota, or network.

### Live mode with OpenAI

```bash
export OPENAI_API_KEY="your-key-here"     # never commit this
export OPENAI_MODEL="gpt-4o-mini"         # optional, this is the default
python app.py
```

### Live mode with Gemini

```bash
export GEMINI_API_KEY="your-key-here"     # never commit this
export GEMINI_MODEL="gemini-3.8-flash"    # optional, this is the default (model availability varies by account; the older gemini-2.0-flash is retired - if a model returns 404, set GEMINI_MODEL to a current flash model). A transient 503 from the model API just means overload: wait a moment and retry.
python app.py
```

If both keys are set, Gemini is used first — it is my primary provider
for this project. Copy `.env.example` for the full
list of variables. No real secrets are stored anywhere in this repository.

### Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

Tests force demo mode and cover: the health endpoint, the leaky example
(valid schema, decision is Redact & Send or Block & Escalate, redacted text
contains neither the fake SSN nor the fake API key), the safe example
(Allow, Low risk), and empty input returning HTTP 400 with a clear error.

## 8. Example Inputs and Outputs

**Leaky example** (all data is FAKE, invented for the demo) — text mentions a
customer name with SSN `123-45-6789`, email `john.doe@example.com`, phone
`(555) 123-4567`, a fake key `sk-FAKE1234567890EXAMPLE`, and a "confidential
internal project codename." Demo-mode result:

- Decision: **Block & Escalate**, risk score **100 (Critical)**
- Findings: Secret/Credential (the API key), PII (SSN, email, phone),
  Confidential Company Information (confidential/codename language)
- Redacted text replaces each item with `[REDACTED API KEY]`,
  `[REDACTED SSN]`, `[REDACTED EMAIL]`, `[REDACTED PHONE]`
- Policy reason: credentials, government IDs, and confidential company
  information must never be sent to a public AI tool; escalate and rotate
  the exposed credential.

**Safe example** — a request to write a public product-launch post. Result:

- Decision: **Allow**, risk score **0 (Low)**, no findings, redacted text is
  the original text unchanged.

## 9. Limitations

- **This tool reduces risk; it is not a guarantee.** No checker — rule-based
  or LLM-based — catches everything. Novel secret formats, obfuscated data
  (spelled-out numbers, screenshots), and context the user does not provide
  can all be missed, and a live model can occasionally misclassify.
- **It is not legal or compliance advice.** The policy reasons are simplified
  governance guidance for education, not a substitute for a company's actual
  policies, DPO, or legal counsel.
- **Demo mode is intentionally simpler than a live model.** Regex and keyword
  heuristics cannot judge context the way the Few-Shot-prompted model can;
  demo results are labeled `"mode": "demo"` for exactly this reason.
- Flagged snippets are shown back to the user in the findings so they can see
  what was caught; users should still treat the original text as sensitive
  and avoid pasting real secrets into any demo environment.

## 10. Future Work

- Browser extension / chat-sidebar version that checks text at the moment of
  pasting, inside the AI tool itself.
- Organization policy packs: load a company's own data-classification rules
  into the prompt template so decisions match internal policy.
- Audit logging (hashed, never raw text) so a governance team can see leak
  trends — the natural bridge to SIEM/telemetry tooling.
- Additional destinations and jurisdictions (e.g. stricter handling for
  health or student records), and a feedback loop where security teams label
  false positives/negatives to improve the Few-Shot examples.

## 11. Presentation / Live Demo Outline (under 2 minutes)

1. **Problem (15s):** "Employees paste secrets and customer data into public
   AI tools because nobody tells them what's risky until it's too late."
2. **Leaky demo (40s):** Click *Load a leaky example* → *Check Prompt*.
   Show the red Block & Escalate banner, the 100/Critical meter, the findings
   cards (API key, SSN, email, codename), and the redacted version.
3. **Safe demo (20s):** Click *Load a safe example* → green Allow, score 0.
   The point: the tool helps you work, it doesn't just block you.
4. **Prompt engineering (25s):** Open `prompts/prompt_template.txt` — Persona
   (governance analyst), Few-Shot (three anchoring examples), Template
   (JSON-only schema that powers the UI).
5. **Close (20s):** "I built a complete Flask + Generative API app around a
   single prompt template, pointed at AI governance — it works with Gemini
   or OpenAI, and the demo mode means this demo could not fail today."
