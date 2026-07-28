# Client-outreach drafts (bluezoo-semantics-resolution, 2026-07-27)

Carried over from `bluezoo-live-verification`'s "Remaining asks," now sharpened
by this workstream's evidence. Owner sends; nothing here has been sent.
Evidence citations refer to `findings.md` in this folder. No customer
identifiers appear below.

---

## Draft A — to BlueZoo (Bill / Yasha)

**Subject: DWH semantics — one rule to confirm, plus a short list of operational questions**

Hi Bill, Yasha,

Thanks again for the Morpheus staging access — it's been genuinely useful. We've
finished a careful read-only analysis of the warehouse, and rather than send you
open-ended questions, we've turned almost everything into confirm-or-correct
items. The first one is the only one that affects our numbers materially.

**1. The `valid` column — please confirm our planned rule.**
From the data we observe that:

- `valid` flips one-way `false` → `true` per sensor (never back and forth),
  typically after a ~3-week initial period;
- currently-valid sensors hold a `pulse_count / expected_pulse_count` ratio
  of ~0.99 while never-accepted ones sit near zero (and the one not-yet-
  accepted sensor we see reporting at 0.99 looks like a pre-acceptance
  snapshot) — so the flip looks like an acceptance/commissioning event;
- a commissioned sensor that later degrades keeps `valid = true` (we found
  several currently at zero pulse health that remain valid);
- `NULL` values simply predate the column's introduction (2021-10-14); and
- your sensor groups contain both valid and invalid sensors, so group
  membership doesn't encode the distinction.

We read `valid` as **"sensor accepted into service"** and plan to count
impressions **only from `valid IS TRUE` rows**, with the exclusion logged.
Please confirm this is the intended consumer behavior — and one sub-question:
do your group-level aggregates (`group_uv_daily` and friends) already apply
the same filter internally when they aggregate over a group's sensors?

**2. Day/time bucketing.** We've verified empirically that the raw
`timestamp` column is UTC (diurnal traffic troughs across venues in different
time zones line up in local time only after applying each sensor's offset).
Two confirmations: (a) are your `group_*_daily` / `_weekly` / `_monthly`
`date` buckets cut on UTC days or venue-local days? (b) We notice `time_zone`
(IANA) is populated on recent rows but null historically, while `time_offset`
varies with DST — which of the two should a consumer treat as authoritative
going forward?

**3. The scan quota, three practical questions.** (a) When one query spans
many sensor locations, is it charged against each location's allowance or a
shared pool? (Our observations suggest per-location.) (b) Is the raised
500 GB/location ceiling on our tenant month-scoped or persistent? (c) Is
there any way to check remaining allowance before hitting the wall — and are
the tables partitioned/clustered on `timestamp`/`sensor_id` so we can predict
a query's cost?

**4. `group_uv_daily.campaign_id`** — we read this as your unique-visitor
measurement campaign over a sensor group (effectively 1:1 with `group_id`),
unrelated to any advertiser's campaign. Confirm it will never carry an
advertising campaign id?

**5. `sensor_visitors_per_minute`** — entitled on our tenant but with no data
since 2025. Is the per-minute feed generally available, opt-in, or being
retired? This decides whether we can use it for sub-15-minute attribution.

**6. Small docs bug, in case it helps others:** every `run_query` requires a
`timestamp`/`date_start`/`date_end` constraint in the WHERE clause (the API
rejects queries without one), but the published example
`select * from sensor_visitors limit 1` doesn't carry one, so it fails
against the live API as documented.

None of these block us — we're proceeding with the rule in #1 pending your
confirmation. Happy to walk through the evidence on a call.

Thanks,
Lavi

---

## Draft B — to the retailer / PoS side

**Subject: Two data questions that gate revenue attribution**

Hi [name],

We're at the point where in-store audience measurement is wired up
end-to-end, and the remaining piece for revenue-per-impression is the sales
side. Two questions:

**1. Which PoS system runs in the pilot stores, and what's the preferred
integration surface?** (API, scheduled export, or a data-warehouse share —
any of the three works for us; we'll conform to what you already operate.)
Granularity we need: per-transaction or per-interval sales by product, per
store, daily at minimum.

**2. How do we join sales to advertised products?** Concretely: what key
does your PoS use for a product (SKU, UPC/EAN, internal item id), and can you
share the mapping for the pilot product set so we can tie "revenue for
product X in store Y" to the ads we ran for X in Y? A one-time CSV for the
pilot is fine; we'd formalize later.

With those two, the loop closes: ads play on screens, sensors measure
impressions, your sales data prices them, and the system promotes the
creatives that actually sell.

Thanks,
Lavi
