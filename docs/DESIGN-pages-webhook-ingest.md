# Design: Event-Driven Page Harvest & Ingest (Webhook Extension)

Status: **scoped, not built** — owner decision pending. Written 2026-08-27 so the
build can start later with full context.

## Purpose

Automate the mechanical stages of the website-pages knowledge pipeline while
preserving the owner-approval gate. Today the pipeline is fully manual:

1. Site changes (marketing pushes to the ciphex-website repo, Netlify deploys).
2. Someone runs `scripts/harvest_pages.py` against the website repo's
   `origin/main` and commits the refreshed `data/kb_source/pages/*.md`.
3. Someone runs `python -m pubs_rag.main ingest-pages` against production
   Postgres (embeds changed pages; new content versions land `approved=FALSE`).
4. The owner reviews `list-pending --pages` and approves each changed slug.

Stages 1–3 are deterministic toil (and each manual run has produced at least
one mechanical failure: stale checkouts, shell quoting, purged local venvs).
Stage 4 is policy — the owner's editorial control required by the Bot
Parameter Requirements — and is explicitly **kept manual** in this design.

## Trigger: extend the existing GitHub webhook (not a cron, not a watch path)

The pubs-rag Railway service already receives an HMAC-verified GitHub `push`
webhook from `Cipherion-Market-Research/ciphex-website` at `/webhook/github`
(built in WP-4, hardened in WP-7c: main-branch-only filter, secret
`PUBS_RAG_GITHUB_WEBHOOK_SECRET`, raw-content fetches authenticated with
`PUBS_RAG_GITHUB_TOKEN`). It currently reacts only to the publication/update
index pages. Every site deploy already announces itself to us — polling (cron)
would be strictly worse latency and more moving parts, and a Railway watch
path triggers *deploys*, not data jobs.

## Flow (per qualifying push event)

1. **Detect**: from the push payload's `commits[].modified/added/removed`,
   collect changed paths matching `src/*.html`. Map to slugs; intersect with
   the corpus scope (see Scope below). Empty intersection → 202, done
   (existing behavior for update-index changes is untouched and runs
   alongside).
2. **Fetch**: for each qualifying slug, GET the file at the pushed commit SHA
   via `raw.githubusercontent.com/<repo>/<sha>/src/<slug>.html` with the
   existing authenticated fetch helper (`fetch_raw`, WP-7 auth-header fix).
   Pin to the payload SHA, not `main`, to avoid races with rapid pushes.
3. **Transform**: run the same extraction used by `scripts/harvest_pages.py`.
   **Refactor prerequisite**: lift the HTML→markdown transform out of the
   script into `pubs_rag/page_harvest.py` (pure function:
   `html_text -> (title, markdown)`), so the script and the webhook share one
   implementation and one test suite. The script becomes a thin CLI over it.
4. **Ingest**: reuse `ingest.ingest_page` (sha256-keyed, idempotent): unchanged
   content is skipped; changed content supersedes the old row and lands
   `approved=FALSE` — the serving corpus keeps the previously-approved
   version until the owner acts. **No auto-approve, ever, in this design.**
5. **Notify**: log a structured `pages_pending_approval` event (slugs +
   count). Optional phase-2: push a Telegram DM to the owner via the bot
   ("2 site pages updated, pending approval: contribute, leadership-team")
   — requires a small core/adapter notification hook; keep out of the first
   build to hold scope.
6. **Removals**: a deleted/renamed page (path in `removed`) marks the page row
   `approved=FALSE` with a `removed_upstream` note (never hard-deletes) and
   logs it. The weekly sitemap-parity check (drift monitor) remains the
   authority for structural changes and will flag it independently.

## Scope rule (single source of truth)

Corpus scope = `(sitemap slugs ∪ KNOWN_NOINDEX_SLUGS) − EXCLUDED_SLUGS −
UTILITY_SLUGS`, exactly as encoded in `drift_monitor/config.py` and reused by
the harvester. The webhook must import/replicate the same constants —
**do not** re-derive scope independently. `insights-and-publications` and
`404`/`unavailable` never ingest (also enforced downstream by
`Config.PAGE_CORPUS_EXCLUDED_SLUGS` as belt-and-suspenders).

## What about the committed `data/kb_source/pages/*.md`?

Server-side ingest makes the database the serving source of truth; the
committed corpus becomes a development/test artifact (fixtures, offline work,
audit trail). Two acceptable postures — owner picks at build time:

- **A (recommended): repo refresh stays manual/periodic** via the script; the
  repo may lag the DB between refreshes. Cheap, no repo-write credentials on
  the service.
- **B: webhook also opens a corpus-refresh PR** via a GitHub App/token with
  `contents:write` on a branch. Keeps repo and DB in lockstep at the cost of
  bot-authored PRs and a write-scoped credential on a public-facing service.
  Not recommended for the first build.

## Changes by file (build checklist)

| File | Change |
|---|---|
| `pubs_rag/page_harvest.py` (new) | extraction transform lifted from the script (pure, tested) |
| `scripts/harvest_pages.py` | thin CLI over `page_harvest` (behavior unchanged) |
| `pubs_rag/webhook.py` | detect `src/*.html` changes → fetch@sha → transform → `ingest_page`; removals → unapprove+note; `pages_pending_approval` log event |
| `pubs_rag/ingest.py` | expose `ingest_page(conn, provider, slug, title, markdown, source_ref)` if not already callable per-page (today's `ingest-pages` iterates the repo corpus; the webhook needs the single-page path) |
| `pubs_rag/config.py` | webhook-pages feature flag `PUBS_RAG_WEBHOOK_PAGES_ENABLED` (default **false** — flip after shadow observation) |
| `pubs_rag/tests/` | payload-driven tests: modified/added/removed paths, out-of-scope paths, non-main pushes, sha-pinned fetch (fake server), idempotent re-delivery, supersede-preserves-served-version |
| `docs/` | this document, updated to "built" with any deviations |

## Failure modes & guarantees

- **Idempotent**: GitHub redelivers webhooks; sha256-keyed ingest makes
  replays no-ops. Handler must return 200 on processed and on no-op.
- **Partial failure**: per-page try/except — one page's fetch/parse failure
  logs and skips, never aborts the batch (mirror the existing per-doc
  behavior). OpenAI embedding failure → that page stays unigested; the next
  push (or manual `ingest-pages`) retries naturally.
- **Serving safety**: a bad harvest can only create *pending* rows; the
  approved corpus is untouched until the owner approves. Worst case of a
  parser regression = garbage sitting in quarantine, visible in
  `list-pending --pages`.
- **Race**: two rapid pushes — each processes at its own pinned sha;
  last-writer's content supersedes on ingest by `ingested_at`. Acceptable.

## Rollout plan

1. Build behind `PUBS_RAG_WEBHOOK_PAGES_ENABLED=false`; deploy dark.
2. Enable in **shadow** for ~2 weeks: handler runs fetch+transform and logs
   what it *would* ingest (`dry_run` mode) — compare against manual harvests.
3. Flip to live ingest. Owner's steady-state duty: `approve <slug> --pages`
   on notification.
4. Revisit phase-2 items only after a clean month: Telegram owner
   notification; auto-approve debate (would need its own owner ruling — this
   design takes no position beyond defaulting to NO).

## Acceptance criteria

- A push changing `src/contribute.html` on main results, within one webhook
  delivery, in a pending `contribute` page version whose markdown matches
  `scripts/harvest_pages.py` output for the same sha byte-for-byte.
- A push touching only excluded/out-of-scope paths results in no DB writes.
- Redelivered webhook: no duplicate rows.
- The approved/served corpus never changes without an `approve` command.

## Open questions for build time

1. Posture A vs B for the committed repo corpus (recommend A).
2. Owner-notification channel for pending approvals (log-only vs Telegram DM).
3. Whether `removed_upstream` pages should also be flagged to the drift
   monitor's findings stream (nice-to-have; sitemap parity covers it weekly).
