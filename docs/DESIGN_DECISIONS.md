# Design Decisions

Trade-offs made during development.
Updated daily as new decisions are made.

---

## 1. Short-Code Generation Algorithm

### Options considered

| Approach | Throughput | Privacy | Complexity | Verdict |
|----------|-----------|---------|------------|---------|
| Counter + Base62 | Highest | ❌ Sequential = guessable | Low | Rejected |
| Pre-generated pool | Highest at request time | ✅ Unpredictable | High | Rejected |
| **Random + SETNX** | Very high | ✅ Unpredictable | Low | ✅ Chosen |

### Why Random + SETNX

**Privacy:** Counter codes are sequential. An attacker iterates
`abc0001`, `abc0002` → harvests all destination URLs.
Random codes from 62^7 ≈ 3.5T keyspace are not enumerable.

**Scalability:** No global counter → no coordination point.
Multiple API instances generate codes independently.

**Collision safety (two layers):**
1. `Redis SET key NX EX=60` — atomic reservation. Only the first
   requester for a given code succeeds. Others retry immediately.
2. `UNIQUE` on `links.short_code` — database final safety net.

**Pressure relief:** After N failed retries at length L, transparently
grow to L+1. Graceful degradation with no manual intervention.

### Trade-off accepted
Non-zero (astronomically small) collision probability vs a counter's
mathematical zero. The two-layer defense makes an actual persisted
duplicate impossible in practice.

---

## 2. Cursor (Keyset) Pagination

**Rejected:** `LIMIT 20 OFFSET 1000`
- Postgres scans and discards 1000 rows on every page request
- Slower as pages go deeper
- Page drift: new inserts shift items between page loads

**Chosen:** `WHERE id < cursor ORDER BY id DESC LIMIT 20`
- Uses primary key index directly — O(log n) at any depth
- Stable: new inserts never cause drift
- `meta.next_cursor` in envelope tells client where to continue

---

## 3. Response Envelope `{data, meta, errors}`

Established on Day 1, not added later. Reason: retrofitting an
envelope on a live API breaks all existing clients. Benefits:
- One response handler on the frontend for every endpoint
- Pagination always lives in `meta`, never mixed into `data`
- `errors` array supports multiple validation messages at once

---

## 4. Lazy Deletion for Expired Links

**Rejected:** Background cron that periodically deletes expired rows
- Extra service to deploy and monitor
- Links are effectively dead at `expires_at` anyway

**Chosen:** Check expiry on access, return 410 Gone
- Zero extra infrastructure
- Dead the instant `expires_at` passes
- Day 2 upgrade: also invalidate Redis cache on expiry detection

---

## 5. 301 vs 302 Redirect

Exposed as `is_permanent: bool` on each link.

| | 301 Permanent | 302 Temporary |
|---|---|---|
| Browser | Caches redirect | Re-requests every visit |
| Analytics | Fires once per browser | Fires on every visit |
| Use case | Stable permanent links | Campaign / tracked links |
| Default | — | ✅ (false) |

Default is `false` (302) because most use cases involve analytics
where every visit should be counted.

---

## 6. `main`-Only Branching Strategy

`develop` exists to protect `main` from broken integration between
multiple developers. This is a solo project — that problem
doesn't apply. Feature branches → PR → `main` gives:
- Always-green, always-deployable `main`
- Full PR history showing process and decisions
- No unnecessary ceremony for a solo build

---

## 7. Caching Strategy *(Day 2)*
*(to be filled)*

## 8. Rate Limiting Strategy *(Day 2)*
*(to be filled)*

## 9. Async Analytics Pipeline *(Day 3)*
*(to be filled)*
