# Demo Video Script — Prompt Leak Checker (under 2 minutes, vertical 1080x1920)

Format: people-free screen recording, title card open, captions on screen,
punchline/close card at the end.
All data shown is FAKE (fake SSN, fake email, fake API key, fake codename).

## Shot list

| Time | Visual | On-screen text / narration |
|---|---|---|
| 0:00-0:08 | Title card | "I almost pasted an API key into ChatGPT" / Prompt Leak Checker — check your prompt BEFORE you send it |
| 0:08-0:25 | The problem, fast cuts of a messy prompt being typed | People paste customer emails, SSNs, API keys, and internal plans into public AI tools every day. Nobody warns them until it is too late. |
| 0:25-1:00 | Screen record: click the Leaky example -> Check Prompt | Red banner: Block & Escalate, Critical risk. Findings: API key, SSN, email, phone, confidential codename. And here is the same prompt, redacted and safe. |
| 1:00-1:15 | Screen record: click the Safe example -> Check Prompt | Not everything gets blocked. A normal prompt gets a green Allow, low risk. It helps you work, it does not just say no. |
| 1:15-1:40 | Quick scroll of prompts/prompt_template.txt | Built with prompt engineering: Persona (an AI governance analyst), Few-Shot examples that anchor each decision, and a Template pattern that forces JSON-only output to power the UI. I built it with Flask + Gemini. |
| 1:40-1:55 | Close card with the three decisions | Allow. Redact & Send. Block & Escalate. Check the prompt before the prompt leaks. |

## Recording notes
- Run the app locally first (python app.py), record at a large font/zoom so
  the decision banner and risk meter are readable on a phone screen.
- Use the built-in Leaky/Safe example links only — no real data on screen.
- Keep total runtime under 2:00 per the assignment; target ~1:50.
- Live Gemini scores vary slightly between runs and can briefly return a
  "busy" error (click Try again). For a guaranteed take, temporarily remove
  the key from `.env` to record in demo mode.
