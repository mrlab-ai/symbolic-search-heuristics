#!/usr/bin/env python3
"""Create and verify anonymous semantic projections of accepted P4/P5 data.

The accepted Lab ``properties`` files contain four execution-packaging
identities that are irrelevant to every reported estimand: two absolute
checkout paths, the compute-node name, and the allocation name.  This utility
replaces exactly those four values with fixed public sentinels.  It never
drops a key and never changes any other value.

Projection is deliberately tied to the byte-exact accepted inputs.  Both raw
and projected files have pinned sizes, SHA-256 digests, record counts, logical
digests, source-key inventories, and per-record key-schema fingerprints.
Unknown or missing fields therefore fail closed.

The ``verify-analysis`` command runs an independently byte-attested replay
implementation after an in-memory compatibility substitution for the frozen
administrative account.  The P4 analyzer is byte-identical to its artifact
freeze; the P5 descendant differs from its artifact-freeze analyzer only in
self-test coverage for the later pre-search outcome 21, not in analysis logic.
All scientific validation remains active.  Generated documents must match the
committed artifacts exactly after removing only the explicitly declared
properties-digest identities.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = SCRIPT_DIR / "artifacts"
PROJECTION_PROTOCOL = (
    "arrhenius-public-properties/exact-four-field-normalization/v1"
)

# This is the complete normalization allowlist.  Values are replaced at the
# top level of every record; keys are retained.  The absolute path sentinels
# deliberately satisfy the frozen analyzers' path-shape and consistency check.
NORMALIZED_FIELDS = {
    "benchmark_worktree": "/artifact/downward-benchmarks",
    "repo": "/artifact/symk",
    "node": "artifact-node",
    "scheduler_account": "artifact-account",
}


class ProjectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileIdentity:
    size: int
    sha256: str


@dataclass(frozen=True)
class StageSpec:
    name: str
    accepted: FileIdentity
    record_count: int
    accepted_logical_sha256: str
    source_keys_sha256: str
    record_schema_sha256: str
    projected: FileIdentity
    projected_logical_sha256: str
    analysis_adapter_logical_sha256: str


STAGES = {
    "p4": StageSpec(
        name="p4",
        accepted=FileIdentity(
            13427825,
            "8b3e6862629a6a7b9234c13083e9840956be5bd973de49e6c9e7831627274dbb",
        ),
        record_count=1000,
        accepted_logical_sha256=(
            "18c53fb37c3968ab394643da6caff73eb822bbc96eda1836a9bf138b716ffbce"
        ),
        source_keys_sha256=(
            "73772db715306a03152099914a33a6af0c84cdbc58dc30e663063518adc050b1"
        ),
        record_schema_sha256=(
            "a86c0d0de6751c87033a486b7f3fb12f04713e90b2c079b127b00e6e1b0d18fe"
        ),
        projected=FileIdentity(
            10714087,
            "6b7bfa9515105825e775e33356f61764ed1c555c5273514b87be591ab369529b",
        ),
        projected_logical_sha256=(
            "dc5eccd39688606755a7968fe67965f59dcd7a8920e4d51c167e81ada1c4076b"
        ),
        analysis_adapter_logical_sha256=(
            "ba2a36bf87c0deb0318d1442f529c1cf89feec8b75f0d39e1e1f814b7b87c8c0"
        ),
    ),
    "p5": StageSpec(
        name="p5",
        accepted=FileIdentity(
            9834799,
            "d508298425b356023b589e643115ab482419c140da19b6744bbeff57a84bc10f",
        ),
        record_count=644,
        accepted_logical_sha256=(
            "0fab37f024188138f0ef2c1468bfe688404243f05cf682212532adf6e200cab1"
        ),
        source_keys_sha256=(
            "ee1b1e80f0e8e4e75ebd177e5f80181cd1f6589fe23d6015e9a6bc92fe9e9cb4"
        ),
        record_schema_sha256=(
            "fd37fd282971026e4da643a4bc1f5d65908324e51280fac6452f632d682ee92b"
        ),
        projected=FileIdentity(
            7966555,
            "4267f384cc6e23d634796fe33efd0054c103d8186df3d4f4fb44f7613c2ce45b",
        ),
        projected_logical_sha256=(
            "996fcc2e1f0990b36afb64dde3a1334565d25d3343678926ddd2619f35857dec"
        ),
        analysis_adapter_logical_sha256=(
            "c36eb1ebefbcff97f05e5e45ba1301a85cb30f55222ad62f439409a1483f3766"
        ),
    ),
}


# ``verify-analysis`` is itself tied to an exact reviewed implementation and
# its direct data contracts.  This prevents a later analyzer edit from being
# silently treated as the accepted P4/P5 analysis.
ANALYSIS_CONTRACT_FILES = {
    "analyze_arrhenius_selector_pilot.py": FileIdentity(
        176939,
        "6b9aa46c2670e89727ceee6d8ae9922d21c8bd818a770327219abd9cfb026f84",
    ),
    "analyze_arrhenius_selector_validation.py": FileIdentity(
        105519,
        "ac4d20cbcaaf6e4387c2741e61f2640e844ae1eb627b866fd0447bb8985b5471",
    ),
    "analyze_ms_caps_pilot.py": FileIdentity(
        43903,
        "d49b311d8daa375956b8adde5a4e8fdb7a45760656acea147f2bb1ebb4026f20",
    ),
    "exp_arrhenius_selector_pilot.py": FileIdentity(
        72125,
        "11d15a6e1e414a37e8c4009a2292cae8dccbd367e6324eacb9a17b2307f6129e",
    ),
    "exp_arrhenius_selector_validation.py": FileIdentity(
        116940,
        "f1a4c4e37386c40137c572756be1d60f27ea304fc91366380a0cfee73a5e5548",
    ),
    "exp_arrhenius_common.py": FileIdentity(
        130510,
        "eec4bfd56881aa62d2befee832d77d05b248f7701396afe9f7aa3ad835130c35",
    ),
    "wbh_parser.py": FileIdentity(
        18485,
        "6197bbd52e258ca309f442530d8475b1254229a7ee43fe4bc32ae4ca34052436",
    ),
    "validate_wbh_log.py": FileIdentity(
        17567,
        "956f796a2ff9d977ef7113947e5f0f8ac656015ea9804ab11d7287acdc186da1",
    ),
    "suite_cost_manifest.py": FileIdentity(
        23420,
        "7ab321838bc8d01ac42bbd37a0c9707ed401bbea41cd9ae7527a242b5c1ec2f8",
    ),
    "selector_pilot_suite.txt": FileIdentity(
        1708,
        "b83d2ce1e5b4474550cd033bd5cb7726a8f86296745ee34be1c66fdb0239ae2c",
    ),
    "heuristic_finalists_validation_suite.txt": FileIdentity(
        3971,
        "08e20e6e37e7a2a3a1bf395766b748e3b3ec74a5c626c67c3c759381b1f4e1c5",
    ),
    "suite_wbh_operator_costs.json": FileIdentity(
        990374,
        "7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168",
    ),
    "suite_wbh_operator_costs.json.sha256": FileIdentity(
        96,
        "a57735f84c28436b279b6550f9581839128ca8d805436d40f9709d2d3bfd6fcd",
    ),
    "requirements.txt": FileIdentity(
        269,
        "7408736632aaa534614e319322fe09a5ca9bb8e0874d7b6e7096a940e4bcfb63",
    ),
}


ACCEPTED_ARTIFACTS = {
    "p4_selection": (
        Path("arrhenius-selector-screen-p4/selection-v3.json"),
        FileIdentity(
            30744,
            "d35a1df68eebbd099fe81f86e6e0f6a96ce770572574f9ae013ab4eb0b2c8eb2",
        ),
    ),
    "p4_report": (
        Path("arrhenius-selector-screen-p4/certified-report-v2.json"),
        FileIdentity(
            58870,
            "e75daadefc6cf3cad3121ffb28959659dbc78523970945d575a97b18a319252c",
        ),
    ),
    "p5_analysis": (
        Path("arrhenius-selector-heldout-p5/analysis-v3.json"),
        FileIdentity(
            30647,
            "7c598f068164224272b8ba035b987973f35d0d45e695f90c9083931790908cea",
        ),
    ),
}


ANALYSIS_EXCLUSIONS = {
    "p4_selection": (("pilot", "properties_canonical_sha256"),),
    "p4_report": (
        ("identity", "pilot", "properties_canonical_sha256"),
        ("identity", "selection_artifact_raw_sha256"),
    ),
    "p5_analysis": (("execution", "properties_canonical_sha256"),),
}


PROJECTED_ANALYSIS_OUTPUTS = {
    "p4_selection": FileIdentity(
        30744,
        "18dd38b73420add56a3f4cbd3597820eff28c4a0a10abbe6e12997d5bec3c2cc",
    ),
    "p4_report": FileIdentity(
        58870,
        "541f67f9cfa4e622d85b5b798c22bc3d3133f5af2e8fbc1a6da3c0f07058169f",
    ),
    "p5_analysis": FileIdentity(
        30647,
        "ff55efc3365a73f2795e43d77a374dcd68b81eabffc3e0a90024952352ca7f19",
    ),
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_json_bytes(value, *, newline: bool = True) -> bytes:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as err:
        raise ProjectionError("value is not finite canonical JSON: {}".format(err))
    return raw + (b"\n" if newline else b"")


def _reject_duplicate_keys(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            raise ProjectionError("duplicate JSON key {!r}".format(key))
        value[key] = child
    return value


def _reject_json_constant(value):
    raise ProjectionError("non-finite JSON constant {}".format(value))


def parse_json_bytes(raw: bytes, label: str):
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except ProjectionError:
        raise
    except (UnicodeError, json.JSONDecodeError) as err:
        raise ProjectionError("cannot parse {}: {}".format(label, err)) from err
    canonical_json_bytes(value, newline=False)
    return value


def _fingerprint(status):
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_nlink,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def stable_read(path, *, identity: FileIdentity | None = None, label="input") -> bytes:
    """Read a stable, single-link, regular, non-symlink file."""
    path = Path(os.path.abspath(Path(path).expanduser()))
    try:
        initial = path.lstat()
    except OSError as err:
        raise ProjectionError("cannot inspect {} {}: {}".format(label, path, err))
    if not stat.S_ISREG(initial.st_mode) or initial.st_nlink != 1:
        raise ProjectionError(
            "{} must be a single-link regular non-symlink file: {}".format(
                label, path
            )
        )
    if identity is not None and initial.st_size != identity.size:
        raise ProjectionError(
            "{} size changed: expected {}, got {}".format(
                label, identity.size, initial.st_size
            )
        )
    if not hasattr(os, "O_NOFOLLOW"):
        raise ProjectionError("stable reading requires O_NOFOLLOW")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or _fingerprint(opened) != _fingerprint(initial)
        ):
            raise ProjectionError("{} identity changed before read".format(label))
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after_read = os.fstat(descriptor)
        if _fingerprint(after_read) != _fingerprint(initial):
            raise ProjectionError("{} changed while being read".format(label))
    except OSError as err:
        raise ProjectionError("cannot stably read {}: {}".format(label, err)) from err
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        after_path = path.lstat()
    except OSError as err:
        raise ProjectionError("{} disappeared after read: {}".format(label, err))
    if _fingerprint(after_path) != _fingerprint(initial):
        raise ProjectionError("{} path identity changed after read".format(label))
    raw = b"".join(chunks)
    if identity is not None:
        digest = _sha256(raw)
        if len(raw) != identity.size or digest != identity.sha256:
            raise ProjectionError(
                "{} identity changed: expected {}/{}, got {}/{}".format(
                    label, identity.size, identity.sha256, len(raw), digest
                )
            )
    return raw


def source_keys_sha256(properties) -> str:
    return _sha256(canonical_json_bytes(sorted(properties), newline=False))


def record_schema_sha256(properties) -> str:
    schema = [[key, sorted(record)] for key, record in sorted(properties.items())]
    return _sha256(canonical_json_bytes(schema, newline=False))


def logical_properties_sha256(properties) -> str:
    records = [dict(record) for record in properties.values()]
    records.sort(
        key=lambda record: (
            str(record.get("algorithm", "")),
            str(record.get("domain", "")),
            str(record.get("problem", "")),
            canonical_json_bytes(record, newline=False),
        )
    )
    return _sha256(canonical_json_bytes(records, newline=False))


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_strings(child)


def validate_properties_structure(properties, spec: StageSpec, *, projected: bool):
    if not isinstance(properties, dict):
        raise ProjectionError("{} properties must be one JSON object".format(spec.name))
    if len(properties) != spec.record_count:
        raise ProjectionError(
            "{} record count changed: expected {}, got {}".format(
                spec.name, spec.record_count, len(properties)
            )
        )
    keys_digest = source_keys_sha256(properties)
    if keys_digest != spec.source_keys_sha256:
        raise ProjectionError(
            "{} source-key inventory changed: expected {}, got {}".format(
                spec.name, spec.source_keys_sha256, keys_digest
            )
        )
    schema_digest = record_schema_sha256(properties)
    if schema_digest != spec.record_schema_sha256:
        raise ProjectionError(
            "{} record key schema changed: expected {}, got {}".format(
                spec.name, spec.record_schema_sha256, schema_digest
            )
        )

    for source_key, record in properties.items():
        if not isinstance(record, dict):
            raise ProjectionError("record {!r} is not an object".format(source_key))
        identity = record.get("id")
        if (
            not isinstance(identity, list)
            or len(identity) != 3
            or not all(isinstance(value, str) and value for value in identity)
            or source_key != "-".join(identity)
            or record.get("algorithm") != identity[0]
            or record.get("domain") != identity[1]
            or record.get("problem") != identity[2]
        ):
            raise ProjectionError(
                "record {!r} has a noncanonical cell identity".format(source_key)
            )
        for field, sentinel in NORMALIZED_FIELDS.items():
            value = record.get(field)
            if not isinstance(value, str) or not value:
                raise ProjectionError(
                    "record {!r} has invalid packaging field {}".format(
                        source_key, field
                    )
                )
            if projected and value != sentinel:
                raise ProjectionError(
                    "record {!r} has noncanonical projected {}".format(
                        source_key, field
                    )
                )
        for field in ("benchmark_worktree", "repo"):
            if not Path(record[field]).is_absolute():
                raise ProjectionError(
                    "record {!r} {} is not absolute".format(source_key, field)
                )
        # Absolute record values outside the path allowlist would be an
        # unreviewed packaging identity, even if a future accepted file hash
        # were accidentally updated without reviewing the projection policy.
        for field, value in record.items():
            if field in NORMALIZED_FIELDS:
                continue
            for child in _walk_strings(value):
                if child.startswith("/"):
                    raise ProjectionError(
                        "record {!r} has unreviewed absolute path in {}".format(
                            source_key, field
                        )
                    )
    return properties


def load_accepted_properties(stage: str, path):
    spec = STAGES[stage]
    raw = stable_read(
        path,
        identity=spec.accepted,
        label="accepted {} properties".format(stage),
    )
    properties = parse_json_bytes(raw, "accepted {} properties".format(stage))
    validate_properties_structure(properties, spec, projected=False)
    logical = logical_properties_sha256(properties)
    if logical != spec.accepted_logical_sha256:
        raise ProjectionError(
            "{} accepted logical digest changed: expected {}, got {}".format(
                stage, spec.accepted_logical_sha256, logical
            )
        )
    return properties


def project_properties(properties, spec: StageSpec):
    validate_properties_structure(properties, spec, projected=False)
    projected = {}
    original_packaging_values = set()
    for source_key, record in properties.items():
        item = dict(record)
        for field, sentinel in NORMALIZED_FIELDS.items():
            original_packaging_values.add(item[field])
            item[field] = sentinel
        projected[source_key] = item
    validate_properties_structure(projected, spec, projected=True)

    # Prove that every non-allowlisted value is unchanged.
    for source_key, source_record in properties.items():
        public_record = projected[source_key]
        for field in source_record:
            if field not in NORMALIZED_FIELDS and (
                canonical_json_bytes(source_record[field], newline=False)
                != canonical_json_bytes(public_record[field], newline=False)
            ):
                raise ProjectionError(
                    "projection changed non-allowlisted {}.{}".format(
                        source_key, field
                    )
                )
    public_strings = [
        value for record in projected.values() for value in _walk_strings(record)
    ]
    sentinels = set(NORMALIZED_FIELDS.values())
    leaked = sorted(
        value
        for value in original_packaging_values
        if value not in sentinels
        and any(value in public_value for public_value in public_strings)
    )
    if leaked:
        raise ProjectionError("projection retained packaging identities")
    return projected


def project_accepted_file(stage: str, path) -> bytes:
    spec = STAGES[stage]
    properties = load_accepted_properties(stage, path)
    projected = project_properties(properties, spec)
    raw = canonical_json_bytes(projected)
    digest = _sha256(raw)
    logical = logical_properties_sha256(projected)
    if len(raw) != spec.projected.size or digest != spec.projected.sha256:
        raise ProjectionError(
            "{} projected byte identity changed: expected {}/{}, got {}/{}".format(
                stage,
                spec.projected.size,
                spec.projected.sha256,
                len(raw),
                digest,
            )
        )
    if logical != spec.projected_logical_sha256:
        raise ProjectionError(
            "{} projected logical digest changed: expected {}, got {}".format(
                stage, spec.projected_logical_sha256, logical
            )
        )
    return raw


def load_projected_properties(stage: str, path):
    spec = STAGES[stage]
    raw = stable_read(
        path, identity=spec.projected, label="public {} properties".format(stage)
    )
    properties = parse_json_bytes(raw, "public {} properties".format(stage))
    if canonical_json_bytes(properties) != raw:
        raise ProjectionError("public {} properties are not canonical".format(stage))
    validate_properties_structure(properties, spec, projected=True)
    logical = logical_properties_sha256(properties)
    if logical != spec.projected_logical_sha256:
        raise ProjectionError(
            "{} public logical digest changed: expected {}, got {}".format(
                stage, spec.projected_logical_sha256, logical
            )
        )
    return properties


def _analyzer_records(properties, scheduler_account):
    records = []
    for source_key, record in properties.items():
        item = copy.deepcopy(record)
        if item.get("scheduler_account") != NORMALIZED_FIELDS["scheduler_account"]:
            raise ProjectionError("public scheduler account sentinel changed")
        # This is an administrative compatibility substitution, not a bypass:
        # the unchanged analyzer still compares the value to its frozen runner
        # contract along with all other static and scientific fields.
        item["scheduler_account"] = scheduler_account
        item["_source_key"] = source_key
        records.append(item)
    return records


def _pop_exact_path(value, path):
    current = value
    for key in path[:-1]:
        if not isinstance(current, dict) or key not in current:
            raise ProjectionError("missing excluded path {}".format(".".join(path)))
        current = current[key]
    leaf = path[-1]
    if not isinstance(current, dict) or leaf not in current:
        raise ProjectionError("missing excluded path {}".format(".".join(path)))
    removed = current.pop(leaf)
    if not isinstance(removed, str) or not re.fullmatch(r"[0-9a-f]{64}", removed):
        raise ProjectionError("excluded path {} is not a SHA-256".format(".".join(path)))
    return removed


def compare_modulo_exclusions(actual, expected, exclusions, label):
    actual = copy.deepcopy(actual)
    expected = copy.deepcopy(expected)
    removed = []
    for path in exclusions:
        removed.append(
            {
                "path": ".".join(path),
                "generated": _pop_exact_path(actual, path),
                "accepted": _pop_exact_path(expected, path),
            }
        )
    actual_bytes = canonical_json_bytes(actual, newline=False)
    expected_bytes = canonical_json_bytes(expected, newline=False)
    if actual_bytes != expected_bytes:
        raise ProjectionError(
            "{} differs from the accepted artifact outside {}".format(
                label, ", ".join(item["path"] for item in removed)
            )
        )
    return removed


def _load_artifact(root, name):
    relative, identity = ACCEPTED_ARTIFACTS[name]
    raw = stable_read(root / relative, identity=identity, label=name)
    value = parse_json_bytes(raw, name)
    if not isinstance(value, dict):
        raise ProjectionError("{} must contain one JSON object".format(name))
    return value, raw


def _attest_analysis_contract():
    for relative, identity in ANALYSIS_CONTRACT_FILES.items():
        stable_read(
            SCRIPT_DIR / relative,
            identity=identity,
            label="analysis contract {}".format(relative),
        )


def _reject_preimported_analysis_modules():
    internal = {
        Path(relative).stem
        for relative in ANALYSIS_CONTRACT_FILES
        if relative.endswith(".py")
    }
    loaded = sorted(
        name
        for name in sys.modules
        if name in internal
        or name == "lab"
        or name.startswith("lab.")
        or name == "downward"
        or name.startswith("downward.")
    )
    if loaded:
        raise ProjectionError(
            "analysis dependencies were imported before attestation: {}".format(
                ", ".join(loaded)
            )
        )


def _check_generated_identity(name, value):
    raw = canonical_json_bytes(value)
    expected = PROJECTED_ANALYSIS_OUTPUTS[name]
    if len(raw) != expected.size or _sha256(raw) != expected.sha256:
        raise ProjectionError(
            "{} projected-analysis identity changed".format(name)
        )


def verify_analysis(p4_path, p5_path, *, artifacts_dir=ARTIFACTS_DIR):
    if platform.python_version() != "3.9.25":
        raise ProjectionError(
            "analysis verification requires Python 3.9.25; found {}".format(
                platform.python_version()
            )
        )
    p4_properties = load_projected_properties("p4", p4_path)
    p5_properties = load_projected_properties("p5", p5_path)
    _attest_analysis_contract()
    accepted_selection, accepted_selection_raw = _load_artifact(
        artifacts_dir, "p4_selection"
    )
    accepted_report, _ = _load_artifact(artifacts_dir, "p4_report")
    accepted_p5, _ = _load_artifact(artifacts_dir, "p5_analysis")

    # Imports are intentionally delayed until after source attestation.
    _reject_preimported_analysis_modules()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        import analyze_arrhenius_selector_pilot as pilot
        import analyze_arrhenius_selector_validation as validation

        # The common runner's ambient default is intentionally not the frozen
        # allocation.  Derive the reviewed value from the frozen runner rather
        # than copying it into this public projection utility.
        scheduler_account = pilot.runner.FIXED_ENVIRONMENT["scheduler_account"]
        pilot.common.SCHEDULER_ACCOUNT = scheduler_account

        p4_records = _analyzer_records(p4_properties, scheduler_account)
        if pilot.logical_properties_sha256(p4_records) != STAGES[
            "p4"
        ].analysis_adapter_logical_sha256:
            raise ProjectionError("P4 analysis-adapter logical identity changed")
        planner_revision, protocol_revision, binary_sha256 = (
            pilot.require_reviewed_pins()
        )
        pilot.validate_runner_contract(
            check_cache_pin=True, expected_cache_hash=binary_sha256
        )
        p4_tasks = pilot.load_manifest(pilot.runner.MANIFEST)
        if [pilot.analyzer_utils.task_label(task) for task in p4_tasks] != (
            pilot.runner.read_manifest()
        ):
            raise ProjectionError("P4 analyzer and runner task sequences differ")
        p4_matrix, errors = pilot.validate_records(
            p4_records,
            p4_tasks,
            planner_revision,
            protocol_revision,
            binary_sha256,
        )
        pilot.raise_validation_errors(errors)
        scores = pilot.analyze_scores(p4_matrix, p4_tasks)
        paired = pilot.all_paired_deltas(
            p4_matrix, p4_tasks, scores["image_time_tiebreak_available"]
        )
        generated_selection = pilot.make_selection_artifact(
            p4_records,
            scores,
            paired,
            planner_revision,
            protocol_revision,
            binary_sha256,
        )
        generated_report = pilot.make_reporting_artifact(
            p4_records, p4_matrix, p4_tasks, generated_selection
        )

        selection_digest = _sha256(accepted_selection_raw)
        validation_contract = validation.validate_selection_artifact(
            copy.deepcopy(accepted_selection)
        )
        p5_revision = validation.require_reviewed_pins(selection_digest)
        validation.validate_runner_contract(
            expected_artifact_sha256=selection_digest
        )
        p5_tasks = validation.load_and_validate_tasks()
        p5_records = _analyzer_records(p5_properties, scheduler_account)
        if validation.logical_properties_sha256(p5_records) != STAGES[
            "p5"
        ].analysis_adapter_logical_sha256:
            raise ProjectionError("P5 analysis-adapter logical identity changed")
        generated_p5 = validation.analyze(
            p5_records,
            p5_tasks,
            validation_contract,
            selection_digest,
            p5_revision,
        )
    except ProjectionError:
        raise
    except Exception as err:
        raise ProjectionError("frozen analyzer rejected public data: {}".format(err))

    generated = {
        "p4_selection": generated_selection,
        "p4_report": generated_report,
        "p5_analysis": generated_p5,
    }
    accepted = {
        "p4_selection": accepted_selection,
        "p4_report": accepted_report,
        "p5_analysis": accepted_p5,
    }
    excluded = {}
    for name in ("p4_selection", "p4_report", "p5_analysis"):
        _check_generated_identity(name, generated[name])
        excluded[name] = compare_modulo_exclusions(
            generated[name],
            accepted[name],
            ANALYSIS_EXCLUSIONS[name],
            name,
        )
    return {
        "protocol": PROJECTION_PROTOCOL,
        "status": "accepted-artifact-equivalent",
        "p4_records": STAGES["p4"].record_count,
        "p5_records": STAGES["p5"].record_count,
        "excluded_identities": excluded,
    }


def _synthetic_spec(raw_properties):
    raw = canonical_json_bytes(raw_properties)
    projected = {
        key: {**record, **NORMALIZED_FIELDS}
        for key, record in raw_properties.items()
    }
    projected_raw = canonical_json_bytes(projected)
    return StageSpec(
        "synthetic",
        FileIdentity(len(raw), _sha256(raw)),
        len(raw_properties),
        logical_properties_sha256(raw_properties),
        source_keys_sha256(raw_properties),
        record_schema_sha256(raw_properties),
        FileIdentity(len(projected_raw), _sha256(projected_raw)),
        logical_properties_sha256(projected),
        logical_properties_sha256(projected),
    )


def self_test():
    identity = ["algorithm", "domain", "problem.pddl"]
    key = "-".join(identity)
    source = {
        key: {
            "id": identity,
            "algorithm": identity[0],
            "domain": identity[1],
            "problem": identity[2],
            "benchmark_worktree": "/private/benchmarks",
            "repo": "/private/repo",
            "node": "private-node",
            "scheduler_account": "private-account",
            "coverage": 1,
            "planner_time": 1.25,
        }
    }
    spec = _synthetic_spec(source)
    public = project_properties(source, spec)
    if public[key]["coverage"] != 1 or public[key]["planner_time"] != 1.25:
        raise AssertionError("scientific fields changed")
    if any(public[key][field] != value for field, value in NORMALIZED_FIELDS.items()):
        raise AssertionError("packaging normalization changed")
    if canonical_json_bytes(public) != canonical_json_bytes(
        {key: dict(reversed(list(public[key].items())))}
    ):
        raise AssertionError("canonical JSON depends on insertion order")

    changed = copy.deepcopy(source)
    changed[key]["unknown"] = True
    try:
        validate_properties_structure(changed, spec, projected=False)
    except ProjectionError:
        pass
    else:
        raise AssertionError("unknown schema field was accepted")
    missing = copy.deepcopy(source)
    del missing[key]["coverage"]
    try:
        validate_properties_structure(missing, spec, projected=False)
    except ProjectionError:
        pass
    else:
        raise AssertionError("missing schema field was accepted")
    for malformed in (b'{"x":1,"x":2}', b'{"x":NaN}'):
        try:
            parse_json_bytes(malformed, "synthetic")
        except ProjectionError:
            pass
        else:
            raise AssertionError("malformed JSON was accepted")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "properties"
        path.write_bytes(canonical_json_bytes(source))
        stable_read(path, identity=spec.accepted)
        link = root / "linked"
        link.symlink_to(path)
        try:
            stable_read(link, identity=spec.accepted)
        except ProjectionError:
            pass
        else:
            raise AssertionError("symlink input was accepted")
    return {
        "protocol": PROJECTION_PROTOCOL,
        "status": "PASS",
        "adversaries": [
            "unknown-field",
            "missing-field",
            "duplicate-key",
            "nonfinite-json",
            "symlink-input",
        ],
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Project and verify accepted P4/P5 Lab properties."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run deterministic in-memory and filesystem adversarial tests.",
    )
    subparsers = parser.add_subparsers(dest="command")
    project = subparsers.add_parser(
        "project", help="Write a canonical public projection to stdout."
    )
    project.add_argument("stage", choices=sorted(STAGES))
    project.add_argument("properties", type=Path)
    verify = subparsers.add_parser(
        "verify", help="Verify an already projected properties file."
    )
    verify.add_argument("stage", choices=sorted(STAGES))
    verify.add_argument("properties", type=Path)
    analysis = subparsers.add_parser(
        "verify-analysis",
        help="Prove P4/P5 analyzer equivalence to committed artifacts.",
    )
    analysis.add_argument("p4_properties", type=Path)
    analysis.add_argument("p5_properties", type=Path)
    analysis.add_argument(
        "--artifacts-dir", type=Path, default=ARTIFACTS_DIR
    )
    args = parser.parse_args(argv)
    if args.self_test and args.command is not None:
        parser.error("--self-test does not accept a subcommand")
    if not args.self_test and args.command is None:
        parser.error("a subcommand or --self-test is required")
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        print(canonical_json_bytes(self_test()).decode("ascii"), end="")
        return 0
    if args.command == "project":
        sys.stdout.buffer.write(project_accepted_file(args.stage, args.properties))
        return 0
    if args.command == "verify":
        properties = load_projected_properties(args.stage, args.properties)
        summary = {
            "protocol": PROJECTION_PROTOCOL,
            "stage": args.stage,
            "records": len(properties),
            "sha256": STAGES[args.stage].projected.sha256,
            "logical_sha256": STAGES[args.stage].projected_logical_sha256,
            "status": "verified",
        }
        print(canonical_json_bytes(summary).decode("ascii"), end="")
        return 0
    result = verify_analysis(
        args.p4_properties,
        args.p5_properties,
        artifacts_dir=args.artifacts_dir,
    )
    print(canonical_json_bytes(result).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ProjectionError, RuntimeError) as err:
        print("projection error: {}".format(err), file=sys.stderr)
        sys.exit(2)
