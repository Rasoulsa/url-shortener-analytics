"""Privacy helpers.

Compatibility wrapper around Phase 3 analytics enrichment helpers.
"""

from __future__ import annotations

from app.services.analytics_enrichment import anonymize_ip

__all__ = ["anonymize_ip"]
