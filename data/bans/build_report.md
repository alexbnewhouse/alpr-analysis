# Ban/pause register build report

Verification dir: `alpr_ban_dataset/verification` · cutoff 2026-09-30

## Verification of the existing register

| status | rows |
| --- | --- |
| confirmed | 156 |
| not_a_decision | 15 |
| duplicate | 4 |
| confirmed|dedup | 3 |
| unconfirmed | 1 |

Confirmed rows whose jurisdiction was wrong (city or state changed): 11
Confirmed rows whose action was recoded: 57

## New decisions from the gap search

| origin | status | rows |
| --- | --- | --- |
| new_midwest | confirmed | 71 |
| new_midwest | duplicate | 3 |
| new_r2_leads | confirmed | 14 |
| new_r2_leads | confirmed|dedup | 4 |
| new_r2_leads | unconfirmed | 2 |
| new_r2_s1_midatl_ne | confirmed | 41 |
| new_r2_s1_midatl_ne | confirmed|dedup | 8 |
| new_r2_s1_midatl_ne | unconfirmed | 7 |
| new_r2_s2_south_plains | confirmed | 42 |
| new_r2_s2_south_plains | confirmed|dedup | 10 |
| new_r2_s2_south_plains | not_a_decision | 3 |
| new_r2_s2_south_plains | duplicate | 2 |
| new_r2_s3_va_nc | confirmed | 16 |
| new_r2_s3_va_nc | unconfirmed | 3 |
| new_r2_s3_va_nc | confirmed|dedup | 1 |
| new_r2_s4_west | confirmed | 56 |
| new_r2_s4_west | confirmed|dedup | 13 |
| new_r2_s4_west | unconfirmed | 7 |
| new_r2_s4_west | duplicate | 6 |
| new_r2_s4_west | not_a_decision | 4 |
| new_r2_s5_highactivity | confirmed | 101 |
| new_r2_s5_highactivity | confirmed|dedup | 30 |
| new_r2_s5_highactivity | unconfirmed | 22 |
| new_r2_s5_highactivity | duplicate | 2 |
| new_r2_s5_highactivity | not_a_decision | 1 |
| new_r2_trackerA | confirmed | 36 |
| new_r2_trackerA | not_a_decision | 10 |
| new_r2_trackerA | confirmed|dedup | 8 |
| new_r2_trackerA | duplicate | 3 |
| new_r2_trackerA | unconfirmed | 2 |
| new_r2_trackerB | confirmed | 29 |
| new_r2_trackerB | not_a_decision | 14 |
| new_r2_trackerB | duplicate | 8 |
| new_r2_trackerB | confirmed|dedup | 5 |
| new_r2_trackerB | unconfirmed | 4 |
| new_r3_sheet | duplicate | 55 |
| new_r3_sheet | confirmed | 5 |
| new_r3_sheet | not_a_decision | 2 |
| new_r3_sheet | unconfirmed | 2 |
| new_south_ne | confirmed | 161 |
| new_south_ne | confirmed|dedup | 22 |
| new_south_ne | duplicate | 2 |
| new_west_national | confirmed|dedup | 112 |
| new_west_national | confirmed | 73 |

## In scope

| geo_type | action | decisions |
| --- | --- | --- |
| county | canceled | 79 |
| county | declined_to_adopt | 7 |
| county | not_renewed | 20 |
| county | ordinance_ban | 6 |
| county | replaced_vendor | 2 |
| county | suspended | 60 |
| cousub | canceled | 24 |
| cousub | declined_to_adopt | 5 |
| cousub | not_renewed | 3 |
| cousub | replaced_vendor | 3 |
| cousub | suspended | 11 |
| place | canceled | 181 |
| place | declined_to_adopt | 50 |
| place | not_renewed | 60 |
| place | ordinance_ban | 3 |
| place | replaced_vendor | 16 |
| place | suspended | 130 |

Duplicate reports collapsed: 216
Partial actions: 31 · high-confidence: 391 · non-Flock vendor: 13
State-triggered (state law, order or request): CT 1, FL 82, TX 8, VT 1, WA 10
Unique jurisdictions: county 159 · cousub 41 · place 398
Confirmed decisions dated after the cutoff (excluded): 92
Confirmed, level=other (state agency, university, ...; excluded): 26

## Unresolved jurisdictions (confirmed rows, no GEOID)

- none

## Validation problems

- none
