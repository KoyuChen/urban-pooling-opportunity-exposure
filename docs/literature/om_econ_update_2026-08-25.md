# Adversarial OM/Econ literature update

**Project:** *Thicker but Narrower? Weakly Supervised Bounds on Opportunity Exposure in Urban Ride-Pooling Markets*  
**Search date:** 2026-08-25  
**Scope:** ride-pooling and market thickness; urban mobility segregation and homophily; partial identification and uncertain linkage.  
**Source rule:** the audit below uses version-of-record journal pages, DOI landing pages, or author/institutional publication pages. Items already in `paper/references.bib` are not repeated.

## Executive verdict

The joint contribution remains viable, but three neighboring literatures must be acknowledged more explicitly.

1. **The phrase “thicker but narrower” is not a free-standing novelty claim.** Li and Netessine (2020) already show that a thicker platform market can reduce the matching rate, while Ghili, Kumar, and Teng (2026) show that economies of density produce spatially unequal ride-sharing access. The paper should cite both in the introduction and define its distinct question immediately: not whether thickness raises aggregate service access or matching, but whether a policy-induced expansion of the *authorized rider pool* changes the socioeconomic composition of feasible, privacy-suppressed co-rider pairings.
2. **The paper cannot claim to be the first socioeconomic or homophily study of pooling.** Soria and Stathopoulos (2021) already show that pooled demand is positively associated with community disadvantage in the same Chicago data ecosystem, and Charles and Kline (2006) use commute carpooling to study cross-racial relational costs. The defensible distinction is the missing *within-vehicle pairing composition*, not the use of neighborhood SES or the idea that social frictions may shape carpooling. Chetty et al. (2022) further distinguish exposure from conditional friending bias: a feasible shared-ride pairing is an opportunity for co-presence, not a friendship, persistent tie, or preference for similar others.
3. **The closest methodological antecedent is constrained record linkage, not generic link prediction.** Sadinle (2017) already imposes global bipartite-matching constraints and quantifies linkage uncertainty. The manuscript's defensible difference is that it has one event file, no observed co-rider edges or cross-file identities, node-level match labels rather than labeled record pairs, and targets optimization bounds on a downstream exposure functional rather than a posterior/point estimate of the linkage itself.

No located paper combines all four elements: (i) privacy-suppressed ride-pooling groups; (ii) weak supervision from node-level match outcomes; (iii) exact global matching/set-packing constraints; and (iv) lower and upper bounds on an urban socioeconomic exposure estimand. The contribution should therefore be framed as **structured partial linkage for a scientific estimand**, not as a new ride-pooling matcher, a new segregation index, or a generic AI classifier.

## Twelve neighboring papers

### A. Ride-pooling, market thickness, and platform operations

#### 1. Li and Netessine (2020), “Higher Market Thickness Reduces Matching Rate in Online Platforms: Evidence from a Quasiexperiment,” *Management Science*

- **Core question.** Does increasing the number of participants necessarily improve platform matching?
- **Method/result.** A one-time migration of property listings creates a quasi-experiment on a peer-to-peer holiday-rental platform. Difference-in-differences estimates show that doubling market size lowers both traveler confirmation and host occupancy; the mechanism evidence points to greater search friction.
- **Adversarial comparison.** This paper already owns the broad counterintuitive claim that thickness can worsen matching. It is not ride-pooling and its mechanism is decentralized search, whereas the present project studies centrally constrained pooling and the composition of latent feasible pairings. Still, omitting it would make the title look unaware of the closest OM thickness result.
- **Placement.** Final paragraph of the Introduction and the opening “shareability and dynamic pooling” paragraph. Use it to say aggregate matching and compositional exposure are separate margins.
- **Primary source.** [INFORMS / DOI](https://doi.org/10.1287/mnsc.2018.3223)

#### 2. Ghili, Kumar, and Teng (2026), “Spatial Distribution of Access to Service: Theory and Evidence from Ride-Sharing,” *Management Science*

- **Core question.** How do economies of density distribute ride-sharing access across dense and sparse urban regions?
- **Method/result.** A spatial platform model predicts that density economies skew access away from less dense regions, particularly on smaller/thinner platforms; price and wage instruments mitigate but do not eliminate the skew. The model is calibrated with ride-level Uber data from New York City.
- **Adversarial comparison.** This is the closest operational-and-spatial competitor. Its outcome is access to ride-sharing service by location, while the proposed estimand is the socioeconomic composition of feasible co-rider encounters conditional on authorization/matching. The manuscript must avoid using “access” without the modifier *opportunity exposure*, or reviewers may see the contribution as a noisy remeasurement of Ghili et al.
- **Placement.** “Efficiency, fairness, and the Chicago evidence,” before the Chicago-specific studies; also one sentence in the Introduction.
- **Primary source.** [INFORMS / DOI](https://doi.org/10.1287/mnsc.2021.02699)

#### 3. Lobel and Martin (2025), “Detours in Shared Rides,” *Management Science*

- **Core question.** What is the Pareto frontier between value generated by shared rides and rider detours?
- **Method/result.** The paper derives a tight value--detour bound, computes the frontier for a family of city topologies, and simulates other networks including Manhattan. Request density is more important than detours for effective shared-ride operations.
- **Adversarial comparison.** It makes density and feasible request combinations central, but assumes requests and their feasible groupings are available to the operator. The current paper observes privacy-coarsened public records and bounds a distributional property of the unknown grouping. It therefore complements rather than replaces Lobel and Martin's operational frontier.
- **Placement.** “Shareability and dynamic pooling,” after Santi et al. and Alonso-Mora et al.; one compact sentence is sufficient.
- **Primary source.** [INFORMS / DOI](https://doi.org/10.1287/mnsc.2020.03125)

#### 4. Yan, Yan, and Shen (2026), “Pricing Shared Rides,” *Operations Research*

- **Core question.** Why do static shared-ride prices perform poorly, and can prices contingent on realized matching improve platform and rider outcomes?
- **Method/result.** A single-origin--destination analytical model yields a match-based pricing policy; a large-scale simulation over hundreds of Chicago origin--destination pairs validates the mechanism. Gains are especially large when costs are high and demand density is low.
- **Adversarial comparison.** This paper is unusually close in application, data geography, and the role of matching. It observes/simulates matching outcomes to design prices; the present project instead uses a public Chicago observation operator that suppresses the co-rider group and asks a distributional exposure question. It should be cited in the Chicago-policy paragraph, particularly because both papers use Chicago data and density as a mechanism.
- **Placement.** “Efficiency, fairness, and the Chicago evidence,” immediately before the Chicago tax studies.
- **Primary source.** [INFORMS / DOI](https://doi.org/10.1287/opre.2023.0513)

### B. Urban exposure, segregation, and homophily

#### 5. Soria and Stathopoulos (2021), “Investigating Socio-spatial Differences between Solo Ridehailing and Pooled Rides in Diverse Communities,” *Journal of Transport Geography*

- **Core question.** Do solo and pooled ride-hailing demand have different socioeconomic and spatial correlates across Chicago communities?
- **Method/result.** The authors combine roughly 127 million Chicago trips (15% pooled) with a Social Disadvantage Index and transit-access measures, then estimate a Spatial Durbin Model. Community disadvantage is positively associated with pooled demand and negatively associated with solo demand; rail access predicts both and generates spatial spillovers.
- **Adversarial comparison.** This is the closest substantive Chicago predecessor and rules out any claim that the paper is first to connect pooling with socioeconomic geography. Its unit is aggregate trip demand by community, however; it does not observe or infer which authorized riders share a vehicle and therefore cannot measure within-pair assortativity or propagate suppressed-group uncertainty into exposure bounds.
- **Placement.** “Efficiency, fairness, and the Chicago evidence,” before Taiebat et al.; describe it as the aggregate socioeconomic-demand benchmark.
- **Primary source.** [Elsevier / DOI](https://doi.org/10.1016/j.jtrangeo.2021.103148)

#### 6. Charles and Kline (2006), “Relational Costs and the Production of Social Capital: Evidence from Carpooling,” *The Economic Journal*

- **Core question.** Do cross-racial relational frictions reduce participation in an activity requiring social connection, namely commute carpooling?
- **Method/result.** The paper relates individual carpool use to neighborhood racial composition, using historical state-of-birth racial composition as an instrument and adding neighborhood and sorting checks. It finds substantial cross-racial relational difficulties for particular group pairs.
- **Adversarial comparison.** This is the closest economics citation to the user's original “homophily + carpool” intuition. It studies the decision to form/use conventional commute carpools and interprets racial composition through relational costs. The current project studies algorithmically generated ride-pooling opportunities, has no individual race or stable identity, and cannot infer preferences from tract-proxy pairing composition. It therefore must avoid claiming that its bounds estimate homophily.
- **Placement.** Opening of “Urban mobility and experienced segregation,” followed immediately by the exposure-versus-preference limitation.
- **Primary source.** [Oxford Academic / DOI](https://doi.org/10.1111/j.1468-0297.2006.01093.x)

#### 7. Davis, Dingel, Monras, and Morales (2019), “How Segregated Is Urban Consumption?,” *Journal of Political Economy*

- **Core question.** How segregated are urban consumption choices, and how much is due to spatial versus social frictions?
- **Method/result.** Yelp review histories in New York City identify restaurant visits; a choice framework separates transit-time frictions from reluctance to visit demographically dissimilar neighborhoods. Consumption is less segregated than residence, but social frictions contribute more than spatial frictions.
- **Adversarial comparison.** This is a stronger urban-economics anchor than a purely descriptive mobility citation. It observes venue choice and estimates spatial/social frictions; the current paper has neither persistent individuals nor realized destination choice and therefore only measures tract-proxy assortativity of feasible pooling opportunities. The contrast sharpens the “opportunity, not preference” claim.
- **Placement.** First citation in “Urban mobility and experienced segregation,” before the mobile-device studies.
- **Primary source.** [University of Chicago Press / DOI](https://doi.org/10.1086/701680)

#### 8. Athey, Ferguson, Gentzkow, and Schmidt (2021), “Estimating Experienced Racial Segregation in U.S. Cities Using Large-Scale GPS Data,” *PNAS*

- **Core question.** How different is segregation in people's daily activity spaces from residential segregation?
- **Method/result.** Large-scale smartphone GPS data produce an experienced-isolation measure. Experienced segregation is lower than residential segregation, though the two remain strongly correlated across cities; transit use and urban density are associated with the gap.
- **Adversarial comparison.** The paper is close in motivation and explicitly urban/economic, but it measures inferred co-location at visited places using individual mobility traces. The current project lacks persistent persons and instead considers candidate dyadic co-rides under a known privacy operator. It should be cited alongside, rather than replaced by, Wang et al. (2018).
- **Placement.** “Urban mobility and experienced segregation,” immediately after Davis et al.
- **Primary source.** [PNAS DOI](https://doi.org/10.1073/pnas.2026160118); [Stanford author record](https://gsbpreserve.stanford.edu/view/58195/estimating-experienced-racial-segregation-in-us-cities-using-large-scale-gps-data)

#### 9. Chetty et al. (2022), “Social Capital II: Determinants of Economic Connectedness,” *Nature*

- **Core question.** Is cross-class disconnection driven by a lack of exposure to high-SES people or by lower friendship formation conditional on exposure?
- **Method/result.** Facebook friendship data for 70.3 million U.S. users decompose economic connectedness into exposure and friending bias; quasi-experimental cohort variation shows that additional exposure translates into friendships mainly where friending bias is low.
- **Adversarial comparison.** This paper supplies the exact conceptual boundary the manuscript needs. A candidate co-ride can at most alter exposure; it cannot reveal friendship, preference, or homophily. Calling the outcome an “echo chamber” would therefore overclaim. The paper also cautions that exposure/friending-bias decompositions depend on the level at which the opportunity set is defined.
- **Placement.** Closing paragraph of “Urban mobility and experienced segregation” and again in Limitations, if page budget permits.
- **Primary source.** [Nature / DOI](https://doi.org/10.1038/s41586-022-04997-3)

### C. Uncertain linkage, missing networks, and partial identification

#### 10. Sadinle (2017), “Bayesian Estimation of Bipartite Matchings for Record Linkage,” *Journal of the American Statistical Association*

- **Core question.** How should records be linked across two files when unique identifiers are absent and pairwise linkage decisions are mutually dependent?
- **Method/result.** The latent parameter is a global bipartite matching, not independent pair labels. A Bayesian model quantifies uncertainty over admissible matchings and permits a reject option that leaves uncertain links unresolved.
- **Adversarial comparison.** This is the closest methodological antecedent because it explicitly enforces one-to-one assignment structure. The differences must be stated, not implied: the present data contain one trip file rather than two entity files; no co-rider link is directly observed; the weak labels live on nodes; and the output is a bound on an exposure functional across feasible pairings, not a posterior or Bayes point estimate of identity linkage.
- **Placement.** Add a short new paragraph, “Uncertain linkage and partial identification,” between the Chicago evidence and urban-mobility paragraphs.
- **Primary source.** [Taylor & Francis / DOI](https://doi.org/10.1080/01621459.2016.1148612)

#### 11. Sheng (2020), “A Structural Econometric Analysis of Network Formation Games Through Subnetworks,” *Econometrica*

- **Core question.** How can preferences in strategic network-formation games be estimated when multiple equilibria prevent point identification?
- **Method/result.** With an observed network and unrestricted equilibrium selection, small-subnetwork probability inequalities deliver computationally tractable bounds on structural parameters.
- **Adversarial comparison.** Sheng's uncertainty comes from equilibrium multiplicity given an observed graph; here uncertainty comes from a privacy observation operator that removes the realized graph. The present method imposes physical compatibility and exact-cover constraints without specifying a utility or equilibrium-selection model. This distinction is valuable because it prevents reviewers from reading the bounds as structural preference estimates.
- **Placement.** Same method paragraph, as the economics partial-identification anchor.
- **Primary source.** [Econometrica / DOI](https://doi.org/10.3982/ECTA12558)

#### 12. Gualdani and Sinha (2023), “Partial Identification in Matching Models for the Marriage Market,” *Journal of Political Economy*

- **Core question.** What features of preferences in a one-to-one transferable-utility matching market remain identified without parametric assumptions on unobserved heterogeneity?
- **Method/result.** The authors characterize tractable identified sets using one large observed marriage market and several nonparametric distributional restrictions, showing that familiar substantive conclusions can be driven by logit assumptions.
- **Adversarial comparison.** This is a high-level economics precedent for resisting a point-imputed matching story, but the observed marriage matches are known and the unknown objects are preference parameters. In the current paper the pairing itself is missing, the goal is a realized opportunity-exposure functional, and bounds follow from compatibility/packing rather than stability plus distributional assumptions.
- **Placement.** Final citation in “Uncertain linkage and partial identification.”
- **Primary source.** [University of Chicago Press / DOI](https://doi.org/10.1086/722415)

## Six references that should enter the main bibliography now

These six cover the largest current omissions with minimal citation load: the thickness reversal, spatial access, Chicago's socioeconomic pooling-demand gradient, the direct carpooling/homophily precedent, the exposure-versus-homophily distinction, and globally constrained uncertain linkage.

```bibtex
@article{linetessine2020thickness,
  author  = {Li, Jun and Netessine, Serguei},
  title   = {Higher Market Thickness Reduces Matching Rate in Online Platforms: Evidence from a Quasiexperiment},
  journal = {Management Science},
  year    = {2020},
  volume  = {66},
  number  = {1},
  pages   = {271--289},
  doi     = {10.1287/mnsc.2018.3223}
}

@article{ghili2026access,
  author  = {Ghili, Soheil and Kumar, Vineet and Teng, Fei},
  title   = {Spatial Distribution of Access to Service: Theory and Evidence from Ride-Sharing},
  journal = {Management Science},
  year    = {2026},
  note    = {Articles in Advance},
  doi     = {10.1287/mnsc.2021.02699}
}

@article{soria2021sociospatial,
  author  = {Soria, Jason and Stathopoulos, Amanda},
  title   = {Investigating Socio-Spatial Differences between Solo Ridehailing and Pooled Rides in Diverse Communities},
  journal = {Journal of Transport Geography},
  year    = {2021},
  volume  = {95},
  pages   = {103148},
  doi     = {10.1016/j.jtrangeo.2021.103148}
}

@article{charleskline2006carpooling,
  author  = {Charles, Kerwin Kofi and Kline, Patrick},
  title   = {Relational Costs and the Production of Social Capital: Evidence from Carpooling},
  journal = {The Economic Journal},
  year    = {2006},
  volume  = {116},
  number  = {511},
  pages   = {581--604},
  doi     = {10.1111/j.1468-0297.2006.01093.x}
}

@article{chetty2022socialcapital2,
  author  = {Chetty, Raj and Jackson, Matthew O. and Kuchler, Theresa and Stroebel, Johannes and others},
  title   = {Social Capital {II}: Determinants of Economic Connectedness},
  journal = {Nature},
  year    = {2022},
  volume  = {608},
  pages   = {122--134},
  doi     = {10.1038/s41586-022-04997-3}
}

@article{sadinle2017linkage,
  author  = {Sadinle, Mauricio},
  title   = {Bayesian Estimation of Bipartite Matchings for Record Linkage},
  journal = {Journal of the American Statistical Association},
  year    = {2017},
  volume  = {112},
  number  = {518},
  pages   = {600--612},
  doi     = {10.1080/01621459.2016.1148612}
}

```

## Paste-ready English related-work text

> Market thickness need not monotonically improve platform outcomes: Li and Netessine exploit a quasi-experimental expansion of an online market and find that greater thickness can reduce matching through search frictions \citep{linetessine2020thickness}, while Ghili, Kumar, and Teng show that economies of density in ride-sharing generate spatially unequal service access that pricing and wages only partly offset \citep{ghili2026access}. Our question concerns a different margin. We ask whether an expansion of the authorized pooling set changes the socioeconomic composition of *feasible co-rider opportunities* when the public observation operator removes the realized groups; we do not equate thickness with service access or aggregate matching. Using the same Chicago data ecosystem, Soria and Stathopoulos show that community disadvantage is positively associated with pooled demand \citep{soria2021sociospatial}, while Charles and Kline use commute carpooling to study cross-racial relational costs \citep{charleskline2006carpooling}. Neither paper observes the socioeconomic composition of algorithmically formed co-rider pairs. Following Chetty et al.'s distinction between exposure and conditional tie formation \citep{chetty2022socialcapital2}, we therefore interpret a feasible co-ride as an opportunity for co-presence, not evidence of friendship, preference-based homophily, or an echo chamber. Methodologically, Sadinle models uncertain record linkage as a globally constrained bipartite matching rather than independent pair classifications \citep{sadinle2017linkage}. We instead observe one privacy-coarsened event file with node-level match labels but no co-rider edges: weak supervision scores candidate edges, exact-cover constraints retain jointly feasible pairings, and optimization propagates the remaining linkage uncertainty directly into bounds on an exposure functional.

## Recommended insertion order under the eight-page constraint

1. Add Li--Netessine and Ghili--Kumar--Teng in two sentences to the existing first/second related-work paragraphs.
2. Add Soria--Stathopoulos and Charles--Kline; these are essential because they block overbroad “first socioeconomic pooling/homophily” language.
3. Add one three-to-four-sentence paragraph on Sadinle; this is the most important missing methodological positioning. Gualdani--Sinha can be added in the same sentence if space permits.
4. Add Chetty et al. by replacing, rather than merely expanding, repetitive language in the current urban-mobility paragraph.
5. Keep Lobel--Martin, Taylor, Yan--Yan--Shen, Davis et al., Athey et al., Zhao et al., and Sheng in the extended/appendix bibliography unless space can be recovered. Yan--Yan--Shen should move into the main text if the Chicago policy analysis becomes a headline empirical contribution.

## Monthly-search watch terms

For future automated runs, query exact combinations rather than broad “AI for cities” terms:

- `ride pooling` AND (`market thickness` OR `demand density`) in *Management Science*, *Operations Research*, *M&SOM*, and *Transportation Science*;
- (`ride sharing` OR `mobility platform`) AND (`access` OR `spatial inequality` OR `segregation`);
- (`experienced segregation` OR `urban mixing`) AND (`transport` OR `co-presence` OR `mobility`);
- (`record linkage` OR `partially observed network`) AND (`matching constraint` OR `downstream inference` OR `partial identification`);
- (`weak supervision` OR `multiple-instance learning`) AND (`matching` OR `latent graph` OR `set packing`).

Each monthly run should first diff DOI strings against `paper/references.bib`, then report only genuinely new or newly published items and explicitly classify each as **threatens novelty**, **strengthens motivation**, **method precedent**, or **not close after inspection**.
