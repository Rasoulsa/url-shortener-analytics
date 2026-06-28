# GeoIP Setup

The analytics feature uses MaxMind's free GeoLite2-City database
to resolve IPs to country and city. This is **optional** — the
service runs fully without it (country/city will be NULL).

## Setup Steps

1. Register free at https://www.maxmind.com/en/geolite2/signup

2. Download `GeoLite2-City.mmdb` from your account dashboard

3. Place the file here:
\`\`\`
url-shortener-analytics/
└── geoip/
    └── GeoLite2-City.mmdb
\`\`\`

4. Docker mounts it automatically (already in `docker-compose.yml`):
\`\`\`yaml
volumes:
  - ./geoip:/data
\`\`\`
The app reads from `/data/GeoLite2-City.mmdb` inside the container.

## Without the File

App starts and runs normally. On first lookup attempt the worker logs:
\`\`\`
WARNING: GeoIP database not found at /data/GeoLite2-City.mmdb
         country/city will be NULL. See docs/GEOIP_SETUP.md
\`\`\`
All other features work normally.

## Privacy

IPs are **anonymized before storage:**
- IPv4: last octet zeroed (`203.0.113.45` → `203.0.113.0`)
- IPv6: truncated to first 4 groups

Raw IP is never persisted.

## License

GeoLite2 is subject to MaxMind's license and cannot be redistributed.
The `geoip/` directory is excluded via `.gitignore`.
