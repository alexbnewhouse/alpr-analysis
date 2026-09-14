# References to add to `ref.bib`

Grouped by where they'd be cited. Page numbers marked `% verify` should be checked before compiling. The Mundlak review (`mundlak-review.md`) may add more.

## Methods — multilevel / Mundlak / FE

```bibtex
@article{steenbergen2002modeling,
  title   = {Modeling Multilevel Data Structures},
  author  = {Steenbergen, Marco R. and Jones, Bradford S.},
  journal = {American Journal of Political Science},
  volume  = {46}, number = {1}, pages = {218--237}, year = {2002}
}

@article{bell2015explaining,
  title   = {Explaining Fixed Effects: Random Effects Modeling of Time-Series Cross-Sectional and Panel Data},
  author  = {Bell, Andrew and Jones, Kelvyn},
  journal = {Political Science Research and Methods},
  volume  = {3}, number = {1}, pages = {133--153}, year = {2015}
}

@article{bell2019fixed,
  title   = {Fixed and Random Effects Models: Making an Informed Choice},
  author  = {Bell, Andrew and Fairbrother, Malcolm and Jones, Kelvyn},
  journal = {Quality \& Quantity},
  volume  = {53}, pages = {1051--1074}, year = {2019}
}

@article{enders2007centering,
  title   = {Centering Predictor Variables in Cross-Sectional Multilevel Models: A New Look at an Old Issue},
  author  = {Enders, Craig K. and Tofighi, Davood},
  journal = {Psychological Methods},
  volume  = {12}, number = {2}, pages = {121--138}, year = {2007}
}

@book{gelman2007data,
  title     = {Data Analysis Using Regression and Multilevel/Hierarchical Models},
  author    = {Gelman, Andrew and Hill, Jennifer},
  publisher = {Cambridge University Press}, year = {2007}
}

@article{stegmueller2013many,
  title   = {How Many Countries for Multilevel Modeling? A Comparison of Frequentist and Bayesian Approaches},
  author  = {Stegmueller, Daniel},
  journal = {American Journal of Political Science},
  volume  = {57}, number = {3}, pages = {748--761}, year = {2013}
}

@article{heisig2019why,
  title   = {Why You Should Always Include a Random Slope for the Lower-Level Variable Involved in a Cross-Level Interaction},
  author  = {Heisig, Jan Paul and Schaeffer, Merlin},
  journal = {European Sociological Review},
  volume  = {35}, number = {2}, pages = {258--279}, year = {2019}
}

@book{wooldridge2010econometric,
  title     = {Econometric Analysis of Cross Section and Panel Data},
  author    = {Wooldridge, Jeffrey M.},
  edition   = {2}, publisher = {MIT Press}, year = {2010}
}

@article{fernandezval2016individual,
  title   = {Individual and Time Effects in Nonlinear Panel Models with Large N, T},
  author  = {Fern{\'a}ndez-Val, Iv{\'a}n and Weidner, Martin},
  journal = {Journal of Econometrics},
  volume  = {192}, number = {1}, pages = {291--312}, year = {2016}
}

@article{neyman1948consistent,
  title   = {Consistent Estimates Based on Partially Consistent Observations},
  author  = {Neyman, Jerzy and Scott, Elizabeth L.},
  journal = {Econometrica},
  volume  = {16}, number = {1}, pages = {1--32}, year = {1948}
}

@article{mullahy1986specification,
  title   = {Specification and Testing of Some Modified Count Data Models},
  author  = {Mullahy, John},
  journal = {Journal of Econometrics},
  volume  = {33}, number = {3}, pages = {341--365}, year = {1986}
}
% Mullahy is the canonical *count* hurdle; Cragg 1971 is the two-part idea. Cite both.

@article{wooldridge1999distribution,
  title   = {Distribution-Free Estimation of Some Nonlinear Panel Data Models},
  author  = {Wooldridge, Jeffrey M.},
  journal = {Journal of Econometrics},
  volume  = {90}, number = {1}, pages = {77--97}, year = {1999}
}

@article{silva2006log,
  title   = {The Log of Gravity},
  author  = {Santos Silva, J. M. C. and Tenreyro, Silvana},
  journal = {The Review of Economics and Statistics},
  volume  = {88}, number = {4}, pages = {641--658}, year = {2006}
}
```

## Software

```bibtex
@article{brooks2017glmmtmb,
  title   = {{glmmTMB} Balances Speed and Flexibility Among Packages for Zero-Inflated Generalized Linear Mixed Modeling},
  author  = {Brooks, Mollie E. and Kristensen, Kasper and van Benthem, Koen J. and Magnusson, Arni and Berg, Casper W. and Nielsen, Anders and Skaug, Hans J. and M{\"a}chler, Martin and Bolker, Benjamin M.},
  journal = {The R Journal},
  volume  = {9}, number = {2}, pages = {378--400}, year = {2017}
}

@article{burkner2017brms,
  title   = {{brms}: An {R} Package for Bayesian Multilevel Models Using {Stan}},
  author  = {B{\"u}rkner, Paul-Christian},
  journal = {Journal of Statistical Software},
  volume  = {80}, number = {1}, pages = {1--28}, year = {2017}
}

@article{bates2015fitting,
  title   = {Fitting Linear Mixed-Effects Models Using {lme4}},
  author  = {Bates, Douglas and M{\"a}chler, Martin and Bolker, Ben and Walker, Steve},
  journal = {Journal of Statistical Software},
  volume  = {67}, number = {1}, pages = {1--48}, year = {2015}
}

@article{zeileis2008regression,
  title   = {Regression Models for Count Data in {R}},
  author  = {Zeileis, Achim and Kleiber, Christian and Jackman, Simon},
  journal = {Journal of Statistical Software},
  volume  = {27}, number = {8}, pages = {1--25}, year = {2008}
}

@misc{berge2018fixest,
  title  = {Efficient Estimation of Maximum Likelihood Models with Multiple Fixed-Effects: The {R} Package {FENmlm}},
  author = {Berg{\'e}, Laurent},
  year   = {2018}, note = {CREA Discussion Paper 2018-13; the {fixest} package} % verify
}
```

## Crime data quality

```bibtex
@article{maltz2002note,
  title   = {A Note on the Use of County-Level {UCR} Data},
  author  = {Maltz, Michael D. and Targonski, Joseph},
  journal = {Journal of Quantitative Criminology},
  volume  = {18}, number = {3}, pages = {297--318}, year = {2002}
}

@misc{kaplan2024ucr,
  title     = {Jacob {Kaplan}'s Concatenated Files: Uniform Crime Reporting Program Data: Offenses Known and Clearances by Arrest (Return A), 1960--2024},
  author    = {Kaplan, Jacob},
  year      = {2024}, % verify version year
  publisher = {Inter-university Consortium for Political and Social Research [distributor]},
  note      = {openICPSR project 100707}
}

@misc{bjs2023lemas,
  title     = {Law Enforcement Management and Administrative Statistics ({LEMAS}), 2020},
  author    = {{Bureau of Justice Statistics}},
  year      = {2023},
  publisher = {Inter-university Consortium for Political and Social Research [distributor]},
  note      = {ICPSR 38651}
}

@misc{bjs2023csllea,
  title     = {Census of State and Local Law Enforcement Agencies ({CSLLEA}), 2018},
  author    = {{Bureau of Justice Statistics}},
  year      = {2023},
  publisher = {Inter-university Consortium for Political and Social Research [distributor]},
  note      = {ICPSR 38771}
}

@misc{census2024cog,
  title     = {2022 Census of Governments: Finance Component, Individual Unit Files},
  author    = {{U.S. Census Bureau}},
  year      = {2024}, month = oct,
  howpublished = {\url{https://www.census.gov/data/datasets/2022/econ/local/public-use-datasets.html}}
}
```

## Sheriffs, local politics, ALPR

```bibtex
@book{farris2024power,
  title     = {The Power of the Badge: Sheriffs and Inequality in the United States},
  author    = {Farris, Emily M. and Holman, Mirya R.},
  publisher = {University of Chicago Press}, year = {2024} % verify year/publisher
}

@article{thompson2020partisan,
  title   = {How Partisan Is Local Law Enforcement? Evidence from Sheriff Cooperation with Immigration Authorities},
  author  = {Thompson, Daniel M.},
  journal = {American Political Science Review},
  volume  = {114}, number = {1}, pages = {222--236}, year = {2020}
}

@article{su2025playing,
  title   = {Playing Politics with Traffic Fines: Sheriff Elections and Political Cycles in Traffic Fines Revenue},
  author  = {Su, Min},
  journal = {American Journal of Political Science},
  year    = {2025}, note = {doi:10.1111/ajps.12866} % verify author first name/volume
}

@article{clarke2019rise,
  title   = {The Rise and Effects of Homeowners Associations},
  author  = {Clarke, Wyatt and Freedman, Matthew},
  journal = {Journal of Urban Economics},
  volume  = {112}, pages = {1--15}, year = {2019} % verify pages
}

@article{cheung2014why,
  title   = {Why and Where Do Homeowners Associations Form?},
  author  = {Cheung, Ron and Meltzer, Rachel},
  journal = {Cityscape},
  volume  = {16}, number = {3}, pages = {69--92}, year = {2014} % verify
}

@article{lum2019license,
  title   = {License Plate Reader (LPR) Police Expansion and Crime Deterrence},
  author  = {Lum, Cynthia and Koper, Christopher S. and Willis, James and Happeny, Stephen and Vovak, Heather and Nichols, Jordan},
  journal = {Justice Quarterly}, year = {2019} % verify — may be the "How Police Use LPRs" NIJ report instead
}

@techreport{crs2024alpr,
  title       = {Law Enforcement and Technology: Use of Automated License Plate Readers},
  author      = {{Congressional Research Service}},
  number      = {R48160}, year = {2024},
  institution = {Congressional Research Service}
}
% Useful for the ALPR overview section: has the LEMAS adoption numbers by agency size.
```

## Added from the Mundlak review (2026-09-13)

```bibtex
@article{hazlett2022understanding,
  title   = {Understanding, Choosing, and Unifying Multilevel and Fixed Effect Approaches},
  author  = {Hazlett, Chad and Wainstein, Leonard},
  journal = {Political Analysis},
  volume  = {30}, number = {1}, pages = {46--65}, year = {2022}
}

@misc{bai2024bcmlm,
  title  = {Bias-Corrected Multilevel Models for Generalized Linear Models},
  author = {Bai, Xinyu and Ferguson, Jake and Wainstein, Leonard and Wells, Martin T.},
  year   = {2024}, note = {arXiv:2411.01723} % verify title/author list
}

@article{wooldridge2019correlated,
  title   = {Correlated Random Effects Models with Unbalanced Panels},
  author  = {Wooldridge, Jeffrey M.},
  journal = {Journal of Econometrics},
  volume  = {211}, number = {1}, pages = {137--150}, year = {2019}
}

@article{schunck2017within,
  title   = {Within- and Between-Cluster Effects in Generalized Linear Mixed Models: A Discussion of Approaches and the {xthybrid} Command},
  author  = {Schunck, Reinhard and Perales, Francisco},
  journal = {The Stata Journal},
  volume  = {17}, number = {1}, pages = {89--115}, year = {2017}
}

@article{greene2004behaviour,
  title   = {The Behaviour of the Maximum Likelihood Estimator of Limited Dependent Variable Models in the Presence of Fixed Effects},
  author  = {Greene, William},
  journal = {The Econometrics Journal},
  volume  = {7}, number = {1}, pages = {98--119}, year = {2004}
}

@article{beck2020estimating,
  title   = {Estimating Grouped Data Models with a Binary-Dependent Variable and Fixed Effects via a Logit versus a Linear Probability Model: The Impact of Dropped Units},
  author  = {Beck, Nathaniel},
  journal = {Political Analysis},
  volume  = {28}, number = {1}, pages = {139--145}, year = {2020}
}

@article{cook2020fixed,
  title   = {Fixed Effects in Rare Events Data: A Penalized Maximum Likelihood Solution},
  author  = {Cook, Scott J. and Hays, Jude C. and Franzese, Robert J.},
  journal = {Political Science Research and Methods},
  volume  = {8}, number = {1}, pages = {92--105}, year = {2020}
}

@article{franzese2007spatial,
  title   = {Spatial Econometric Models of Cross-Sectional Interdependence in Political Science Panel and Time-Series-Cross-Section Data},
  author  = {Franzese, Robert J. and Hays, Jude C.},
  journal = {Political Analysis},
  volume  = {15}, number = {2}, pages = {140--164}, year = {2007}
}

@article{shipan2008mechanisms,
  title   = {The Mechanisms of Policy Diffusion},
  author  = {Shipan, Charles R. and Volden, Craig},
  journal = {American Journal of Political Science},
  volume  = {52}, number = {4}, pages = {840--857}, year = {2008}
}

@article{clark2015should,
  title   = {Should I Use Fixed or Random Effects?},
  author  = {Clark, Tom S. and Linzer, Drew A.},
  journal = {Political Science Research and Methods},
  volume  = {3}, number = {2}, pages = {399--408}, year = {2015}
}

@article{fairbrother2014two,
  title   = {Two Multilevel Modeling Techniques for Analyzing Comparative Longitudinal Survey Datasets},
  author  = {Fairbrother, Malcolm},
  journal = {Political Science Research and Methods},
  volume  = {2}, number = {1}, pages = {119--140}, year = {2014}
}

@article{elff2021multilevel,
  title   = {Multilevel Analysis with Few Clusters: Improving Likelihood-Based Methods to Provide Unbiased Estimates and Accurate Inference},
  author  = {Elff, Martin and Heisig, Jan Paul and Schaeffer, Merlin and Shikano, Susumu},
  journal = {British Journal of Political Science},
  volume  = {51}, number = {1}, pages = {412--426}, year = {2021}
}

@book{allison2009fixed,
  title     = {Fixed Effects Regression Models},
  author    = {Allison, Paul D.},
  publisher = {Sage}, year = {2009}
}

@article{allison2002fixed,
  title   = {Fixed-Effects Negative Binomial Regression Models},
  author  = {Allison, Paul D. and Waterman, Richard P.},
  journal = {Sociological Methodology},
  volume  = {32}, number = {1}, pages = {247--265}, year = {2002}
}

@article{mullahy1998much,
  title   = {Much Ado About Two: Reconsidering Retransformation and the Two-Part Model in Health Econometrics},
  author  = {Mullahy, John},
  journal = {Journal of Health Economics},
  volume  = {17}, number = {3}, pages = {247--281}, year = {1998}
}

@article{correia2020fast,
  title   = {Fast {Poisson} Estimation with High-Dimensional Fixed Effects},
  author  = {Correia, Sergio and Guimar{\~a}es, Paulo and Zylkin, Tom},
  journal = {The Stata Journal},
  volume  = {20}, number = {1}, pages = {95--115}, year = {2020}
}

@misc{stammann2018alpaca,
  title  = {Fast and Feasible Estimation of Generalized Linear Models with High-Dimensional k-Way Fixed Effects},
  author = {Stammann, Amrei},
  year   = {2018}, note = {arXiv:1707.01815; R package alpaca}
}

@article{morris2019bayesian,
  title   = {Bayesian Hierarchical Spatial Models: Implementing the {Besag York Molli\'e} Model in {Stan}},
  author  = {Morris, Mitzi and Wheeler-Martin, Katherine and Simpson, Dan and Mooney, Stephen J. and Gelman, Andrew and DiMaggio, Charles},
  journal = {Spatial and Spatio-temporal Epidemiology},
  volume  = {31}, pages = {100301}, year = {2019}
}
```
