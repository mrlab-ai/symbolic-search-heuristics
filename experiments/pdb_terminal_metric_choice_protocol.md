# Terminal metric choice campaign protocol (v1)

This campaign tests whether using terminal incidence `I` rather than masked
joint residual complexity `mJ` in an otherwise identical budget and selection
rule improves end-to-end search while holding every upstream choice fixed. It
is a new layer and does not modify the Confirmation A/B protocol or launcher.

## Authorization and sealing order

1. Seal the exact planner manifest, including the final revision descended
   from selector base `ccc93bed78d4aa864c2e27d68d80461c1c20807c`, cache
   name, driver/binary/preprocess/tree hashes, build options, all three search
   strings, option digest, and dual trace schema. Run
   `pdb_terminal_metric_choice_calibration.py` only on its three generated
   `__metric_choice_calibration__` development tasks. Those identifiers and
   bytes are defined prospectively in source and are ineligible for benchmark,
   Confirmation A/B, and source-audit cohorts. The external receipt exposes
   only trace completion, completed probe layers, and probe/selector CPU, wall,
   and peak-memory measurements. It cannot contain selected identities,
   winners, references, coverage, exit codes, search times, plan costs, or
   other search outcomes.

   The manifest is derived reproducibly from exact planner revision
   `8148f798f13059ee881ad2471bd20cdd61d2ec18` and its attested revision-cache
   entry. Create it once with
   `python3 experiments/pdb_terminal_metric_choice_planner_manifest.py produce`.
   This command uses exclusive creation and never replaces an existing file.
   Recheck the fixed artifact without rewriting it with the same command and
   action `verify`; verification independently re-derives the revision,
   selector ancestry, driver, binaries, source tree, options, searches, and
   trace-schema binding.
   Calibration verifies and executes the driver and binaries inside that
   manifest's exact revision-cache directory, never the mutable working-tree
   build, under the pinned Python 3.12.13 environment.
2. Only after the calibration receipt is sealed, obtain canonical standalone
   K=32 evidence for every sealed Confirmation B task. The producer binding
   repeats the exact planner/options/binary/tree manifest and the exact
   Confirmation B parse-receipt, fetch-receipt, and fetched-properties paths
   and hashes. The producer checks the parse-to-fetch-to-properties chain and
   rebuilds each record from the live, sealed B properties. Each record logs
   normalized pool and K=32 representative score certificates so the
   reference is reconstructed, rather than accepted as an arbitrary pool
   member. It contains no search outcomes. This standalone step is the first
   campaign step permitted to open the sealed Confirmation B verifier.
3. Choose `--scheduler-time` and `--scheduler-memory` using only the redacted
   calibration receipt, then run `pdb_terminal_metric_choice_freeze.py` with
   those explicit values. The freeze independently reopens and revalidates the
   sealed Confirmation B verifier. It fails unless
   Confirmation A authorized the guided study, B is still the exact sealed
   300-task guided-B projection from the fresh V11 census, the exact disjoint
   650-task Confirmation A projection and its freeze validate,
   calibration completed,
   and every source, planner, option, task, K=32 record, and receipt hash binds.
   The freeze must be made from a clean working copy whose parent is recorded
   as the freeze source revision; all campaign sources and bound inputs must be
   tracked with the same bytes at that revision. The planner revision, sealed-B
   V11 preflight source, preflight seal, and full seal revisions and the sealed
   Confirmation A and B freeze revisions must all be its ancestors. The
   freeze rebuilds the complete standalone evidence from the live B properties
   both before validation and immediately before exclusive publication.
   Campaign resources are absent from source defaults and are frozen only by
   this post-calibration operation; the freeze rejects values too small to
   cover three sequential planner limits or one planner memory limit. It also
   reconstructs the doubled maximum selector wall time and peak-memory delta
   from the nine redacted observations and rejects resources below the larger
   of those calibration floors and the planner-limit floors.

Every campaign input/output uses one exact lexical sealed path. Readers walk
every component below a trusted root through retained directory descriptors
with `O_DIRECTORY | O_NOFOLLOW`, open the leaf relative to its retained parent,
and revalidate all ancestor, leaf-descriptor, and leaf-entry identities after
same-descriptor reading and hashing. Calibration is completely
loaded and validated before the freeze code opens any V11 A/B evidence. Its
generated IDs and domain/problem hashes are then checked against both sealed
A and B cohorts. No outcome may be inspected before the freeze exists.
The inherited V11 provenance authenticates one fresh 1,640-task census, its
outcome and resource-exclusion summaries, the exact 950 eligible tasks, the
disjoint 650-task Confirmation A and 300-task guided-B projections, the
preflight authorization and canary chain, and the full, preflight, and combined
committed-file closures. No earlier campaign payload is reused. The direct
freeze embeds the canonical B source projection and the canonical A projection
from its own freeze; later readers validate those bytes without reopening the
V11 census payload. Repository closure construction also binds every V11
combined-closure path. If that path is independently bound by a later A, B, or
direct source manifest, the digests must agree; conflicting historical and
descendant bytes fail closed rather than receiving precedence.
The direct validator reconstructs the translator-source digest from exactly
the 38 `src/translate/*.py` entries in that committed closure and requires the
two authorized Confirmation A analyses to have identical SHA-256 digests.
Every recorded repository revision is exactly 40 lowercase hexadecimal
characters. At freeze time, ancestry is checked on each adjacent edge in the
ordered chain V11 source to preflight seal to full seal to Confirmation A
freeze to Confirmation B freeze to direct freeze; planner ancestry to the
direct freeze is checked separately.

## Execution

The three modes are:

- `terminal_dual_incidence_guided`
- `terminal_dual_mj_guided`
- `terminal_dual_matched_control`

After the freeze and its source closure are sealed, the only permitted launch
sequence is:

```
experiments/data/pdb-terminal-incidence-shadow-venv/bin/python -B experiments/pdb_terminal_metric_choice_runner.py build
experiments/data/pdb-terminal-incidence-shadow-venv/bin/python -B experiments/pdb_terminal_metric_choice_runner.py prepare-job
experiments/data/pdb-terminal-incidence-shadow-venv/bin/python -B experiments/pdb_terminal_metric_choice_runner.py launch
experiments/data/pdb-terminal-incidence-shadow-venv/bin/python -B experiments/pdb_terminal_metric_choice_runner.py status
```

All production runner, cohort, audit, execution, and analysis entry points
consume the embedded direct freeze. They derive the 300 tasks from its exact
guided-B projection and validate the benchmark bytes against the embedded
domain/problem hashes; they never reopen or recompute live Confirmation A/B
artifacts. Live A/B verification is restricted to construction of the direct
freeze.

The launch likewise requires a clean working copy. Its commit must descend
from the exact planner, V11 preflight source, preflight seal, full seal, sealed
Confirmation A and B freezes, and recorded direct-freeze source revisions; the
campaign-freeze bytes tracked in that commit must match the live freeze exactly.

`prepare-job` renders but does not submit. `launch` writes an exclusive
tokenized intent, then passes the exact validated job bytes on standard input
to the byte-pinned `/usr/bin/sbatch`; its recorded command is options-only and
contains no mutable script path. The receipt and SHA-256 pin are exclusive.
If the launcher stops after writing its intent, `recover-launch` may only
reconcile that token against the byte-pinned `sacct` journal; ambiguity or no
exact journal match fails closed and never triggers a second submission.

There are exactly 900 cells: one three-mode triad for each of the exact 300 B
tasks. Array task `t` owns run cells `3t-2`, `3t-1`, and `3t`. Within each
family, mode order rotates cyclically by task position. The full task-major
mapping and digest are frozen. The Slurm array is exactly `1-300`, has no `%`
throttle, uses exactly one node, one task, and one CPU per array task, and never
requeues automatically. Every SBATCH line is parsed as one canonical long-form
token; aliases, duplicates, space-form values, unknown directives, resource
overrides, throttling, and requeue are rejected. `PLANNER_CACHE_NAME` is a
frozen property. Recovery derives a canonical 300-entry journal from the
scheduler-array snapshot, scans the real run namespaces, archives every actual
started regular output without replacement, binds per-cell entry manifests,
and performs real post-archive and immediate pre-submit rescans. Submission is
only possible inside this coordinator, using the exact validated recovery
array and pinned in-memory job bytes. Every interrupted triad is replayed as
all three cells, including an interrupted triad whose three cells had all
completed. Zero interruption is an explicit no-submit result. Active or
semantic-failure triads block recovery. For infrastructure interruption, first
run `snapshot`, then `recover`. A stopped recovery submission is reconciled
with `recover-reconcile`. The protocol permits exactly one recovery wave;
interruption of that recovery, an incomplete recovery triad, or an interruption
before a recoverable launch intent exists fails closed rather than starting an
ambiguous additional wave.

Only when `status` reports 300 terminal-complete triads and all 900 structural
cell markers may `seal` publish the execution receipt and pin. The seal binds
the exact primary and optional recovery launch receipts, scheduler resource
rows, effective-attempt matrix, all dynamic run files, and Slurm logs. Before
each planner launch, the cell helper writes canonical
`execution-hardware-v1.json` containing only the unique whitespace-normalized
`/proc/cpuinfo` model name and `os.uname().machine`; it records no hostname,
job identifier, timestamp, raw processor data, or memory value. The seal
requires all 900 records, requires the three cells in each allocation to
agree, and binds their ordered digest and processor-model/architecture counts.
Parsing and fetching are rejected until this receipt revalidates against live
launch and scheduler evidence. Every run carries the canonical V11 source
provenance: census and code hashes; launch, execution, attestation, preflight,
and canary hashes; all-record and exact A/B projection hashes; all three source
revisions; all three committed-closure digests; and the Confirmation A freeze
hash and revision. It also carries a digest of the complete V11 bindings. The
double-run analyzer copies that closure,
the freeze and B-freeze revisions, standalone B receipt/property hashes and
the campaign execution-receipt path/hash and validated hardware summary into
both outputs and its receipt; hardware is non-gating provenance.
The post-seal sequence is:

```
experiments/data/pdb-terminal-incidence-shadow-venv/bin/python -B experiments/pdb_terminal_metric_choice_runner.py seal
experiments/data/pdb-terminal-incidence-shadow-venv/bin/python -B experiments/pdb_terminal_metric_choice_runner.py parse
experiments/data/pdb-terminal-incidence-shadow-venv/bin/python -B experiments/pdb_terminal_metric_choice_runner.py fetch
experiments/data/pdb-terminal-incidence-shadow-venv/bin/python -B experiments/pdb_terminal_metric_choice_analyzer.py
```

On tasks whose blind state space reaches 16 layers, all arms use the same
completed blind probe layers; fixed candidate pool; cap grid; materialization;
terminal-incidence measurements; joint-residual measurements; and separate
budgets `B_I` and `B_M` derived from the same standalone K=32 reference. Only
the final chosen pointer changes. If the blind state space yields fewer than
16 layers, all three arms must expose the same certified three-event
short-probe trace, exit `SEARCH_UNSUPPORTED` (34), record coverage 0, and
perform no candidate selection or fallback. Such a symmetric short triad is a
valid terminal campaign outcome: it is retained in both full-cohort contrasts
as PAR2=3600 in every arm, supplies no metric winner, and is excluded only from
the differing-winner subset. Any asymmetric status or short-trace mismatch
fails the audit.

## Trace certification

`pdb_terminal_metric_choice_parser.py` treats JSONL as an untrusted
certificate. Trace schema v2 adds a canonical breadth-first masked-ADD DAG for
each candidate/layer. The parser uses bounded iterative traversal and walks
reverse parents from
every active semantic terminal, normalizes the numeric dead-end sentinel, and
reconstructs `I`; the incumbent incidence-v3 projection remains byte-exact.
Every count, budget, identifier, and sentinel must have exact JSON integer
type (never Boolean or floating point). It rejects duplicate keys,
unknown/missing fields, malformed histograms, overlarge traversal certificates,
cycles, unreachable nodes, overflow-shaped integers, incomplete complete traces, trailing
events after a short probe, or any mismatch in:

- state-cut and candidate-pool canonical hashes;
- incidence-v3 canonical projection;
- `I` sums over 16 layers;
- `J_g`, the sum of distinct signed-BDD/regular-ADD joint residual pairs over
  every state cut except the terminal cut;
- `k_g`, distinct active finite heuristic values plus semantic dead end exactly
  once; and `mJ = sum_g k_g J_g`;
- terminal-cut exclusion, projection/product bounds, semantic dead-end
  separation, cap transforms, and cap-refinement monotonicity;
- K=32 reference, the distinct `B_I` and `B_M`, both feasibility/retained-cap
  flag sets, both winners, and the mode-selected pointer;
- complete identical incidence/joint work accounting and all bound hashes.

The audit reruns the applicable complete or short parser from every stored
outcome-free structural trace before comparing arms. It requires
byte-equivalent normalized structural certificates across the three arms
(timing/memory and, for complete traces, the selected event are excluded),
mandatory run/array/family/triad mapping fields, validated scheduler contract,
and exact frozen mapping/provenance. Complete triads additionally require exact
standalone K=32 agreement and reconstructed hashes, work, references, winners,
and pointers. Short triads require exact unsupported outcome metadata, forbid
all candidate-selection fields, and retain only their common schema, variable
order, and incomplete probe certificate.

## Registered analysis

The primary contrast is incidence-guided minus mJ-guided. It passes only if all
four clauses hold:

1. incidence-guided coverage is not lower;
2. equal-family normalized PAR2 improvement is at least `0.02`;
3. the pre-registered 100,000-replicate family bootstrap 95% lower bound is
   strictly positive;
4. every leave-one-family/domain-out estimate is strictly positive.

The same four clauses must hold on tasks where the reconstructed I and mJ
winners differ, and that subset must contain at least 50 tasks from at least 10
families. Incidence-guided versus matched K=32 is reported as secondary and
cannot change the primary decision. Symmetric short-probe triads remain in
both full-cohort contrasts as three equal PAR2 failures and are excluded from
the differing-winner subset because they expose no winners.

Every contrast also reports a fixed non-gating outcome decomposition. Its
paired solve table counts tasks solved by both arms, only incidence, only the
comparator, or neither. Among tasks solved by both arms, it reports
`(comparator total time - incidence total time) / 1800`, aggregated task first
with equal family weight. This decomposition is frozen before any campaign
outcome and cannot change a decision.

Before launch we fix a non-gating mechanism panel over the certified selector
trace: treatment uptake and cap-versus-pattern changes; own-budget utilization,
binding and cross-feasibility/retention; the frozen selection-score relation
and first decisive score criterion among the two winners and reference;
candidate-work counts; and phase
overhead. Complete triads contribute these selector diagnostics once per task,
not once per arm. Symmetric short probes contribute only support, completed
layers and probe-overhead summaries. The trace contains neither exact
partition effort `E` nor a final-search bucket trajectory, so this panel tests
the selection mechanism and cannot establish fragmentation mediation. It is
descriptive and cannot change the primary decision.

The main paper will always report complete/short support, the I-versus-mJ
winner-change rate among complete probes and cap-only-versus-pattern split, the
higher/tied/lower
frozen selection-score relation and decisive criterion on differing winners,
own-budget utilization
and binding, and paired differences in the sum of recorded probe and selection
wall/CPU times. The supplement or artifact
will always publish the complete selected-candidate source-set, cap and
pattern-size histograms,
irrespective of their direction.

The parser, audit, and analyzer are deterministic except for the fixed-seed
bootstrap. Synthetic unit tests are the only tests permitted before launch;
they do not read campaign artifacts, data directories, or outcomes.
