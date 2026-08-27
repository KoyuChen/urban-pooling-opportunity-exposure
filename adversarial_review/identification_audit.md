# Identification Audit

## Audit verdict

The frozen manuscript's observation target is incorrect. For a customer
transaction with `Shared Trip Match = true` and `Trips Pooled = 2`, the City
field definitions reveal that realized co-presence occurred and that the sole
other transaction in the hidden empty-to-empty run is its co-present partner.
The missing object is the partner identity, not the existence of co-presence
and not a platform opportunity set.

The score-free optimization has a valid but narrower interpretation: it gives
attained lower and upper endpoints of a transaction-pair statistic conditional
on a declared candidate graph, a correct chain-complete node population, and a
globally optimal exact cover. The present candidate graph is not a justified
coverage graph, the complete-case preprocessing can generate entirely false
pairings, and the current policy functional is not an intention-to-treat
effect. The learned score does not identify edge probabilities.

## 1. Official observation operator

The [Chicago TNP Reporting Manual](https://chicago.github.io/tnp-reporting-manual/trip/)
defines a trip as one transaction with a specific customer. A separately
booked customer is a separate transaction even when simultaneously present in
the vehicle. It defines:

- `Shared Trip Authorized`: the customer agreed to shared service, whether or
  not sharing occurred;
- `Shared Trip ID`: the complete empty-to-empty vehicle run identifier required
  in provider reporting but not published in the public trip table;
- `Shared Trip Match`: the passenger shared the vehicle with a separately
  booked passenger at some point during the trip.

The [public dataset documentation](https://dev.socrata.com/foundry/data.cityofchicago.org/6dvr-xwnh)
states that `Trips Pooled` counts the transactions in the overall shared run,
including transactions that need not all overlap when the run has more than
two transactions. Each component transaction receives a separate public row.
Times are rounded to 15 minutes and location may be released at tract,
community-area, or missing resolution.

Let (i) index reported customer transactions. A useful abstraction of the
public row is

\[
O_i=\left(R_{15}(S_i),R_{15}(E_i),L_i,\widetilde G_i,
          A_i,Y_i,K_i,C_i^{\rm public}\right),
\]

where (A_i) is authorization, (Y_i) is actual match/co-presence, (K_i)
is the published run size, and the public table omits provider, vehicle, and
Shared Trip ID. On

\[
U_2=\{i:Y_i=1,\ K_i=2\},
\]

the hidden Shared Trip IDs induce a perfect matching (M^\dagger), provided
the extraction contains both components of every run and the released fields
are internally consistent. Since a run in (U_2) contains only two customer
transactions and (Y_i=1), the paired transactions were co-present at some
point. This implication fails for pairwise links inside (K_i>2) runs: A can
overlap B and B can overlap C while A never overlaps C.

The analysis unit is a customer transaction or booking, not necessarily one
person. A booking may contain multiple passengers.

The structural implication is conditional rather than a row-filter identity.
The current release contains `Match=true` rows with authorization false or
`Trips Pooled=1`, as well as null match flags. A production cohort must retain
literal values, report contradictions, and verify run closure; it must not
coerce null to false or assume that an authorized-only slice is an outer set.

## 2. Correct target and incorrect targets

A coherent descriptive target is the neighborhood-context composition of
realized two-transaction co-presence. For a feasible matching (M) and
context bins (B_i), one example is

\[
H(M,B)=\frac{2}{|U_2|}\sum_{\{i,j\}\in M}\mathbf 1\{B_i=B_j\}.
\]

This is not any of the following:

- a platform dispatch or offer opportunity set;
- a rider-income or rider-preference measure;
- a general statistic for all shared runs when (K>2) is excluded;
- a fixed-population traveler ITT;
- a verified partner graph until the partner ambiguity is resolved or bounded.

The name “opportunity exposure” is therefore misleading unless explicitly
defined as a graph-conditional sensitivity object. “Contextual composition of
realized two-transaction co-presence” matches the released field semantics.

## 3. Exact-cover endpoint result

For a declared undirected graph (G_C=(U_2,E_C)), define

\[
\mathcal M(E_C)=\left\{z\in\{0,1\}^{E_C}:
  \sum_{e\ni i}z_e=1\quad\forall i\in U_2\right\}.
\]

If this set is nonempty and a scalar target (T(z)) is evaluated on each
matching, then

\[
\underline T=\min_{z\in\mathcal M(E_C)}T(z),\qquad
\overline T=\max_{z\in\mathcal M(E_C)}T(z)
\]

are attained because the feasible set is finite. They are sharp *endpoints*
over the declared graph. The exact attainable scalar set is

\[
\mathcal S_T(E_C)=\{T(z):z\in\mathcal M(E_C)\},
\]

which need not equal the interval between the endpoints. On a four-cycle the
two perfect matchings may attain only 0 and 1; (1/2) lies in the displayed
range but is not attainable. Thus the interval is the scalar convex hull of
the attainable set, not generally the sharp identified set itself.

Truth is covered only under the additional support condition

\[
M^\dagger\subseteq E_C.
\]

That condition is neither observed nor implied by exact-cover feasibility.

## 4. The current candidate graph is not an outer set

Released values support analyst-defined candidate graphs, not one identified
physical graph. The current code:

- splits by start-date and forbids cross-date edges;
- requires start times within 30 minutes;
- requires released pickup centroids within 4 km and drop-off centroids within
  7 km;
- requires a route-direction cosine threshold;
- proposes only 96 nearest neighbors;
- greedily caps final degree at 16.

None of the spatial thresholds or caps is a necessary condition for
co-presence. A long first transaction can overlap a later transaction whose
start and pickup are far away. A midnight-spanning pair is deleted by the date
split. A true edge can be the seventeenth plausible neighbor. Mixing tract and
community-area centroids also treats unequal coarsening resolutions as
equal-precision points.

A defensible coverage graph should use only implications that are necessary
under the official operator. At minimum it must include boundary buffers and
possible temporal overlap under timestamp rounding. Arbitrary spatial screens
and computational caps must be separate sensitivity graphs, not the
inferential supergraph. Nodes whose partner may be outside the extraction
horizon must be excluded or explicitly treated as boundary-ambiguous.

## 5. Node weak supervision does not identify edge probabilities

The implementation defines nonnegative edge hazards (h_e) and node
marginals

\[
q_i=1-\exp\left(-\sum_{e\ni i}h_e\right).
\]

The product of Bernoulli node terms is a composite marginal scoring objective,
not a coherent joint likelihood for overlapping node events. With one latent
edge, its two endpoint labels must agree, while the product assigns positive
probability (q(1-q)) to one endpoint matching and the other not matching.

The node marginals also do not identify edge rankings. On a four-cycle, let
the consecutive edge hazards be

\[
(t,L-t,t,L-t),\qquad 0<t<L.
\]

Every node has incident hazard sum (L), so every node marginal is identical
for every (t). Yet the two perfect matchings exchange their score ordering
as (t) crosses (L/2). Any edge ranking therefore comes from the feature
parameterization and regularization, not from node labels alone.

Required claim boundary: the learned output may be called a weakly supervised
compatibility score. It is not a posterior probability of co-presence and its
edge ranking requires independent validation.

## 6. Score-restricted sets

The current restriction

\[
\sum_e w_ez_e\ge \rho W^*,\qquad
W^*=\max_{z\in\mathcal M(E_C)}\sum_e w_ez_e,
\]

is a mathematically defined sensitivity set but is not invariant to arbitrary
score origin or scale. Adding a constant to every edge score changes the set
even though every edge ranking remains the same. A monotone nonlinear
transformation can also reverse the ordering of total matching scores.

For fixed-cardinality exact covers, normalized regret

\[
R_w(z)=\frac{W^*-W(z)}{W^*-W_{\min}}
\]

is invariant to positive affine transformations of edge scores. This repairs
only a scale defect. It remains graph-dependent and has no shared coverage
meaning across unrelated score maps without an external calibration rule.
Consequently, equal numerical radii cannot be used as a fair rule-versus-AI
horse race.

## 7. Missing neighborhood context

Deleting context-missing nodes before exact cover is invalid. If true pairs
are ((1,2)) and ((3,4)), but only nodes 1 and 3 have released contexts, the
complete-case pipeline can feasibly pair 1 with 3 although neither retained
node's true partner remains. Feasibility and even parity do not reveal the
error.

All (Y=1,K=2) nodes must be exact-covered before neighborhood context enters
the objective. Two coherent targets are available.

First, among pairs whose two contexts are observed,

\[
H_{\rm pair\text{-}observed}(M)=
\frac{\sum_{\{i,j\}\in M}R_iR_j\mathbf 1\{B_i=B_j\}}
     {\sum_{\{i,j\}\in M}R_iR_j},
\]

where both numerator and denominator vary with (M). Bounds require a
fractional optimization and must report the attainable denominator range.

Second, declare a set \(\mathcal B_i\) of possible bins for every missing
context and optimize jointly over (M) and (B_i\in\mathcal B_i). If each
missing label may be any of at least two bins, an edge with both labels observed
has a fixed equality contribution; every edge with a missing endpoint has
lower contribution 0 and upper contribution 1. Because an exact cover selects
each node once, these edgewise envelopes give attained global endpoints. More
informative community-area restrictions can replace the unrestricted sets but
must preserve joint feasibility.

## 8. Policy functional

The current conditional pair share is post-treatment selected on successful
matching, (K=2), candidate support, and context release. It is not an ITT for
a fixed traveler population. The public table contains realized completed TNP
transactions, so `authorization/all` and `matched/all` are compositions among
reported transactions unless an external stable denominator is supplied.
Moreover, the current downloader explicitly filters to authorized trips and
therefore cannot construct either `/all` denominator.

If a descriptive policy coefficient among reported transactions is desired,
define an endpoint-level outcome for every analysis row. For example, a matched
(K=2) transaction receives its selected pair's cross-bin indicator and every
other transaction receives a predeclared zero. Let (X) be a fixed regression
design and let

\[
c^\top=e_\beta^\top(X^\top X)^{-1}X^\top.
\]

For pair value (g_{ij}), the coefficient is

\[
\widehat\beta(z)
=\sum_{\{i,j\}\in E_C}(c_i+c_j)g_{ij}z_{ij}.
\]

This follows by substituting the edge-induced endpoint outcomes into the OLS
coefficient. It can be minimized and maximized over one global matching, so
pairs that cross dates, zones, or active-hour cells are not broken apart. It
does not turn the released transactions into a fixed-population traveler ITT.

Policy eligibility must use pickup *or* drop-off in a covered zone, matching
the official tax rule. The January 2026 single/shared schedule also differs
between weekdays and weekends. `Additional Charges` bundles multiple fees and
is at most a noisy first-stage diagnostic.

## 9. Suppression-coupled latent geography

The simple missing-bin repair treats each missing context independently. That
is correct under independent supports but reduces to ordinary weighted perfect
matching. A documented Chicago privacy operator can provide stronger, globally
coupled restrictions, but documentary scope and implementation validation must
remain distinct.

[Mucci and Erhardt (2022)](https://doi.org/10.32866/001c.34191) establish that
suppression is selective and consequential in the legacy Chicago data. Their
description must not substitute for the City's operator definition. The
current base dataset metadata states that the City's
[privacy methodology](https://data.cityofchicago.org/stories/s/82d7-i4i2)
describes the approach used in `6dvr-xwnh`; that current-linked note lists the
dataset and documents an at-most-two-trip threshold with paired endpoint
coarsening. The companion
[City clarification](https://data.cityofchicago.org/stories/s/28mt-8asw)
states that pickup buckets are defined by pickup tract and rounded start time,
while drop-off buckets are defined by drop-off tract and rounded end time. If
either endpoint belongs to a bucket of fewer than three trips, both tract
fields are removed. The clarification's footer lists legacy dataset IDs, so it
supports the endpoint-marginal interpretation of the current-linked overview
but is not independent proof of the 2025/2026 transformation code.

This operator is not an OD-tract-pair capacity rule. A suppressed row may have
a pickup in a bucket of at least three if its drop-off bucket is small. A
visibly released pickup bucket may display only two rows if a third row sharing
that pickup bucket was suppressed because of its drop-off. Thus visible counts
alone do not reveal bucket totals.

Under the documented endpoint-marginal rule, conditional on production
implementation validation, let \(x^P_{ip}\) and \(x^D_{id}\) assign row \(i\) to a pickup and a
drop-off tract consistent with its released community areas. Define latent
bucket counts over *all* trips contributing to the privacy cells:

\[
n^P_{cp}=\sum_{i:\,c^P_i=c}x^P_{ip},\qquad
n^D_{cd}=\sum_{i:\,c^D_i=c}x^D_{id}.
\]

Introduce high-count indicators satisfying, for a valid cell-specific upper
bound \(M_c\),

\[
3h^P_{cp}\le n^P_{cp}\le2+(M_c-2)h^P_{cp},\qquad
3h^D_{cd}\le n^D_{cd}\le2+(M_c-2)h^D_{cd}.
\]

A row with visible internal tracts must be assigned to high pickup and drop-off
buckets under the documented removal implication. The converse is not
documented: a suppressed internal row can be required to have at least one low
assigned bucket only under a separately declared strong assumption that the
threshold is the sole cause of internal tract absence. Under the weak
documented model, missing rows receive no low-count constraint. These cases can
be imposed with standard binary linear constraints conditional on \(x^P\) and
\(x^D\). External trips, unlocatable rows, and ACS join failures require
separate structural states; they are not privacy-suppressed Chicago tracts.

Let \(s_{ib}\) be the pickup-income-bin assignment implied by \(x^P\). For
candidate partner edge \(e=\{i,j\}\), introduce

\[
y_{eb}=z_es_{ib}s_{jb}.
\]

The triple product has the exact binary linearization

\[
y_{eb}\le z_e,\quad y_{eb}\le s_{ib},\quad y_{eb}\le s_{jb},\quad
y_{eb}\ge z_e+s_{ib}+s_{jb}-2.
\]

Then minimizing or maximizing

\[
\frac{1}{m}\sum_{e,b}y_{eb}
\]

jointly over exact-cover, assignment, and endpoint-bucket threshold constraints
gives suppression-consistent endpoints conditional on the graph and verified
operator. Unlike independent edge envelopes, bucket-count coupling can make
several edgewise maxima jointly unattainable. The executable four-node example
in `adversarial_review/counterexamples.py` demonstrates this only under the
explicit strong converse (missing means at least one assigned endpoint bucket
is low); it does not claim that the converse governs the current release.

The explicit-DNF LOW/HIGH release compiler and its exact projection/replay
tests are now established in the artifact. A Chicago-specific applicability
adapter is not. It still requires:

1. validation of implementation partitions, late-row recomputation, DST
   handling, tract vintage, and one-way-versus-converse null causes;
2. all trips contributing to every privacy cell, because authorized-only or
   prefix samples do not preserve the count constraint;
3. separation of suppression, external geography, and ACS join failure;
4. correct tract vintage and tract/community-area maps;
5. a run-closed temporal order and measured production frontier/resource
   profile;
6. privacy review ensuring that only aggregate endpoints—not latent tract
   assignments—are released.

Until those conditions hold, the compiler is a valid methods result but no
suppression-aware Chicago endpoint is licensed.

## 10. Claim classification

| Claim | Classification |
|---|---|
| A transaction authorized shared service | Identified from the released row |
| A matched transaction shared with another booking at some point | Identified from `Shared Trip Match`, subject to reporting consistency |
| The sole partner for a chain-complete (Y=1,K=2) cohort exists | Identified structurally; its identity is hidden |
| Partner identity | Not identified without structural restrictions |
| Min/max statistic endpoints | Sharp conditional on the declared graph, node set, context model, and certified global optimization |
| Learned edge score or ranking | Model-dependent inductive output, not identified from node labels |
| Score-restricted endpoint range | Model-sensitivity region, not a confidence interval |
| Platform opportunity or dispatch feasibility | Not identified from the public release |
| Rider income, race, preference, or stable social relation | Not identified |
| Chicago complete-day contextual composition | Empirically untested in the frozen evidence |
| January 2026 policy effect | Empirically untested; current ITT language invalid |

## 11. Minimum coherent repair

1. Rename the object as contextual composition of realized two-transaction
   co-presence.
2. Extract a chain-complete, boundary-buffered (Y=1,K=2) population and
   exact-cover every target node globally.
3. Use a coverage graph built only from necessary implications of rounded
   temporal overlap; label spatial screens and caps as sensitivities.
4. Handle missing contexts inside the optimization.
5. Recast noisy-OR as a composite node scoring loss and remove edge-probability
   language.
6. Replace raw same-`rho` comparisons with score-specific sensitivity or a
   positively affine-invariant radius with external calibration.
7. Optimize a global descriptive coefficient over matchings; do not call it a
   traveler ITT.
8. Keep complete Chicago and policy claims gated until the production path,
   solver certificates, and observation-operator audits pass.

## Status

Independent reconstruction and adversarial cross-audit are complete for the
declared-input method. Current City documentation confirms the high-level
threshold-and-paired-end rule; implementation/null-cause validation,
snapshot-stable production data, the full external scan, and scientific
validation remain external gates rather than completed results.
