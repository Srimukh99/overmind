---
name: legal-traps
description: Use when building or shipping a consumer app - signup, checkout, subscriptions, email, SMS, uploads, analytics or tracking scripts - to catch the legal traps new builders miss (COPPA, HIPAA, wiretap claims, CAN-SPAM, auto-renewal, drip pricing, DMCA, remote fonts).
---

# legal-traps

The mistakes that get small apps sued, fined or pulled from app stores. Most are
cheap to fix before launch and expensive after. Not legal advice: this catches
the common traps, a lawyer signs off on the product.

Run the scanner first, then read only the sections it flags:
`python3 skills/legal-traps/scripts/legal_traps.py .`
Silence a reviewed line with a `legal-traps: ignore` comment.

## Kids: COPPA
- Applies when the service is directed at under-13s or you actually know a user is under 13. "We never asked" is not a defence if the app plainly appeals to kids.
- Use a neutral age screen: ask date of birth, don't hint at the cutoff, don't let a blocked user go back and change it. Never a pre-ticked "I am over 13" box.
- Under 13 means verifiable parental consent before collecting anything, including persistent identifiers used for ads.
- The amended FTC rule (compliance date April 2026) adds separate parental consent for sharing with third parties for advertising and a written retention policy.
- State age-appropriate-design and app-store age laws are spreading; check the states you serve.

## Health data: HIPAA and beyond
- HIPAA binds covered entities and their business associates. Every vendor that touches PHI (hosting, email, support desk, analytics) needs a signed BAA. No BAA, no PHI in that tool.
- No ad pixels or session replay on pages where users enter health information. This is the single most common healthcare violation in web apps.
- Not covered by HIPAA? The FTC Health Breach Notification Rule and state laws (Washington's My Health My Data Act) still apply to consumer health apps.
- Deeper rules: route to `reg-phi`.

## Fonts and third-party assets (EU)
- Loading Google Fonts from Google's servers sends the visitor's IP to Google. A Munich court awarded damages for exactly this in 2022, followed by waves of demand letters.
- Self-host fonts (`@fontsource/*` or download the files). Same logic for any CDN asset that isn't essential.

## Wiretap and recording claims
- California's Invasion of Privacy Act is the basis of thousands of suits over session replay (Hotjar, FullStory, LogRocket, Clarity), chat widgets and tracking pixels, framed as a third party "eavesdropping".
- Load these only after consent, disclose them in the privacy policy, and mask form inputs in replay tools.
- Pixels on pages that play video can trigger the Video Privacy Protection Act.
- Recording calls: some states require every party's consent. Announce it.

## Email and SMS
- Every marketing email: a working unsubscribe link, a valid physical postal address, honest subject line. Honour opt-outs within 10 business days (CAN-SPAM).
- Bulk senders to Gmail and Yahoo also need one-click unsubscribe (`List-Unsubscribe` and `List-Unsubscribe-Post` headers), SPF, DKIM and DMARC.
- Marketing texts need prior express written consent (TCPA); statutory damages are per message. Keep consent records and support STOP.

## Checkout: no hidden fees
- Show the full price, including mandatory fees, from the first price displayed. California's honest-pricing law bans drip pricing; the FTC fees rule covers tickets and short-term lodging.
- No pre-ticked add-ons, no fake countdown timers, no confirmshaming on the decline button.

## Subscriptions and renew buttons
- California's Automatic Renewal Law: disclose renewal terms clearly next to the button, get express affirmative consent to those terms, send an acknowledgement, and let users cancel online as easily as they signed up.
- Skip the consent and California treats whatever you delivered as an unconditional gift: you can't keep charging for it and refunds are owed. Since July 2025 the law also requires click-to-cancel and annual reminders.
- Federally, ROSCA still requires clear disclosure, express informed consent and simple cancellation. Many other states have their own auto-renew laws.
- Make the button say what it does: "Start subscription - $9.99/month, renews until cancelled", not "Continue".

## User uploads
- Designate a DMCA agent with the US Copyright Office (renew every 3 years), publish the contact, and keep a repeat-infringer policy. Without it you lose safe harbour for what users post.
- Have a takedown path for non-consensual intimate images; the TAKE IT DOWN Act requires removal within 48 hours of a valid request.
- If you become aware of child sexual abuse material you must report it to NCMEC. Use a hash-matching service on image uploads.
- Face detection or face matching on photos: Illinois BIPA requires written consent first.
- Strip EXIF location data from public images.

## Payments
- Never let card numbers touch your servers or logs. Use the processor's hosted fields or checkout. Deeper rules: `reg-pci`.

## Baseline every app needs
- A privacy policy, linked from every page that collects data (CalOPPA). A "Do Not Sell or Share" link and honouring Global Privacy Control where CCPA applies.
- In-app account deletion if users can create accounts in your app (Apple and Google require it).
- Cookie consent before non-essential cookies for EU and UK visitors.
- Accessibility: WCAG 2.1 AA. ADA website suits are routine in the US, and the European Accessibility Act has applied since June 2025.
- Terms of service accepted by an explicit click, not a footer link.

## How to apply
1. Run the scanner. Fix FAIL items before shipping.
2. For each WARN, decide: fix, or note why it doesn't apply.
3. Add a line to the PR description listing which traps were checked.
4. Anything involving kids, health or money: name it to the user as needing a lawyer's review.
