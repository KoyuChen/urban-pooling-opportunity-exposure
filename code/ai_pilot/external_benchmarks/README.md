# External relation-truth benchmark audit

Checked against primary repository/package documentation on **2026-08-27**.
No external data rows are committed here. The executable audit was run against
all ten cached UCI inner block ZIPs and the FEBRL4 files bundled in
`recordlinkage==0.16`; only aggregate results, hashes, and declarative metadata
are checked in. The installed loader did not retain the outer `donation.zip`,
so the report pins every inner ZIP/member but does not invent an outer-archive
hash.

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

The committed [all-ten UCI report](results/UCI_ALL_BLOCKS_REPORT.md) reconciles
exactly 5,749,132 unique candidate pairs and 20,931 unique positives, with no
self-pair, within-block duplicate, cross-block duplicate, or label conflict.
The full positive relation has 12,925 components over 29,301 records, reaches
nine-record entities and positive degree eight, and is therefore not a
matching. The global reduction retains 10,297 postal-observed truth dyads; its
induced graph has 249,048 edges, including 238,751 alternatives. The combined
[benchmark report](results/BENCHMARK_REPORT.md) also records FEBRL4's six-pair
exhaustive and 20-pair numerical checks. Verified Blossom solves the UCI upper
endpoint exactly at `9924/10297 = 0.963776`; the lower endpoint remains
`UNRESOLVED` after the predeclared 120-second limit and is not replaced by a
fractional relaxation. These results do **not** validate the joint latent
endpoint-attribute compiler, Chicago transfer, UCI blocking recall, or
independent-market split-conformal coverage.

The source is already privacy-reduced: it exposes record identifiers and
pairwise agreement patterns, not the underlying names, dates of birth, sex, or
postal codes. The checked-in adapter additionally HMAC-pseudonymizes record
identifiers, bins continuous name similarities, turns missing binary
comparisons into declared `{0,1}` supports, and puts `is_match` in a physically
separate truth file. Because every raw block is label-sorted, the compiler now
sorts output by keyed HMAC edge ID rather than source position, audits 96-bit
pseudonym collisions, stores no key hash, and cleans up both public/truth
outputs on handled exceptions. The two-file install is not claimed crash-atomic.

## Candidate comparison

| Candidate | License / access | Reproducibility and size | Relation truth | Coarsened operator fit | Main leakage or validity risk | Verdict |
|---|---|---|---|---|---|---|
| **UCI Record Linkage Comparison Patterns (Krebsregister), dataset 210** | Explicit **CC BY 4.0**; official page offers a public 53.8 MB archive and `ucimlrepo` loader; no account is described | Stable DOI `10.24432/C51K6B`; 100,000 source records, 5,749,132 blocked candidate pairs, 20,931 adjudicated matches, ten approximately balanced files | Real deduplication/entity relation; pair labels came from extensive manual review; record IDs allow positive connected components | Strong matching-only special case after preserving group topology and isolating a truth-conditioned dyad subset | The supplied blocking procedure can omit true pairs; ten files are edge partitions over heavily overlapping records, not independent markets; positive components contain more than two records; source row order reveals labels | **Selected real boundary test. All ten blocks executed and exactly reconciled.** |
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
2. Record the archive SHA-256 and member manifest before extraction. In the
   current cache, `recordlinkage==0.16` already extracted and discarded the
   outer `donation.zip`; therefore `archive_sha256: null` is a provenance
   limit, not a wildcard. The audit instead pins SHA-256, CRC32, and sizes for
   all ten inner ZIPs and CSV members and reconciles the official totals.
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
5. Never preserve source row order: all ten raw files put positive labels
   before negative labels. Stage rows privately and emit them in ascending
   HMAC edge-ID order. Store neither the key nor a hash of the key.
6. Audit truncated node/edge pseudonym collisions and install the public and
   truth files only after the complete parse, keyed sort, and serialization
   succeed.
7. Reject out-of-range values, non-binary exact comparisons, missing/self
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
6. Audit component sizes before proposing any split. In the all-ten result one
   component contains 19,346 nodes and 93.94% of retained dyads, so no
   source/calibration/test split is formed. Do not make a conformal coverage
   claim unless a defensible external market sampling unit is supplied
   separately.

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

Install the isolated external dependencies and rerun the all-ten UCI audit
without network access:

```bash
python -m pip install -r \
  code/ai_pilot/external_benchmarks/requirements.txt

python code/ai_pilot/external_benchmarks/uci_all_blocks_audit.py \
  --uci-block-dir /secure/uci_rlcp \
  --frontier-time-limit-seconds 120 \
  --output-json /tmp/uci_all_blocks_results.json \
  --output-report /tmp/UCI_ALL_BLOCKS_REPORT.md
```

Use `--skip-frontier` for the unconditional topology-only audit; it records the
truth-conditioned endpoint status as `NOT_RUN` without suppressing any
topology result. The full endpoint path uses pinned `rustworkx` Blossom with
maximum cardinality, `verify_optimum=True`, and independent aggregate witness
replay. The runner refuses to download data or overwrite outputs. FEBRL4 applies the
analyst-created `febrl4_coarsened_v1` operator (Soundex names, capped length
bins, suburb/address initials, and birth decade), independently permutes each
bipartite side, builds complete candidate graphs without truth, excludes birth
decade from its target-free score, and consults hidden links only for final
evaluation. Market membership itself is truth-conditioned and is labeled as
such. The result pins the UCI block ZIP and both bundled FEBRL4 CSVs by
SHA-256, records dependency versions, and stores no raw row, identifier, truth
edge, or raw endpoint edge list. It discloses aggregate witness replay counts
and a digest. Observed runtime fields are omitted from the checked-in artifacts.
The topology/count output is deterministic; a time-limited solver status is an
observed environment-dependent outcome and is not claimed byte-identical across
hardware.

## Completed all-ten gate and remaining boundary

The v2 combined artifacts at `results/benchmark_results.json` and
`results/BENCHMARK_REPORT.md` replace the stale v1 block-1 UCI section while
preserving the FEBRL4 evidence. The dedicated all-ten UCI JSON/report expose
the same UCI object separately for easier replay and audit.

The all-ten scan now establishes exact row/positive totals, zero duplicate or
conflicting pairs, the complete candidate and positive topology, the global
dyad population, query missingness, 100% retained-truth eligibility, induced
candidate topology, and privacy-safe provenance. It also falsifies two hoped-for
shortcuts:

1. block-local dyads are not globally valid—7,597 of 17,910 apparent local
   dyads join larger positive entities through other blocks; and
2. component-level source/calibration/test splitting is not meaningful—the
   19,346-node giant component dominates the retained graph.

Thus UCI closes the real-data topology gate and supplies an exact upper
matching endpoint, while the exact lower endpoint remains a clearly isolated
computational gate. It also supplies neither natural independent markets nor
blocking recall. It cannot by itself complete matching-level conformal
calibration or license transfer to Chicago.
