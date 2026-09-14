# Mundlak / CRE review for "What the Flock?"

Prepared 2026-09-13 for the Nov 6, 2026 lab memo. Covers the county random intercept + county-mean-of-covariates ("Mundlak device") in the place- and tract-level hurdle models, and how to get to a real multilevel model with county- and state-level covariates.

## Summary verdict

> - **Mundlak/CRE is mainstream, not niche.** Same estimator as the "hybrid", "within-between (REWB)", "contextual-effects", and "bias-corrected MLM" models; endorsed in *PSRM* (Bell & Jones 2015) and *Political Analysis* (Hazlett & Wainstein 2022). Cite the lineage and use the REWB parameterisation.
> - **"Exact same information as county FE" is only true for linear models.** For logit and truncated NB it is an approximation (Wooldridge 2019; Bai et al. 2024; Schunck & Perales 2017), and it is weakest in counties with 1–5 camera-bearing units. Soften the claim and show an FE benchmark.
> - **The "software can't fit thousands of FE" excuse is false** (fixest, alpaca, glmmTMB `sparseX`, `ppmlhdfe`). The real reason is incidental-parameters bias with tiny counties (Greene 2004; Fernández-Val & Weidner 2016). Say that instead.
> - **Keep the hurdle + CRE design.** Change: group-mean centring, county-size terms, cluster-bootstrap SEs, county covariates entered directly.
> - **Three alternatives, in order:** (1) FE two-part benchmark in fixest/alpaca; (2) Bayesian hierarchical hurdle in brms with county + state intercepts; (3) spatial dependence (Moran's I now, BYM/spatial lag later).

## Where Mundlak/CRE stands in polisci

**Same model, five names.** Know the mapping so reviewers from any tradition recognise it.

- **Correlated random effects (CRE):** Mundlak (1978, *Econometrica*); Chamberlain (1982); Wooldridge (2010, chs. 10, 15, 18; 2019 *J. Econometrics*). Stata ships it as `xtreg, cre` + `estat mundlak`.
- **Hybrid model:** Allison (2009, *Fixed Effects Regression Models*, Sage); Schunck (2013, *Stata Journal*); Schunck & Perales (2017, *Stata Journal*, `xthybrid` for GLMMs).
- **Within-between RE (REWB):** Bell & Jones (2015, *PSRM* 3:133–153) — "RE can provide everything FE promises and more"; Bell, Fairbrother & Jones (2019, *Quality & Quantity* 53:1051–1074) for cross-sectional multilevel data.
- **Contextual-effects / group-mean-centred HLM:** Raudenbush & Bryk (2002, ch. 5); Enders & Tofighi (2007, *Psychological Methods*). Between minus within coefficient = contextual effect.
- **Bias-corrected MLM (bcMLM):** Hazlett & Wainstein (2022, *Political Analysis* 30:46–65).

**Polisci uptake.**

- **Bartels (2008, PolMeth)** introduced the framework; **Fairbrother (2014, *PSRM*)** applied it to comparative surveys; **Clark & Linzer (2015, *PSRM*)** give the Monte Carlo FE-vs-RE typology.
- **Hazlett & Wainstein reviewed 100+ multilevel papers: only 1 of 39 polisci articles applied any debiasing correction.** The student is doing what the methods literature recommends and most applied work skips. Say so explicitly.
- **In the linear case bcMLM is exact:** "the point estimate and standard error for the target coefficient are exactly equal to those of the analogous FE model with cluster-robust standard errors" (Hazlett & Wainstein). Default MLM SEs undercover; use cluster-robust or cluster bootstrap.
- **Why REWB rather than raw Mundlak:** group-mean centring removes the x/x̄ collinearity and makes the between coefficient directly interpretable (Bell & Jones 2015; Bell, Jones & Fairbrother 2018).

**Two caveats from the same literature.**

- **Few upper-level units.** Fine with thousands of counties; a problem if state statutes enter via a 50-state random intercept (Stegmueller 2013 *AJPS*; Elff et al. 2021 *BJPS* — REML + t-based inference fixes most of it).
- **Group-level covariates are between-group contrasts.** Hazlett & Wainstein: with group-level covariates bcMLM "can fail to eliminate potential biases" for those coefficients. County crime or sheriff budget effects are as confounded as a county-level cross-section; interpret them that way.

## Does it hold here?

**(a) Linear vs nonlinear, balanced vs unbalanced.**

- **Linear + unbalanced: exact.** Wooldridge (2019) proves FE on an unbalanced panel "is identical" to pooled OLS with means computed "over the time periods where we observe a full set of data" added; adding group size T_i, T_i × x̄_i, or size-specific coefficients on x̄_i leaves within coefficients unchanged.
- **Nonlinear: approximate, targets APEs.** Wooldridge (2019) models D(c_i | w_i) parametrically and says "at a minimum we should allow the variance of c_i to change with T_i"; T_i = 1 units "cannot be used to estimate the coefficients" of the within part.
- **GLM evidence:** Bai, Ferguson, Wainstein & Wells (2024, arXiv 2411.01723): "generalized forms of bcMLM and FE are not necessarily equivalent in the GLM setting." Schunck & Perales (2017): GLMM hybrid within-estimates "are not identical to those from standard fixed-effects models, which may lead to bias (Brumback et al. 2010)."
- **How bad can it get:** Neuhaus & Kalbfleisch (1998, *Biometrics*); Neuhaus & McCulloch (2006, *JRSS-B*); Goetgeluk & Vansteelandt (2008); Brumback et al. (2010, 2013) — bias up to 45% when the cluster effect is nonlinear in the cluster means. Allison's fix: add squared/cubed county means and see whether within coefficients move.

**(b) Small clusters — the real weakness.**

- **Uncorrected RE at n_g = 5 is "almost as biased as OLS"** (Hazlett & Wainstein, Fig. 2); corrected linear case is exact at any n_g.
- **GLM case: both FE and bcMLM show non-negligible bias at n_g = 5, residual bias at n_g = 25** (Bai et al. 2024). Many counties will have 1–3 camera-bearing places.
- **Singleton counties add nothing to within identification** (x − x̄ = 0); they only inform between coefficients.
- **Fix:** report the distribution of units per county; add log n_j (or bins), n_j × county-mean interactions, and an n_j-dependent intercept variance (glmmTMB `dispformula`; brms distributional syntax). The tract model (38,400 units) is much healthier.

**(c) Means computed on the ≥1-camera sample.**

- **Defensible by construction.** Part 2 models y | y > 0, so county dummies in a true FE truncated-NB would use the same subsample; Wooldridge (2019) shows means over selected observations are the right analogue, with selection allowed to be "arbitrarily correlated" with covariates and heterogeneity but not with shocks.
- **Caveat 1: noisy means in small counties attenuate between coefficients** (Bell & Jones fn. 14; Grilli & Rampichini 2011).
- **Caveat 2: independence of the two parts' county intercepts is an assumption.** brms can correlate them across parts (`(1 | c | county)`); cheap robustness check.

**(d) Normality of the random intercept.**

- **Least sensitive part.** Bell & Jones cite Beck & Katz: "RE models perform well, even when the Normality assumptions are violated"; Wooldridge (2019): once APEs are identified "we are free to use any number of approximations to the true distribution."
- **Correlation between random effect and covariates is itself a misspecified mixing distribution** (Neuhaus & McCulloch 2006) — that is what the county means repair.
- **Do:** plot county BLUPs; if ugly, Student-t intercept in the Bayesian model.

**(e) The software claim, and the better justification.**

- **Thousands of FE are fittable:** fixest `fenegbin`/`fepois`/`feglm` handle "any number of fixed-effects" (Bergé 2018); alpaca `feglm` + `biasCorr()` (Stammann 2018); glmmTMB `truncated_nbinom2` with `sparseX = c(cond = TRUE)` (Brooks et al. 2017, *R Journal*); Stata `ppmlhdfe` (Correia, Guimarães & Zylkin 2020, *Stata Journal*).
- **The real reason is incidental parameters.** Greene (2004, *Econometrics Journal*): "save for some well documented cases, such as the Poisson model, in which there actually is no incidental parameters problem," FE MLEs are "indeed biased, and in a few instances, substantially so even when T is fairly large"; ancillary parameters (variance, overdispersion) are biased even when slopes are not.
- **Logit specifics:** Katz (2001, *Political Analysis*) and Coupé (2005) document unconditional FE-logit bias at small T; Fernández-Val & Weidner (2016, *J. Econometrics*) give the analytical correction.
- **NB specifics:** Allison & Waterman (2002, *Sociological Methodology*) — Stata `xtnbreg, fe` is not a true FE estimator; dummy-variable NB is "encouraging" but unproven.
- **Poisson FE is the clean exception:** consistent under only the conditional-mean assumption (Wooldridge 1999, *J. Econometrics*; Santos Silva & Tenreyro 2006, *REStat*).
- **Bonus argument for CRE in the adoption logit:** county FE drop every all-zero / all-one county (Beck 2020, *Political Analysis*; Cook, Hays & Franzese 2020, *PSRM*); CRE keeps them.

## Three alternatives

### 1. FE two-part benchmark in fixest / alpaca

- **What it is:** county-FE logit for adoption (bias-corrected for tracts) + county-FE Poisson QMLE on positives, cluster-robust SEs.
- **Why here:** the credibility check reviewers will ask for — a table showing CRE within-coefficients match FE (Schunck & Perales' explicit advice). Poisson FE has no incidental-parameters bias (Greene 2004; Wooldridge 1999) and is robust to overdispersion.
- **Cost:** one afternoon. Loses county-level covariates and the truncated-NB interpretation; logit part still small-county biased; all-zero counties drop.
- **Cite:** Wooldridge 1999; Santos Silva & Tenreyro 2006; Greene 2004; Fernández-Val & Weidner 2016; Mullahy 1998 (*J. Health Econ.*, GLM second part of a two-part model); Bergé 2018; Stammann 2018.
- **R:** `fixest::fepois(cams ~ x | county, data = subset(d, cams > 0), vcov = ~county)`; `alpaca::biasCorr(alpaca::feglm(any ~ x | county, d, binomial()))`.

### 2. Bayesian hierarchical hurdle in brms

- **What it is:** joint hurdle-NB with county and state random intercepts, county means (CRE) plus county and state covariates entered directly, county intercepts correlated across parts, partial pooling.
- **Why here:** it is the "truly multilevel" model the student wants — cross-level covariates and interactions (statute × Trump share) with propagated uncertainty; Bayesian estimation is the safe route for cross-level interactions with a 50-unit upper level (Stegmueller 2013 *AJPS*). Cross-classified `(1 | place)` is one extra term.
- **Cost:** hours of sampling on 38k tracts (start with places; use cmdstanr + threads); priors to justify; county-level coefficients are still between-county contrasts (Hazlett & Wainstein). glmmTMB `truncated_nbinom2` + separate binomial fit is the fast frequentist stand-in.
- **Cite:** Gelman & Hill 2007 (ch. 12); McElreath 2020; Bürkner 2017 (*JSS*); Stegmueller 2013; Brooks et al. 2017.
- **R:** `brm(bf(cams ~ x_c + xbar + county_covs + state_covs + (1|c|county) + (1|state), hu ~ x_c + xbar + county_covs + state_covs + (1|c|county) + (1|state)), family = hurdle_negbinomial(), data = d)`.

### 3. Spatial dependence

- **What it is:** either a spatially structured county/tract random effect (BYM/ICAR in Stan or R-INLA; brms `car()`) or a spatial-lag term (share of neighbouring places with cameras) in the adoption logit.
- **Why here:** county intercepts absorb within-county common exposure, not cross-boundary contagion; Flock's regional-network sales model and policy-diffusion theory (Shipan & Volden 2008 *AJPS*) predict exactly that. Cook, Hays & Franzese (2020) and Franzese & Hays (2007 *PA*) argue theory should pick the spatial specification; Beck, Gleditsch & Beardsley (2006 *ISQ*) justify non-geographic "distance" (sales territories, shared sheriff).
- **Cost:** adjacency matrices; a simultaneity argument for the lag version; interpretation via spatial multipliers. Start with Moran's I on residuals — if near zero, this is a paragraph, not a model.
- **Cite:** Franzese & Hays 2007; Cook, Hays & Franzese 2020; Beck, Gleditsch & Beardsley 2006; Darmofal 2015; Morris et al. 2019 (BYM in Stan, tract-level example).
- **R:** `spdep::moran.test(resid, nb2listw(poly2nb(sf_places)))`; later `brm(..., + car(W, gr = county), ...)`.

**Why not the others.** REWB is not an alternative but the reparameterisation to adopt now; cross-classified effects are a one-line add-on inside #2; bias-corrected FE logit is folded into #1.

## Recommendation & sequencing (6 weeks, two other deadlines)

**Keep**

- The Cragg hurdle, the county CRE device, state FE in the county model.

**Change — week 1 (~2 days)**

- **Rewrite the methods text:** "REWB/CRE model (Mundlak 1978; Bell & Jones 2015; Wooldridge 2019; Hazlett & Wainstein 2022) that approximates county FE for lower-level covariates and, unlike FE, permits county- and state-level covariates." Delete "exact same information."
- **Replace the software excuse** with the incidental-parameters argument (Greene 2004; Fernández-Val & Weidner 2016) and the dropped-counties point (Beck 2020).
- **Group-mean-centre** the place/tract covariates (REWB form).
- **Add county-size terms:** log n_j and n_j × county-mean interactions (Wooldridge 2019); report units-per-county distribution.
- **Swap SEs** for a county cluster bootstrap (Hazlett & Wainstein; Bai et al.).
- **Add the county covariates you already have** (crime, police spending, sheriff budget) to place and tract models; label them between-county effects.

**Robustness — weeks 2–3 (~3 days)**

- **Alternative 1 table:** CRE within-coefficients vs FE-Poisson / FE-logit, place and tract.
- **Allison's polynomial-means check** (squared/cubed county means).
- **glmmTMB `truncated_nbinom2` with `sparseX` county dummies**, place model only, to show the truncated-NB FE numbers exist.

**Next-step model — weeks 3–5 (background compute)**

- **Alternative 2 in brms, place model:** county + state intercepts, state statutes, one cross-level interaction, correlated county intercepts across parts. Present as the dissertation direction, not the headline table.

**Diagnostics only — week 5 (1 day)**

- **Moran's I on residuals** by county and tract; a spatially lagged adoption share as one covariate. BYM after Nov 6.

**Write — week 6**

- **Flag honestly:** the GLM-CRE literature has not simulated truncated counts at n_g of 1–5; the FE-Poisson benchmark is doing the heavy lifting.

## Reading list

1. **Bell & Jones (2015) *PSRM*** — read first; the polisci statement of REWB with equations to cite.
2. **Hazlett & Wainstein (2022) *Political Analysis*** — the review, the exact-equivalence result, the SE and group-covariate warnings.
3. **Wooldridge (2019) *J. Econometrics*** — unbalanced groups, selected-sample means, T_i adjustments (secs. 2, 4, 6).
4. **Bai, Ferguson, Wainstein & Wells (2024) arXiv** — why equivalence is only approximate in GLMs; cluster bootstrap.
5. **Schunck & Perales (2017) *Stata Journal*** — GLMM hybrids; "compare to FE" advice.
6. **Greene (2004) *Econometrics Journal*** — the incidental-parameters evidence you need.
7. **Bell, Fairbrother & Jones (2019) *Quality & Quantity*** — cross-sectional multilevel framing.
8. **Wooldridge (2010), chs. 15.8 and 18.7** — CRE probit and count models.
9. **Bürkner (2017) *JSS* + brms hurdle docs** — for alternative 2.
10. **Franzese & Hays (2007) *PA*; Cook, Hays & Franzese (2020)** — spatial specification choice.
11. **Enders & Tofighi (2007)** — optional; centring rules.
12. **Clark & Linzer (2015) *PSRM*; Stegmueller (2013) *AJPS*** — optional; FE/RE trade-off; small upper level.

## Sources (URLs consulted)

- Bell & Jones 2015 PSRM: https://www.cambridge.org/core/journals/political-science-research-and-methods/article/explaining-fixed-effects-random-effects-modelling-of-timeseries-crosssectional-and-panel-data/0334A27557D15848549120FE8ECD8D63 ; preprint https://research-information.bris.ac.uk/ws/files/34439622/FixedvsRandom.pdf
- Bell, Fairbrother & Jones 2019: https://link.springer.com/article/10.1007/s11135-018-0802-x
- Bell, Jones & Fairbrother 2018 (group mean centering): https://link.springer.com/article/10.1007/s11135-017-0593-5
- Clark & Linzer 2015 PSRM: https://www.cambridge.org/core/journals/political-science-research-and-methods/article/abs/should-i-use-fixed-or-random-effects/12DFCB222123587A37163F2226E85C67
- Fairbrother 2014 PSRM: https://econpapers.repec.org/RePEc:cup:pscirm:v:2:y:2014:i:01:p:119-140_00
- Bartels 2008 PolMeth: https://home.gwu.edu/~bartels/cluster.pdf
- Hazlett & Wainstein 2022 PA: https://www.cambridge.org/core/journals/political-analysis/article/understanding-choosing-and-unifying-multilevel-and-fixed-effect-approaches/8101D49CFD3B129F5753FC878F416980
- Bai, Ferguson, Wainstein & Wells 2024: https://arxiv.org/abs/2411.01723
- Wooldridge 2019 J. Econometrics: https://econpapers.repec.org/RePEc:eee:econom:v:211:y:2019:i:1:p:137-150 ; working-paper text https://www.healtheconometrics.org/KeynotePaper2010.pdf
- Stata CRE news (`xtreg, cre`; `estat mundlak`): https://www.stata.com/stata-news/news39-4/correlated-random-effects-models/
- Schunck 2013 Stata Journal: https://journals.sagepub.com/doi/10.1177/1536867X1301300105
- Schunck & Perales 2017 Stata Journal: https://journals.sagepub.com/doi/10.1177/1536867X1701700106
- Neuhaus & Kalbfleisch 1998 Biometrics: https://www.semanticscholar.org/paper/2ba04fcc505715b6ba3577a69663e34a272f117e
- Neuhaus & McCulloch 2006 JRSS-B: https://academic.oup.com/jrsssb/article/68/5/859/7110607
- Brumback et al. 2010: https://www.sciencedirect.com/science/article/abs/pii/S0167715210002002
- Allison, "Problems with the hybrid method": https://statisticalhorizons.com/problems-with-the-hybrid-method/
- Allison, "Beware of software for FE negative binomial": https://statisticalhorizons.com/fe-nbreg/
- Allison & Waterman 2002 Soc. Methodology: https://onlinelibrary.wiley.com/doi/abs/10.1111/1467-9531.00117
- Greene 2004 Econometrics Journal: https://onlinelibrary.wiley.com/doi/10.1111/j.1368-423X.2004.00123.x ; text https://pages.stern.nyu.edu/~wgreene/nonlinearfixedeffects.pdf
- Fernández-Val & Weidner 2016 J. Econometrics: https://www.sciencedirect.com/science/article/pii/S0304407615002997
- Katz 2001 / Coupé 2005 Political Analysis: https://www.semanticscholar.org/paper/da3f80c5ab85a8b7e226e93e1bcebf7478c2322b ; https://econpapers.repec.org/RePEc:cup:polals:v:13:y:2005:i:03:p:292-295_00
- Beck 2020 Political Analysis: https://www.cambridge.org/core/journals/political-analysis/article/estimating-grouped-data-models-with-a-binarydependent-variable-and-fixed-effects-via-a-logit-versus-a-linear-probability-model-the-impact-of-dropped-units/AD6E3A3EA15BEDECA6B6FD49FE0216B3
- Cook, Hays & Franzese 2020 PSRM: https://sites.pitt.edu/~jch61/articles/fixed_effects.pdf
- Wooldridge 1999 J. Econometrics: https://www.sciencedirect.com/science/article/abs/pii/S0304407698000335
- Santos Silva & Tenreyro 2006: https://personal.lse.ac.uk/tenreyro/lgw.html
- Correia, Guimarães & Zylkin 2020 (ppmlhdfe): https://journals.sagepub.com/doi/10.1177/1536867X20909691
- fixest femlm/fenegbin: https://lrberge.github.io/fixest/reference/femlm.html ; walkthrough https://cran.r-project.org/web/packages/fixest/vignettes/fixest_walkthrough.html
- alpaca biasCorr: https://rdrr.io/cran/alpaca/man/biasCorr.html
- glmmTMB (truncated_nbinom2, sparseX): https://glmmtmb.github.io/glmmTMB/reference/glmmTMB.html ; Brooks et al. 2017 https://journal.r-project.org/articles/RJ-2017-066/
- brms: https://www.jstatsoft.org/v80/i01/ ; hurdle_negbinomial https://github.com/paul-buerkner/brms/blob/master/inst/chunks/fun_hurdle_negbinomial.stan
- Stegmueller 2013 AJPS: https://onlinelibrary.wiley.com/doi/abs/10.1111/ajps.12001
- Elff, Heisig, Schaeffer & Shikano 2021 BJPS: https://www.cambridge.org/core/journals/british-journal-of-political-science/article/multilevel-analysis-with-few-clusters-improving-likelihoodbased-methods-to-provide-unbiased-estimates-and-accurate-inference/B2328D08B0BB80C2A113DDCC52C4DD1D
- Enders & Tofighi 2007: https://pubmed.ncbi.nlm.nih.gov/17563168/
- Gelman & Hill 2007 ch. 12: https://spia.uga.edu/faculty_pages/tyler.scott/teaching/PADP8130_Spring2017/readings/gelman.hill.2007.ch12.pdf
- Dieleman & Templin 2014 PLoS ONE (+2016 correction): https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0110257
- Franzese & Hays 2007 PA: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1447745
- Cook, Hays & Franzese, "Model specification and spatial interdependence": https://www.sas.rochester.edu/psc/polmeth/papers/Cook_Hays_Franzese.pdf
- Beck, Gleditsch & Beardsley 2006 ISQ: https://academic.oup.com/isq/article-abstract/50/1/27/1818385
- Darmofal 2015: https://www.cambridge.org/core/books/abs/spatial-analysis-for-the-social-sciences/bibliography/88421108283441112899B0628DC0D10A
- Morris et al. 2019 (BYM in Stan): https://www.sciencedirect.com/science/article/abs/pii/S1877584518301175
- Shipan & Volden 2008 AJPS: https://onlinelibrary.wiley.com/doi/10.1111/j.1540-5907.2008.00346.x
- Mullahy 1998 J. Health Econ.: https://econpapers.repec.org/RePEc:eee:jhecon:v:17:y:1998:i:3:p:247-281
