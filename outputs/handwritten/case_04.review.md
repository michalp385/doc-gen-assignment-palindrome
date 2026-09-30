# Review sheet -- case_04

## Status

Release state: draft
Cache replay vs live: 6 replayed, 7 live
Gates: 22/22 passed

## Blocking before sign-off

- We noted the jointly-held General Investment Account on the Holloway platform shows different values on our two records for the same date; we will confirm the correct balance before anything is finalised.

## Other open actions (not blocking)

None.

## Markers to fill

- #1: current value of Marcus Bell & Fiona Bell's General Investment Account, whose records disagree (records disagree on the same date (R9); firm policy: never estimated or converted), section: account_table
- #2: ongoing platform charge rate, Holloway (firm policy: never estimated), section: fees_charges
- #3: ongoing advice charge rate for the accounts on Holloway (firm policy: never estimated), section: fees_charges

## Conflicts and how they were resolved

- B-GIA-01: sources give different values on the same date (15 April 2026): £63,000 (client_data_db.json); £61,000 (client_data_db.json); no value is selected; confirm which is right before anything is finalised.

## Superseded values

None.

## Accounts left out

None.

## Section decisions

- Tax Implications: omitted (predicate: taxable_disposal)

## Notes

None.

## How this draft degraded

None.