# Ban/pause register build report

Verification dir: `alpr_ban_dataset/verification` · cutoff 2026-09-30

## Verification of the existing register

| status | rows |
| --- | --- |
| confirmed | 156 |
| not_a_decision | 14 |
| unconfirmed | 4 |
| duplicate | 3 |
| confirmed|dedup | 2 |

Confirmed rows whose jurisdiction was wrong (city or state changed): 11
Confirmed rows whose action was recoded: 57

## New decisions from the gap search

| origin | status | rows |
| --- | --- | --- |
| new_midwest | confirmed | 66 |
| new_midwest | unconfirmed | 8 |
| new_south_ne | confirmed | 144 |
| new_south_ne | confirmed|dedup | 22 |
| new_south_ne | unconfirmed | 19 |
| new_west_national | confirmed|dedup | 112 |
| new_west_national | confirmed | 69 |
| new_west_national | unconfirmed | 4 |

## In scope

| geo_type | action | decisions |
| --- | --- | --- |
| county | canceled | 54 |
| county | declined_to_adopt | 2 |
| county | not_renewed | 14 |
| county | ordinance_ban | 2 |
| county | replaced_vendor | 1 |
| county | suspended | 38 |
| cousub | canceled | 23 |
| cousub | declined_to_adopt | 3 |
| cousub | not_renewed | 3 |
| cousub | replaced_vendor | 2 |
| cousub | suspended | 10 |
| place | canceled | 134 |
| place | declined_to_adopt | 21 |
| place | not_renewed | 47 |
| place | ordinance_ban | 1 |
| place | replaced_vendor | 5 |
| place | suspended | 64 |

Duplicate reports collapsed: 136
State-triggered (FL DOT / TX funding pause / WA SB 6002): FL 33, TX 6, WA 2
Unique jurisdictions: county 104 · cousub 36 · place 263
Confirmed decisions dated after the cutoff (excluded): 1
Confirmed, level=other (state agency, university, ...; excluded): 6

## Unresolved jurisdictions (confirmed rows, no GEOID)

- none

## Validation problems

- none
