"""The canonical demo-data constants.

DEMO_RPI is THE single revenue-per-impression constant on the demo-data path
(phase-doc step 4). The donor duplicated 0.05 in two places
(REVENUE_PER_IMPRESSION and an inline SQL literal); here it exists once.
Flat by owner decision (ws05 working doc): demo revenue is exactly
impressions x DEMO_RPI, so demo RPI is identical across creatives until
Phase 7 revisits.
"""

# Dollars of attributed revenue per impression (donor's effective constant).
DEMO_RPI = 0.05

# Every generation call fills the backward window [anchor - 29, anchor].
DEMO_WINDOW_DAYS = 30
