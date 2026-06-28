"""
Short-code generation service.

Algorithm chosen: Random Base62 + Redis SETNX collision-retry.

Trade-off table (full rationale in docs/DESIGN_DECISIONS.md):

┌──────────────────────┬───────────┬──────────────────┬───────────┐
│ Approach             │ Speed     │ Privacy          │ Verdict   │
├──────────────────────┼───────────┼──────────────────┼───────────┤
│ Counter + Base62     │ Fastest   │ Sequential=guessable│ ❌      │
│ Pre-generated pool   │ Fastest   │ Unpredictable    │ ❌ complex│
│ Random + SETNX retry │ Very fast │ Unpredictable    │ ✅ chosen │
└──────────────────────┴───────────┴──────────────────┴───────────┘

Why Random + SETNX:
  1. Unpredictable codes — not enumerable (privacy + security)
  2. No global counter — no coordination point, horizontally scalable
  3. 62^7 ≈ 3.5 trillion keyspace — collisions are extremely rare
  4. SETNX atomically reserves the code before DB insert
     → eliminates check-then-insert race conditions
  5. DB UNIQUE constraint is the final safety net
  6. Keyspace pressure: grow length transparently after max_tries
"""

import secrets

from app.core.config import settings
from app.core.redis_client import redis_client

# Base62: digits + lowercase + uppercase (URL-safe, no special chars)
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

_RESERVE_KEY = "code_reserved:{code}"
_RESERVE_TTL = 60  # seconds — abandon reservation if DB insert doesn't follow


def _random_code(length: int) -> str:
    """Generate a cryptographically random Base62 string."""
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


async def reserve_code(code: str) -> bool:
    """
    Atomically reserve a code in Redis using SET NX.
    Returns True if reservation succeeded (we own this code).
    Returns False if already reserved (collision — caller should retry).
    """
    key = _RESERVE_KEY.format(code=code)
    return bool(await redis_client.set(key, "1", nx=True, ex=_RESERVE_TTL))


async def generate_unique_code(
    length: int | None = None,
    max_tries: int = 5,
) -> str:
    """
    Generate a unique short code.

    1. Generate random Base62 code.
    2. Atomically reserve via SETNX.
    3. On collision retry up to max_tries.
    4. On exhaustion grow length by 1 and retry recursively.
    """
    length = length or settings.short_code_length

    for _ in range(max_tries):
        code = _random_code(length)
        if await reserve_code(code):
            return code

    # Keyspace pressure — widen length and retry
    return await generate_unique_code(length + 1, max_tries)


def encode_base62(number: int) -> str:
    """
    Encode a non-negative integer to Base62 string.
    Demonstrates the counter-based alternative algorithm.
    """
    if number < 0:
        raise ValueError("Number must be non-negative")
    if number == 0:
        return ALPHABET[0]

    base = len(ALPHABET)
    digits: list[str] = []
    while number:
        number, remainder = divmod(number, base)
        digits.append(ALPHABET[remainder])
    return "".join(reversed(digits))


def decode_base62(code: str) -> int:
    """Decode a Base62 string back to an integer."""
    base = len(ALPHABET)
    result = 0
    for char in code:
        result = result * base + ALPHABET.index(char)
    return result
