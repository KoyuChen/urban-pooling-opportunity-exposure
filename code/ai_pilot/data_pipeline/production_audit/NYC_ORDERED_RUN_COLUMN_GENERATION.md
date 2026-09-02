# Fixed-time ordered-run column generation

## 1. Decomposition master

Let `C0` be the public core rows and `B0` the declared candidate buffers. For a
fixed simultaneous capacity `C`, let `R_C` be the family of all positive-overlap
connected interval runs that contain at least two rows and at least one core.
For each run `R`, let `b_R=|R intersect B0|` and introduce a nonnegative master
variable `lambda_R`.

The LP relaxation of maximum reachable buffer support is

```text
maximize   sum_R b_R lambda_R
subject to sum_{R: i in R} lambda_R = 1       for every core i,
           sum_{R: j in R} lambda_R <= 1      for every buffer j,
           lambda_R >= 0.
```

The equalities couple otherwise independent run columns. The model is a
Dantzig--Wolfe relaxation of the integer latent-run partition.

## 2. Exact rooted pricing

Write the master in minimization form and let `pi_i` be the dual of core
coverage and `mu_j <= 0` the dual of buffer use. A run has negative reduced cost
exactly when

```text
sum_{i in R intersect C0} pi_i
+ sum_{j in R intersect B0} (1 + mu_j) > 0.
```

Thus pricing is an additive-weight single-run problem. For every possible core
root, the existing fixed-span interval LP oracle maximizes this reward under
positive-overlap connectivity and simultaneous capacity.

Candidate spans need only start at an observed interval start and end at an
observed interval end. Moreover, if a span strictly extends the root interval,
segment coverage already forces at least one companion. Forced-companion
enumeration is needed only for the one span equal to the root interval when its
unconstrained optimum is the singleton root. This reduces the pricing wrapper
from companion enumeration at every span to one LP per candidate span plus at
most `n-1` exceptional LPs.

### Proposition 1: certified full-master LP bound

If every rooted pricing call is solved exactly and no negative reduced-cost
column exists, the current restricted-master value equals the optimum of the
full fixed-time master LP over all feasible run columns.

This is standard Dantzig--Wolfe optimality, but its usefulness here comes from
the exact interval pricing oracle. The implementation uses a phase-one
artificial-core master; a positive converged artificial mass certifies
infeasibility of the full master LP. It then maximizes selected-buffer support
and records the terminal minimum reduced cost, primal residuals, generated
column count, and oracle workload.

## 3. The integer master remains nonintegral

Integral pricing does **not** imply an integral coupling master. Consider
capacity `C=2` with four cores

```text
c0=[1,2), c1=[4,7), c2=[0,2), c3=[1,2)
```

and five buffers

```text
b0=[0,7), b1=[5,6), b2=[5,7), b3=[1,2), b4=[2,6).
```

Complete run-column enumeration gives an LP maximum of four selected buffers.
One fractional optimum uses weights `1/2,1,1/2,1/2,1/2,1/2` on the columns

```text
{c0,c2}, {c1,b1}, {c2,b3}, {c3,b3}, {c0,b0,b4}, {c3,b0,b4}.
```

Every core has total coverage one and every buffer has use at most one. The
exact integer maximum is only three, for example through

```text
{c0,c2}, {c3,b0,b1}, {c1,b4}.
```

Hence the full master LP has integrality gap one on this instance.

### Consequence

The current algorithm certifies an upper bound from the full LP relaxation and
obtains an integer feasible lower bound by solving the generated restricted
master as a binary MILP. It is not yet a polynomial-time exact algorithm for
the full latent-run decomposition. Exact production optimization requires a
branch-and-price scheme, an alternative integral formulation, or a direct
complexity/parameterized boundary.

## 4. Audit plan

The deterministic Gate compares column generation with complete run-column
enumeration on random tiny interval libraries and on the explicit
nonintegrality witness. The real-data smoke test fixes one public 4-core,
12-buffer exact-time NYC cohort and, for `C=2,3,4`, reports:

- full enumerated column count;
- generated column count and fraction;
- full enumerated LP optimum;
- exact integer support maximum;
- restricted-master integer lower bound;
- phase-one and phase-two iterations;
- exact pricing LP calls and terminal reduced cost.

No raw public row, row identifier, generated run column, or selected run witness
is serialized.

## 5. Claim boundary

Supported: exact rooted pricing; certified optimality of the full fixed-time LP
relaxation when pricing closes; exact tiny-instance comparison; an explicit
master nonintegrality witness.

Not supported: polynomial-time exact solution of the full integer problem,
NP-hardness of this specific decomposition, production-scale performance,
actual co-rider recovery, realized capacity, or TLC matching logic.
