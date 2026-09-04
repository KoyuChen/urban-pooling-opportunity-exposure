# Controlled-truth benchmark

This directory contains the only active synthetic validation for EventFrontier.

- `relation_incomplete_event_benchmark.py` defines the deterministic generator
  and exact fixed-time evaluation helpers.
- `event_frontier_truth_benchmark.py` implements the canonical point-rule,
  threshold-decision, and candidate-truncation evaluation contract.
- `event_frontier_truth_benchmark_scale.py` extends the frozen design to
  `C=2,3,4` and 1,000 seeds per capacity.

Truth memberships are used only for generation and evaluation. They are never
inputs to the frontier or point comparators.

```bash
python code/ai_pilot/benchmarks/event_frontier_truth_benchmark_scale.py \
  --self-test
```

Paper-scale outputs are generated into ignored directories and are not committed
as row-level files.
