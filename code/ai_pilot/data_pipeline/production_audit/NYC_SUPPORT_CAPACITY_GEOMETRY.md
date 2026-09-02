# Timestamp-support and capacity geometry for ordered latent runs

This note isolates the monotonicity results that are valid for existential
latent-time completion.  It also records why treating an outer timestamp
envelope as the realized active interval is a different, nonmonotone model.
The statements are conditional feasible-world results; they do not recover an
actual vehicle run or a realized vehicle capacity.

## Setup

Let `I` index public trip rows.  The core set `K` must be covered exactly once;
a buffer row may be unused or covered once.  Public row `i` admits latent exact
pickup/drop-off pairs

\[
\mathcal T_i\subseteq
\{(s_i,e_i):s_i+\varepsilon\le e_i\},
\qquad \varepsilon>0.
\]

For a chosen completion, rows `i` and `j` have a positive-overlap edge when

\[
\max\{s_i,s_j\}+\varepsilon
\le
\min\{e_i,e_j\}.
\]

A latent run is a set of at least two rows whose positive-overlap graph is
connected.  A collection of runs is feasible at capacity `C` when:

1. every core row belongs to exactly one run;
2. every buffer row belongs to at most one run; and
3. at every time, each run contains at most `C` simultaneously active rows.

Let

\[
\mathcal F(\mathcal T,C,q)
\]

be the set of feasible completed worlds selecting exactly `q` buffer rows, and
let

\[
Q(\mathcal T,C)
=
\{q:\mathcal F(\mathcal T,C,q)\ne\varnothing\}
\]

be the reachable support-cardinality set.  When nonempty, define

\[
M(\mathcal T,C)=\max Q(\mathcal T,C).
\]

## Proposition 1: joint nesting

Suppose

\[
\mathcal T_i\subseteq\mathcal T'_i
\quad\text{for every }i,
\qquad C\le C'.
\]

Then, for every fixed support count `q`,

\[
\mathcal F(\mathcal T,C,q)
\subseteq
\mathcal F(\mathcal T',C',q).
\]

Consequently,

\[
Q(\mathcal T,C)
\subseteq
Q(\mathcal T',C'),
\qquad
M(\mathcal T,C)
\le
M(\mathcal T',C')
\]

whenever the maxima are defined.

### Proof

Take any world in `F(T,C,q)`.  Its selected latent timestamps remain admissible
because each old support is contained in the new support.  Its run partition,
positive-overlap edges, selected buffers, and core coverage therefore remain
unchanged.  The occupancy of every run is at most `C`, hence also at most
`C'`.  The same witness lies in `F(T',C',q)`.  The statements for reachable
counts and their maxima follow immediately.  ∎

Two one-dimensional corollaries are used by the audits:

\[
\mathcal F(\mathcal T,C,q)
\subseteq
\mathcal F(\mathcal T',C,q)
\quad\text{under support expansion},
\]

and

\[
\mathcal F(\mathcal T,C,q)
\subseteq
\mathcal F(\mathcal T,C',q)
\quad\text{under capacity relaxation}.
\]

## Proposition 2: endpoint monotonicity at a common estimand

Let `H(w)` be any real-valued functional defined on feasible worlds, and hold
`q` fixed.  If the assumptions of Proposition 1 hold and both feasible sets
are nonempty, then

\[
\min_{w\in\mathcal F(\mathcal T',C',q)}H(w)
\le
\min_{w\in\mathcal F(\mathcal T,C,q)}H(w),
\]

and

\[
\max_{w\in\mathcal F(\mathcal T',C',q)}H(w)
\ge
\max_{w\in\mathcal F(\mathcal T,C,q)}H(w).
\]

### Proof

Both inequalities are the elementary monotonicity of minimization and
maximization under feasible-set inclusion.  ∎

The fixed-`q` qualification is essential.  Comparing outcomes conditional on a
capacity-specific maximum `q=M(T,C)` changes the estimand when `C` changes; its
interval width need not expand monotonically.

## Definition: capacity-equivalent support loss

For nested fine and coarse timestamp supports, define the fine-time capacity
increment needed to match coarse support reachability by

\[
\kappa_{\mathcal T\to\mathcal T'}(C)
=
\min\{k\ge0:
M(\mathcal T,C+k)\ge M(\mathcal T',C)\},
\]

when such a `k` exists in the declared capacity range.  This is an
identification-geometry index, not an estimate of physical vehicle seats.

In a time-limited computation, let `L(T',C)` be the largest coarse support count
with a replayed certified feasible witness.  Since

\[
L(\mathcal T',C)\le M(\mathcal T',C),
\]

we can report only

\[
\underline\kappa(C)
=
\min\{k\ge0:
M(\mathcal T,C+k)\ge L(\mathcal T',C)\}
\le
\kappa_{\mathcal T\to\mathcal T'}(C).
\]

Thus unresolved coarse counts can only make the true capacity-equivalent loss
larger than the reported certified lower bound.  They are never converted to
infeasibility.

## Proposition 3: an outer envelope is not an existential relaxation

Let `[a_i,b_i]` be a released outer envelope containing one possible realized
interval `[s_i,e_i]`.  Replacing every realized interval by its whole envelope
and imposing capacity on the envelopes does not generally produce a superset of
fine-time feasible worlds.

### Counterexample

At capacity two, consider the exact intervals

\[
[0,2],\quad[1,3],\quad[2,4].
\]

With a sufficiently small positive-overlap margin, they form a connected chain
and have maximum simultaneous depth two.  Now use the containing envelopes

\[
[-1,3],\quad[0,4],\quad[1,5].
\]

All three envelopes overlap simultaneously on a positive-length interval, so
the envelope depth is three and violates capacity two.  The exact feasible
world is therefore rejected by the envelope-occupancy model even though its
realized intervals lie inside those envelopes.  ∎

The monotone release model must use the quantifier order

\[
\exists\,(s_i,e_i)\in\mathcal T_i
\quad\text{such that connectivity and occupancy hold},
\]

not require connectivity and occupancy of the complete outer envelopes.

## Computational interpretation

For fixed exact timestamps on a small audit cohort, the repository completely
enumerates unlabeled feasible run columns and solves the disjoint-column master
by dynamic programming.  For interval-valued timestamp supports, the coarse
side uses a continuous-time mixed-integer formulation and reports certified
feasible witnesses, proven infeasibility, and unresolved states separately.

The propositions above justify only nesting and endpoint comparisons for the
declared feasible-world model.  They make no statement about candidate recall,
TLC's actual observation operator, production matching logic, co-rider identity,
vehicle identity, or population prevalence.
