---
name: reg-money
description: Use when code calculates, stores, moves or displays money, including prices, balances, payments, refunds, interest, fees, taxes, FX, ledgers or invoices.
---

# reg-money

## Representation

1. Never use binary floating point for money. Use integer minor units (cents) or a decimal type with a fixed scale.
2. Every amount carries its currency (ISO 4217). Never add amounts in different currencies.
3. Respect each currency's minor units (JPY has 0, USD 2, some have 3).

## Calculation

4. Rounding mode is explicit and documented (half-up, half-even), and rounding happens at defined steps, not wherever it's convenient.
5. Allocations distribute remainders deterministically: splitting 100.00 three ways gives 33.34, 33.33, 33.33 and still sums to 100.00.
6. FX conversions store the rate, its source and its timestamp alongside the result.
7. Interest and date math use an explicit day-count convention and business-day calendar.

## Movement

8. Every money-moving request has an idempotency key; retries must never double-charge or double-pay.
9. Use a double-entry, append-only ledger. Corrections are new reversing entries, never edits or deletes.
10. Payments follow an explicit state machine (for example pending, authorized, settled, failed, reversed) with allowed transitions enforced.
11. A reconciliation job compares the ledger with the processor or bank and alerts on any difference.

## Tests

- Property tests: debits always equal credits; allocations always sum to the total.
- Boundaries: zero, negative, maximum, smallest unit, currency with 0 and 3 decimals.
- Retry tests prove idempotency.

Audit trail requirements: `reg-audit`. Card data: `reg-pci`.
