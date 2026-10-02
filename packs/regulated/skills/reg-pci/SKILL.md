---
name: reg-pci
description: Use when code handles payment cards such as card numbers, CVV, expiry dates, cardholder names, checkout forms or tokenization, or touches any system in PCI DSS scope.
---

# reg-pci

Engineering guardrails for cardholder data under PCI DSS v4.0. This is not compliance advice; your QSA and security team decide scope.

## Best move: keep card data out

Use the payment processor's hosted fields, redirect or SDK so raw card numbers (PANs) never reach your servers. You then store only processor tokens, which shrinks your audit scope dramatically.

## If card data does touch your systems

1. **Never store** CVV/CVC, full magnetic stripe data or PIN blocks after authorization. Not encrypted, not anywhere.
2. **PAN at rest**: tokenized, or strongly encrypted with keys in an HSM or KMS, kept separate from the data.
3. **Display**: mask to at most the first 6 and last 4 digits, and only for roles that need it.
4. **Never in**: logs, URLs, error messages, analytics, support tickets, screenshots or LLM prompts.
5. **Scope**: segment the network so only the cardholder data environment can reach card data.
6. **Access**: unique IDs, MFA for any access into the card data environment, every access logged (`reg-audit`).
7. **Test data**: the processor's published test card numbers only.
8. **Web pages** that load payment forms: inventory and authorize every script on the page.

## Review checklist

- [ ] Raw PAN avoided entirely, or the reason is documented
- [ ] No CVV stored anywhere, including logs and queues
- [ ] PAN masked on display; tokens used everywhere else
- [ ] No card data in logs, URLs, errors, analytics or prompts
- [ ] Card data environment access logged and MFA-protected

`vibe-check` blocks Luhn-valid card numbers in diffs and allows common processor test cards.
