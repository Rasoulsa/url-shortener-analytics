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
| `clicks` table not partitioned | Out of scope for Phase 3 | `RANGE` partition by `clicked_at` monthly |
| GeoIP city missing for some IPs | MaxMind data coverage | No fix — infrastructure IPs are expected to lack city data |
| Webhooks on click thresholds not implemented | Future work | Fire on `links.click_count` threshold crossing |
| Analytics dashboard not implemented | Phase 4 | Chart.js UI over stats API |
| No JWT / OAuth | Scope | Add refresh tokens + OAuth2 providers |
| No email verification | Scope | Add verification + confirmation flow |
| No soft delete | Scope | Add `deleted_at` tombstone column |
| Single region | Scope | Redis Cluster + read replicas |

## Failure Behavior

```text
┌────────────────────────────────────┬──────────────────────────────────────────────┐
│ Failure                            │ Behavior                                     │
├────────────────────────────────────┼──────────────────────────────────────────────┤
│ Redis metadata cache unavailable   │ Fall back to PostgreSQL lookup               │
├────────────────────────────────────┼──────────────────────────────────────────────┤
│ Redis click counter unavailable    │ Fall back to PostgreSQL click increment      │
├────────────────────────────────────┼──────────────────────────────────────────────┤
│ Redis rate limiter unavailable     │ Fail open and allow request                  │
├────────────────────────────────────┼──────────────────────────────────────────────┤
│ Celery broker unavailable          │ Log warning; redirect still succeeds         │
├────────────────────────────────────┼──────────────────────────────────────────────┤
│ Celery worker unavailable          │ Tasks may queue; redirect still succeeds     │
├────────────────────────────────────┼──────────────────────────────────────────────┤
│ GeoIP database missing             │ Click stored with country/city = NULL        │
├────────────────────────────────────┼──────────────────────────────────────────────┤
│ PostgreSQL unavailable             │ API management and cache misses fail normally│
└────────────────────────────────────┴──────────────────────────────────────────────┘
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

### Bloom Filter (Future)

A Bloom filter in Redis could pre-check code existence before the full cache lookup, reducing misses for invalid/bot codes. Not implemented—overkill for evaluation scale, worth noting for production.

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
