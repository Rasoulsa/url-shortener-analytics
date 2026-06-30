"""User-Agent parsing helpers.

Compatibility wrapper around Phase 3 analytics enrichment helpers.
"""

from __future__ import annotations

from app.services.analytics_enrichment import UserAgentInfo, parse_user_agent

ParsedUserAgent = UserAgentInfo

__all__ = ["ParsedUserAgent", "parse_user_agent"]
