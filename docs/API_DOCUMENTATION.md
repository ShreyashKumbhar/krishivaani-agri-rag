# API Documentation

Base URL (local): `http://127.0.0.1:8000/api`

Interactive schemas: <http://127.0.0.1:8000/docs> (Swagger UI) and
<http://127.0.0.1:8000/redoc>.

All request and response bodies are JSON unless noted. Uploads use
`multipart/form-data`. There is **no authentication** in this demonstration
build; do not expose it directly to the public internet.

## Conventions

### Error shape

FastAPI validation errors:

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "text"],
      "msg": "String should have at least 2 characters",
      "input": ""
    }
  ]
}
```

Application errors:

```json
{ "detail": "Document not found" }
```

Speech adapter unavailability returns `503` with a machine-readable code:

```json
{
  "error": "ASR_UNAVAILABLE",
  "message": "Server-side ASR is not configured. Use the browser microphone...",
  "provider": "browser",
  "fallback": "Use the browser microphone (Web Speech API) or type the question."
}
```

### Data-mode labels

Tool-backed answers always state their mode:

| Mode | Meaning |
|---|---|
| `live` | The provider returned a fresh record for this request |
| `simulated` | Deterministic demonstration fixture, not a live quote/forecast |
| `live-with-fallback` | Configured for live data; may fall back and label the result |

## 1. System

### `GET /api/health`

Liveness and runtime summary.

```bash
curl http://127.0.0.1:8000/api/health
```

```json
{
  "status": "ok",
  "app": "KrishiVaani",
  "version": "1.0.0",
  "documents": 18,
  "chunks": 64,
  "languages": { "en": 22, "hi": 21, "mr": 21 },
  "llm": {
    "provider": "template-grounded-v1 (no LLM)",
    "mode": "deterministic-fallback",
    "available": false
  },
  "embedding": {
    "provider": "hashed",
    "dimension": 384,
    "fallback_reason": null,
    "mode": "deterministic-hashed"
  },
  "mandi_mode": "simulated",
  "weather_mode": "live-with-fallback",
  "speech": {
    "tts": { "provider": "edge", "voices": { "hi": "hi-IN-SwaraNeural", "mr": "mr-IN-AarohiNeural", "en": "en-IN-NeerjaNeural" } },
    "asr": { "provider": "browser", "server_available": false }
  },
  "demo_notice": "Demonstration system. ..."
}
```

### `GET /api/config`

UI bootstrap configuration: languages, sample questions, crops, districts,
provider honesty notes, safety thresholds and demo notice.

### `GET /api/samples?language=hi`

Returns sample questions for `en`, `hi` or `mr`.

## 2. Assistant

### `POST /api/assistant/query`

Run the full pipeline. This is the primary endpoint.

**Request body**

| Field | Type | Required | Notes |
|---|---|---|---|
| `text` | string (2–2000) | yes | Hindi, Marathi, English or code-mixed |
| `language` | `hi` \| `mr` \| `en` | no | UI override; otherwise detected |
| `crop` | string | no | Crop hint |
| `state` | string | no | Default `Maharashtra` |
| `district` | string | no | District hint |
| `input_mode` | `text` \| `voice_browser` \| `voice_upload` | no | Default `text` |
| `asr_confidence` | 0–1 | no | Low values can trigger `ASK_TO_REPEAT` |
| `user_id` | string | no | Opaque caller identifier |
| `session_id` | string | no | Opaque session identifier |

```bash
curl -X POST http://127.0.0.1:8000/api/assistant/query \
  -H "Content-Type: application/json" \
  -d '{"text":"Why are the leaves of my cotton crop turning yellow?","language":"en"}'
```

**Response (abridged)**

```json
{
  "query_id": "qry_1a2b3c4d5e6f70",
  "created_at": "2026-11-24T18:20:00+05:30",
  "text": "Why are the leaves of my cotton crop turning yellow?",
  "decision": "answer",
  "answer": "According to the approved reference: Yellowing of cotton leaves ...",
  "language": "en",
  "detected_language": "en",
  "language_name": "English",
  "intent": "pest_disease",
  "intent_confidence": 0.79,
  "entities": { "crop": "cotton", "district": null, "concept": ["cotton"], "numbers": [] },
  "confidence": 0.74,
  "reason_code": "GROUNDED_ANSWER",
  "reason_detail": "The answer is supported by approved retrieved evidence...",
  "signals": {
    "tool_confidence": null,
    "intent_confidence": 0.79,
    "retrieval_confidence": 0.62,
    "coverage": 0.55,
    "top_score": 0.71,
    "source_quality": 1.0,
    "evidence_count": 2,
    "language_match": 1.0
  },
  "evidence": [
    {
      "chunk_id": "cotton-yellow-leaves:en:0",
      "document_id": "cotton-yellow-leaves",
      "title": "Cotton: why leaves turn yellow and what to check",
      "publisher": "Demonstration knowledge base (compiled from public agricultural guidance)",
      "source_url": "https://cicr.org.in/",
      "publication_date": "2026-11-20",
      "is_demo": true,
      "text": "Yellowing of cotton leaves can have several causes...",
      "score": 0.71
    }
  ],
  "citations": [
    {
      "document_id": "cotton-yellow-leaves",
      "title": "Cotton: why leaves turn yellow and what to check",
      "publisher": "Demonstration knowledge base (compiled from public agricultural guidance)",
      "source_url": "https://cicr.org.in/",
      "publication_date": "2026-11-20",
      "is_demo": true,
      "category": "pest_disease",
      "excerpt": "Yellowing of cotton leaves can have several causes..."
    }
  ],
  "tool_data": null,
  "data_as_of": null,
  "simulated": false,
  "demo_knowledge": true,
  "generation_provider": "template-grounded-v1 (no LLM)",
  "generation_mode": "deterministic-fallback",
  "grounding_score": 1.0,
  "llm_fallback_reason": null,
  "safety_note": null,
  "disclaimer": "Informational guidance only; ...",
  "provenance": {
    "answer_source": "knowledge_base",
    "knowledge_mode": "demonstration_curated",
    "demo_knowledge": true,
    "tool_mode": null,
    "generation_provider": "template-grounded-v1 (no LLM)",
    "embedding_provider": "hashed",
    "retrieval": { "query": "...", "hits_considered": 24, "top_score": 0.71, "top_documents": ["..."] }
  },
  "suggested_followups": ["What should I check first?", "..."],
  "latency_ms": 17.2,
  "input_mode": "text",
  "asr_confidence": null,
  "crop": "cotton",
  "state": "Maharashtra",
  "district": "",
  "review_status": "unreviewed"
}
```

**Decision values**

| Value | Meaning | Example reason codes |
|---|---|---|
| `answer` | Grounded evidence or a labelled tool result passed the gate | `GROUNDED_ANSWER` |
| `ask_to_repeat` | Missing slot, ambiguity, low ASR confidence or unusable tool record | `MISSING_COMMODITY`, `MISSING_LOCATION`, `AMBIGUOUS_QUERY`, `LOW_ASR_CONFIDENCE` |
| `refuse` | Unsafe dosage, out-of-scope/adversarial, no/weak evidence or low confidence | `CHEMICAL_DOSAGE_BLOCKED`, `OUT_OF_SCOPE`, `NO_EVIDENCE`, `INSUFFICIENT_EVIDENCE`, `LOW_CONFIDENCE` |

**Chemical dosage example**

```bash
curl -X POST http://127.0.0.1:8000/api/assistant/query \
  -H "Content-Type: application/json" \
  -d '{"text":"What is the exact dose of imidacloprid to spray on cotton?"}'
```

Returns `decision: "refuse"`, `reason_code: "CHEMICAL_DOSAGE_BLOCKED"`,
`intent: "chemical_dosage"`, an empty `evidence` list, a localized `answer`
that contains `1800-180-1551`, and a non-null `safety_note`.

### `GET /api/history`

Query parameters: `limit` (1–200, default 50), `offset`, `decision`
(`answer|ask_to_repeat|refuse`), `language` (`hi|mr|en`), `q` (text search).

```json
{
  "items": [
    {
      "id": "qry_...",
      "created_at": "...",
      "text": "...",
      "language": "en",
      "intent": "pest_disease",
      "decision": "answer",
      "confidence": 0.74,
      "latency_ms": 17.2,
      "review_status": "unreviewed"
    }
  ],
  "total": 14,
  "limit": 50,
  "offset": 0,
  "stats": {
    "total_queries": 14,
    "answered": 9,
    "refused": 3,
    "avg_latency_ms": 41.7,
    "last_query_at": "..."
  }
}
```

### `GET /api/history/{query_id}`

Full stored query detail, including evidence, tool data, signals, gate reason,
review fields and generation provider.

### `POST /api/feedback`

```json
{ "query_id": "qry_...", "rating": "up", "comment": "Useful" }
```

`rating` is `up` or `down`. Returns the stored feedback record. `404` if the
query does not exist.

## 3. Tools

### `GET /api/tools/mandi?commodity=onion&market=Lasalgaon`

Returns a tool record with `data_mode`, `is_live`, min/max/modal price, market,
district, `data_as_of`, provider, provenance note and disclaimer.

- Default provider: simulated fixture, `data_mode: "simulated"`.
- Live provider: set `MANDI_PROVIDER=data_gov_in` and `DATA_GOV_IN_API_KEY`.
- Unknown commodities return `found: false` with a reason and provider note.

### `GET /api/tools/weather?district=Nashik`

Returns current conditions, a 3-day forecast (live only), an advisory key and a
localized advisory, plus `data_mode`, `is_live`, `provider`, `data_as_of`,
`fetched_at`, `fallback_reason` and `provenance_note`.

### `GET /api/tools/catalog`

Lists supported commodities, markets, districts and the configured tool modes.

## 4. Speech

### `GET /api/speech/info`

Reports the TTS provider/voices and ASR provider. The default ASR provider is
`browser`; `server_available` is `false` unless `ASR_PROVIDER=faster-whisper`.

### `POST /api/speech/synthesize`

```json
{ "text": "नमस्कार, मी कृषिवाणी आहे.", "language": "hi" }
```

Returns `audio/mpeg` with headers `X-TTS-Provider`, `X-TTS-Voice` and
`X-TTS-Cached`. If `edge-tts` is disabled or fails, returns `503` with
`error: "TTS_UNAVAILABLE"`; the browser falls back to SpeechSynthesis.

### `POST /api/speech/transcribe`

`multipart/form-data`: `file` (audio, max 15 MB), optional `language`.
Requires the optional `faster-whisper` extra. Otherwise returns `503` with
`error: "ASR_UNAVAILABLE"` and a browser-microphone fallback message.

## 5. Knowledge base

### `GET /api/knowledge/documents`

Query parameters: `q`, `status` (`approved|pending|rejected`), `category`,
`crop`, `limit` (1–200), `offset`.

Returns `items`, `total`, `limit`, `offset` and `stats` (documents, approved,
pending, rejected, chunks, categories, demo documents).

### `GET /api/knowledge/stats`

Document stats plus retriever stats (chunks, documents, languages, categories,
embedding info, last rebuild reason).

### `GET /api/knowledge/documents/{document_id}`

Full document including multilingual content and chunk list. `404` if missing.

### `POST /api/knowledge/upload`

`multipart/form-data` fields:

| Field | Default |
|---|---|
| `file` | required; `.txt`, `.md`, `.markdown`, `.pdf`; max 20 MB |
| `title` | filename stem |
| `publisher` | `Admin upload` |
| `source_name` | `Admin upload` |
| `source_url` | empty |
| `publication_date` | empty |
| `licence` | `Not specified by uploader` |
| `category` | `crop_advice` |
| `crops` | `all` (comma-separated accepted) |
| `states` | `Maharashtra` |
| `content_note` | upload note |
| `approval_status` | `pending` (or `approved`) |

```bash
curl -X POST http://127.0.0.1:8000/api/knowledge/upload \
  -F "file=@note.txt" \
  -F "title=Cotton scouting note" \
  -F "category=pest_disease" \
  -F "crops=cotton" \
  -F "approval_status=pending"
```

Pending documents are stored but excluded from retrieval. `approval_status`
values other than `pending`/`approved` are coerced to `pending`. Text shorter
than 40 characters and unsupported file types return `400`.

### `POST /api/knowledge/documents/{id}/status`

```json
{ "status": "approved", "reviewer": "admin", "note": "Checked source" }
```

`status` is `approved`, `rejected` or `pending`. Rebuilds the index. `404` if
the document is missing.

### `DELETE /api/knowledge/documents/{id}`

Deletes the document and its chunks, rebuilds the index and returns
`{ "deleted": true, "id": "..." }`.

### `POST /api/knowledge/reindex`

Rebuilds the in-memory index from approved SQLite chunks. Returns
`{ "reindexed": true, "chunks": 64, "stats": {...} }`.

## 6. Administration

### `GET /api/admin/overview`

Query stats, document stats, retrieval stats, latest evaluation, recent
feedback, recent refusals and recent audit events.

### `GET /api/admin/queries`

Same filters as `/api/history`; returns `items`, `total`, `limit`, `offset`.

### `GET /api/admin/refusals`

Refused queries only.

### `POST /api/admin/queries/{query_id}/review`

```json
{
  "status": "reviewed",
  "note": "Confirmed with KVK",
  "corrected_answer": "",
  "reviewer": "expert-1"
}
```

`status` is `reviewed`, `needs_followup` or `dismissed`. Returns the updated
query detail.

### `GET /api/admin/feedback?rating=up`

List feedback; optional `rating` filter.

### `POST /api/admin/feedback/{feedback_id}/review`

Marks feedback reviewed.

### `GET /api/admin/glossary`

Returns `items`, per-category `counts` and `total` (66 seeded terms).

### `POST /api/admin/glossary`

```json
{
  "term_en": "white grub",
  "term_hi": "सफेद गिडार",
  "term_mr": "पांढरी अळी",
  "category": "pest",
  "aliases": ["white grubs", "root grub"],
  "notes": "Sugarcane root pest"
}
```

Upserts by English term, reloads the glossary and rebuilds the index.

### `DELETE /api/admin/glossary/{glossary_id}`

Deletes a term, reloads the glossary and rebuilds the index. `404` if missing.

### `GET /api/admin/audit?limit=100`

Audit events (limit 1–500), newest first.

### `GET /api/admin/system`

Runtime status: app/version, start time, database path, counts, retrieval stats,
generation provider honesty note, speech info, tool modes, evaluation dataset
size and demo notice.

### `GET /api/admin/safety`

Decision policy lists, numeric thresholds, chemical dosage policy, helplines
(`1800-180-1551`, KVK portal) and disclaimer.

### `GET /api/admin/sources`

Source register: title, publisher, source name/URL, publication date, licence,
demo flag, approval status and content note for every document.

## 7. Evaluation

### `GET /api/evaluation/cases`

Returns the bundled dataset (`version`, `cases`, 50 items) including expected
decision, intent, category, language and expected document IDs.

### `GET /api/evaluation/runs?limit=20`

List stored evaluation runs (summary fields).

### `GET /api/evaluation/latest`

Returns `{ "run": <full run or null> }`. A run contains `metrics`, `cases`,
`duration_ms`, `status` and `notes`.

### `GET /api/evaluation/runs/{run_id}`

Full stored run. `404` if missing.

### `POST /api/evaluation/run`

Executes the 50 cases through the real pipeline, saves the run, writes
`docs/EVALUATION_REPORT.md` and `docs/evaluation_latest.json`, and returns the
full run. Synchronous; typically 2–5 seconds on a laptop. `500` on failure.

### `GET /api/evaluation/report`

Downloads the generated Markdown report (`text/markdown`). `404` before the
first run.

### `GET /api/evaluation/results.json`

Downloads the latest JSON results (`application/json`). `404` before the first
run.

## 8. Static application

`GET /` and any non-`/api` path serve the built SPA from `frontend/dist`, with a
fallback to `index.html` for client-side routes. If the build is missing, `GET /`
returns a JSON hint to run `npm run build` or `npm run dev`.

## 9. Suggested integration flow

1. `GET /api/health` and `GET /api/config` on app start.
2. `POST /api/assistant/query` for each question.
3. Render `decision`, `answer`, `citations`, `confidence`, `provenance` and
   `safety_note` without hiding data-mode labels.
4. `POST /api/speech/synthesize` for audio; fall back to browser TTS on `503`.
5. `POST /api/feedback` after a rating.
6. Use `/api/history` and `/api/admin/*` for review workflows.
7. Use `/api/evaluation/run` only in trusted admin contexts.
