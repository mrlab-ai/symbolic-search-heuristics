# Private reproducibility audit manifest (release after unblinding)

This internal manifest binds the exact execution and analysis records used by
the paper. It is deliberately excluded from the double-blind review bundle:
revision, scheduler, account, path, and source identities can link the
submission to its authors. The review bundle is PDF-only. After unblinding,
this manifest accompanies the source, record, and analysis verification pack.

The paper does **not** combine runtimes or coverage from the earlier P4/P5/P6
study. The focused cap-grid pilot and the focused full evaluation use one
planner revision and one execution environment. The 50 pilot tasks are a
development screen only. Every one of the 1,377 tasks, including those 50, is
rerun in every full-evaluation configuration; no pilot record substitutes for
a full-census cell.

## Typesetting provenance

The review manuscript uses the official AAAI 2027 author kit retrieved on
2026-08-24 from `https://aaai.org/authorkit27/`. The downloaded archive was
5,495,535 bytes with SHA-256
`e28c6ac9bc6eb3b4e2d849547d2cefb5162610ee39d0a12e0dc62d1126b44a7d`;
two independent downloads were byte-identical and passed the archive integrity
test. The repository vendors the untouched files `paper/aaai2027.sty`
(SHA-256
`391bce82815bf698b8e382dd3ae7e30c75d7ab46df140cb295b1266016bc8623`)
and `paper/aaai2027.bst` (SHA-256
`5db7765ba99de5c1e4686f9b3940a0add9c5e702f2164514462bec130ccb6e3c`).
Both the build and the standalone submission checker reject links or byte
drift in these files. AAAI 2027's own page rule is not used as an ICAPS rule;
until ICAPS 2027 publishes its author instructions, the project audit retains
the preceding ICAPS eight-content-page assumption as an explicit configurable
target.

## Executable sources

- Pilot runner and parser:
  `experiments/exp_pdb_cap_grid_pilot.py` and
  `experiments/pdb_cap_selector_parser.py`
- Pilot analyzer:
  `experiments/analyze_pdb_cap_grid_pilot.py`
- Focused full protocol and runner:
  `experiments/pdb_cap_grid_full_protocol.py` and
  `experiments/exp_pdb_cap_grid_full.py`
- Focused full analyzer and frozen secondary contract:
  `experiments/analyze_pdb_cap_grid_full.py` and
  `experiments/pdb_cap_grid_full_secondary_contract.py`
- Fail-closed paper renderer:
  `experiments/render_pdb_cap_grid_full_paper.py`
- Independent post-hoc diagnostics analyzer and fail-closed renderer:
  `experiments/analyze_pdb_cap_grid_posthoc_review.py` and
  `experiments/render_pdb_cap_grid_posthoc_review.py`
- Prospective profile holdout runner, execution audit, recovery, and analyzer:
  `experiments/exp_pdb_profile_certificate_holdout.py`,
  `experiments/audit_pdb_profile_certificate_holdout.py`,
  `experiments/recover_pdb_profile_certificate_holdout.py`, and
  `experiments/analyze_pdb_profile_certificate_holdout.py`
- Frozen denominator audit and fail-closed holdout renderer:
  `experiments/analyze_pdb_profile_denominator_audit.py` and
  `experiments/render_pdb_profile_certificate_holdout_paper.py`
- Fixed-heuristic variable-order intervention runner and analyzer:
  `experiments/exp_pdb_profile_order_intervention.py` and
  `experiments/analyze_pdb_profile_order_intervention.py`

## Common benchmark and planner identity

- Benchmark repository revision:
  `48d6a00d482de2384a9e751f9343df58bf5582be`
- Benchmark origin: `https://github.com/aibasel/downward-benchmarks`
- Planner revision:
  `e04d56cc61d00c954f2369e9fb74bd469277d52e`
- Stripped planner binary SHA-256:
  `77cf4950563be2d2a60aded13783a3ffe26c0c8391ac9d626f3bd618231941fa`
- Copied preprocessor SHA-256:
  `fc3233bfd260210cf4d0cce11146fe6f3198820d6e19a8b56740c1240039378b`
- Full task-manifest SHA-256:
  `295bff030c51eaf39871714335ff9cb945ce39ebc556774eeb3bfad112681345`
- Full task-source-record SHA-256:
  `9ce25a012592bfb2557fe21cc4a3fdb3dbd24f9d2a4ed79ee16e75be183be5dd`
- Source-manifest SHA-256:
  `7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168`
- Domain-sequence SHA-256:
  `b0d849f351ff6d5c793d9c209c67c11ab5a7d6963fed5666f5ad49ce73845811`
- Domain-count-vector SHA-256:
  `5db83d994be7d9145233adb0a3839a69f8717145878d08b138f328b19fc9d9e2`
- Primary 1,327-task complement manifest SHA-256:
  `1e126791b438d903cb6adcc441391b92d76a7e14cf46f6a89465a066823a986f`
- Primary task-source-record SHA-256:
  `158e5446e3b97ddd63095441c518ecbe6d2e3ce3529aa9a8fd412df23e706068`

Every selected PDDL source is byte-attested before grid construction. Each run
receives a separate read-only single-link domain/problem copy, and the launch
gate rechecks all copied bytes and both executables.

## Development mechanism screen

- Protocol: `pdb-cap-grid-development-screen-v3`
- Launch revision:
  `6fb512eb6b0359b38f23e4f72053d0027b697e00`
- Analysis revision:
  `91c60fa37c6c32e070df92db7037e5c651fdf90f`
- Screen task-manifest SHA-256:
  `3195dac7e62a34e5ac4cbeb715ab7f9b99e2ee64341082dd7d718ea2820751ca`
- Matrix: 50 tasks x 6 configurations = 300 fresh cells
- Fetched properties: 6,910,178 raw bytes; raw SHA-256
  `f7d4b3142ac974ebf3949864f4a6c5651aa14ba9f67655bc6b758175a29380ba`;
  protocol-canonical logical SHA-256
  `cfb7ddca779c3d5645635057b9ae5f9bafbb65a91d1de89d026b879e6196ca22`
- Accepted artifact:
  `experiments/artifacts/pdb-cap-grid-development-p4/analysis-v3.json`
  (9,515 raw bytes), SHA-256
  `d28ae76392d0befb9ec927a519dc52aef61bc76e2aa1f12f6197549f853f4656`

The prospective promotion rule required a complete certified screen, matching
same-K raw pools, solved-cost agreement, strictly more cap-aware
semantic-nontrivial selections, and nonnegative K=8 coverage wins minus losses.
K=32 was a fixed sensitivity and could not replace K=8. The observed K=8
screen passed that rule. No screen performance observation enters either the
1,327-task primary complement or the full-census performance rows.

## Focused full evaluation

- Protocol: `pdb-cap-grid-focused-full-evaluation-v1`
- Outcome-independent implementation revision:
  `af483cab87a9e2cc6873f8aae1bcc34294bcd4c3`
- Clean launch revision:
  `0fa5ecc1d93884e9cf35b433bacfe684765ba112`
- Configurations: blind forward search; uncapped unaligned M&S (10,000
  states); CEGAR PDB (100,000 states, seed 2011, 10-second pattern-generation
  limit); exact-width PDB selector K=8; cap-aware PDB selector K=8
- Matrix: 1,377 tasks x 5 configurations = 6,885 fresh cells
- Option-matrix SHA-256:
  `94238d64a699142ef81cc4a35489467af8b78dcdf46973536556eb7e3f6b6f78`
- Array assignment: 984 tasks, at most seven cells each; SHA-256
  `977a1cac30b027990c8ed5f23803032a351c9497b26a837b303ba9604fc4f775`
- Prospective start-job SHA-256:
  `24efc07fc6fdfd19d2a7532d4e717f072b1f5a2e893b946b529aedf4158ebc81`
- Private scheduler job: `1363335`; account binding:
  `WBH_ACCOUNT=naiss2025-5-561-cpu`
- Completion: all 984 array elements `COMPLETED` with exit `0:0`; all 6,885
  cells have canonical completion markers, wrapper exit 0, restart count 0,
  and regular driver logs; zero partial archives, temp markers, nonempty driver
  errors, or Slurm-log bytes
- Fetched properties: 151,753,705 raw bytes; raw SHA-256
  `0e97eb3a18271f149874f49ec1c0efbd362ad5a863665e7a0600c0ad8cdbbc12`;
  protocol-canonical logical SHA-256
  `bddc69b2eedcc1442e6a42517d4d294e9a6ae0ab7dbf4aebc49714b152c0f215`
- Lab collected exactly 6,885 records with zero unexplained parser errors

The primary population is the fixed 1,327-task development complement with all
46 domains. The primary estimand is cap-aware minus exact K=8 equal-domain
macro coverage. The all-1,377-task contrast is a prespecified census
sensitivity. Blind, M&S, CEGAR, full-census rows, and all operational ratios
are descriptive. There are no confidence intervals, p-values, adaptive
reranking, or superpopulation claims.

## Analysis, secondary contract, and paper data

- Analysis schema:
  `symbolic-search-heuristics/pdb-cap-grid-focused-full/v1`
- Analysis protocol: `pdb-cap-grid-focused-full-analysis-v1`
- Analyzer input-pin commit:
  `1c44fc197d0804141f3a941347fc2b8d7d267974`
- Accepted canonical artifact commit:
  `a9fbfc6b0c3935bb124ae93b79d9d94ec2704fca`
- Accepted artifact:
  `experiments/artifacts/pdb-cap-grid-focused-full/analysis-v1.json`
  (31,495 raw bytes), SHA-256
  `fb8db53b4f5eea7306961351d110b0d331abc87fa2a31242321de429f32ad60a`
- Artifact sidecar:
  `experiments/artifacts/pdb-cap-grid-focused-full/analysis-v1.json.sha256`
- The analyzer was run twice from the clean pin commit; both byte streams were
  identical to the committed artifact
- Secondary descriptive contract SHA-256:
  `1df86a1255cb301ffe2b6eb0db52ba81ca7f8c511e5a011cd028d8eff2dfc862`
- Secondary timing status:
  `frozen-during-active-full-execution-before-properties-fetch-or-scientific-outcome-aggregation/v2`
- Renderer pin commit:
  `fbe8f4f4875daf4b96fa130602018e9ad1ad2c6b`
- Generated-paper-data commit:
  `dd8037db2d949ef55d1435696001805d4134b34e`
- Generated paper input:
  `paper/generated/pdb-cap-grid-full-v1.tex` (9,146 raw bytes), SHA-256
  `6bed124d4972bb76c87739cb96bf09d65f65c0a70818072f131f794d3421fb65`
- Two independent renderer invocations were byte-identical; restricted atomic
  `--write` and subsequent `--check` both passed

The renderer reads only the committed canonical artifact and its exact
sha256sum sidecar. It validates schema, provenance, population conservation,
all primary-within-census relations, mechanism contingencies, PAR2 identities,
paired denominators, selector summaries, and generated table dimensions. It
never reads Lab properties or run directories.

## Preserved archive and post-hoc review diagnostics

The exact preserved evaluation archive is
`/nobackup/proj/disk/dfsplan/personal/jendrik/symk-pdb-cap-grid-full-protocol/experiments/data/exp_pdb_cap_grid_full-eval.tar.gz`;
its logical basename `exp_pdb_cap_grid_full-eval.tar.gz` has SHA-256
`f2bf90dbc2e06ea109b221bb1de250bd7560776faf9d42f4955da8fef961e12d`.
The archive contains the fetched `exp_pdb_cap_grid_full-eval/properties`
whose raw-file and canonical logical digests are recorded in the focused-full
section above.

Raw experiment regeneration requires the clean launch revision, planner,
benchmark checkout, revision cache, scheduler envelope, and account binding
declared above. The Python environment is installed exactly from
`experiments/requirements.txt` (SHA-256
`7408736632aaa534614e319322fe09a5ca9bb8e0874d7b6e7096a940e4bcfb63`),
which pins `lab==8.0`; the archived records report Python 3.9.25, installed
Lab 8.0, and required Lab 8.0. The common runner reads the scheduler account
from `WBH_ACCOUNT` but has a different fallback account. The focused-full
runner therefore rejects build or launch unless the exact account binding
recorded above is supplied. Verifying the committed analysis artifacts does
not recreate or authorize a raw cluster run.

After extracting the archive, invoke the independent post-hoc analyzer listed
under Executable sources with `--properties` pointing to that exact
`properties` file. It uses no Lab imports and fails closed on the canonical
logical properties digest already recorded above, the exact record/schema
manifest SHA-256
`e944922a633c08594e48a2c667bf84cd35d6b8121d85d2b1c672aed4abea533e`,
and the accepted prospective artifact and execution pins. Its role is
`post-hoc-theorem-guided-descriptive`: it reports no tests, intervals, or
population generalization. The audit now includes same-PDB raw-to-capped
certificate compression; conservation of completed bucket/image-call counts,
expanded nodes and exact-decimal image time; normalized work per completed
call with explicit zero denominators; and target-metric effort for strictly
certified triple-solved blind/exact/cap-aware tasks, including finite-cap
leave-one-domain-out descriptions. Triple-solved eligibility also certifies
one BDD piece per expanded bucket, while node leave-one-domain-out totals are
bound to the paired operational population. These additions do not alter the
frozen primary estimand or secondary contract.

- Canonical post-hoc artifact:
  `experiments/artifacts/pdb-cap-grid-posthoc-review/analysis-v1.json`
  (37,928 raw bytes), SHA-256
  `211ba15a3b15235175d5f98ec4d374dada5d00cacf8997a5f919543041a06312`
- Post-hoc artifact sidecar:
  `experiments/artifacts/pdb-cap-grid-posthoc-review/analysis-v1.json.sha256`
- Generated post-hoc paper input:
  `paper/generated/pdb-cap-grid-posthoc-v1.tex`, SHA-256
  `b31ded49ca6bf2ef35a089ea7cdd8628375610c2283ad78e92b29c3646b99e52`

The post-hoc renderer reads only that canonical artifact and sidecar. Its
self-test and `--check` gate validate the artifact pin and the generated TeX
byte for byte. Thus the committed diagnostics remain independently bound to
the canonical logical properties digest even where the Lab/account environment
needed for raw regeneration is unavailable.

## Exclusions and claim boundary

Earlier cluster runs and the earlier P4/P5/P6 study are not used by this paper.
The development screen determines only whether the cap-aware method advances
to the already frozen full protocol. The full matrix reruns all controls and
both selector variants under one environment. No missing cell is filled and no
old cell is reused.

The accepted primary result favors cap-aware over same-K exact selection, but
uncapped unaligned M&S is the best descriptive full-census coverage row.
Moreover, strict mechanism attribution is not certified because paired trace
coverage is incomplete, even though every observed paired raw-pool identity
matches. The paper reports these boundaries explicitly and does not claim that
cap-aware selection is a universally best heuristic or that the experiment
validates the worst-case theorem.
