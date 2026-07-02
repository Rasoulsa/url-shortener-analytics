# Assumptions, Limitations & Additional Considerations

## Assumptions

- **Auth scope:** API-key authentication is sufficient for this evaluation.
  Production would add JWT refresh tokens and OAuth2 providers.

- **Single region:** Designed for single-region deployment. Multi-region would require distributed cache strategy and DB replication.

- **PostgreSQL source of truth:** PostgreSQL is the authoritative storage layer
  for users, links, ownership, custom aliases, expiration, password protection,
  and durable click events.

- **Redis performance layer:** Redis is treated as a performance and
  coordination layer, not the source of truth. Redis can be cleared or
  restarted without corrupting authoritative link, user, or click data.

- **Redis cache fallback:** If the Redis metadata cache is unavailable, redirects should fall back to PostgreSQL lookup.

- **Redis counter fallback:** If the Redis click counter is unavailable, the system should fall back to PostgreSQL click increment.

- **Rate limiter availability:** If Redis rate limiting is unavailable, the system fails open and allows requests to preserve availability.

- **Celery availability:** If the Celery broker or worker is unavailable, redirects should still succeed. Analytics tasks may be delayed or skipped, but redirect correctness must not depend on Celery.

- **Analytics consistency:** Analytics processing is eventually consistent.
  Redirect latency does not depend on analytics enrichment, GeoIP lookup,
  User-Agent parsing, or webhook processing. Counter flushes to PostgreSQL
  happen every ~30 seconds via Celery Beat.

- **GeoIP optional:** System works fully without the MaxMind database.
  `country`/`city` fields will be NULL. GeoIP lookup fails open — missing
  database, missing package, or invalid IPs all return empty values.
  See [GEOIP_SETUP.md](GEOIP_SETUP.md).

- **GeoIP lookup uses raw IP:** The raw client IP is used for GeoIP lookup
  accuracy. Only the anonymized IP is persisted. The raw IP is never written
  to PostgreSQL or Redis.

- **IP privacy:** IPv4 last octet zeroed before storage (`203.0.113.45 → 203.0.113.0`). Common GDPR-friendly approach.

- **Custom alias safety:** Checked in DB + reserved via `SETNX`. In extreme race conditions, PostgreSQL `UNIQUE` constraint is the final safety net.

- **Click counter flush safety:** The flush task uses Redis `GETDEL` so
  successful flushes never double-count. If the database update fails after
  `GETDEL`, the counter value is restored and the task retries with
  exponential backoff.

- **Webhook delivery is async:** Webhook delivery never blocks redirects.
  If the receiver is slow or unavailable, Celery retries with backoff.
  The redirect path only performs `INCR`; threshold detection and delivery
  happen in the background flush and worker.

- **Webhook fires at most once per link:** The `webhook_fired` flag is set
  inside the flush transaction before enqueueing delivery. This guarantees a
  single threshold event per link regardless of flush overlap or task retries.
  Resetting a webhook requires explicitly clearing `webhook_fired` and
  setting a new threshold.

- **Webhook receiver must verify HMAC:** The service signs webhook payloads
  with HMAC SHA-256 (`X-Webhook-Signature: sha256=<hex>`). Receivers are
  responsible for verifying the signature before trusting the payload.

- **Dashboard reuses Phase 3 analytics API:** The `/dashboard` UI consumes
  the existing `timeseries` and `breakdown` endpoints. No separate analytics
  store is required for the dashboard.

- **Country table is sufficient for geographic breakdown:** A map
  visualization is not required per the project specification. The dashboard
  uses a sortable country table.

- **Multi-link comparison is zero-filled:** The comparison endpoint
  zero-fills missing days so all series share the same date labels. Missing
  days reflect zero clicks, not missing data.

## Infrastructure Assumptions

- PostgreSQL is the source of truth for users, links, and click events.
- Redis DB 0 is used for API cache, click counters, rate-limit keys, and analytics counters.
- Redis DB 1 is used as the Celery broker.
- Redis DB 2 is used as the Celery result backend.
- If Redis cache is unavailable, redirects fall back to PostgreSQL.
- If Redis click counters are unavailable, click increments fall back to PostgreSQL.
- If Redis rate limiting is unavailable, the system fails open to preserve availability.
- If the Celery broker or worker is unavailable, redirects still succeed.
- Analytics processing is eventually consistent.
- GeoIP city coverage depends on MaxMind data quality. Infrastructure and CDN
  IPs (e.g. `8.8.8.8`, `1.1.1.1`) often return country only with no city.
  This is a data coverage limitation, not a bug.

## Limitations

| Limitation | Reason | Future Fix |
|---|---|---|
| `clicks` table not partitioned | Out of scope for evaluation | `RANGE` partition by `clicked_at` monthly |
| GeoIP city missing for some IPs | MaxMind data coverage | No fix — infrastructure IPs are expected to lack city data |
| Single webhook threshold per link | Phase 4 scope | Multiple thresholds or repeatable events via event log |
| Dashboard uses country table, not map | Sufficient per requirements | Add map library if visual geographic breakdown is needed |
| No JWT / OAuth | Scope | Add refresh tokens + OAuth2 providers |
| No email verification | Scope | Add verification + confirmation flow |
| No soft delete | Scope | Add `deleted_at` tombstone column |
| Single region | Scope | Redis Cluster + read replicas |
| Test coverage tuning deferred | Time constraint | Continue as a maintenance branch |

## Failure Behavior

```text
┌────────────────────────────────────┬───────────────────────────────────────────----───┐
│ Failure                            │ Behavior                                         │
├────────────────────────────────────┼──────────────────────────────────────────----────┤
│ Redis metadata cache unavailable   │ Fall back to PostgreSQL lookup                   │
├────────────────────────────────────┼──────────────────────────────────────────----────┤
│ Redis click counter unavailable    │ Fall back to PostgreSQL click increment          │
├────────────────────────────────────┼──────────────────────────────────────────----────┤
│ Redis rate limiter unavailable     │ Fail open and allow request                      │
├────────────────────────────────────┼───────────────────────────────────────────----───┤
│ Celery broker unavailable          │ Log warning; redirect still succeeds             │
├────────────────────────────────────┼───────────────────────────────────────────----───┤
│ Celery worker unavailable          │ Tasks may queue; redirect still succeeds         │
├────────────────────────────────────┼──────────────────────────────────────────----────┤
│ GeoIP database missing             │ Click stored with country/city = NULL            │
├────────────────────────────────────┼────────────────────────────────────────────----──┤
│ Webhook receiver slow / down       │ Celery retries with backoff; redirect unaffected │
├────────────────────────────────────┼───────────────────────────────────────────----───┤
│ Webhook permanently failing        │ Logged; webhook_fired stays true (no spam)       │
├────────────────────────────────────┼────────────────────────────────────────────----──┤
│ PostgreSQL unavailable             │ API management and cache misses fail normally    │
└────────────────────────────────────┴───────────────────────────────────────────----───┘
```

## Additional Considerations

### Scaling the Click Counter

Redis `INCR` is used as a fast write-through counter to reduce PostgreSQL write pressure during redirects.

The redirect path should prefer Redis for click increments. If Redis is unavailable, PostgreSQL is used as a fallback so the request can still be counted.

Phase 3 completes the flush loop:

- Redirect path: `INCR link:{short_code}:clicks` in Redis
- Celery Beat (~30s): `GETDEL` counter → `UPDATE links SET click_count = click_count + N`
- `GETDEL` is atomic — successful flushes never double-count
- On DB failure: counter value is restored and task retries (max 3, exponential backoff)

### Analytics Pipeline

Phase 3 adds full click enrichment via an async Celery task:

1. Redirect enqueues `analytics.process_click_event` immediately and returns
2. Worker parses User-Agent → `browser`, `os`, `device_type`
3. Worker performs GeoIP lookup on the ***raw IP*** → `country`, `city`
4. Worker anonymizes IP → `ip_anonymized` (last octet zeroed)
5. Worker inserts one enriched `clicks` row in PostgreSQL
6. Worker updates lightweight Redis analytics counters

The raw IP is used only during step 3 for lookup accuracy and is never
persisted anywhere.


### Cache-Aside Metadata

Link metadata is cached in Redis using the cache-aside pattern.

PostgreSQL remains authoritative. Redis only stores redirect-required metadata such as:

- `short_code`
- `long_url`
- `expires_at`
- `is_permanent`
- `password_hash`

If metadata is missing from Redis, the API loads it from PostgreSQL and then stores it back in Redis with a TTL.

### Rate Limiting Failure Mode

Rate limiting depends on Redis sorted sets and Lua scripts.

If Redis is unavailable, the limiter fails open instead of blocking all traffic. This is intentional because availability is more important than strict abuse protection during a Redis outage.

### Celery Failure Mode

Celery is used for non-blocking analytics processing.

Redirects should not fail just because:

- The Celery broker is temporarily unavailable
- The Celery worker is unhealthy
- Analytics enrichment is delayed
- The result backend is unavailable

The redirect response should still succeed after the link is resolved.

### Webhooks

Phase 4 adds click-threshold webhook support built on top of the Phase 3
analytics flush pipeline.

Key assumptions carried through implementation:

- Threshold detection runs inside `analytics.flush_click_counters`, which
  owns the authoritative `click_count` update after `GETDEL`.
- The `webhook_fired` flag is set before the delivery task is enqueued,
  inside the same flush operation that detects the crossing. This gives a
  single-flight guarantee even when multiple flush runs overlap.
- Delivery is a separate Celery task with retry/backoff so slow or failing
  receivers are isolated from analytics processing.
- Payloads are signed with HMAC SHA-256 so receivers can verify authenticity.
- A webhook event fires once per link per threshold configuration. More
  complex behaviors (repeatable events, multiple thresholds, event logs)
  are deferred as future work.

### Dashboard

The analytics dashboard at `/dashboard` is built with Jinja2 and Chart.js
and consumes the Phase 3 stats API.

Key assumptions:

- Aggregation stays in the backend. The dashboard UI is thin and fetches
  pre-aggregated data from the API.
- The multi-link comparison endpoint zero-fills missing days so all series
  align on the same labels regardless of when each link was created.
- A country **table** is used for geographic breakdown. No external map
  library or API key is required.
- GeoIP data quality limitations (city missing for CDN/infra IPs) also
  affect the country table. This is expected and documented.

Production website: `www.matinrayaneharyan.ir`

### Click Table Partitioning (Future)

```sql
-- Future production migration example:
CREATE TABLE clicks_2026_06 PARTITION OF clicks
  FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
```

Monthly RANGE partitions allow old data to be archived or dropped without affecting query performance on recent data.

### MaxMind GeoLite2 License

Free but requires registration at `maxmind.com`. Cannot be redistributed.

`geoip/*.mmdb` is `.gitignored`.

Full setup instructions → [GEOIP_SETUP.md](GEOIP_SETUP.md)
