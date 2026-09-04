# EventFrontier code

The active implementation is intentionally small at the top level:

- `data_pipeline/production_audit/` contains the ordered-event model,
  enumeration, interval pricing, column generation, branch-and-price,
  existential-time programs, public-data extraction, fixtures, tests, and
  experiment protocols.
- `data_pipeline/results/` contains only redacted aggregate evidence used by the
  current manuscript.
- `benchmarks/` contains the controlled-truth generator and evaluation wrappers.
- `requirements.txt` pins the numerical stack used by CI.

The path name `ai_pilot` is historical. No weak-node-score, conformal-matching,
record-linkage, release-compiler, external-topology, or legacy integration code
remains in the active tree.

## Tests

```bash
python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests -v
python code/ai_pilot/benchmarks/event_frontier_truth_benchmark_scale.py \
  --self-test
```

Timeouts remain unresolved; they are never converted to optimality or
infeasibility. Public-data outputs must remain aggregate and must not serialize
raw trip identifiers, latent event assignments, or partner witnesses.
