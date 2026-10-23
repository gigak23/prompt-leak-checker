"""
app.py - Flask server for Prompt Leak Checker + Governance Decision.

My CS4680 Assignment 3 project. The architecture I used:
prompt template file -> Python call to a Generative API -> Flask
server -> web UI served by Flask that renders structured JSON.

Routes:
  GET  /           serves the web UI (templates/index.html)
  GET  /health     returns JSON status
  POST /api/check  accepts JSON {prompt_text, destination_tool,
                   data_context} and returns the result schema
                   documented in prompts/prompt_template.txt and
                   README.md (decision, risk_score, risk_level,
                   summary, findings[], redacted_text,
                   policy_reason, mode).
"""

import os

from flask import Flask, jsonify, render_template, request

import llm_client

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "prompt-leak-checker",
        "mode": llm_client.current_mode(),
    })


@app.post("/api/check")
def api_check():
    payload = request.get_json(silent=True) or {}
    prompt_text = (payload.get("prompt_text") or "").strip()
    destination_tool = (payload.get("destination_tool") or "Other public AI tool").strip()
    data_context = (payload.get("data_context") or "").strip()

    if not prompt_text:
        return jsonify({
            "error": "prompt_text is required and cannot be empty. "
                     "Paste the text you want to check and try again."
        }), 400

    try:
        result = llm_client.analyze(prompt_text, destination_tool, data_context)
    except llm_client.LLMError as exc:
        # Clear error JSON - never leak a stack trace to the user.
        return jsonify({
            "error": f"The AI provider could not complete this check: {exc} "
                     "Check the API key / model configuration, or remove the "
                     "key to run in demo mode."
        }), 502
    except Exception as exc:  # Defensive: same clear-error contract.
        return jsonify({
            "error": f"Unexpected error while checking this prompt: {exc}"
        }), 500

    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=False)
