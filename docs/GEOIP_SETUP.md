# GeoIP Setup

The analytics feature uses MaxMind's free **GeoLite2-City** database to resolve
IP addresses to country and city. This is **optional** — the service runs fully
without it. When the database is absent, `country` and `city` are stored as
NULL and every other feature works normally.

---

## Setup Steps

### 1. Register for a free MaxMind account

Sign up at https://www.maxmind.com/en/geolite2/signup

Registration is free but required. The GeoLite2 license does not permit
redistribution, which is why the database is not committed to this repository.

### 2. Download the database

From your MaxMind account dashboard, download **GeoLite2-City** in the
`.mmdb` (binary) format. You will receive a `.tar.gz` archive — extract it and
locate the `GeoLite2-City.mmdb` file inside.

```bash
# Example after downloading
tar -xzf GeoLite2-City_*.tar.gz
find . -name "GeoLite2-City.mmdb"
```

### 3. Place the file

Put `GeoLite2-City.mmdb` in the `geoip/` directory at the project root:

```text
url-shortener-analytics/
└── geoip/
    └── GeoLite2-City.mmdb
```

### 4. Restart the stack

Docker mounts the `geoip/` directory automatically (already configured in
`docker-compose.yml`):

```yaml
volumes:
  - ./geoip:/data
```

The app and worker read from `/data/GeoLite2-City.mmdb` inside the container.

```bash
docker compose up -d --build worker api
```

> The `GEOIP_DB_PATH` environment variable points at
> `/data/GeoLite2-City.mmdb` by default. Override it only if you mount the
> database at a different path.

---

## Verify It Works

After placing the file and restarting, verify GeoIP resolution inside the
worker container:

```bash
docker compose exec -T worker python - <<'PY'
from app.services.geoip import lookup_geoip
for ip in ["8.8.8.8", "81.2.69.142", "127.0.0.1"]:
    print(ip, lookup_geoip(ip))
PY
```

Expected output when the database is present:

```text
8.8.8.8     GeoIPLocation(country='United States', city=None)
81.2.69.142 GeoIPLocation(country='United Kingdom', city='London')
127.0.0.1   GeoIPLocation(country=None, city=None)
```

- `81.2.69.142` is a well-known MaxMind test IP that resolves to **London,
  United Kingdom** — the clearest confirmation that city lookup works.
- `8.8.8.8` (Google DNS) resolves to a **country only** — infrastructure and
  CDN IPs frequently have no city in GeoLite2. This is expected.
- `127.0.0.1` and private ranges (`192.168.x.x`, Docker `172.x.x.x`) never
  resolve — they are not public IPs.

### End-to-end click test

```bash
curl -i \
  -H "X-Forwarded-For: 81.2.69.142" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36" \
  -H "Referer: https://google.com" \
  http://localhost:8001/YOUR_SHORT_CODE

docker compose exec db psql -U postgres -d urlshort -c \
"SELECT ip_anonymized, country, city, browser, os, device_type
 FROM clicks ORDER BY clicked_at DESC LIMIT 1;"
```

Expected:

```text
ip_anonymized | country        | city   | browser | os      | device_type
81.2.69.0     | United Kingdom | London | Chrome  | Windows | desktop
```

Note that the **stored** IP is anonymized (`81.2.69.0`) even though the
**lookup** used the full IP (`81.2.69.142`) — see [Privacy](#privacy) below.

> **Dashboard:** Country data populated here flows directly into the
> geographic breakdown table on `/dashboard`. If GeoIP is absent, the country
> column in the dashboard table will be empty or show NULL — all other
> dashboard views (timeseries, referrers, browsers, comparison chart) are
> unaffected.

---

## Without the File

The app and worker start and run normally. On the first lookup attempt the
worker logs a warning once and continues:

```text
WARNING: GeoIP database not found at /data/GeoLite2-City.mmdb
         country/city will be NULL. See docs/GEOIP_SETUP.md
```

Clicks are still recorded — only `country` and `city` are NULL. All other
enrichment (browser, OS, device type, referrer, anonymized IP) works
unchanged.

The `geoip2` Python package is also optional at runtime: if it is missing,
GeoIP lookup fails open in exactly the same way (NULL country/city).

---

## Privacy

GeoIP uses the **raw IP for lookup accuracy**, then stores only the
**anonymized IP**:

```python
geoip_info    = lookup_geoip(ip_address)   # raw IP → accurate country/city
ip_anonymized = anonymize_ip(ip_address)   # 8.8.8.8 → 8.8.8.0 (stored)
```

Anonymization rules:

- **IPv4:** last octet zeroed — `203.0.113.45` → `203.0.113.0`
- **IPv6:** truncated to the first 4 groups

The raw IP exists only transiently in worker memory during enrichment. It is
**never** persisted to PostgreSQL, Redis, or logs. Only the anonymized form is
stored.

Looking up on the raw IP matters: if we anonymized *before* lookup, city-level
accuracy would drop sharply because the zeroed octet removes subnet precision.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| All lookups return `country=None` | Database file missing | Confirm `geoip/GeoLite2-City.mmdb` exists, then restart worker |
| Warning about missing DB in logs | File not mounted | Check `./geoip:/data` volume in `docker-compose.yml` |
| Country populates but city is always empty | Testing with infra/CDN IPs | Use a residential test IP like `81.2.69.142` |
| `GeoIPLocation(country=None...)` for `127.0.0.1` | Private/local IP | Expected — local IPs are not in GeoIP data |
| File exists but still NULL | Wrong path | Verify `GEOIP_DB_PATH=/data/GeoLite2-City.mmdb` |
| `geoip2` import error | Package not installed | Run `uv sync --all-extras` |

---

## License

GeoLite2 is subject to MaxMind's license and **cannot be redistributed**.

The database is excluded from version control via `.gitignore`:

```gitignore
geoip/*.mmdb
```

Each developer or deployment must download their own copy from MaxMind.
MaxMind also releases updated databases regularly — refresh the file
periodically for the best accuracy.
