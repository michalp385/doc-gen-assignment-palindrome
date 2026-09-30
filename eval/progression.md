# Progression: baseline against the current pipeline

Baseline: `eval/results/20260930T203207Z_50a3687.json` (commit `50a3687`). Current: `eval/results/20260930T203208Z_50a3687.json` (commit `50a3687`). n/a means that side has no value: no report for the client, or no judge answer in the cache.

### client_01_clean

| Measure | Baseline | Current |
|---|---|---|
| Release state (expected draft) | n/a (starter has no release states) | draft |
| Failed deterministic gates | 9 | 0 |
| Deterministic gates passed | 5 of 14 | 14 of 14 |
| Failing gates | G1, G2, G3, G9, G11, G12, G13, G14, G15 | none |
| Q1 | 2 | 3 |
| Q2 | 3 | 4 |
| Q3 | 1 | 5 |
| Q4 | 2 | 4 |
| Q5 | n/a (no markers) | 5 |
| Q6 | 1 | 5 |

### client_02_medium

| Measure | Baseline | Current |
|---|---|---|
| Release state (expected draft) | n/a (starter has no release states) | draft |
| Failed deterministic gates | 9 | 0 |
| Deterministic gates passed | 5 of 14 | 14 of 14 |
| Failing gates | G1, G2, G3, G4, G11, G12, G13, G14, G15 | none |
| Q1 | 2 | 2 |
| Q2 | 1 | 5 |
| Q3 | 2 | 5 |
| Q4 | 2 | 4 |
| Q5 | n/a (no markers) | 5 |
| Q6 | 1 | 5 |

### client_03_hard

| Measure | Baseline | Current |
|---|---|---|
| Release state (expected draft) | n/a (starter has no release states) | draft |
| Failed deterministic gates | 10 | 0 |
| Deterministic gates passed | 4 of 14 | 14 of 14 |
| Failing gates | G1, G2, G3, G4, G9, G11, G12, G13, G14, G15 | none |
| Q1 | 2 | 2 |
| Q2 | 2 | 3 |
| Q3 | 2 | 2 |
| Q4 | 2 | 4 |
| Q5 | n/a (no markers) | 5 |
| Q6 | 1 | 5 |

### client_04_stretch

| Measure | Baseline | Current |
|---|---|---|
| Release state (expected draft) | n/a (starter has no release states) | draft |
| Failed deterministic gates | 10 | 0 |
| Deterministic gates passed | 4 of 14 | 14 of 14 |
| Failing gates | G1, G2, G3, G4, G9, G11, G12, G13, G14, G15 | none |
| Q1 | 2 | 2 |
| Q2 | 2 | 4 |
| Q3 | 2 | 2 |
| Q4 | 2 | 3 |
| Q5 | n/a (no markers) | 5 |
| Q6 | 1 | 5 |

n/a (no markers): the report had no adviser-review markers, so the judge's Q5 of 5 is vacuous and is not shown as a score.
