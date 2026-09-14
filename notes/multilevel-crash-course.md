# Multilevel modeling crash course — for the Flock paper

*Written 2026-09-13. Four hours of reading gets you to: (1) explain why the paper's Mundlak spec is already a multilevel model, (2) add county- and state-level covariates correctly, (3) defend it at APRL. `mundlak-review.md` covers whether Mundlak is the **best** choice.*

## TL;DR

- The paper's Equation 3 **is a random-intercept model with Mundlak means** — two levels, unit in county. Nobody's said so out loud.
- FE absorbs everything at the county level → **you can't estimate county-level covariates with FE.** Mundlak/REWB lets you. That's the whole reason to prefer it, not "software limitations."
- Rewrite it in **within/between form** and you get interpretable between-county effects for free.
- Add county covariates (`z_c`) as a third block; add state as a second random intercept.
- Two things to check before trusting it: **means computed over adopters only** (should be all units), and **conditional vs marginal** logit coefficients when comparing to FE.

## 1. Ten terms

- **Level** — tract (L1) ⊂ county (L2) ⊂ state (L3). Same for places. **Tracts don't nest in places** → cross-classified.
- **Random intercept (RI)** — each county gets a baseline `v_c ~ N(0, σ²)`. Small counties get **shrunk** toward the mean.
- **Fixed effect (FE)** — each county gets a free dummy. Absorbs *everything* constant within county — including any county covariate you wanted.
- **Within effect** — richer tract vs poorer tract *in the same county*. What FE identifies.
- **Between effect** — counties with richer tracts vs counties with poorer tracts. FE throws it away; naive RE blends it with within.
- **Contextual effect** — between minus within. The county's income, holding the tract's fixed.
- **Mundlak = CRE = REWB = hybrid** — four names, one move: RE + group means of every L1 covariate. Within ≈ FE; between = the means' coefficients. Standard, not niche. The *name* is niche.
- **Cross-level interaction** — L1 slope depends on an L2 variable.
- **Random slope** — let an L1 effect vary by county. Required before any cross-level interaction (Heisig & Schaeffer 2019).
- **ICC** — share of variance between counties. Null model: `σ²_v / (σ²_v + π²/3)` for logit.

## 2. What the paper does, in these terms

- Draft Eq. 3: `log μ_i = x_i'δ + x̄_c'γ + v_c`
  - `δ` = within-county effects (≈ FE)
  - `γ` = between **minus** within, not the between effect itself
- Rewrite as REWB: `log μ_i = β_W (x_i − x̄_c) + β_B x̄_c + v_c`
  - Same likelihood, same fit. `β_W = δ`, `β_B = δ + γ`.
  - **Report `β_W` and `β_B` side by side.** Far better than "county means not shown."
- Better reasons for Mundlak than "software limitations":
  - **Incidental parameters.** FE in nonlinear models with many small groups is biased (Neyman & Scott 1948; Fernández-Val & Weidner 2016). Many counties have 1–5 places.
  - **You want county covariates.** FE makes sheriff spend, 287(g), county crime, state statutes *unestimable*.

## 3. Adding higher-level covariates (the thing you want)

Three-level tract intensity model:

```
log μ_i = β_W (x_i − x̄_c) + β_B x̄_c + γ z_c + λ w_s + v_c + u_s
```

- `x_i` — tract covariates (have)
- `x̄_c` — county means over **all** tracts (see §6)
- `z_c` — county: sheriff spend/capita, sworn per 1k, elected, 287(g), crime rates, county-govt share of police, unincorporated share
- `w_s` — state: ALPR statute, retention limit. Or just `u_s`.
- `v_c`, `u_s` — county, state random intercepts

How to read it:
- **`γ` is a between-county effect** net of tract *and* county composition. `x̄_c` and `z_c` compete for the same variance → check VIFs on the between block; drop means with no plausible contextual story.
- **Cross-level interaction** `(x_i − x̄_c) × z_c`: e.g., does within-county share-Black depend on 287(g)? Add the random slope first.
- **Places:** `own_pd × crime` — crime matters where there's a PD to act on it; county crime is the context for sheriff-policed places.
- **Cross-classified:** `(1 | county) + (1 | place)`, `place = "none"` for unincorporated tracts + an `in_place` dummy. glmmTMB/lme4 handle it natively.

## 4. Software

| Piece | R | Note |
|---|---|---|
| Adoption logit, county FE | `fixest::feglm(y ~ x \| county, family = binomial, cluster = ~county)` | Fast with thousands of FE; drops all-0/all-1 counties |
| Adoption logit, RI + Mundlak + county covariates | `glmmTMB(y ~ xw + xb + z + (1\|county) + (1\|state), family = binomial)` | Faster than `glmer` at n = 82k. Coefficients are *conditional* — see §6 |
| Intensity, zero-truncated NB, RI + Mundlak | `glmmTMB(y ~ xw + xb + z + (1\|county), family = truncated_nbinom2, data = subset(d, y > 0))` | What the paper already does. Adding `z` and `(1\|state)` is one line |
| Intensity, truncated NB, county FE | `glmmTMB(... + factor(county))` — slow; `fixest` has no truncated family | The "software" claim is *half* true: FE-Poisson on positives is trivial in `fixest::fepois` |
| Joint hurdle, fully multilevel | `brms::brm(bf(y ~ ..., hu ~ ...), family = hurdle_negbinomial)` | One model, both parts; hours on 82k rows, fine on 24k places; `loo` for free |
| Random slope | `(1 + xw_black \| county)` | LRT vs RI-only |
| ICC | `performance::icc(m)` | works on glmmTMB / lme4 / brms |

Centering and means:

```r
d <- d |>
  group_by(county) |>
  mutate(across(c(log_pop, log_income, pct_black, pct_hispanic, pct_asian,
                  pct_renter, employment_ratio, pct_jobs_retail_food),
                list(cm = ~ mean(.x, na.rm = TRUE)))) |>        # county mean, ALL units
  mutate(across(c(log_pop, log_income, pct_black, pct_hispanic, pct_asian,
                  pct_renter, employment_ratio, pct_jobs_retail_food),
                list(w = ~ .x - get(paste0(cur_column(), "_cm")))))
# then: y ~ log_pop_w + log_pop_cm + ... + sheriff_spend_pc + sheriff_287g + (1|county) + (1|state)
```

## 5. What to report (three of these are blanks in the draft)

- **Null-model ICCs** at each level, adoption and intensity. One sentence each.
- **FE vs REWB within-coefficient dot plot** — fills the empty "FE v. Mundlak" appendix. Demonstrates the claim instead of asserting it.
- **Within and between side by side** for composition variables. The tract share-Black result (positive within, null between with state FE) *is* a within/between contrast.
- **The `γ` table** — county covariates. New.
- **IRRs with 95% CIs** in the talk; raw logs in the appendix.
- **Rootogram** for the count part (`countreg::rootogram` / `bayesplot::ppc_rootogram`).

## 6. Pitfalls specific to this paper

- **Means over the selected sample.** Intensity model computes `x̄_c` over units with ≥1 camera. The review says this is defensible by construction (a true FE truncated-NB would use the same subsample; Wooldridge 2019) — but small-county means are noisy and attenuate between effects. Recompute over all units as a sensitivity check; add `log n_j` as a covariate.
- **Standard errors.** Default GLMM SEs undercover (Hazlett & Wainstein 2022). Use a county cluster bootstrap for the headline tables.
- **Collinearity `x̄_c` vs `z_c`.** County mean of tract income ≈ county median income. One representation per construct.
- **Singleton counties.** One place → no within variation. FE drops them; RI shrinks them. Report the count (~700 of 3,144?).
- **Conditional vs marginal logit.** RI-logit coefficients are ≈ `sqrt(1 + 0.346 σ²_v)` larger than population-averaged ones. Compare FE and Mundlak columns by **sign and ratio**, or use `marginaleffects::avg_slopes`.
- **Spatial dependence.** A county RI captures a shared level, not neighbor contagion. Cameras follow arterials across tract lines; Flock sells network adoption. Moran's I on residuals (`spdep`); CAR/BYM if large.
- **MAUP isn't solved by MLM.** Three separate aggregations = sensitivity design. A joint three-level model is the natural next paper.
- **Everything is significant at n = 82k.** Report effect sizes in cameras via `marginaleffects`.
- **Log pop + log area + log density** can't all enter — nor can their county means.

## 7. Reading list (first four ≈ 4 h)

1. **Steenbergen & Jones 2002**, AJPS 46(1) — the polisci intro. 45 min.
2. **Bell & Jones 2015**, PSRM 3(1) — REWB; "FE vs RE" is a false choice. 60 min.
3. **Gelman & Hill 2007**, ch. 11–13 (+14 for GLMMs) — partial pooling intuition. 90 min skim.
4. **Enders & Tofighi 2007**, Psych Methods 12(2) — centering in cross-sectional multilevel. Exactly your case. 30 min.
5. **Bell, Fairbrother & Jones 2019**, Q&Q 53 — the balanced update of #2.
6. **Stegmueller 2013**, AJPS 57(3) — few L2 groups; when to go Bayesian.
7. **Heisig & Schaeffer 2019**, ESR 35(2) — always add the random slope.
8. **Wooldridge 2010**, §15.8.2 (CRE probit), ch. 18 (counts) — the econometric warrant.
9. **Snijders & Bosker 2012**, ch. 4–5, 17 — reference.
10. **McElreath 2020**, ch. 13 — best intuition if the others don't land.
11. **glmmTMB** "Getting started" vignette + `truncated_nbinom2` docs; **brms** distributional-models vignette.
12. **Gelman 2005**, Annals of Statistics — §6 on why "fixed/random" mean five things.

## 8. Four-hour plan (low-fuel slots)

- **Slot 1 (60 min):** Steenbergen & Jones. Write 3 sentences: the levels, the ICC question, the cross-level question.
- **Slot 2 (60 min):** Bell & Jones §1–4. Rewrite Eq. 3 in REWB form by hand.
- **Slot 3 (60 min):** Gelman & Hill 12.1–12.6. Draw shrinkage for a one-place county.
- **Slot 4 (60 min):** Enders & Tofighi + glmmTMB vignette. Write the `glmmTMB` call with sheriff covariates. Don't run it.
