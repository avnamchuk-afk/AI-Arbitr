# AI-Arbitr analytics report templates

These templates are designed for paid, aggregated analytics. They must be built from anonymized tables only:

- `contract_analytics_snapshots`
- `analytics_events`

Do not export emails, names, passports, phones, raw message text, or full contract text.

## 1. Contract Funnel And Cycle-Time Report

Buyer:
LegalTech operators, marketplaces, property platforms, SME SaaS teams, product owners.

Question answered:
Where do users drop off between draft, review, signature, dispute, and completion?

Core metrics:

- Generated contracts
- Contracts sent to review
- Party 2 approvals
- Party 1 approvals
- Finalized contracts
- Completed without dispute
- Disputed contracts
- Conversion rates by contract category
- Median time from creation to review
- Median time from review to finalization

Current DB coverage:

| Metric | Source | Status |
| --- | --- | --- |
| Generated contracts | `contract_analytics_snapshots.version_count > 0` or `analytics_events.event_type = contract_version_created` | Covered |
| Sent to review | `sent_to_review` or `invite_sent` | Covered |
| Party approvals | `signed_by_party_1`, `signed_by_party_2`, `party_approved`, `party_2_approved` | Covered |
| Finalized contracts | `finalized`, `contract_finalized` | Covered |
| Completed without dispute | `completed_without_dispute` | Covered |
| Disputed contracts | `dispute_opened`, `dispute_opened` event | Covered |
| Cycle time | `created_at`, `updated_at`, `analytics_events.created_at` | Partly covered |

Example SQL sketch:

```sql
select
  contract_category,
  count(*) filter (where version_count > 0) as generated,
  count(*) filter (where sent_to_review) as sent_to_review,
  count(*) filter (where signed_by_party_2) as party_2_signed,
  count(*) filter (where finalized) as finalized,
  count(*) filter (where completed_without_dispute) as completed_without_dispute,
  count(*) filter (where dispute_opened) as disputed
from contract_analytics_snapshots
group by contract_category
order by generated desc;
```

Recommended next fields:

- `first_version_created_at`
- `first_sent_to_review_at`
- `finalized_at`
- `completed_at`

## 2. Market Terms Benchmark Report

Buyer:
Real estate platforms, landlord/tenant services, insurance, banks, marketplaces, SME advisors.

Question answered:
What terms are common in user-generated contracts by category?

Core metrics:

- Median monthly payment
- Median deposit
- Deposit-to-monthly-payment ratio
- Average term length
- Share with auto-prolongation
- Share with utilities paid separately
- Share allowing children
- Share allowing pets
- Distribution by contract category

Current DB coverage:

| Metric | Source | Status |
| --- | --- | --- |
| Contract category | `contract_category` | Covered |
| Monthly payment | `monthly_payment_amount` | Covered for rent-like contracts |
| Deposit | `deposit_amount` | Covered for rent-like contracts |
| Term | `term_months` | Covered when extractable |
| Auto-prolongation | `auto_prolongation` | Covered |
| Utilities separate | `utilities_separate` | Covered |
| Children allowed | `children_allowed` | Covered |
| Pets allowed | `pets_allowed` | Covered |

Example SQL sketch:

```sql
select
  contract_category,
  percentile_cont(0.5) within group (order by monthly_payment_amount) as median_monthly_payment,
  percentile_cont(0.5) within group (order by deposit_amount) as median_deposit,
  avg(deposit_amount / nullif(monthly_payment_amount, 0)) as avg_deposit_to_payment_ratio,
  avg(term_months) as avg_term_months,
  avg(case when auto_prolongation then 1 else 0 end) as auto_prolongation_share,
  avg(case when utilities_separate then 1 else 0 end) as utilities_separate_share,
  avg(case when children_allowed then 1 else 0 end) as children_allowed_share,
  avg(case when pets_allowed then 1 else 0 end) as pets_allowed_share
from contract_analytics_snapshots
where contract_category = 'housing_rent'
group by contract_category;
```

Recommended next fields:

- Region/city extracted as normalized non-personal location
- Object type: apartment, room, house, commercial premises
- Payment due day
- Deposit installment count
- Notice periods

## 3. Risk, Dispute And Clause Coverage Report

Buyer:
Insurers, legal marketplaces, compliance teams, property managers, dispute-resolution partners.

Question answered:
Which contracts create more disputes or require more negotiation, and which protective terms reduce friction?

Core metrics:

- Dispute rate by category
- Finalization rate by category
- Number of versions before finalization
- Number of user messages before finalization
- Share sent to review but not signed
- Share signed by second party but not first party
- Completion-without-dispute rate
- Clause coverage proxies: AI-Arbitr dispute clause, auto-prolongation, deposit, utilities, pet restriction

Current DB coverage:

| Metric | Source | Status |
| --- | --- | --- |
| Dispute rate | `dispute_opened` | Covered |
| Finalization rate | `finalized` | Covered |
| Version count | `version_count` | Covered |
| Message count | `message_count`, `user_message_count` | Covered |
| Sent but unsigned | `sent_to_review`, `signed_by_party_2`, `finalized` | Covered |
| Completed without dispute | `completed_without_dispute` | Covered |
| Clause coverage proxies | `auto_prolongation`, `utilities_separate`, `deposit_amount`, `pets_allowed` | Partly covered |

Example SQL sketch:

```sql
select
  contract_category,
  count(*) as contracts,
  avg(case when finalized then 1 else 0 end) as finalization_rate,
  avg(case when dispute_opened then 1 else 0 end) as dispute_rate,
  avg(version_count) as avg_versions,
  avg(user_message_count) as avg_user_messages,
  avg(case when sent_to_review and not finalized then 1 else 0 end) as sent_not_finalized_rate,
  avg(case when completed_without_dispute then 1 else 0 end) as clean_completion_rate
from contract_analytics_snapshots
where version_count > 0
group by contract_category
order by dispute_rate desc;
```

Recommended next fields:

- Clause inventory table with normalized clause flags
- Risk score at version level
- Reason for dispute category
- Which party opened dispute
- Outcome of dispute

## Fit Summary

The current DB structure is strong enough for MVP analytics sales discovery:

- Funnel analytics: mostly ready
- Rent-market benchmark: ready for first demo, needs location/object normalization
- Risk/dispute analytics: ready for basic rates, needs clause inventory and dispute outcome for paid-grade reports

Next recommended table:

`contract_clause_features`

One row per session/version with normalized booleans such as:

- `has_ai_arbitr_clause`
- `has_auto_prolongation`
- `has_deposit_return_deadline`
- `has_unilateral_price_change_limit`
- `has_notice_period`
- `has_acceptance_procedure`
- `has_ip_transfer_clause`
- `has_confidentiality_clause`
- `has_liability_cap`

