# Exploration: decision-focused selective disclosure

Status: **active branch experiment; not yet a paper claim**.

## 1. Why this is the next question

The frozen NYC panel makes the negative result unusually stark. At the
candidate-median threshold, 125 of 126 outcome--capacity cells are certified
ambiguous. The quartile and transparent fixed-threshold sensitivities do not
materially change that diagnosis: every resolved group remains ambiguous.
This is useful as an audit, but a reviewer can reasonably ask what the method
does after it says that the public release is insufficient.

The proposed next object is therefore:

> Do not recover the entire missing relation. Ask for the smallest truthful
> relation disclosure that is sufficient to certify the particular downstream
> decision.

This turns EventFrontier from a diagnostic endpoint into an audit-interface and
release-design problem.

A second current weakness motivates the same extension. The model permits any
event-label-invariant functional, but the public headline outcomes are mainly
means over the selected buffers. They depend strongly on membership and only
indirectly on how selected rows are partitioned. A partition-dependent target,
such as event count, average event size, or within-event exposure, is needed to
show why ordered event worlds are more than a complicated subset selector.

## 2. Formal object

Let \(\mathcal W\) be the current feasible-world set and let
\[
 d_\eta(F)=\mathbf 1\{H(F)\ge \eta\}
\]
be the decision induced by threshold \(\eta\). An audit interface contains
binary atoms \(a\in\mathcal A\), each with a truthful answer
\(g_a(F)\in\{0,1\}\). Two atom families are natural:

1. **row usage:** whether optional row \(i\) belongs to any selected event;
2. **pair co-membership:** whether active rows \(i,j\) belong to the same event.

For a realized world \(F^\star\), a set \(S\subseteq\mathcal A\) is a
*decision certificate* when every feasible world agreeing with \(F^\star\) on
all atoms in \(S\) has the same decision:
\[
 g_a(F)=g_a(F^\star)\ \forall a\in S
 \quad\Longrightarrow\quad
 d_\eta(F)=d_\eta(F^\star).
\]
The minimum certificate size is denoted \(\tau(F^\star,\eta)\).

### Proposition 1: exact hitting-set representation

For every opposite-decision world \(F\), define its disagreement set
\[
 D(F^\star,F)=\{a\in\mathcal A:g_a(F)\ne g_a(F^\star)\}.
\]
Then \(S\) is a decision certificate if and only if it intersects every
\(D(F^\star,F)\) over opposite-decision worlds. Consequently,
\(\tau(F^\star,\eta)\) is the optimum of a unit-cost hitting set.

The proof is immediate but useful. Missing one disagreement set leaves an
opposite-decision world consistent with all disclosed answers; hitting every
set removes all such worlds.

### Corollary 1: membership-only upper bound

Suppose the decision is determined by the selected-buffer set, there are
\(n\) candidate buffers, and all feasible worlds are conditioned on the same
selected count \(q\). Revealing all selected rows or all unselected rows fixes
the selected set. Hence
\[
 \tau(F^\star,\eta)\le \min\{q,n-q\}.
\]
This bound does **not** apply to partition-dependent queries. Even complete row
usage can leave multiple event partitions and opposite event-count decisions.

## 3. Exact controlled-truth pilot

The new benchmark reuses the current 3-core, 8-buffer controlled generator and
its exact fixed-time master. Truth is used only to answer audit queries and to
evaluate the realized certificate. Candidate construction, feasible worlds,
and outcomes are unchanged.

### 3.1 Selected-member mean

Across 1,000 seeds at each \(C\in\{2,3,4\}\) and the three existing thresholds,
there are 9,000 capacity--threshold comparisons. The exact pilot finds 5,954
initially ambiguous comparisons. Conditional on ambiguity:

| Statistic | Minimum row-usage certificate |
|---|---:|
| Mean | 1.56 |
| Median | 1 |
| 90th percentile | 3 |
| Maximum | 4 |
| At most one fact | 55.8% |
| At most two facts | 89.3% |
| At most three facts | 99.2% |

The middle threshold is hardest: its conditional mean certificate is about
1.89--1.95 facts across capacities, versus about 1.17--1.31 at the outer
thresholds. Thus a wide frontier need not imply that a full latent relation is
needed. In these controlled cells, one or two targeted membership facts usually
resolve the actual decision.

An optimal adaptive minimax decision tree was also evaluated on 200 seeds per
capacity. Conditional on initial ambiguity, the realized path has mean 2.80 and
median 3 queries; the policy's worst-case depth has mean 4.02, median 4, and
maximum 5. This is larger than the ex-post minimum certificate, as expected:
the adaptive policy does not know the realized answers before querying.

### 3.2 A genuinely partition-dependent target

Condition on the **complete true selected-row set** and consider the decision
\[
 \text{number of latent events}\le 2.
\]
The generated truth contains three events. Over 100 seeds per capacity, the
selected set admits both sides of this event-count decision in 98.6% of
\(C=2\) instances and all \(C=3,4\) instances. Mean event-count width is 0.99,
1.64, and 1.98 respectively.

All row-usage answers are identical across these worlds, so no number of usage
queries can resolve an ambiguous cell. Pair co-membership facts can:

| Capacity | Event-count ambiguity | Mean minimum pair certificate | Median | Maximum |
|---:|---:|---:|---:|---:|
| 2 | 98.6% | 2.02 | 2 | 3 |
| 3 | 100.0% | 2.92 | 3 | 3 |
| 4 | 100.0% | 2.93 | 3 | 3 |

This is the most important exploratory result. The same row-usage and
Ryan--Foster pair predicates already used inside branch-and-price become
information atoms for decision certification. They distinguish membership
uncertainty from partition uncertainty operationally, not only conceptually.

## 4. Scalable algorithmic route

Explicit feasible-world enumeration is only a small-instance oracle. At scale,
use constraint generation:

1. a hitting-set master selects candidate disclosure atoms;
2. condition EventFrontier on the realized answers for those atoms;
3. solve a separation problem for any feasible world with the opposite
   decision;
4. if found, add its disagreement-set cut; otherwise the current disclosures
   are a valid certificate.

For selected-member additive targets, row-usage fixes are already implemented
as branch-node constraints. For partition targets, pair co-membership answers
are exactly the together/separate restrictions already supported by the
Ryan--Foster pricing layer. The missing engineering object is therefore not a
new solver; it is a certificate master around the existing branch-compatible
separation oracle.

The adaptive version chooses the next atom before seeing its answer. A minimax
policy solves
\[
 V(\mathcal S)=
 \begin{cases}
 0, & d_\eta \text{ is constant on }\mathcal S,\\
 1+\min_a\max_{y\in\{0,1\}}V(\{F\in\mathcal S:g_a(F)=y\}),&\text{otherwise}.
 \end{cases}
\]
Exact dynamic programming is available only for the small benchmark. Larger
instances need greedy decision-balance, information-gain, or bound-reduction
policies, each audited against the exact small oracle.

## 5. Literature position and novelty risk

Active clustering methods such as HS2 and A3S strategically request point or
pair labels to improve or recover a clustering. The proposed target is weaker
and more decision-focused: stop as soon as every still-feasible event world
agrees on one specified aggregate decision, even if most of the partition
remains unknown.

A July 2026 paper, *Identifiability of Relational Queries in Multi-View
Pretraining*, is a direct novelty warning for generic “minimum information
augmentation” language. It studies schema/interface-law identifiability and
minimum attribute augmentation via Set Cover. Our defensible distinction must
be explicit:

- instance-level relation facts rather than schema attribute closure;
- a realized-world certificate or adaptive audit rather than a single static
  interface augmentation;
- temporally ordered, capacity-constrained event worlds;
- an implicit separation oracle built from branch-and-price;
- decision certification without full relation recovery.

If these distinctions do not generate a nontrivial theorem and scaling result,
the extension should not be sold as a separate main contribution.

## 6. Real-truth gate

The Porto Taxi Service Trajectory dataset is a promising second-stage benchmark:
1,710,671 completed trips from 442 taxis over one year, with `TRIP_ID`,
`TAXI_ID`, timestamp, and a trajectory point every 15 seconds. Hiding
`TAXI_ID` creates real relation truth rather than another synthetic partition.

It does not fit the current positive-overlap event definition without an
extension, because one taxi's consecutive trips normally do not overlap. A
clean candidate model would separate:

- **occupancy:** capacity on the original trip intervals;
- **continuity:** a directed short-gap and spatially compatible edge between a
  trip end and a later trip start.

A vehicle-shift event is then a connected path/chain under continuity, with
`TAXI_ID` retained only for evaluation. This extension should remain outside
the main paper until the local oracle and shift-boundary treatment are proved.

## 7. Falsification gates

1. **Reproduction:** the committed script must reproduce the certificate table
   from a clean environment and retain exact solver status.
2. **Implicit separation:** recover the explicit small-instance optimum without
   enumerating worlds.
3. **Information savings:** compare certificate size with the number of facts
   needed to identify the full selected set or complete partition.
4. **Target diversity:** repeat for event count, average event size,
   within-event dispersion, and exposure; avoid a result driven by one
   threshold.
5. **Noise:** study erroneous or abstaining audit answers. Exact certificates
   are brittle if the oracle is imperfect.
6. **Real truth:** hide Porto taxi identity and measure decision coverage,
   certificate validity, and candidate-world retention.
7. **Privacy boundary:** report only certificate size and aggregate performance;
   do not publish relation answers or reconstructed worlds.

## 8. Recommendation

This direction is materially stronger than adding another city panel. It
answers the main practical objection to an almost-everywhere ambiguous public
frontier and forces the empirical section to include a truly partition-dependent
query. The branch should remain exploratory until the full benchmark is frozen
and the implicit certificate solver matches the explicit oracle.

A possible eventual title/framing is:

> **Certify the Decision, Not the Relation: Selective Disclosure for
> Relation-Incomplete Event Streams.**
