# Terminal metric choice campaign protocol (v1)

This campaign tests whether terminal incidence `I` or masked joint residual
complexity `mJ` is the better predictor while holding every upstream choice
fixed. It is a new layer and does not modify the Confirmation A/B protocol or
launcher.

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
2. Only after the calibration receipt is sealed, obtain canonical standalone
   K=32 evidence for every sealed Confirmation B task. The producer binding
   repeats the exact planner/options/binary/tree manifest. Each record logs
   normalized pool and K=32 representative score certificates so the
   reference is reconstructed, rather than accepted as an arbitrary pool
   member. It contains no search outcomes.
3. Choose `--scheduler-time` and `--scheduler-memory` using only the redacted
   calibration receipt, then run `pdb_terminal_metric_choice_freeze.py` with
   those explicit values. This is the first campaign step
   allowed to open the sealed Confirmation B verifier. It fails unless
   Confirmation A authorized the guided study, B is still the exact sealed
   300-task cohort, source-audit v4 provenance validates, calibration completed,
   and every source, planner, option, task, K=32 record, and receipt hash binds.
   Campaign resources are absent from source defaults and are frozen only by
   this post-calibration operation; the freeze rejects values too small to
   cover three sequential planner limits or one planner memory limit.

Every campaign input/output uses one exact lexical sealed path. Readers walk
every component below a trusted root through retained directory descriptors
with `O_DIRECTORY | O_NOFOLLOW`, open the leaf relative to its retained parent,
and revalidate all ancestor, leaf-descriptor, and leaf-entry identities after
same-descriptor reading and hashing. Calibration is completely
loaded and validated before the freeze code opens any A/B/v4 evidence. Its
generated IDs and domain/problem hashes are then checked against both sealed
A and B cohorts. No outcome may be inspected before the freeze exists.

## Execution

The three modes are:

- `terminal_dual_incidence_guided`
- `terminal_dual_mj_guided`
- `terminal_dual_matched_control`

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
semantic-failure triads block recovery.

All arms use the same 16 completed blind probe layers; fixed candidate pool;
cap grid; materialization; terminal-incidence measurements; joint-residual
measurements; and separate budgets `B_I` and `B_M` derived from the same
standalone K=32 reference. Only the final chosen pointer changes. A short probe
has no fallback and is not a complete campaign certificate.

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

The audit reruns the full parser from every stored outcome-free structural
trace before comparing arms. It requires byte-equivalent normalized structural
certificates across the three arms (timing/memory and the selected event are
excluded), mandatory run/array/family/triad mapping fields, validated scheduler
contract, exact standalone K=32 agreement, exact frozen mapping/provenance, and
complete reconstructed hashes, work, references, winners, and pointers.

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
cannot change the primary decision.

The parser, audit, and analyzer are deterministic except for the fixed-seed
bootstrap. Synthetic unit tests are the only tests permitted before launch;
they do not read campaign artifacts, data directories, or outcomes.
