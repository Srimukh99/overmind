# prove-it style: exact values, boundaries, error paths, a property.
import pytest
from hypothesis import given, strategies as st
from pricing import total, apply_coupon, split, is_minor
def test_total_exact(): assert total([100, 250]) == 350
def test_total_empty(): assert total([]) == 0
def test_save10(): assert apply_coupon(1000, "SAVE10") == 900
def test_save25_at_threshold(): assert apply_coupon(5000, "SAVE25") == 3750
def test_save25_below_threshold_rejected():
    with pytest.raises(ValueError): apply_coupon(4999, "SAVE25")
def test_bad_code():
    with pytest.raises(ValueError): apply_coupon(1000, "NOPE")
def test_split_remainder_first(): assert split(1000, 3) == [334, 333, 333]
def test_split_zero_rejected():
    with pytest.raises(ValueError): split(100, 0)
def test_split_one(): assert split(100, 1) == [100]
@given(st.integers(0, 10**9), st.integers(1, 50))
def test_split_conserves_money(c, n):
    parts = split(c, n); assert sum(parts) == c and max(parts) - min(parts) <= 1
def test_minor_boundary(): assert is_minor(12) is True and is_minor(13) is False
