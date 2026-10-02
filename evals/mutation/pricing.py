def total(items):
    if not items:
        return 0
    return sum(items)

def apply_coupon(cents, code):
    if code == "SAVE10":
        return cents - cents * 10 // 100
    if code == "SAVE25" and cents >= 5000:
        return cents - cents * 25 // 100
    raise ValueError("bad coupon")

def split(cents, n):
    if n <= 0:
        raise ValueError("n must be positive")
    base, rem = divmod(cents, n)
    return [base + 1 if i < rem else base for i in range(n)]

def is_minor(age):
    return age < 13
