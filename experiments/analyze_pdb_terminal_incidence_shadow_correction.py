#!/usr/bin/env python3
"""Run the frozen analysis with two narrow input-contract corrections."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

import analyze_pdb_terminal_incidence_shadow as Original
import audit_pdb_terminal_incidence_shadow as Audit
import pdb_terminal_incidence_shadow_protocol as P


class CorrectionError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
CORRECTION_WRAPPER_PATH = Path(__file__).absolute()
ORIGINAL_ANALYZER_PATH = SCRIPT_DIR / "analyze_pdb_terminal_incidence_shadow.py"
ORIGINAL_ANALYZER_SHA256 = (
    "9359210856f18692f146b403dc9878df2f59bc5ba33b13650a8bf30cd25c54ba"
)
CORRECTION_ID = (
    "pdb-terminal-incidence-shadow-input-contract-correction-v3"
)
CORRECTION_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-shadow-analysis-correction/v3"
)
ATTESTATION_ALIASES = (
    ("domain_source_sha256", "domain_sha256"),
    ("problem_source_sha256", "problem_sha256"),
)
EXCLUDED_TERMINAL_OUTCOMES = {
    30: {
        "error": "exitcode-30",
        "coverage": 0,
        "unsolvable": 0,
        "construction_completed": None,
        "profile_present": False,
        "expansion_present": False,
    },
    34: {
        "error": "search-unsupported",
        "coverage": 0,
        "unsolvable": 0,
        "construction_completed": None,
        "profile_present": True,
        "expansion_present": True,
    },
    247: {
        "error": "sigkill",
        "coverage": 0,
        "unsolvable": 0,
        "construction_completed": None,
        "profile_present": False,
        "expansion_present": False,
    },
    250: {
        "error": "exitcode-250",
        "coverage": 0,
        "unsolvable": 0,
        "construction_completed": True,
        "profile_present": True,
        "expansion_present": True,
    },
}
EXCLUDED_OUTCOME_CLASS = "excluded_terminal_error"

_FROZEN_VALIDATE_MATRIX = Original.validate_matrix
_FROZEN_VALIDATE_INTERVENTION_CELLS = Original._validate_intervention_cells
_FROZEN_SEMANTIC_IDENTITY = Original._semantic_identity
_FROZEN_ANALYZE_RECORDS = Original.analyze_records
_FROZEN_OUTCOME_SPECS = Original.OUTCOME_SPECS
_FROZEN_OUTCOME_SPECS_COPY = dict(Original.OUTCOME_SPECS)
_FROZEN_REQUESTED_MODES = Original.REQUESTED_MODES
_FROZEN_REQUESTED_MODES_COPY = dict(Original.REQUESTED_MODES)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as err:
        raise CorrectionError("cannot hash the frozen original analyzer") from err
    return digest.hexdigest()


def _require_regular_file(path: Path, label: str) -> None:
    try:
        info = Path(path).lstat()
    except OSError as err:
        raise CorrectionError("{} is unavailable".format(label)) from err
    if Path(path).is_symlink() or not stat.S_ISREG(info.st_mode):
        raise CorrectionError("{} is not a regular file".format(label))


def _assert_original_analyzer() -> None:
    _require_regular_file(ORIGINAL_ANALYZER_PATH, "frozen original analyzer")
    if Path(Original.__file__).resolve() != ORIGINAL_ANALYZER_PATH.resolve():
        raise CorrectionError("loaded original analyzer path changed")
    if Original.P is not P:
        raise CorrectionError("original analyzer protocol module changed")
    if Original._semantic_identity is not _FROZEN_SEMANTIC_IDENTITY:
        raise CorrectionError("original semantic identity entry point changed")
    if (
        Original.OUTCOME_SPECS is not _FROZEN_OUTCOME_SPECS
        or Original.OUTCOME_SPECS != _FROZEN_OUTCOME_SPECS_COPY
    ):
        raise CorrectionError("original analyzer outcome table changed")
    if (
        Original.REQUESTED_MODES is not _FROZEN_REQUESTED_MODES
        or Original.REQUESTED_MODES != _FROZEN_REQUESTED_MODES_COPY
    ):
        raise CorrectionError("original requested-mode table changed")
    if _sha256_file(ORIGINAL_ANALYZER_PATH) != ORIGINAL_ANALYZER_SHA256:
        raise CorrectionError("frozen original analyzer bytes changed")


def _excluded_outcome_provenance() -> list[dict]:
    return [
        {"planner_exit_code": code, **EXCLUDED_TERMINAL_OUTCOMES[code]}
        for code in sorted(EXCLUDED_TERMINAL_OUTCOMES)
    ]


def _requested_mode_provenance() -> dict:
    return {
        "field": "pdb_fixed_pattern_requested_mode",
        "derived_from": "algorithm",
        "applied_only_when_original_value_is_null": True,
        "mapping": {
            label: _FROZEN_REQUESTED_MODES_COPY[label]
            for label in sorted(_FROZEN_REQUESTED_MODES_COPY)
        },
    }


def _validate_excluded_terminal_contract(records, labels) -> None:
    for record in records:
        if record.get("algorithm") not in labels:
            continue
        code = record.get("planner_exit_code")
        if type(code) is not int:
            raise CorrectionError("cell has an unrecognized terminal outcome")
        if code in _FROZEN_OUTCOME_SPECS_COPY:
            continue
        if code not in EXCLUDED_TERMINAL_OUTCOMES:
            raise CorrectionError("cell has an unrecognized terminal outcome")
        expected = EXCLUDED_TERMINAL_OUTCOMES[code]
        exact_fields = {
            "error": record.get("error"),
            "coverage": record.get("coverage"),
            "unsolvable": record.get("unsolvable"),
            "construction_completed": record.get("construction_completed"),
            "profile_present": record.get("wbh_profile_present"),
            "expansion_present": record.get("wbh_expansion_profile_present"),
        }
        if exact_fields != expected or any(
            type(record.get(field)) is not int
            for field in ("coverage", "unsolvable")
        ):
            raise CorrectionError(
                "excluded terminal outcome fields changed for code {}".format(
                    code
                )
            )
        errors = record.get("unexplained_errors")
        if (
            not isinstance(errors, list)
            or any(not isinstance(message, str) for message in errors)
            or expected["error"] not in errors
            or Original.LAB_SLURM_ERROR not in errors
            or Original._measurement_surface_valid(record)
        ):
            raise CorrectionError(
                "excluded terminal outcome lacks invalidating evidence"
            )


@contextlib.contextmanager
def _extended_outcome_specs():
    _assert_original_analyzer()
    if set(EXCLUDED_TERMINAL_OUTCOMES) & set(_FROZEN_OUTCOME_SPECS_COPY):
        raise CorrectionError("excluded terminal correction collides")
    extended = dict(_FROZEN_OUTCOME_SPECS_COPY)
    extended.update({
        code: (
            expected["error"],
            expected["coverage"],
            expected["unsolvable"],
            EXCLUDED_OUTCOME_CLASS,
        )
        for code, expected in EXCLUDED_TERMINAL_OUTCOMES.items()
    })
    expected_extended = dict(extended)
    Original.OUTCOME_SPECS = extended
    try:
        yield extended
    finally:
        changed = (
            Original.OUTCOME_SPECS is not extended
            or Original.OUTCOME_SPECS != expected_extended
        )
        Original.OUTCOME_SPECS = _FROZEN_OUTCOME_SPECS
        if changed:
            raise CorrectionError("corrected terminal outcome table changed")


def _corrected_attestation_payload(raw: bytes) -> bytes:
    if hashlib.sha256(raw).hexdigest() != P.COST_ATTESTATION_SHA256:
        raise CorrectionError("frozen source attestation bytes changed")
    try:
        data = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise CorrectionError("frozen source attestation is not ASCII JSON") from err
    if not isinstance(data, dict) or raw != P.canonical_json(data) + b"\n":
        raise CorrectionError("frozen source attestation is not canonical")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != P.COHORT_TASKS:
        raise CorrectionError("frozen source attestation task count changed")
    for task in tasks:
        if not isinstance(task, dict):
            raise CorrectionError("frozen source attestation task changed")
        for alias, source in ATTESTATION_ALIASES:
            if alias in task:
                raise CorrectionError("source attestation already contains alias keys")
            value = task.get(source)
            if (
                not isinstance(value, str)
                or Original.SHA256_RE.fullmatch(value) is None
            ):
                raise CorrectionError("source attestation hash field changed")
            task[alias] = value
    return P.canonical_json(data) + b"\n"


def _load_corrected_attestation_payload() -> bytes:
    path = P.COST_ATTESTATION_PATH
    _require_regular_file(path, "frozen source attestation")
    try:
        raw = path.read_bytes()
    except OSError as err:
        raise CorrectionError("cannot read the frozen source attestation") from err
    return _corrected_attestation_payload(raw)


@contextlib.contextmanager
def _aliased_attestation_view():
    original_path = P.COST_ATTESTATION_PATH
    payload = _load_corrected_attestation_payload()
    descriptor, temporary = tempfile.mkstemp(
        prefix="pdb-terminal-incidence-attestation-alias-",
        suffix=".json",
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        P.COST_ATTESTATION_PATH = temporary_path
        yield
    finally:
        P.COST_ATTESTATION_PATH = original_path
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _validate_matrix_with_active_corrections(
    records, expected_tasks=P.COHORT_TASKS
):
    expected_outcomes = dict(_FROZEN_OUTCOME_SPECS_COPY)
    expected_outcomes.update({
        code: (
            expected["error"],
            expected["coverage"],
            expected["unsolvable"],
            EXCLUDED_OUTCOME_CLASS,
        )
        for code, expected in EXCLUDED_TERMINAL_OUTCOMES.items()
    })
    if Original.OUTCOME_SPECS != expected_outcomes:
        raise CorrectionError("corrected terminal outcome table changed")
    if expected_tasks != P.COHORT_TASKS:
        raise CorrectionError("corrected analysis requires the frozen full cohort")
    with _aliased_attestation_view():
        return _FROZEN_VALIDATE_MATRIX(records, expected_tasks)


def validate_matrix(records, expected_tasks=P.COHORT_TASKS):
    """Delegate with the two narrow frozen-input compatibility corrections."""
    _assert_original_analyzer()
    _validate_excluded_terminal_contract(records, set(P.PRIMARY_LABELS))
    with _extended_outcome_specs():
        return _validate_matrix_with_active_corrections(records, expected_tasks)


@contextlib.contextmanager
def _corrected_validate_matrix():
    if Original.validate_matrix is not _FROZEN_VALIDATE_MATRIX:
        raise CorrectionError("original analyzer validation entry point changed")
    Original.validate_matrix = _validate_matrix_with_active_corrections
    try:
        yield
    finally:
        Original.validate_matrix = _FROZEN_VALIDATE_MATRIX


def _validate_intervention_cells_with_correction(matrix, tasks):
    records = [matrix[(P.INTERVENTION_LABEL, task)] for task in tasks]
    _validate_excluded_terminal_contract(records, {P.INTERVENTION_LABEL})
    return _FROZEN_VALIDATE_INTERVENTION_CELLS(matrix, tasks)


@contextlib.contextmanager
def _corrected_validate_intervention_cells():
    if (
        Original._validate_intervention_cells
        is not _FROZEN_VALIDATE_INTERVENTION_CELLS
    ):
        raise CorrectionError(
            "original intervention validation entry point changed"
        )
    Original._validate_intervention_cells = (
        _validate_intervention_cells_with_correction
    )
    try:
        yield
    finally:
        Original._validate_intervention_cells = (
            _FROZEN_VALIDATE_INTERVENTION_CELLS
        )


def _semantic_identity_with_requested_mode(record, label, heuristic):
    field = "pdb_fixed_pattern_requested_mode"
    if field not in record:
        raise CorrectionError("direct identity lacks requested-mode field")
    if record.get("algorithm") != label:
        raise CorrectionError("direct identity algorithm and label disagree")
    try:
        expected = _FROZEN_REQUESTED_MODES_COPY[label]
    except KeyError as err:
        raise CorrectionError("direct identity has an unknown label") from err
    actual = record[field]
    if actual is None:
        corrected = dict(record)
        corrected[field] = expected
        return _FROZEN_SEMANTIC_IDENTITY(corrected, label, heuristic)
    return _FROZEN_SEMANTIC_IDENTITY(record, label, heuristic)


@contextlib.contextmanager
def _corrected_semantic_identity():
    if Original._semantic_identity is not _FROZEN_SEMANTIC_IDENTITY:
        raise CorrectionError("original semantic identity entry point changed")
    Original._semantic_identity = _semantic_identity_with_requested_mode
    try:
        yield
    finally:
        changed = (
            Original._semantic_identity
            is not _semantic_identity_with_requested_mode
        )
        Original._semantic_identity = _FROZEN_SEMANTIC_IDENTITY
        if changed:
            raise CorrectionError("corrected semantic identity entry point changed")


def analyze_records(records):
    _assert_original_analyzer()
    _validate_excluded_terminal_contract(records, set(P.PRIMARY_LABELS))
    _require_regular_file(CORRECTION_WRAPPER_PATH, "analysis correction wrapper")
    correction_sha256 = _sha256_file(CORRECTION_WRAPPER_PATH)
    attestation_alias_view_sha256 = hashlib.sha256(
        _load_corrected_attestation_payload()
    ).hexdigest()
    with _extended_outcome_specs():
        with _corrected_validate_matrix():
            with _corrected_validate_intervention_cells():
                with _corrected_semantic_identity():
                    result = _FROZEN_ANALYZE_RECORDS(records)
    _assert_original_analyzer()
    _require_regular_file(CORRECTION_WRAPPER_PATH, "analysis correction wrapper")
    if _sha256_file(CORRECTION_WRAPPER_PATH) != correction_sha256:
        raise CorrectionError("analysis correction wrapper bytes changed")
    if hashlib.sha256(
        _load_corrected_attestation_payload()
    ).hexdigest() != attestation_alias_view_sha256:
        raise CorrectionError("attestation alias view changed during analysis")
    provenance = {
        "frozen_protocol_sha256": P.PROTOCOL_SHA256,
        "analysis_correction": {
            "schema": CORRECTION_SCHEMA,
            "correction_id": CORRECTION_ID,
            "attestation_key_aliases": {
                alias: source for alias, source in ATTESTATION_ALIASES
            },
            "excluded_terminal_outcomes": _excluded_outcome_provenance(),
            "requested_mode_derivation": _requested_mode_provenance(),
            "original_analyzer_sha256": ORIGINAL_ANALYZER_SHA256,
            "original_attestation_sha256": P.COST_ATTESTATION_SHA256,
            "attestation_alias_view_sha256": attestation_alias_view_sha256,
            "correction_wrapper_sha256": correction_sha256,
        },
    }
    if any(field in result for field in provenance):
        raise CorrectionError("corrected analysis provenance field collision")
    result.update(provenance)
    return result


def _load_live_input(properties: Path):
    _assert_original_analyzer()
    P.validate_protocol_without_sources()
    try:
        fetch_sha, fetch_receipt = Audit.load_fetch_receipt(verify_live=True)
    except Audit.ExecutionAuditError as err:
        raise CorrectionError("fetched properties provenance is invalid") from err
    try:
        properties_raw = properties.read_bytes()
    except OSError as err:
        raise CorrectionError("cannot read the sealed fetched properties") from err
    if (
        properties.resolve() != Audit.EVAL_PROPERTIES.resolve()
        or hashlib.sha256(properties_raw).hexdigest()
        != fetch_receipt["properties_sha256"]
    ):
        raise CorrectionError(
            "analysis input is not the sealed fetched properties file"
        )
    records = Original.load_records(properties)
    if hashlib.sha256(properties.read_bytes()).hexdigest() != (
        fetch_receipt["properties_sha256"]
    ):
        raise CorrectionError("sealed fetched properties changed while loading")
    return records, fetch_sha, fetch_receipt["properties_sha256"]


def _write_exclusive(path: Path, payload: bytes) -> None:
    try:
        with Path(path).open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise CorrectionError("refusing to overwrite analysis output") from err


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("properties", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    records, fetch_sha, properties_sha = _load_live_input(args.properties)
    result = analyze_records(records)
    result["input"] = {
        "path": str(args.properties.resolve()),
        "sha256": properties_sha,
        "fetch_receipt_sha256": fetch_sha,
    }
    payload = Original._canonical(result) + b"\n"
    if args.output:
        _write_exclusive(args.output, payload)
    else:
        print(payload.decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        CorrectionError,
        Original.TerminalIncidenceAnalysisError,
        P.ProtocolError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
