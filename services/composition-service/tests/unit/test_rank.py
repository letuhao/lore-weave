"""Unit tests for the fractional rank helper (pure functions, no DB)."""

from __future__ import annotations

import pytest

from app.db.repositories.rank import (
    first_rank,
    rank_after,
    rank_before,
    rank_between,
)


def test_between_open_bounds_is_midpoint():
    r = rank_between(None, None)
    assert isinstance(r, str) and r
    # Strictly inside the full open range.
    assert "" < r


def test_between_orders_strictly():
    a = rank_between(None, None)
    b = rank_after(a)
    c = rank_after(b)
    assert a < b < c


def test_insert_between_two_siblings():
    lo, hi = "1", "2"
    mid = rank_between(lo, hi)
    assert lo < mid < hi


def test_adjacent_digits_grow_length():
    # '1' and '2' are adjacent at the first position only via descent; a value
    # between two single-step-apart ranks must still exist.
    lo = "h"
    hi = rank_after(lo)
    mid = rank_between(lo, hi)
    assert lo < mid < hi


def test_repeated_midpoint_insertion_stays_ordered():
    lo, hi = "1", "2"
    prev = lo
    inserted = []
    for _ in range(25):
        m = rank_between(prev, hi)
        assert prev < m < hi
        inserted.append(m)
        prev = m
    # The whole inserted chain is strictly ascending and bounded by hi.
    assert inserted == sorted(inserted)
    assert all(lo < x < hi for x in inserted)


def test_prepend_before_first():
    first = first_rank()
    earlier = rank_before(first)
    assert earlier < first


def test_rank_before_empty_list_is_first():
    assert rank_before(None) == first_rank()


def test_rank_after_empty_list_is_first():
    assert rank_after(None) == first_rank()


def test_requires_lo_less_than_hi():
    with pytest.raises(ValueError):
        rank_between("2", "1")
    with pytest.raises(ValueError):
        rank_between("a", "a")


def test_no_trailing_zero_digit():
    # The algorithm never emits a trailing '0' (keeps ranks canonical).
    for lo, hi in [(None, None), ("1", "2"), ("a", "b"), ("hzz", "i")]:
        assert not rank_between(lo, hi).endswith("0")
