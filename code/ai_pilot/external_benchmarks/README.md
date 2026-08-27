# External relation-truth benchmark audit

Checked against primary repository/package documentation on **2026-08-27**.
No external data rows are committed here. The executable audit was run against
an official cached UCI block-1 ZIP and the FEBRL4 files bundled in
`recordlinkage==0.16`; only aggregate results and declarative metadata are
checked in.

## Decision

Use **UCI Record Linkage Comparison Patterns (dataset 210)** as the real,
non-Chicago relation-topology boundary test and **FEBRL4** as a paired external
synthetic complete-matching method-fit test. UCI is the only candidate audited
here that combines manual real-data pair adjudication, useful scale, a stable
DOI, public credential-free download, and an explicit dataset license. Its
positive relation is not a matching, so the full relation is reported without
repair; a separately labeled, truth-conditioned dyad reduction exercises a
matching-only aggregate frontier. FEBRL4 supplies the complete one-to-one
topology that UCI does not.

The committed [benchmark report](results/BENCHMARK_REPORT.md) records the
block-1 result: 2,093 adjudicated positives over 4,028 records include 152
records with positive degree above one. The dyad reduction retains 1,796 true
dyads and 741 alternative edges; its score-free postal-agreement frontier is
`[0.918151, 0.954900]` and contains adjudicated truth at the upper endpoint.
FEBRL4's six-pair exhaustive and 20-pair numerical benchmarks both cover their
hidden truth. These results do **not** validate the joint latent
endpoint-attribute compiler, Chicago transfer, UCI blocking recall, or
independent-market split-conformal coverage.

The source is already privacy-reduced: it exposes record identifiers and
pairwise agreement patterns, not the underlying names, dates of birth, sex, or
postal codes. The checked-in adapter additionally HMAC-pseudonymizes record
identifiers, bins continuous name similarities, turns missing binary
comparisons into declared `{0,1}` supports, and puts `is_match` in a physically
separate truth file.

## Candidate comparison

| Candidate | License / access | Reproducibility and size | Relation truth | Coarsened operator fit | Main leakage or validity risk | Verdict |
|---|---|---|---|---|---|---|
| **UCI Record Linkage Comparison Patterns (Krebsregister), dataset 210** | Explicit **CC BY 4.0**; official page offers a public 53.8 MB archive and `ucimlrepo` loader; no account is described | Stable DOI `10.24432/C51K6B`; 100,000 source records, 5,749,132 blocked candidate pairs, 20,931 adjudicated matches, ten approximately balanced files | Real deduplication/entity relation; pair labels came from extensive manual review; record IDs allow positive connected components | Strong matching-only special case after preserving group topology and isolating a truth-conditioned dyad subset | The supplied blocking procedure can omit true pairs; ten files are not independent markets; positive components contain more than two records; `is_match` and raw IDs are direct leakage | **Selected real boundary test.** Block 1 executed; all-ten-block scan remains before a full result |
| **FEBRL4 via Python Record Linkage Toolkit 0.16** | Bundled in the BSD-3-Clause toolkit; original FEBRL project declares MPL 1.1 provenance | Public PyPI wheel is 926.9 kB and source is 1.0 MB with published SHA-256 hashes; loader is deterministic; 5,000 originals plus 5,000 duplicates | Exact bipartite one-to-one truth: one duplicate per original, ideal for a perfect-matching solver | Strongest mechanical fit: hide true links, generalize synthetic fields, and bound field-agreement aggregates | Fully synthetic corruption process; all 5,000 source ID pairs directly encode partner number; returned links and IDs must be isolated | **Executed secondary method-fit test.** Six-pair exhaustive and 20-pair numerical markets; cannot close the external-realism gate |
| **WDC Product Data Corpus / Gold Standard v2** | Official page offers public direct downloads, but states no dataset license; the general WDC page licenses only the *extraction framework* under Apache, not this corpus/gold standard | Gold files are roughly 274--705 kB normalized/non-normalized; 4,400 manually reviewed pairs (1,200 positive, 3,200 negative); full corpus is 26M offers in 16M identifier clusters and is 4.5--6.5 GB | Pair-labeled product identity with multi-offer groups; gold standard samples two positives plus selected negatives for each of 600 focal products | Titles/descriptions can be token-count or similarity bins; brands/categories and prices can be generalized; no human PII | Gold pairs were deliberately selected using title/description similarity; corpus identifiers and `cluster_id` are label proxies; sampled pairs are not a closed-world matching; privacy analogy is weak; redistribution license is unresolved | **Hold.** Useful robustness data only after written license clarification and a group-relation design |

### Primary documentation supporting the table

- UCI dataset page, schema, provenance, counts, DOI, download size, and CC BY
  4.0 license:
  <https://archive.ics.uci.edu/dataset/210/record%2Blinkage%2Bcomparison%2Bpatterns>
- UCI donation policy confirming that accepted datasets are assigned a DOI and
  licensed CC BY 4.0:
  <https://archive.ics.uci.edu/contribute/donation>
- Python Record Linkage Toolkit dataset API, including UCI/Krebsregister and
  all four FEBRL structures:
  <https://recordlinkage.readthedocs.io/en/stable/ref-datasets.html>
- PyPI release page for RecordLinkage 0.16, including BSD-3-Clause, file sizes,
  public downloads, and hashes: <https://pypi.org/project/recordlinkage/>
- Original FEBRL project page and MPL 1.1 declaration:
  <https://sourceforge.net/projects/febrl/>
- WDC v2 corpus/gold-standard construction, schemas, pair counts, selection
  process, and downloads:
  <https://webdatacommons.org/largescaleproductcorpus/v2/index.html>
- WDC general license text, which explicitly names only the extraction
  framework: <https://webdatacommons.org/structureddata/#toc9>

## UCI integration contract

### Frozen source and provenance

1. Fetch only from the official UCI dataset record/direct archive recorded in
   `fixtures/uci_rlcp_metadata.json`. No Kaggle or repackaged mirror is an
   acceptable source.
2. Record the archive SHA-256 and member manifest before extraction. UCI's
   page reports a size but no checksum; `archive_sha256: null` is deliberate,
   not a wildcard.
3. Preserve the original archive read-only outside the repository. Do not
   commit source blocks, public JSONL, truth JSONL, or the HMAC key.

### Observation operator `uci_rlcp_public_coarsened_v1`

For every documented candidate pair:

1. Replace each internal record ID by a 96-bit truncated HMAC-SHA-256
   pseudonym under an uncommitted key. This removes numeric/order cues but is
   not claimed to anonymize the originating health registry.
2. Map each of four name similarities to fixed bins:
   `unknown`, `zero`, `low=(0,.5)`, `medium=[.5,.8)`, `high=[.8,1)`, or
   `exact=1`.
3. Release each exact comparison (`sex`, birth-day/month/year, postal code) as
   support `[0]`, `[1]`, or `[0,1]` when UCI marks the comparison missing.
4. Omit `is_match` from the public observation. Write it to
   `uci_rlcp_pair_truth_v1` keyed by the pseudonymous edge ID.
5. Reject out-of-range values, non-binary exact comparisons, missing/self
   record IDs, unknown columns, schema drift, and overwriting of any output.

### Relation compiler

The UCI truth is an entity relation, not promised to be a matching. Compile a
matching benchmark as follows:

1. Scan **all ten blocks together** and form connected components using only
   positive adjudicated pairs.
2. Retain a component as a truth dyad only when it has exactly two distinct
   records and its positive edge occurs once. Do not split larger components
   into arbitrary pairs.
3. Mark the records in retained dyads as core. Retain every documented UCI
   candidate edge whose endpoints are both retained core records. The hidden
   dyads then constitute the benchmark's reference perfect matching under the
   supplied adjudicated labels. This is not a claim that UCI blocking found
   every real-world same-entity pair.
4. Decompose the retained candidate graph into connected components for exact
   optimization. Connected components are computational units, **not** assumed
   iid calibration markets.
5. Predeclare one edge-additive query whose value is observable on every true
   dyad used for evaluation, for example postal-code agreement. Candidate-edge
   missingness contributes lower/upper edge weights from its declared support.
   Report score-free endpoints first; any learned restriction is secondary.
6. Split connected components, not individual edges, across source/test folds.
   Do not make a conformal coverage claim unless a defensible external market
   sampling unit is supplied separately.

### Commands and reproducibility

The adapter takes extracted CSV block paths and performs no network access.

```bash
python code/ai_pilot/external_benchmarks/uci_rlcp_adapter.py metadata

python code/ai_pilot/external_benchmarks/uci_rlcp_adapter.py profile \
  /secure/uci_rlcp/block_*.csv \
  --output /secure/uci_rlcp/relation_profile.json

export UCI_RLCP_ID_KEY='an-uncommitted-random-key-of-at-least-16-bytes'
python code/ai_pilot/external_benchmarks/uci_rlcp_adapter.py compile \
  /secure/uci_rlcp/block_*.csv \
  --truth-dyads-only \
  --public-output /secure/uci_rlcp/public_coarsened.jsonl \
  --truth-output /secure/uci_rlcp/hidden_pair_truth.jsonl \
  --manifest-output /secure/uci_rlcp/compile_manifest.json
```

Run the offline adapter/benchmark tests with:

```bash
python -m unittest discover \
  -s code/ai_pilot/external_benchmarks/tests -v
```

Install the isolated loader dependency and rerun the block-1/FEBRL4 benchmark
without network access:

```bash
python -m pip install -r \
  code/ai_pilot/external_benchmarks/requirements.txt

python code/ai_pilot/external_benchmarks/run_external_relation_truth_benchmark.py \
  --uci-block-zip /secure/uci_rlcp/block_1.zip \
  --output-json /tmp/external_relation_truth_results.json \
  --output-report /tmp/EXTERNAL_RELATION_TRUTH_REPORT.md
```

The runner refuses to download data or overwrite outputs. FEBRL4 applies the
analyst-created `febrl4_coarsened_v1` operator (Soundex names, capped length
bins, suburb/address initials, and birth decade), independently permutes each
bipartite side, builds complete candidate graphs without truth, excludes birth
decade from its target-free score, and consults hidden links only for final
evaluation. Market membership itself is truth-conditioned and is labeled as
such. The result pins the UCI block ZIP and both bundled FEBRL4 CSVs by
SHA-256, records dependency versions and observed runtimes, and stores no raw
row, identifier, truth edge, or endpoint witness.

## Exact remaining full-data gate

The block-1 audit and FEBRL4 method-fit test pass their limited contracts. A
full UCI empirical result still requires the official all-ten-block scan.
Before any all-data paper result, that scan must establish all of the
following:

1. the official archive hash/member manifest and actual delimiter/filenames;
2. exactly 5,749,132 unique candidate pairs and 20,931 unique positive pairs,
   reconciling any duplicate pair across files before analysis;
3. the full positive-component size histogram and the count of two-record
   components with a nonmissing predeclared query field;
4. enough retained dyads and negative cross-dyad edges to form nontrivial
   ambiguous candidate components (not isolated truth edges);
5. 100% inclusion of each retained truth dyad in the retained candidate graph;
6. component-level source/test separation with no record or edge overlap; and
7. runtime, width, replayed endpoint witnesses, point-linkage baseline, and
   score-free aggregate coverage against the isolated truth file.

Failure of items 3 or 4 makes UCI a pair-classification benchmark only. Even a
pass does not provide natural independent markets, so it cannot by itself
complete the matching-level conformal calibration gate or license transfer to
Chicago.
