# User Guide

KrishiVaani has two audiences: farmers/advisors who ask questions, and
administrators/experts who curate knowledge and review answers. The same web app
serves both; the navigation is in the left sidebar.

> This is a demonstration build. It is not official ICAR/KVK advice. Always
> verify chemical, scheme, market and weather information with the official
> source or a qualified professional.

## 1. Getting started

1. Start the app using the Quick start instructions in the [README](../README.md).
2. Open <http://127.0.0.1:8000>.
3. The top bar shows backend health (`18 docs · 64 chunks`), the demonstration
   badge and a refresh button.
4. The sidebar shows the five views and the Kisan Call Centre number
   **1800-180-1551**.

![Home](screenshots/01-farmer-assistant-home.png)

## 2. Farmer Assistant

### 2.1 Ask by typing

1. Choose **हिंदी**, **मराठी** or **English**.
2. Type a question, for example:
   - “Why are the leaves of my cotton crop turning yellow?”
   - “मेरी कपास की पत्तियाँ पीली क्यों हो रही हैं?”
   - “माझ्या कापसाची पाने पिवळी का होत आहेत?”
3. Optionally choose a **Crop** and **District**, or leave them on
   **Auto-detect**.
4. Press **Get answer** (or `Enter`; use `Shift+Enter` for a new line).

### 2.2 Ask by voice

1. Press **Speak** and allow microphone access when the browser asks.
2. Speak clearly in Hindi, Marathi or English.
3. The browser Web Speech API transcribes your speech into the text box.
4. Review the transcript and press **Get answer**.

Voice input uses the browser's speech recognition. Support and accuracy vary by
browser, OS and network. If the microphone is unavailable, type the question.
Server-side `faster-whisper` is optional and disabled by default.

### 2.3 Listen to the answer

Press **Listen** on an answer card. The server synthesizes speech with
`edge-tts` (Hindi, Marathi or English voice). If server TTS is unavailable, the
app falls back to the browser's SpeechSynthesis voice.

### 2.4 Read the answer card

| Area | What it shows |
|---|---|
| Status chips | Decision (`Answered`, `Needs clarification`, `Refused safely`), intent, language, demo corpus |
| Confidence | Combined confidence and the gate reason |
| Side panel | Intent confidence, evidence count, grounding score, detected entities |
| Answer body | Localized grounded answer |
| Sources used | Citations with title, publisher, date, excerpt, demo badge and source link |
| Follow-up questions | Suggested next questions in the selected language |
| Feedback | **Yes** / **Not really** buttons |
| Provenance | Expand to inspect retrieval scores, embedding provider, generation mode and data mode |

![English answer](screenshots/02-farmer-assistant-answer.png)

### 2.5 Hindi example

![Hindi answer](screenshots/03-farmer-assistant-hindi.png)

### 2.6 When the assistant refuses

Chemical dosage questions are always refused. The card explains why, shows a
safety note and refers you to the product label, CIB&RC, KVK and Kisan Call
Centre **1800-180-1551**. The assistant will not provide a dose number.

![Dosage refusal](screenshots/04-farmer-assistant-refusal.png)

Other refusal or clarification cases:

- **Needs clarification** — missing crop/commodity or district, a pronoun-only
  question (“Why is it yellow?”), or low speech-recognition confidence.
- **Refused safely** — out-of-scope/adversarial questions, no approved evidence,
  weak retrieval coverage or low combined confidence.

### 2.7 Tools and labels

- **Mandi price** — asks for a commodity (and optionally a market). The default
  demo returns deterministic simulated prices and labels them **SIMULATED** in
  the answer. A live data.gov.in key enables real Agmarknet records labelled
  **LIVE**.
- **Weather** — asks for a district. Open-Meteo returns a live forecast labelled
  **LIVE** when the request succeeds. If the network fails, the app uses a
  deterministic fixture labelled **SIMULATED** with a reason.
- **Agromet guidance** — questions such as “Should I spray if rain is expected?”
  retrieve knowledge-base guidance rather than a live forecast.

### 2.8 Session strip and history

Answered questions appear in **This session** below the answer card. The full
persistent log is in **Query History**.

## 3. Knowledge Base

The Knowledge Base view lists approved, pending and rejected documents.

![Knowledge base](screenshots/05-knowledge-base.png)

### 3.1 Upload a document

1. Press **Upload document**.
2. Choose a `.txt`, `.md` or text-based `.pdf` (max 20 MB).
3. Fill in title, publisher, source name/URL, publication date, licence,
   category, crops, states and a content note.
4. Choose **Pending review** (recommended) or **Approve immediately**.
5. Press **Upload document**.

Pending uploads are stored but **not retrievable**. Only approved chunks enter
the index.

### 3.2 Approve, reject, delete

- Use the check icon on a row to approve, or the × icon to reject.
- Open a row to inspect multilingual content and indexed chunks.
- **Approve & index** makes the document retrievable.
- **Reject** removes it from retrieval without deleting it.
- **Delete** removes the document, its chunks and its retrieval entries.
- **Rebuild index** re-embeds approved chunks.

### 3.3 Source hygiene

Every document should have a publisher, source URL and content note. The demo
documents are marked **Demo summary**; admin uploads are marked **Admin source**.
Do not upload copyrighted material without permission. Scanned PDFs need OCR,
which is not enabled.

## 4. Query History

![Query history](screenshots/06-query-history.png)

- Filter by text, decision or language.
- Click a row to open the detail modal.
- Inspect the question, answer, confidence, gate reason, generation provider,
  retrieved evidence and tool mode.
- Use **Expert review** to set status (`Reviewed`, `Needs follow-up`,
  `Dismissed`), reviewer, note and an optional corrected answer.
- Reviews are persisted and appear in the history table.

Refusals are retained for review. A reviewer can mark a refusal as reviewed,
needs follow-up or dismissed, and record a corrected answer.

## 5. Evaluation

![Evaluation](screenshots/07-evaluation.png)

- The view loads the latest stored run.
- Press **Run evaluation** to execute the bundled 50-case set locally.
- Review Recall@5, faithfulness, correct refusal, intent accuracy, decision
  accuracy and latency.
- Use the case table filters to inspect individual results.
- Download the Markdown report or JSON results.
- Read the “Provenance and honesty notes” panel: faithfulness is lexical, voice
  round-trip is not measured, and the corpus is small and curated.

Evaluation runs are synchronous and typically take 2–5 seconds. They write
local results to `docs/EVALUATION_REPORT.md` and
`docs/evaluation_latest.json`; the generated Markdown report is not versioned.

## 6. Administration

![Administration](screenshots/08-administration.png)

The Administration view is read-mostly plus glossary editing.

### 6.1 Runtime status

Provider cards show:

- **Answer generation** — template composer (default, no LLM) or configured LLM.
- **Embeddings** — hashed or neural, dimensions and fallback reason.
- **Speech** — TTS provider and ASR mode.
- **Mandi** — simulated or live, with the key requirement.
- **Weather** — Open-Meteo live-with-fallback.
- **Runtime** — version, start time, database path and single-process note.

Cards explicitly label fallbacks; a mock is never shown as a live integration.

### 6.2 Safety policy

Shows the refuse/ask/answer rules, thresholds (`min retrieval score`, `min
evidence coverage`, `min answer confidence`, RRF/top-k values), the chemical
dosage policy and the helplines.

### 6.3 Glossary

- Search across English, Hindi, Marathi and aliases.
- Add a term with English/Hindi/Marathi names, category and comma-separated
  aliases.
- Deleting a term rebuilds the index.
- Glossary terms improve language detection, entity extraction, query expansion
  and cross-lingual retrieval.

### 6.4 Source register and audit

- The source register lists every document with publisher, source link, approval
  status, type (demo/admin) and note.
- Recent audit events record uploads, status changes, deletions, glossary
  changes and feedback reviews.

### 6.4.1 Admin sign-in and document versions

Use **Admin sign in** in the page header before uploading, approving, rejecting,
re-indexing or deleting documents. The demo credentials are configured through
`ADMIN_USERNAME` and `ADMIN_PASSWORD` in `.env` (defaults are intended only for
local demonstration). A successful sign-in stores a time-limited bearer token
in the browser. Documents show their version and status; uploading changed
content under the same title creates a new major version, while identical
content is rejected. The previous approved version is superseded when the new
version is approved.

### 6.5 Configuration limits

The bottom panel states the demo notice, evaluation set size, optional API keys
and the SQLite path. It is a quick way to confirm what is actually configured.

## 7. Privacy and safe use

- Queries are stored locally in SQLite, including text, answer, evidence and
  review fields. Do not enter personal or sensitive information.
- Admin mutations require a signed-in administrator. This is a single shared
  admin account, not role-based access control; query history remains locally
  readable to anyone who can reach the app.
- Do not use the assistant as the sole basis for chemical application, scheme
  eligibility or market decisions.
- For urgent agricultural help call the Kisan Call Centre **1800-180-1551** or
  contact your local KVK.

## 8. Keyboard and accessibility tips

- `Enter` sends; `Shift+Enter` adds a new line.
- Language tabs and buttons are keyboard-focusable.
- The layout is responsive down to phone width; the sidebar becomes a drawer
  below 760 px.
- High-contrast text and visible focus styles are used, but no formal WCAG audit
  has been performed.
