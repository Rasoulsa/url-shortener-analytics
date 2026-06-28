"""
Tests for app/services/shortener.py

Coverage:
  - ALPHABET charset and uniqueness
  - _random_code: length contract, only valid chars, randomness
  - reserve_code: SETNX True on first call, False on collision, key format, TTL
  - generate_unique_code: happy path, collision retry, length growth, default length
  - encode_base62: known values, zero, negative raises ValueError
  - decode_base62: known values
  - encode/decode roundtrip: parametrized
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.shortener import (
    ALPHABET,
    _random_code,
    decode_base62,
    encode_base62,
    generate_unique_code,
    reserve_code,
)

# ── ALPHABET ──────────────────────────────────────────────────────────────────


class TestAlphabet:
    def test_length_is_62(self) -> None:
        assert len(ALPHABET) == 62

    def test_all_chars_unique(self) -> None:
        assert len(set(ALPHABET)) == 62

    def test_contains_digits(self) -> None:
        assert all(c in ALPHABET for c in "0123456789")

    def test_contains_lowercase(self) -> None:
        assert all(c in ALPHABET for c in "abcdefghijklmnopqrstuvwxyz")

    def test_contains_uppercase(self) -> None:
        assert all(c in ALPHABET for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    def test_no_special_characters(self) -> None:
        """Codes must be URL-safe — no special characters allowed."""
        special = set("!@#$%^&*()-_=+[]{}|;:',.<>?/`~")
        assert not special.intersection(set(ALPHABET))


# ── _random_code ──────────────────────────────────────────────────────────────


class TestRandomCode:
    def test_correct_length(self) -> None:
        assert len(_random_code(7)) == 7

    def test_custom_lengths(self) -> None:
        for length in [1, 5, 10, 20]:
            assert len(_random_code(length)) == length

    def test_only_alphabet_chars(self) -> None:
        alphabet_set = set(ALPHABET)
        for _ in range(50):
            assert all(c in alphabet_set for c in _random_code(7))

    def test_randomness(self) -> None:
        """
        62^7 ≈ 3.5 trillion keyspace.
        100 independent draws should never collide.
        """
        codes = {_random_code(7) for _ in range(100)}
        assert len(codes) == 100


# ── reserve_code ──────────────────────────────────────────────────────────────


class TestReserveCode:
    async def test_returns_true_on_first_reservation(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True

        with patch("app.services.shortener.redis_client", mock_redis):
            result = await reserve_code("abc1234")

        assert result is True

    async def test_returns_false_on_collision(self) -> None:
        """Redis returns None when SETNX fails (key already exists)."""
        mock_redis = AsyncMock()
        mock_redis.set.return_value = None

        with patch("app.services.shortener.redis_client", mock_redis):
            result = await reserve_code("abc1234")

        assert result is False

    async def test_redis_called_with_correct_key(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True

        with patch("app.services.shortener.redis_client", mock_redis):
            await reserve_code("XyZ9999")

        mock_redis.set.assert_called_once_with(
            "code_reserved:XyZ9999",
            "1",
            nx=True,
            ex=60,
        )

    async def test_ttl_is_60_seconds(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True

        with patch("app.services.shortener.redis_client", mock_redis):
            await reserve_code("anything")

        _, kwargs = mock_redis.set.call_args
        assert kwargs["ex"] == 60

    async def test_nx_flag_is_set(self) -> None:
        """NX flag must be True — guarantees atomic SETNX behaviour."""
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True

        with patch("app.services.shortener.redis_client", mock_redis):
            await reserve_code("anything")

        _, kwargs = mock_redis.set.call_args
        assert kwargs["nx"] is True


# ── generate_unique_code ──────────────────────────────────────────────────────


class TestGenerateUniqueCode:
    async def test_happy_path_returns_correct_length(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True

        with patch("app.services.shortener.redis_client", mock_redis):
            code = await generate_unique_code(length=7)

        assert isinstance(code, str)
        assert len(code) == 7

    async def test_code_contains_only_alphabet_chars(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True

        with patch("app.services.shortener.redis_client", mock_redis):
            code = await generate_unique_code(length=7)

        assert all(c in ALPHABET for c in code)

    async def test_uses_settings_length_when_none(self) -> None:
        """length=None must fall back to settings.short_code_length."""
        from app.core.config import settings

        mock_redis = AsyncMock()
        mock_redis.set.return_value = True

        with patch("app.services.shortener.redis_client", mock_redis):
            code = await generate_unique_code()

        assert len(code) == settings.short_code_length

    async def test_retries_on_collision_and_eventually_succeeds(self) -> None:
        """
        First 2 reservations collide (None), 3rd succeeds (True).
        Redis.set must be called exactly 3 times.
        """
        mock_redis = AsyncMock()
        mock_redis.set.side_effect = [None, None, True]

        with patch("app.services.shortener.redis_client", mock_redis):
            code = await generate_unique_code(length=7, max_tries=5)

        assert isinstance(code, str)
        assert mock_redis.set.call_count == 3

    async def test_grows_length_after_max_tries_exhausted(self) -> None:
        """
        All max_tries collide at length=7 → recursive call with length=8.
        The 6th call (length=8) succeeds.
        Returned code must be length 8.
        """
        mock_redis = AsyncMock()
        #                 ── length=7 attempts ──  length=8
        mock_redis.set.side_effect = [None, None, None, None, None, True]

        with patch("app.services.shortener.redis_client", mock_redis):
            code = await generate_unique_code(length=7, max_tries=5)

        assert len(code) == 8
        assert mock_redis.set.call_count == 6

    async def test_single_max_tries_still_works(self) -> None:
        """max_tries=1: if first attempt succeeds, returns immediately."""
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True

        with patch("app.services.shortener.redis_client", mock_redis):
            code = await generate_unique_code(length=7, max_tries=1)

        assert len(code) == 7
        assert mock_redis.set.call_count == 1


# ── encode_base62 ─────────────────────────────────────────────────────────────


class TestEncodeBase62:
    def test_zero_returns_first_alphabet_char(self) -> None:
        assert encode_base62(0) == ALPHABET[0]

    def test_62_encodes_to_10(self) -> None:
        """62 in base-62 is '10' (1×62¹ + 0×62⁰)."""
        assert encode_base62(62) == "10"

    def test_61_encodes_to_last_char(self) -> None:
        """61 is the last valid single-digit in Base62."""
        assert encode_base62(61) == ALPHABET[61]

    def test_large_number_returns_string(self) -> None:
        result = encode_base62(1_000_000)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_output_only_alphabet_chars(self) -> None:
        for n in [0, 1, 61, 62, 100, 999, 100_000]:
            assert all(c in ALPHABET for c in encode_base62(n))

    def test_negative_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            encode_base62(-1)

    def test_negative_large_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            encode_base62(-999)


# ── decode_base62 ─────────────────────────────────────────────────────────────


class TestDecodeBase62:
    def test_first_char_decodes_to_zero(self) -> None:
        assert decode_base62(ALPHABET[0]) == 0

    def test_10_decodes_to_62(self) -> None:
        assert decode_base62("10") == 62

    def test_last_char_decodes_to_61(self) -> None:
        assert decode_base62(ALPHABET[61]) == 61

    def test_large_encoded_value(self) -> None:
        result = decode_base62(encode_base62(1_000_000))
        assert result == 1_000_000


# ── encode / decode roundtrip ─────────────────────────────────────────────────


class TestBase62Roundtrip:
    @pytest.mark.parametrize(
        "number",
        [
            0,
            1,
            61,
            62,
            63,
            100,
            999,
            3_521_614_606_208,  # 62^7
            62**7 - 1,  # max 7-char value
        ],
    )
    def test_encode_decode_roundtrip(self, number: int) -> None:
        """decode(encode(n)) == n for all non-negative integers."""
        assert decode_base62(encode_base62(number)) == number

    def test_decode_encode_roundtrip(self) -> None:
        """encode(decode(s)) == s for valid Base62 strings."""
        for code in ["0", "1", "Z", "10", "abc123", "ZZZZZZZ"]:
            assert encode_base62(decode_base62(code)) == code
