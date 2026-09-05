# Exploration: certify the decision versus recover the relation

Status: **exact controlled-truth comparison on the selective-disclosure branch**.

Pinned workflow run `33851588861`, artifact `9928566517`, source commit
`65112dc2bf578dc14342501da37800c1fc43a92b`.

## Question

Selective disclosure is useful only if certifying the downstream decision
requires materially less information than identifying the latent relation. We
therefore compare two exact certificates over the same feasible-world set:

- a **decision certificate**, which only rules out worlds with the opposite
  threshold decision;
- a **recovery certificate**, which distinguishes the realized selected set or
  realized partition from every alternative feasible one.

Both are minimum hitting sets over disagreement patterns. The difference is the
set of worlds that must be hit.

## Selected-member mean

The comparison uses the same 1,000 instances per capacity and three thresholds
as the primary selective-disclosure benchmark. Among 5,954 initially ambiguous
capacity--threshold comparisons:

| Quantity | Decision certificate | Full selected-set certificate |
|---|---:|---:|
| Mean facts | 1.557 | 3.488 |
| Median facts | 1 | 3 |
| 90th percentile | 3 | 4 |
| Maximum | 4 | 4 |

Strict savings occur in **95.1%** of ambiguous comparisons. The mean saving is
**1.93 facts**, and the mean decision/full ratio is **0.452**; the median ratio
is one third.

This is the cleanest evidence for the proposed framing. The target is not a
cheaper approximate reconstruction. It is a strictly weaker information task:
many relation alternatives can remain unresolved once they all imply the same
decision.

## Partition-dependent event count

The event-count experiment fixes the complete true selected-row set, so row
usage is already fully disclosed. Pair co-membership facts are then used either
to certify the decision `event_count <= 2` or to identify the complete
partition.

Among 272 initially ambiguous instances:

| Quantity | Event-count decision | Full partition recovery |
|---|---:|---:|
| Mean pair facts | 2.015 | 2.643 |
| Median pair facts | 2 | 3 |
| 90th percentile | 3 | 4 |
| Maximum | 3 | 4 |

Strict savings occur in **52.6%** of ambiguous instances. The mean saving is
**0.629 pair facts**, and the mean decision/full ratio is **0.772**.

The partition savings are smaller because the controlled events are tiny and
the three-event negative decision already requires separating representatives
from three realized events. This is not a weakness in the calculation; it is a
warning that larger or richer events are needed before claiming a dramatic
partition-level privacy or audit benefit.

## Interpretation

The result supports three claims only within the controlled generator:

1. decision certification is usually information-cheaper than selected-set
   recovery for additive composition thresholds;
2. row-usage disclosure is insufficient for a genuinely partition-dependent
   target even after all selected rows are known;
3. pair co-membership can certify event count without fully revealing the
   partition, but the savings are modest in the current small-event design.

It does not price an operational query, establish privacy utility, or show that
Chicago or NYC can expose these facts. Those require an explicit disclosure
mechanism and a real-truth dataset.

## Next falsification gate

The next controlled generator should vary event cardinality and number of
realized events. The pair-certificate theorem predicts that for a realized
negative decision `K > k`, at most `binom(k+1,2)` negative pair facts are
needed, whereas complete partition recovery can grow with the active set. The
empirical question is whether that asymptotic separation appears before the
EventFrontier solver becomes intractable.
