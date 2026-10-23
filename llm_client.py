"""
llm_client.py - Generative API provider logic for Prompt Leak Checker.

The flow I implemented: prompt template file -> fill variables -> call a
Generative API from Python -> parse structured JSON output.

Providers, in priority order:
  1. Gemini  - used when GEMINI_API_KEY is set. This is my primary
               live provider for this project.
               Model from GEMINI_MODEL (default: gemini-3.8-flash).
  2. OpenAI  - used when OPENAI_API_KEY is set (and no Gemini key).
               Model from OPENAI_MODEL (default: gpt-4o-mini).
  3. Demo    - no key set. A clearly labeled local rule + heuristic
               analyzer that returns the SAME JSON schema, so the
               live demo can never fail for lack of an API key.

Only the Python standard library (urllib) is used for API calls.
The only external dependency of this project is Flask (see app.py).
"""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent / "prompts" / "prompt_template.txt"

DECISIONS = ("Allow", "Redact & Send", "Block & Escalate")
RISK_LEVELS = ("Low", "Medium", "High", "Critical")


class LLMError(Exception):
    """Raised when a live provider call or its JSON parsing fails."""


# ----------------------------------------------------------------------
# Prompt template
# ----------------------------------------------------------------------

def load_prompt(prompt_text, destination_tool, data_context):
    """Fill the prompt template file with the user's inputs.

    Uses simple string replacement (not str.format) because the
    template intentionally contains many literal JSON braces for the
    Template pattern's output schema.
    """
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{destination_tool}", destination_tool or "")
        .replace("{data_context}", data_context or "")
        .replace("{prompt_text}", prompt_text or "")
    )


# ----------------------------------------------------------------------
# Provider selection
# ----------------------------------------------------------------------

def current_mode():
    """Return 'gemini', 'openai', or 'demo' based on the environment."""
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "demo"


# ----------------------------------------------------------------------
# Live provider calls (stdlib urllib only)
# ----------------------------------------------------------------------

def _post_json(url, payload, headers, timeout=30):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LLMError(f"Provider returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"Could not reach the provider: {exc.reason}.") from exc


def _call_openai(prompt):
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": "You are an AI governance and data protection "
                           "analyst. Respond with JSON only, matching the "
                           "schema in the user message exactly.",
            },
            {"role": "user", "content": prompt},
        ],
    }
    result = _post_json(
        "https://api.openai.com/v1/chat/completions",
        payload,
        {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
    )
    try:
        return result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("Unexpected response shape from OpenAI.") from exc


def _call_gemini(prompt):
    model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    api_key = os.environ["GEMINI_API_KEY"]
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    result = _post_json(url, payload, {})
    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("Unexpected response shape from Gemini.") from exc


# ----------------------------------------------------------------------
# JSON parsing / normalization (shared by all providers)
# ----------------------------------------------------------------------

def parse_model_json(raw_text):
    """Parse model output robustly: strip code fences, extract the
    outermost JSON object, and raise a clear LLMError on failure."""
    if not raw_text or not raw_text.strip():
        raise LLMError("The model returned an empty response.")
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMError("The model did not return a JSON object.")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"The model returned invalid JSON: {exc}.") from exc


def risk_level_for(score):
    if score >= 75:
        return "Critical"
    if score >= 50:
        return "High"
    if score >= 25:
        return "Medium"
    return "Low"


def normalize_result(data, mode):
    """Validate/coerce a parsed result into the exact app schema."""
    if not isinstance(data, dict):
        raise LLMError("The model result was not a JSON object.")

    try:
        score = int(round(float(data.get("risk_score", 0))))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))

    decision = data.get("decision")
    if decision not in DECISIONS:
        if score >= 75:
            decision = "Block & Escalate"
        elif score >= 25 or data.get("findings"):
            decision = "Redact & Send"
        else:
            decision = "Allow"

    findings = []
    for item in data.get("findings") or []:
        if not isinstance(item, dict):
            continue
        findings.append({
            "category": str(item.get("category", "Confidential Company Information")),
            "severity": str(item.get("severity", "Medium")),
            "snippet": str(item.get("snippet", "")),
            "explanation": str(item.get("explanation", "")),
            "recommendation": str(item.get("recommendation", "")),
        })

    return {
        "decision": decision,
        "risk_score": score,
        "risk_level": risk_level_for(score),
        "summary": str(data.get("summary", "")),
        "findings": findings,
        "redacted_text": str(data.get("redacted_text", "")),
        "policy_reason": str(data.get("policy_reason", "")),
        "mode": mode,
    }


# ----------------------------------------------------------------------
# Demo fallback analyzer (no API key required)
# Rule + heuristic analyzer producing the SAME JSON schema.
# ----------------------------------------------------------------------

def _finding(category, severity, snippet, explanation, recommendation):
    return {
        "category": category,
        "severity": severity,
        "snippet": snippet,
        "explanation": explanation,
        "recommendation": recommendation,
    }


def analyze_demo(prompt_text, destination_tool, data_context):
    text = prompt_text or ""
    redacted = text
    findings = []
    score = 0
    is_public = "Company-approved" not in (destination_tool or "")

    def redact(pattern, placeholder, flags=0):
        # Replace every match in the working redacted copy.
        nonlocal redacted
        redacted = re.sub(pattern, placeholder, redacted, flags=flags)

    # --- Secrets / credentials (checked first: highest severity) ---
    secret_patterns = [
        (r"\bsk-[A-Za-z0-9\-_]{8,}\b", "Secret/Credential", "Critical", 50,
         "[REDACTED API KEY]",
         "This looks like an API key. Anyone who has it can use the account it belongs to.",
         "Remove the key, rotate/revoke it in the provider dashboard, and load keys from an environment variable or secrets manager instead."),
        (r"\bAKIA[0-9A-Z]{16}\b", "Secret/Credential", "Critical", 50,
         "[REDACTED AWS ACCESS KEY]",
         "This matches the pattern of an AWS access key ID, a cloud credential.",
         "Remove it, deactivate the key in AWS IAM, and issue a replacement credential."),
        (r"\bghp_[A-Za-z0-9]{20,}\b", "Secret/Credential", "Critical", 50,
         "[REDACTED GITHUB TOKEN]",
         "This looks like a GitHub personal access token.",
         "Remove it and revoke the token in GitHub settings."),
        (r"(?i)\b(password|passwd|pwd)\s*[:=]\s*\S+", "Secret/Credential", "High", 40,
         "[REDACTED PASSWORD]",
         "A password value appears in plain text in the prompt.",
         "Remove the password and change it anywhere it was reused."),
        (r"(?i)\b(api[_-]?key|secret|token)\s*[:=]\s*[\"']?[A-Za-z0-9\-_\.]{8,}", "Secret/Credential", "High", 40,
         "[REDACTED SECRET]",
         "A secret, token, or API key value appears in the prompt.",
         "Remove the value and rotate the credential if it was ever real."),
    ]
    # Patterns are searched in the evolving `redacted` copy: once a
    # fragment is replaced by a placeholder it cannot trigger a second,
    # weaker pattern (e.g. an SSN's digits matching the phone pattern).
    for pattern, category, severity, points, placeholder, why, fix in secret_patterns:
        for match in re.finditer(pattern, redacted):
            findings.append(_finding(category, severity, match.group(0), why, fix))
            score += points
        redact(pattern, placeholder)

    # --- PII ---
    pii_patterns = [
        (r"\b\d{3}-\d{2}-\d{4}\b", "PII", "Critical", 45,
         "[REDACTED SSN]",
         "This matches the pattern of a US Social Security number, a government ID.",
         "Remove government IDs entirely; they are never needed by an AI writing assistant."),
        (r"\b(?:\d[ -]?){13,16}\b", "PII", "High", 40,
         "[REDACTED CARD NUMBER]",
         "This long digit sequence looks like a payment card number.",
         "Remove payment card numbers; use only the last 4 digits if you must refer to a card."),
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "PII", "Medium", 25,
         "[REDACTED EMAIL]",
         "A personal email address identifies a specific person.",
         "Replace personal email addresses with a role or placeholder before sending."),
        (r"(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}\b", "PII", "Medium", 25,
         "[REDACTED PHONE]",
         "A phone number identifies a specific person.",
         "Replace phone numbers with a placeholder before sending."),
    ]
    # Order matters: SSN and card run before email and phone, and each
    # search uses the evolving `redacted` copy (see note above).
    for pattern, category, severity, points, placeholder, why, fix in pii_patterns:
        for match in re.finditer(pattern, redacted):
            findings.append(_finding(category, severity, match.group(0), why, fix))
            score += points
        redact(pattern, placeholder)

    # --- Confidential / internal company information (keyword heuristics) ---
    confidential_keywords = [
        (r"(?i)\bconfidential\b", "The text is marked confidential."),
        (r"(?i)\binternal only\b", "The text is marked for internal use only."),
        (r"(?i)\bdo not share\b", "The text says it should not be shared."),
        (r"(?i)\bproprietary\b", "The text mentions proprietary information."),
        (r"(?i)\btrade secret\b", "The text mentions a trade secret."),
        (r"(?i)\bunder nda\b", "The text mentions material under an NDA."),
        (r"(?i)\bunreleased\b", "The text mentions unreleased plans or products."),
        (r"(?i)\bcodename\s+[A-Za-z][A-Za-z0-9\-]*(\s+[A-Z][a-zA-Z]+)?", "The text references an internal project codename."),
        (r"(?i)\bproject\s+[A-Z][a-zA-Z]+\b", "The text names an internal project."),
        (r"(?i)\bcustomer (database|list|export)\b", "The text references customer database / list material."),
        (r"(?i)\broadmap\b", "The text references an internal roadmap."),
    ]
    confidential_found = False
    for pattern, why in confidential_keywords:
        match = re.search(pattern, text)
        if match:
            confidential_found = True
            findings.append(_finding(
                "Confidential Company Information", "High", match.group(0).strip(),
                why + " Non-public company information can leak strategy, "
                      "customer data, or unreleased plans when sent outside company control.",
                "Remove internal codenames, plans, and customer material, or use the company-approved AI tool with an approved use case.",
            ))
            score += 25
            break  # One confidential finding is enough; details are in the summary.

    if data_context and re.search(r"(?i)customer|patient|employee|salary|financial", data_context):
        findings.append(_finding(
            "Confidential Company Information", "Medium", "(data context)",
            "The stated data context involves sensitive records (customer, patient, employee, salary, or financial data).",
            "Confirm this destination tool is approved for that data category before sending anything.",
        ))
        score += 15
        confidential_found = True

    score = max(0, min(100, score))

    has_critical = any(f["severity"] == "Critical" for f in findings)
    has_secret = any(f["category"] == "Secret/Credential" for f in findings)

    if score >= 75 or has_secret or has_critical:
        decision = "Block & Escalate"
    elif findings:
        decision = "Redact & Send"
    else:
        decision = "Allow"

    destination_label = destination_tool or "an AI tool"
    if decision == "Block & Escalate":
        summary = (
            f"This text is not safe to send to {destination_label}. It contains "
            f"{len(findings)} flagged item(s), including high-severity material "
            "such as a credential, government ID, or confidential company information."
        )
        policy_reason = (
            "Company AI governance policy: credentials, government IDs, and "
            "confidential company information must never be sent to "
            + ("a public AI tool outside company control. " if is_public else "an AI tool without security review. ")
            + "Escalate to the security / AI governance team, and rotate any exposed credential."
        )
    elif decision == "Redact & Send":
        summary = (
            f"This text contains {len(findings)} flagged item(s) for {destination_label}, "
            "but it can be used safely if you send the redacted version instead of the original."
        )
        policy_reason = (
            "Company AI governance policy: personal data and internal information "
            "must be removed or replaced with placeholders before text is sent to "
            + ("a public AI tool. " if is_public else "an AI tool. ")
            + "The redacted version satisfies that requirement for this text."
        )
    else:
        summary = (
            f"No PII, secrets, or confidential company information were found. "
            f"This text looks safe to send to {destination_label}."
        )
        policy_reason = (
            "Company AI governance policy: text with no personal data, credentials, "
            "or confidential company information may be sent to an AI tool. "
            "Demo mode note: this result came from the local rule-based analyzer, not a live model."
            if current_mode() == "demo" else
            "Company AI governance policy: text with no personal data, credentials, "
            "or confidential company information may be sent to an AI tool."
        )
        redacted = text

    if decision == "Allow":
        redacted = text

    return {
        "decision": decision,
        "risk_score": score,
        "risk_level": risk_level_for(score),
        "summary": summary,
        "findings": findings,
        "redacted_text": redacted,
        "policy_reason": policy_reason,
        "mode": "demo",
    }


# ----------------------------------------------------------------------
# Main entry point used by app.py
# ----------------------------------------------------------------------

def analyze(prompt_text, destination_tool, data_context):
    """Return a result dict in the exact app schema.

    Uses a live provider when a key is configured; otherwise the demo
    fallback. Live provider / parsing failures raise LLMError, which
    app.py converts into a clear error JSON (never a stack trace).
    """
    mode = current_mode()
    if mode == "demo":
        return analyze_demo(prompt_text, destination_tool, data_context)

    prompt = load_prompt(prompt_text, destination_tool, data_context)
    if mode == "gemini":
        raw = _call_gemini(prompt)
    else:
        raw = _call_openai(prompt)
    data = parse_model_json(raw)
    return normalize_result(data, mode)
