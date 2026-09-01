# NYC unknown-capacity latent-group benchmark

## Scope

Chicago exposes `Trips Pooled = 2`, so a public `K=2` matching benchmark is
well defined. NYC HVFHV exposes `shared_match_flag = Y` but not realized pool
size, co-rider identity, vehicle identity, or a shared-run key. A direct
pairwise matching model is therefore only a conditional benchmark.

This note defines the first tractable unknown-capacity extension. It is
intentionally weaker than a full vehicle-run reconstruction.

## Released objects

For a fixed provider and fixed public cohort, each public shared-match row
`i` has

- released pickup time `s_i`,
- released drop-off time `e_i`,
- released pickup and drop-off Taxi Zones, and
- public outcomes such as trip miles and trip time.

Let `V = C0 union B` denote the fixed core and buffer candidate rows. Let
`A(i,j)` indicate that the two released onboard intervals are temporally
compatible under the declared time-resolution model.

## Anchored latent groups

A feasible anchored group has one released row `r` designated as its anchor.
Every member assigned to anchor `r` must satisfy `A(i,r)=1`. The anchor itself
is a member. The group-size cap is an explicit analyst sensitivity parameter
`C`:

```
2 <= |g_r| <= C.
```

The model does **not** assert that the actual NYC pool size is at most `C`.
Rather, `C in {2,3,4}` indexes a family of conditional identified sets.

Binary variables are

- `y_r`: anchor `r` opens a latent group;
- `x_ir`: public row `i` is assigned to anchor `r`.

The benchmark feasible set is

```
x_rr = y_r                                         for every anchor r
x_ir <= y_r                                        for every admissible (i,r)
x_ir = 0                                           if A(i,r)=0
2 y_r <= sum_i x_ir <= C y_r                       for every anchor r
sum_r x_ir = 1                                     for every core row i
sum_r x_ir <= 1                                    for every buffer row i
```

Core rows must be explained exactly once; buffer rows may be unused. An
anchor candidate can be restricted to core rows for the first real-data Gate,
which keeps the optimization size manageable and makes every latent group
relevant to the target core.

## Identified quantities

For any public attribute `z_i`, define anchor-relative group dispersion

```
D_z(x) = (1 / |C0|) * sum_r sum_i x_ir * |z_i - z_r|.
```

The sharp conditional endpoints within this benchmark are

```
L_C(z) = min_x D_z(x)
U_C(z) = max_x D_z(x).
```

The same formulation works for binary same-zone indicators.

Because enlarging the capacity cap only relaxes the feasible set,

```
F_2 subseteq F_3 subseteq F_4 subseteq ...,
```

so whenever all endpoints are well defined,

```
L_2(z) >= L_3(z) >= L_4(z) >= ...,
U_2(z) <= U_3(z) <= U_4(z) <= ... .
```

This monotonicity is a deterministic audit identity for the implementation.

## What this benchmark establishes

It gives a first unknown-capacity partial-identification object using public
NYC rows and public times without inventing co-rider IDs. It also separates the
capacity-assumption contribution from the timestamp-resolution contribution.

## What it does not establish

The anchored-group benchmark is not a complete latent vehicle-run model.
Specifically, it does not yet allow an arbitrarily long chain of riders to
enter and exit one vehicle while the instantaneous occupancy remains bounded
by `C`. It therefore should not be interpreted as a recovered shared run.

The next extension replaces anchored groups by temporally ordered latent runs,
requires each shared-match row to overlap another member of its run, and bounds
maximum simultaneous occupancy rather than total group cardinality. That
extension is the natural place to study tractability versus hardness.
