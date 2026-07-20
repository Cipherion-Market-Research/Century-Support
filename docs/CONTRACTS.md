# Century Platform — Integration Contracts v1.0 (FROZEN 2026-07-20)

These four contracts are the only coordination points between work packages
(see the audit report, §7, and `docs/BUILD_HANDOFF.md`). They are frozen.
Any agent needing a change raises it to the project owner in the audit
thread — never edits this file unilaterally. Changes land as a version bump
by owner PR only.

---

## C1 — Message envelope (adapter → core)

Every channel adapter translates an inbound platform event into exactly this
shape and POSTs it to `POST /v1/messages` on Century Core.

```json
{
  "channel": "telegram | discord | slack | x",
  "channel_msg_id": "string — platform-native message id",
  "user_ref": "string — stable per-channel user id (platform id; never a username)",
  "chat_ref": "string — group/guild-channel/workspace-channel/DM id",
  "thread_ref": "string | null — platform thread/topic id if threaded",
  "text": "string — raw user text with the bot mention left in place",
  "command": { "name": "price", "args": "string" },
  "is_dm": true,
  "mentioned": true,
  "locale": "string | null — BCP-47 if the platform provides it",
  "ts": "ISO-8601 UTC"
}
```

Rules:
- `command` is non-null only when the platform natively parsed a command
  (Telegram `/cmd`, Discord slash command, Slack slash command). Core also
  detects command-like text itself; adapters do not.
- `user_ref` is channel-scoped. There is NO cross-channel identity linking.
- Adapters never call the LLM, never format facts, never answer locally.

## C2 — Response IR (core → adapter)

Core replies with ordered blocks. Renderers translate blocks per channel;
they never add, reorder, or invent content.

```json
{
  "blocks": [
    { "type": "heading",   "text": "string" },
    { "type": "paragraph", "md": "portable-markdown" },
    { "type": "fact",      "label": "string", "value": "string",
      "source": "url", "as_of": "ISO-8601" },
    { "type": "links",     "items": [ { "label": "string", "url": "url" } ] },
    { "type": "warning",   "md": "portable-markdown" },
    { "type": "buttons",   "items": [ { "label": "string", "url": "url" } ] }
  ],
  "meta": {
    "answer_kind": "command | faq | rag | llm | refusal",
    "facts_used": [ "facts.tokenomics.fy2026_fd_supply" ],
    "kpis_used": [ "kpi:claim_api:price" ]
  }
}
```

Portable-markdown subset: `**bold**`, `*italic*`, `` `code` ``,
`[label](url)`. No tables, images, headings-in-md, or raw HTML.

Renderer rules (summary — full matrix lives with each adapter):
- Telegram: MarkdownV2 with escaping; split at 4,096 chars on block
  boundaries; `buttons` → inline keyboard.
- Discord: `heading` → embed title, `fact` → embed field, `warning` → its
  own embed; split at 2,000/4,096 limits; `buttons` → link buttons.
- Slack: Block Kit — `heading` → header block, `paragraph`/`warning` →
  section mrkdwn, `fact` → fields, `links`/`buttons` → actions/context.
- X (restricted mode): plaintext ≤ 280 chars from the first heading +
  paragraph + first link only. `fact` blocks require as_of inline.

Hard rule: a `fact` block's value/source/as_of come from the stores
verbatim. Renderers must render `as_of` visibly wherever a fact appears.

## C3 — KPI envelope (sync service → Redis → core)

Key convention: `kpi:<source>:<metric>`
Sources: `claim_api`, `ams_marketing`, `ams_keymetrics`, `abacus_index`,
`onchain_base`, `onchain_eth`.

Value (JSON string):

```json
{
  "value": "any JSON scalar or object",
  "unit": "string | null",
  "source": "url of the upstream feed",
  "as_of": "ISO-8601 | null — upstream's own timestamp when it provides one",
  "fetched_at": "ISO-8601 UTC — when the poller fetched it",
  "ttl_s": 3600,
  "stale_after_s": 1800
}
```

Rules:
- Consumers treat `now - fetched_at > stale_after_s` as STALE: the bot says
  the feed is stale instead of quoting the last value. Pollers keep the key
  alive past staleness (ttl_s > stale_after_s) so consumers can distinguish
  "stale" from "never existed".
- Each poller also writes `kpi:<source>:__health` =
  `{ "ok": bool, "last_success": ISO-8601, "consecutive_failures": int }`
  (consumed by WP-7 alerting).
- Rate limits are the poller's job: ≤10 req/min against `ams.ciphex.io`.

## C4 — facts.yaml schema (canonical facts store)

```yaml
version: 1
facts:
  <category>.<key>:            # categories: identity | contracts |
    value: <scalar|list|map>   #   round-terms | tokenomics | products |
    verified_on: YYYY-MM-DD    #   links | legal
    source_url: <url>
    notes: <string, optional>
```

Rules:
- `value: unknown` is a legal and REQUIRED sentinel for anything not
  verified (e.g. support@ routing — OQ-1). Never guess identity facts.
- Every fact has `source_url` + `verified_on`. No fact without provenance.
- The file changes only by PR reviewed by the project owner. The WP-7 drift
  checker proposes changes; it never mutates this file.
- Core's rule of use: numeric and identity answers come only from facts or
  C3 KPIs. A key that is absent or `unknown` → core answers "I don't know"
  plus the official link.

---

## Open questions (owner to answer; agents treat as `unknown` meanwhile)

- OQ-1  Does support@ciphex.io still route? (site publishes only hello@ /
        partnerships@)
- OQ-2  Canonical Alpha domain: ams.ciphex.io vs alpha.ciphex.io
- OQ-3  Is the Uniswap DEX listing live? (dashboard listing block is
        labeled sample data in source)
- OQ-4  Stable subdomain in front of the Abacus Indexer ALB
        (e.g. index.ciphex.io) — WP-3 must keep the base URL configurable
