"""DBT-11 / D-R14 — the tz→local-day computation. Pure, no DB, no network."""

from datetime import date, datetime, timezone

from app.services.local_date import compute_local_date


def _utc(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_positive_offset_rolls_to_the_next_local_day():
    # 23:30 UTC on the 10th is 08:30 on the 11th in Tokyo (UTC+9) — the message
    # belongs to the user's *next* day, not the server's UTC day.
    assert compute_local_date("Asia/Tokyo", _utc(2026, 3, 10, 23, 30)) == date(2026, 3, 11)


def test_negative_offset_rolls_to_the_previous_local_day():
    # 02:00 UTC on the 10th is 18:00 on the 9th in Los Angeles (UTC-8).
    assert compute_local_date("America/Los_Angeles", _utc(2026, 3, 10, 2, 0)) == date(2026, 3, 9)


def test_utc_timezone_is_the_utc_day():
    assert compute_local_date("UTC", _utc(2026, 3, 10, 23, 30)) == date(2026, 3, 10)


def test_none_or_blank_falls_back_to_utc_day():
    assert compute_local_date(None, _utc(2026, 3, 10, 23, 30)) == date(2026, 3, 10)
    assert compute_local_date("", _utc(2026, 3, 10, 23, 30)) == date(2026, 3, 10)


def test_invalid_timezone_falls_back_to_utc_day_without_raising():
    # A garbage tz must degrade, never raise into the message-write path.
    assert compute_local_date("Not/AZone", _utc(2026, 3, 10, 23, 30)) == date(2026, 3, 10)
    assert compute_local_date("Europe/Nowhere", _utc(2026, 3, 10, 12, 0)) == date(2026, 3, 10)


def test_naive_now_is_treated_as_utc():
    assert compute_local_date("Asia/Tokyo", datetime(2026, 3, 10, 23, 30)) == date(2026, 3, 11)
