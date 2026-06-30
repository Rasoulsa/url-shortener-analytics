from __future__ import annotations

import ipaddress


def anonymize_ip(ip: str | None) -> str | None:
    """
    Anonymize IP before storage.

    IPv4:
        203.0.113.45 -> 203.0.113.0

    IPv6:
        Store /64 network address.
    """
    if not ip:
        return None

    raw_ip = ip.strip()

    if not raw_ip:
        return None

    try:
        parsed = ipaddress.ip_address(raw_ip)
    except ValueError:
        return None

    if isinstance(parsed, ipaddress.IPv4Address):
        parts = raw_ip.split(".")
        if len(parts) != 4:
            return None
        parts[-1] = "0"
        return ".".join(parts)

    if isinstance(parsed, ipaddress.IPv6Address):
        network = ipaddress.ip_network(f"{parsed}/64", strict=False)
        return str(network.network_address)

    return None
