#!/usr/bin/env python3
"""Run the frozen terminal-incidence analysis with one attestation-key fix."""

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
    "pdb-terminal-incidence-shadow-attestation-key-alias-correction-v1"
)
CORRECTION_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-shadow-analysis-correction/v1"
)
ATTESTATION_ALIASES = (
    ("domain_source_sha256", "domain_sha256"),
    ("problem_source_sha256", "problem_sha256"),
)

_FROZEN_VALIDATE_MATRIX = Original.validate_matrix
_FROZEN_ANALYZE_RECORDS = Original.analyze_records


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
    if _sha256_file(ORIGINAL_ANALYZER_PATH) != ORIGINAL_ANALYZER_SHA256:
        raise CorrectionError("frozen original analyzer bytes changed")


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


def validate_matrix(records, expected_tasks=P.COHORT_TASKS):
    """Delegate to the frozen validator with only the attestation aliases added."""
    _assert_original_analyzer()
    if expected_tasks != P.COHORT_TASKS:
        raise CorrectionError("corrected analysis requires the frozen full cohort")
    with _aliased_attestation_view():
        return _FROZEN_VALIDATE_MATRIX(records, expected_tasks)


@contextlib.contextmanager
def _corrected_validate_matrix():
    if Original.validate_matrix is not _FROZEN_VALIDATE_MATRIX:
        raise CorrectionError("original analyzer validation entry point changed")
    Original.validate_matrix = validate_matrix
    try:
        yield
    finally:
        Original.validate_matrix = _FROZEN_VALIDATE_MATRIX


def analyze_records(records):
    _assert_original_analyzer()
    _require_regular_file(CORRECTION_WRAPPER_PATH, "analysis correction wrapper")
    correction_sha256 = _sha256_file(CORRECTION_WRAPPER_PATH)
    attestation_alias_view_sha256 = hashlib.sha256(
        _load_corrected_attestation_payload()
    ).hexdigest()
    with _corrected_validate_matrix():
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
