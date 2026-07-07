# JobPilot Platform — REST API Design (Phase 3)

**Contract:** [`api/openapi.yaml`](../api/openapi.yaml) — OpenAPI 3.1, validated
(52 paths, 70 operations, 42 schemas). In Phase 4 FastAPI becomes the live
source of truth and CI diffs the generated spec against this contract; the
frontend TypeScript client is generated from it (`openapi-typescript`).

---

## 1. Conventions

| Concern | Decision |
|---|---|
| Base path | `/api/v1` — version in path; breaking changes ⇒ `/api/v2` |
| Auth | `Authorization: Bearer <access JWT>` (15 min TTL). Rotate via `POST /auth/refresh` (14-day refresh token, single-use, reuse detection revokes the whole chain) |
| Errors | RFC-7807 `application/problem+json` everywhere: `{type, title, status, detail, errors[{field, message}]}` |
| Pagination | `?page=1&size=25` → `{items, page, size, total}`; `size` capped at 100 |
| Sorting | `?sort=field` / `?sort=-field` (enumerated per endpoint) |
| Timestamps | ISO-8601 UTC in payloads; user timezone applied client-side |
| IDs | UUIDs in URLs; never sequential integers for user-facing resources |
| Long work | Anything touching connectors or LLMs returns `202` + a pollable resource (`SearchRun`, `GeneratedDocument.status`) — HTTP requests never block on scraping or AI |
| Streaming | Assistant replies stream as Server-Sent Events (`text/event-stream`): token deltas, tool-call notices, final message object |
| Secrets | API keys / webhooks are write-only: accepted in PUT/POST, returned masked (`sk-***`) |
| RBAC | `/admin/**` requires `ADMIN` role — enforced by dependency, documented per tag |

## 2. Surface map (9 resource groups)

| Group | Endpoints | Notes |
|---|---|---|
| `auth` | register, login, refresh, logout, password forgot/reset, OAuth authorize/callback | Unauthenticated by design; login rate-limited; forgot-password always `202` (no user enumeration) |
| `profile` | `/users/me` (+ preferences, skills, notification-settings) | `PUT /users/me/preferences` is the single knob that drives ingestion, matching, and auto-apply policy |
| `resumes` | CRUD + upload (multipart), set-default, `/analysis` (AI: ATS score, gaps, suggestions), `/file` | Upload triggers parse + chunk + embed pipeline |
| `jobs` | list (all preference filters incl. W2/C2C, sponsorship, posted-within), detail, CSV export, search-runs (trigger + poll) | `GET /jobs` is the "browse everything found" view; export always works for SEARCH_LINK sources |
| `matches` | ranked list, per-job breakdown, recompute | Breakdown returns every sub-score + LLM reasoning → answers "why was this ranked low?" |
| `applications` | CRUD (soft delete), status transitions (event-sourced), events, contacts, `POST /apply` | `/apply` is compliance-gated: `409` + manual link when automation isn't permitted for that source |
| `documents` | generate (5 types), list, get, download file | Generation is async; guardrail-checked against the source resume before `READY` |
| `assistant` | conversations CRUD, `POST .../messages` (SSE) | RAG over the user's own jobs/resumes/applications; tool calls audited |
| `analytics` | `/dashboard` (composite, cached), `/trends` | One round-trip renders the dashboard page |
| `admin` | AI settings/keys, prompts (versioned, activate), connectors (toggle/health), watchlist, schedules (edit/run-now), run history, users, audit log | Everything the robot does is inspectable here |

## 3. Key flows

**Daily autonomous loop (no API calls needed):** beat triggers `ingest.full`
→ workers populate jobs/extractions/scores → auto-apply policy from
preferences fires where compliant → `report.daily` emails at 21:00 CT.
The API exposes the same machinery for on-demand use (`POST /search-runs`,
`POST /applications/{id}/apply`).

**Manual apply flow:** `GET /matches?min_score=70` → `POST /applications`
(status `SAVED`) → `POST /documents` (tailored resume + cover letter) →
user applies via `job.url` → `POST /applications/{id}/status {APPLIED}`.

**Assistant flow:** `POST /assistant/conversations` →
`POST .../messages {"content": "what should I apply to today?"}` → SSE stream;
assistant may call `get_top_matches` / `tailor_resume` tools, each emitted as
a `tool` event so the UI can render activity, each written to the audit log.

## 4. Example error (RFC-7807)

```json
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
{
  "type": "https://jobpilot.dev/problems/automation-not-permitted",
  "title": "Automation not permitted for this source",
  "status": 409,
  "detail": "linkedin_links is a SEARCH_LINK source. Apply manually via the provided URL.",
  "apply_url": "https://www.linkedin.com/jobs/view/…"
}
```

## 5. Deferred (explicitly not in v1)

- Webhooks/event subscriptions for third parties — not needed for one user; SSE covers the UI.
- Bulk endpoints (`PATCH /applications:batch`) — add when the tracker UI needs multi-select.
- API keys for programmatic access — JWT only until there's a second consumer.
