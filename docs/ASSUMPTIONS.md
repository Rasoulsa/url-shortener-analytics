# Assumptions, Limitations & Additional Considerations

## Assumptions

- **Auth scope:** API-key authentication is sufficient for this evaluation.
  Production would add JWT refresh tokens and OAuth2 providers.

- **Single region:** Designed for single-region deployment. Multi-region
  would require distributed cache strategy and DB replication.

- **GeoIP optional:** System works fully without the MaxMind database.
  Country/city fields will be NULL. See [GEOIP_SETUP.md](GEOIP_SETUP.md).

- **IP privacy:** IPv4 last octet zeroed before storage
  (`203.0.113.45` → `203.0.113.0`). Common GDPR-friendly approach.

- **Analytics lag:** ≤30 seconds by design. Celery flushes Redis counters
  to Postgres every 30s. Redirect path is never blocked by a DB write.

- **Custom alias safety:** Checked in DB + reserved via SETNX. In extreme
  race conditions, Postgres UNIQUE constraint is the final safety net.

## Limitations

| Limitation | Reason | Future fix |
|------------|--------|------------|
| `clicks` table not partitioned | Out of scope | RANGE partition by `clicked_at` monthly |
| No JWT / OAuth | Scope | Add refresh tokens + OAuth providers |
| No email verification | Scope | Add verification + confirmation flow |
| Sync click count (Day 1) | Upgraded Day 2/3 | Already planned |
| No soft delete | Scope | Add `deleted_at` tombstone column |
| Single region | Scope | Redis Cluster + read replicas |

## Additional Considerations

### Scaling the click counter
Redis `INCR` as write-through buffer (Day 2) + periodic Celery flush
to Postgres (Day 3). The redirect path only touches Redis — Postgres
is never in the critical path of a redirect request.

### Bloom filter (future)
A Bloom filter in Redis could pre-check code existence before the full
cache lookup, reducing misses for invalid/bot codes. Not implemented —
overkill for evaluation scale, worth noting for production.

### Click table partitioning (future)
\`\`\`sql
-- Future production migration example:
CREATE TABLE clicks_2026_06 PARTITION OF clicks
  FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
\`\`\`
Monthly RANGE partitions allow old data to be archived or dropped
without affecting query performance on recent data.

### MaxMind GeoLite2 license
Free but requires registration. Cannot be redistributed.
`geoip/` is `.gitignore`d. Instructions in `docs/GEOIP_SETUP.md`.
