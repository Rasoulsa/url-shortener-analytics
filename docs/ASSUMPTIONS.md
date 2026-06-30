# Assumptions, Limitations & Additional Considerations

## Assumptions

- **Auth scope:** API-key authentication is sufficient for this evaluation.
  Production would add JWT refresh tokens and OAuth2 providers.

- **Single region:** Designed for single-region deployment. Multi-region would require distributed cache strategy and DB replication.

- **PostgreSQL source of truth:** PostgreSQL is the authoritative storage layer for users, links, ownership, custom aliases, expiration, and password protection.

- **Redis performance layer:** Redis is treated as a performance and coordination layer, not the source of truth. Redis can be cleared or restarted without corrupting authoritative link/user data.

- **Redis cache fallback:** If the Redis metadata cache is unavailable, redirects should fall back to PostgreSQL lookup.

- **Redis counter fallback:** If the Redis click counter is unavailable, the system should fall back to PostgreSQL click increment.

- **Rate limiter availability:** If Redis rate limiting is unavailable, the system fails open and allows requests to preserve availability.

- **Celery availability:** If the Celery broker or worker is unavailable, redirects should still succeed. Analytics tasks may be delayed or skipped, but redirect correctness must not depend on Celery.

- **Analytics consistency:** Analytics processing is eventually consistent. Redirect latency should not depend on analytics enrichment, GeoIP lookup, user-agent parsing, or future webhook processing.

- **GeoIP optional:** System works fully without the MaxMind database. Country/city fields will be NULL. See `GEOIP_SETUP.md`.

- **IP privacy:** IPv4 last octet zeroed before storage (`203.0.113.45 → 203.0.113.0`). Common GDPR-friendly approach.

- **Custom alias safety:** Checked in DB + reserved via `SETNX`. In extreme race conditions, PostgreSQL `UNIQUE` constraint is the final safety net.

## Day 2 Infrastructure Assumptions

- PostgreSQL is the source of truth for users and links.
- Redis is treated as a performance and coordination layer.
- Redis DB 0 is used for API cache, click counters, rate-limit keys, and analytics counters.
- Redis DB 1 is used as the Celery broker.
- Redis DB 2 is used as the Celery result backend.
- If Redis cache is unavailable, redirects should fall back to PostgreSQL.
- If Redis click counters are unavailable, click increments should fall back to PostgreSQL.
- If Redis rate limiting is unavailable, the system fails open to preserve availability.
- If Celery broker or worker is unavailable, redirects should still succeed.
- Analytics processing is eventually consistent.

## Limitations

| Limitation | Reason | Future Fix |
|------------|---------|------------|
| clicks table not partitioned | Out of scope | RANGE partition by clicked_at monthly |
| No JWT / OAuth | Scope | Add refresh tokens + OAuth providers |
| No email verification | Scope | Add verification + confirmation flow |
| Redis counters not durably flushed yet | Day 2 scope | Add periodic Celery flush to PostgreSQL |
| Analytics enrichment is minimal | Day 2 scope | Add GeoIP, UA parsing, and time-series aggregation |
| No soft delete | Scope | Add deleted_at tombstone column |
| Single region | Scope | Redis Cluster + read replicas |

## Additional Considerations

### Scaling the Click Counter

Redis `INCR` is used as a fast write-through counter to reduce PostgreSQL write pressure during redirects.

The redirect path should prefer Redis for click increments. If Redis is unavailable, PostgreSQL is used as a fallback so the request can still be counted.

**Future improvement:**

- Periodic Celery job flushes Redis counters into PostgreSQL.
- PostgreSQL stores durable aggregate counts.
- Redirect path remains fast and avoids synchronous database writes where possible.

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

Free but requires registration. Cannot be redistributed.

`geoip/` is `.gitignored`.

Instructions are provided in `docs/GEOIP_SETUP.md`.
