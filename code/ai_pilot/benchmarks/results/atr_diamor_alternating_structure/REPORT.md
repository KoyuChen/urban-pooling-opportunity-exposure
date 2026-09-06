# ATR DIAMOR alternating-structure audit v1

Status: **PASS**.

This descriptive post-hoc audit compares replayed minimum- and maximum-distance
matching witnesses on the 82 DIAMOR-2 snapshots. Their symmetric difference is
decomposed into alternating path and cycle components. Results are reported for
both the frozen 3 m/120 degree graph and its frozen `k=2` local-degree cap.

Every fixed-graph snapshot has positive width, distinct endpoint witnesses, and
at least one ambiguous evaluated threshold. In 73/82 snapshots the endpoint
witnesses differ through more than one disconnected alternating component. The
returned witnesses contain 243 path components and three cycles; no component
has more than four edges. Most components are only one or two edges.

The degree cap leaves all 82 lower endpoints unchanged and contracts 21 upper
endpoints. Among changed cells the mean contraction is 0.177 m and the maximum
is 0.577 m; mean width falls from 1.897 m to 1.852 m. Nevertheless, every
snapshot retains the same number of ambiguous thresholds. Candidate-graph
compression therefore changes some continuous bounds without changing any of
the 246 evaluated decisions.

The evidence supports a distributed-local interpretation for the returned
witnesses: ambiguity is sustained by many small alternative assignments rather
than one giant alternating structure. This is not an enumeration of all optimal
matchings. Solver tie-breaking can choose one of several endpoint witnesses, so
component counts are descriptive and post-hoc, whereas endpoint values and
their equality comparisons are replay-audited.

