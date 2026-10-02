# What agents typically write when nothing pushes back: happy paths, shape checks.
from pricing import total, apply_coupon, split, is_minor
def test_total():
    assert total([100, 200]) > 0
def test_coupon():
    assert apply_coupon(1000, "SAVE10") is not None
def test_split():
    assert len(split(1000, 3)) == 3
def test_minor():
    assert isinstance(is_minor(10), bool)
