from __future__ import annotations

from dataclasses import dataclass

from user_agents import parse


@dataclass(frozen=True)
class ParsedUserAgent:
    browser: str | None
    os: str | None
    device_type: str


def parse_user_agent(user_agent: str | None) -> ParsedUserAgent:
    if not user_agent:
        return ParsedUserAgent(
            browser=None,
            os=None,
            device_type="other",
        )

    parsed = parse(user_agent)

    browser = parsed.browser.family or None
    os_name = parsed.os.family or None

    if parsed.is_bot:
        device_type = "bot"
    elif parsed.is_tablet:
        device_type = "tablet"
    elif parsed.is_mobile:
        device_type = "mobile"
    elif parsed.is_pc:
        device_type = "desktop"
    else:
        device_type = "other"

    return ParsedUserAgent(
        browser=browser,
        os=os_name,
        device_type=device_type,
    )
