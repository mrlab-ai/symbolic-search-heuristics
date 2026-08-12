"""Strict Lab parser for the cap-grid PDB selector protocol.

Uncapped ``fixed_pool_v1`` and legacy PDB logs are delegated byte-for-byte to
the frozen parser in :mod:`exp_arrhenius_common`.  This module owns only the
new ``fixed_pool_cap_grid_v6`` records, so accepting the development protocol
cannot weaken the accepted P4--P6 trace contract.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections import defaultdict

from lab import tools
from lab.parser import Parser

import exp_arrhenius_common as C


PROTOCOL = "fixed_pool_cap_grid_v6"
SCORE_VERSION = (
    "per_pattern_strongest_feasible_cap_then_"
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1"
)
PARSER_PROTOCOL = "run.log/pdb-cap-grid-whole-trace/v4"
RAW_POOL_SHA256_PROPERTY = "pdb_selector_raw_pool_sha256"
GRID = (0, 1, 2, 4, 8, 16, 32, 64, 128, 256)
RECORD_KEYS = (
    "protocol",
    "score_version",
    "sources",
    "pattern",
    "abstract_states",
    "initial_dead_end",
    "initial_h",
    "finite_sum",
    "finite_count",
    "dead_count",
    "cofactor_width",
    "width_upper_bound",
    "cofactor_width_budget",
    "value_cap",
    "add_nodes",
    "num_terminals",
    "raw_add_nodes",
    "raw_num_terminals",
    "raw_cofactor_width",
    "raw_width_upper_bound",
    "raw_num_values",
    "raw_max_finite_value",
    "raw_finite_sum",
    "raw_finite_count",
    "raw_dead_count",
    "raw_initial_dead_end",
    "raw_initial_h",
    "raw_initial_value_count",
    "raw_value_histogram",
    "transformed_num_values",
    "feasible",
    "rejection_reason",
)
STATISTIC_KEYS = (
    "initial_dead_end",
    "initial_h",
    "finite_sum",
    "finite_count",
    "dead_count",
    "cofactor_width",
    "width_upper_bound",
    "add_nodes",
    "num_terminals",
    "raw_add_nodes",
    "raw_num_terminals",
    "raw_cofactor_width",
    "raw_width_upper_bound",
    "raw_num_values",
    "raw_max_finite_value",
    "raw_finite_sum",
    "raw_finite_count",
    "raw_dead_count",
    "raw_initial_dead_end",
    "raw_initial_h",
    "raw_initial_value_count",
    "raw_value_histogram",
    "transformed_num_values",
)
INT_MAX = 2147483647
INT64_MAX = 9223372036854775807
MAX_ABSTRACT_STATES = 100000
MAX_HISTOGRAM_BYTES = 800003
MAX_HISTOGRAM_BASE64 = (MAX_HISTOGRAM_BYTES * 4 + 2) // 3
HISTOGRAM_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HISTOGRAM_WIRE_RE = re.compile(r"^[A-Za-z0-9_-]+$")
CAP_PROTOCOL_HINT_RE = re.compile(
    r'"protocol"\s*:\s*"fixed_pool_cap_grid_v6"'
)
SELECTOR_RE = re.compile(
    r"^\[t=\d+\.\d{6}s, \d+ KB\] "
    r"PDB width-selector v1 (candidate|selected): (.*)$"
)
FINAL_RE = re.compile(
    r"^\[t=\d+\.\d{6}s, \d+ KB\] "
    r"wbh PDB heuristic: pattern_size=(0|[1-9][0-9]{0,9}), "
    r"selected_source=([a-z_]+), abstract_states=(0|[1-9][0-9]{0,9}), "
    r"cofactor_width_budget=(0|[1-9][0-9]{0,9}), "
    r"value_cap=(0|[1-9][0-9]{0,9}|-[1-9][0-9]{0,9}), "
    r"values=(0|[1-9][0-9]{0,9}), "
    r"cofactor_width=(0|[1-9][0-9]{0,9}), "
    r"width_upper_bound=(0|[1-9][0-9]{0,9})$"
)


def _nonnegative_int(value):
    return type(value) is int and value >= 0


def _load(payload):
    return json.loads(
        payload,
        object_pairs_hook=C._unique_json_object,
        parse_constant=C._reject_json_constant,
    )


def _append_uvarint(result, value):
    while True:
        byte = value & 0x7F
        value >>= 7
        result.append(byte | (0x80 if value else 0))
        if not value:
            return


def encode_raw_value_histogram(pairs):
    """Return the producer's canonical histogram encoding (used by tests)."""
    data = bytearray()
    _append_uvarint(data, len(pairs))
    previous = -1
    for distance, count in pairs:
        if (
            type(distance) is not int
            or type(count) is not int
            or not 0 <= distance < INT_MAX
            or not 1 <= count <= MAX_ABSTRACT_STATES
            or distance <= previous
        ):
            raise ValueError("invalid raw histogram pair")
        _append_uvarint(data, distance - previous)
        _append_uvarint(data, count)
        previous = distance
    return base64.urlsafe_b64encode(bytes(data)).rstrip(b"=").decode("ascii")


def _read_uvarint(data, offset, maximum):
    value = 0
    shift = 0
    start = offset
    while offset < len(data) and offset - start < 5:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            if offset - start > 1 and byte == 0:
                raise ValueError("noncanonical raw histogram varint")
            if value > maximum:
                raise ValueError("raw histogram integer exceeds producer type")
            return value, offset
        shift += 7
    raise ValueError("unterminated raw histogram varint")


def decode_raw_value_histogram(payload):
    if (
        not isinstance(payload, str)
        or not payload
        or len(payload) > MAX_HISTOGRAM_BASE64
        or len(payload) % 4 == 1
        or HISTOGRAM_WIRE_RE.fullmatch(payload) is None
    ):
        raise ValueError("raw histogram base64 is malformed")
    try:
        data = base64.b64decode(
            payload + "=" * (-len(payload) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError) as err:
        raise ValueError("raw histogram base64 is malformed") from err
    if len(data) > MAX_HISTOGRAM_BYTES:
        raise ValueError("raw histogram exceeds its byte bound")
    canonical = base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")
    if canonical != payload:
        raise ValueError("raw histogram base64 is noncanonical")
    count, offset = _read_uvarint(data, 0, MAX_ABSTRACT_STATES)
    if count < 1:
        raise ValueError("raw histogram has no finite values")
    pairs = []
    previous = -1
    total = 0
    for _ in range(count):
        delta, offset = _read_uvarint(data, offset, INT_MAX)
        frequency, offset = _read_uvarint(data, offset, MAX_ABSTRACT_STATES)
        if delta < 1 or frequency < 1:
            raise ValueError("raw histogram uses zero delta/count")
        distance = previous + delta
        if distance >= INT_MAX:
            raise ValueError("raw histogram distance uses the infinity sentinel")
        total += frequency
        if total > MAX_ABSTRACT_STATES:
            raise ValueError("raw histogram exceeds state budget")
        pairs.append((distance, frequency))
        previous = distance
    if offset != len(data):
        raise ValueError("raw histogram has trailing bytes")
    if pairs[0][0] != 0:
        raise ValueError("raw histogram omits the zero-valued goal")
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    return pairs, digest


def _with_histogram_digest(record, digest):
    return {
        key: (digest if key == "raw_value_histogram" else record[key])
        for key in RECORD_KEYS
    }


def _validate_record(record, kind, *, retained):
    if not isinstance(record, dict) or tuple(record) != RECORD_KEYS:
        return "{} cap-grid payload keys/order changed".format(kind)
    if record["protocol"] != PROTOCOL:
        return "{} cap-grid protocol changed".format(kind)
    if record["score_version"] != SCORE_VERSION:
        return "{} cap-grid score changed".format(kind)
    sources = record["sources"]
    if (
        not isinstance(sources, list)
        or not sources
        or any(not isinstance(source, str) for source in sources)
        or len(sources) != len(set(sources))
        or any(source not in C.PDB_SELECTOR_SOURCES for source in sources)
        or [C.PDB_SELECTOR_SOURCES.index(source) for source in sources]
        != sorted(C.PDB_SELECTOR_SOURCES.index(source) for source in sources)
    ):
        return "{} cap-grid sources are malformed".format(kind)
    pattern = record["pattern"]
    if (
        not isinstance(pattern, list)
        or any(type(var) is not int or not 0 <= var <= INT_MAX for var in pattern)
        or pattern != sorted(set(pattern))
    ):
        return "{} cap-grid pattern is malformed".format(kind)
    if (
        type(record["abstract_states"]) is not int
        or not 1 <= record["abstract_states"] <= INT_MAX
    ):
        return "{} cap-grid abstract_states is invalid".format(kind)
    budget = record["cofactor_width_budget"]
    if type(budget) is not int or not 1 <= budget <= INT_MAX:
        return "{} cap-grid width budget is invalid".format(kind)
    cap = record["value_cap"]
    if type(cap) is not int or cap < -1 or (cap > 0 and cap not in GRID):
        return "{} cap-grid value cap is invalid".format(kind)
    if type(record["feasible"]) is not bool:
        return "{} cap-grid feasibility is not boolean".format(kind)

    unmaterialized = all(record[key] is None for key in STATISTIC_KEYS)
    if unmaterialized:
        if (
            kind != "candidate"
            or sources != ["cegar"]
            or len(pattern) != 1
            or not MAX_ABSTRACT_STATES < record["abstract_states"] <= INT_MAX
            or record["feasible"] is not False
            or record["rejection_reason"] != "abstract_state_budget"
        ):
            return "{} cap-grid unmaterialized outcome is invalid".format(kind)
        return None
    nullable = {
        "initial_h", "raw_initial_h", "raw_initial_value_count",
        "raw_value_histogram",
    }
    if any(
        record[key] is None
        for key in STATISTIC_KEYS
        if key not in nullable
    ):
        return "{} cap-grid statistics are only partially present".format(kind)
    histogram = record["raw_value_histogram"]
    if retained:
        if not isinstance(histogram, str) or not HISTOGRAM_DIGEST_RE.fullmatch(histogram):
            return "{} cap-grid retained histogram digest is invalid".format(kind)
    elif histogram is not None and (
        not isinstance(histogram, str)
        or not histogram
        or len(histogram) > MAX_HISTOGRAM_BASE64
        or HISTOGRAM_WIRE_RE.fullmatch(histogram) is None
    ):
        return "{} cap-grid wire histogram is malformed".format(kind)
    int32_keys = (
        "finite_count", "dead_count", "num_terminals", "raw_num_terminals",
        "raw_num_values", "raw_max_finite_value", "raw_finite_count",
        "raw_dead_count", "transformed_num_values",
    )
    int64_keys = (
        "finite_sum", "cofactor_width", "width_upper_bound", "add_nodes",
        "raw_add_nodes", "raw_cofactor_width", "raw_width_upper_bound",
        "raw_finite_sum",
    )
    if any(
        type(record[key]) is not int or not 0 <= record[key] <= INT_MAX
        for key in int32_keys
    ) or any(
        type(record[key]) is not int or not 0 <= record[key] <= INT64_MAX
        for key in int64_keys
    ):
        return "{} cap-grid numeric field exceeds producer type".format(kind)
    if type(record["initial_dead_end"]) is not bool:
        return "{} cap-grid initial_dead_end is invalid".format(kind)
    if record["initial_dead_end"]:
        if record["initial_h"] is not None or record["dead_count"] < 1:
            return "{} cap-grid initial dead-end evidence is invalid".format(kind)
    elif type(record["initial_h"]) is not int or not 0 <= record["initial_h"] < INT_MAX:
        return "{} cap-grid initial_h is invalid".format(kind)
    if type(record["raw_initial_dead_end"]) is not bool:
        return "{} cap-grid raw_initial_dead_end is invalid".format(kind)
    if record["raw_initial_dead_end"]:
        if (
            record["raw_initial_h"] is not None
            or record["raw_initial_value_count"] is not None
            or record["raw_dead_count"] < 1
        ):
            return "{} cap-grid raw initial-dead evidence is invalid".format(kind)
    elif (
        type(record["raw_initial_h"]) is not int
        or not 0 <= record["raw_initial_h"] < INT_MAX
        or type(record["raw_initial_value_count"]) is not int
        or not 1 <= record["raw_initial_value_count"] <= INT_MAX
    ):
        return "{} cap-grid raw initial support is invalid".format(kind)
    if (record["finite_sum"] == 0) != (record["transformed_num_values"] == 1):
        return "{} cap-grid transformed value count contradicts its sum".format(kind)
    if (record["raw_finite_sum"] == 0) != (record["raw_num_values"] == 1):
        return "{} cap-grid raw value count contradicts its sum".format(kind)
    if record["finite_count"] + record["dead_count"] != record[
        "abstract_states"
    ]:
        return "{} cap-grid abstract-state census does not conserve".format(kind)
    if (
        record["raw_finite_count"] + record["raw_dead_count"]
        != record["abstract_states"]
        or record["raw_finite_count"] != record["finite_count"]
        or record["raw_dead_count"] != record["dead_count"]
        or record["raw_initial_dead_end"] is not record["initial_dead_end"]
    ):
        return "{} cap-grid raw/transformed census changed".format(kind)
    if record["finite_count"] < 1:
        return "{} cap-grid has no finite goal state".format(kind)
    if record["abstract_states"] > MAX_ABSTRACT_STATES:
        return "{} cap-grid materialized candidate exceeds state budget".format(
            kind
        )
    if len(record["pattern"]) > 16:
        return "{} cap-grid materialized pattern exceeds bounded encoding".format(
            kind
        )
    if (
        not record["initial_dead_end"]
        and record["finite_sum"] < record["initial_h"]
    ):
        return "{} cap-grid finite_sum is smaller than initial_h".format(kind)
    if record["cofactor_width"] < 1 or record["width_upper_bound"] < record[
        "cofactor_width"
    ]:
        return "{} cap-grid transformed widths are invalid".format(kind)
    expected_terminals = record["transformed_num_values"] + int(
        record["dead_count"] > 0
    )
    expected_raw_terminals = record["raw_num_values"] + int(
        record["dead_count"] > 0
    )
    if (
        record["num_terminals"] != expected_terminals
        or record["raw_num_terminals"] != expected_raw_terminals
        or record["width_upper_bound"]
        != record["add_nodes"] + record["num_terminals"]
        or record["raw_width_upper_bound"]
        != record["raw_add_nodes"] + record["raw_num_terminals"]
        or record["cofactor_width"] < record["num_terminals"]
        or record["raw_cofactor_width"] < record["raw_num_terminals"]
        or record["add_nodes"] < record["num_terminals"] - 1
        or record["raw_add_nodes"] < record["raw_num_terminals"] - 1
        or (record["num_terminals"] == 1) != (record["add_nodes"] == 0)
        or (record["raw_num_terminals"] == 1)
        != (record["raw_add_nodes"] == 0)
    ):
        return "{} cap-grid A/T/U/V identity is invalid".format(kind)
    if (
        record["raw_cofactor_width"] < 1
        or record["raw_cofactor_width"] > record["raw_width_upper_bound"]
        or record["raw_cofactor_width"] < record["cofactor_width"]
        or record["raw_add_nodes"] < record["add_nodes"]
        or record["raw_num_terminals"] < record["num_terminals"]
        or record["raw_width_upper_bound"] < record["width_upper_bound"]
        or record["raw_num_values"] < record["transformed_num_values"]
        or record["raw_num_values"] < 1
        or not 0 <= record["raw_max_finite_value"] < INT_MAX
        or record["raw_num_values"] > record["raw_max_finite_value"] + 1
        or record["raw_finite_sum"] < record["finite_sum"]
        or record["raw_finite_sum"] < record["raw_max_finite_value"]
        or (
            not record["raw_initial_dead_end"]
            and record["raw_finite_sum"] < record["raw_initial_h"]
        )
        or record["raw_finite_sum"]
        > record["raw_max_finite_value"] * (record["raw_finite_count"] - 1)
        or (
            not record["raw_initial_dead_end"]
            and record["raw_initial_h"] > record["raw_max_finite_value"]
        )
        or record["transformed_num_values"] < 1
    ):
        return "{} cap-grid transform increased its representation".format(kind)
    if cap >= 0:
        if record["transformed_num_values"] > cap + 1:
            return "{} cap-grid finite-value ceiling failed".format(kind)
        if (
            not record["initial_dead_end"] and record["initial_h"] > cap
        ) or record["finite_sum"] > cap * record["finite_count"]:
            return "{} cap-grid finite values exceed the cap".format(kind)
        if (
            not record["initial_dead_end"]
            and record["initial_h"] != min(record["raw_initial_h"], cap)
        ):
            return "{} cap-grid initial value is not the exact cap".format(kind)
    elif (
        record["cofactor_width"] != record["raw_cofactor_width"]
        or record["width_upper_bound"] != record["raw_width_upper_bound"]
        or record["transformed_num_values"] != record["raw_num_values"]
        or record["finite_sum"] != record["raw_finite_sum"]
        or record["finite_count"] != record["raw_finite_count"]
        or record["dead_count"] != record["raw_dead_count"]
        or record["initial_dead_end"] is not record["raw_initial_dead_end"]
        or record["initial_h"] != record["raw_initial_h"]
    ):
        return "{} cap-grid exact transform differs from raw".format(kind)
    feasible = record["cofactor_width"] <= budget
    if record["feasible"] is not feasible:
        return "{} cap-grid feasibility contradicts exact width".format(kind)
    reason = None if feasible else "cofactor_width_budget"
    if record["rejection_reason"] != reason:
        return "{} cap-grid rejection reason is invalid".format(kind)
    if kind == "selected" and not feasible:
        return "cap-grid selected record is infeasible"
    if "empty" in sources:
        empty_expected = {
            "pattern": [],
            "abstract_states": 1,
            "initial_dead_end": False,
            "initial_h": 0,
            "finite_sum": 0,
            "finite_count": 1,
            "dead_count": 0,
            "cofactor_width": 1,
            "width_upper_bound": 1,
            "value_cap": -1,
            "add_nodes": 0,
            "num_terminals": 1,
            "raw_add_nodes": 0,
            "raw_num_terminals": 1,
            "raw_cofactor_width": 1,
            "raw_width_upper_bound": 1,
            "raw_num_values": 1,
            "raw_max_finite_value": 0,
            "raw_finite_sum": 0,
            "raw_finite_count": 1,
            "raw_dead_count": 0,
            "raw_initial_dead_end": False,
            "raw_initial_h": 0,
            "raw_initial_value_count": 1,
            "transformed_num_values": 1,
            "feasible": True,
            "rejection_reason": None,
        }
        if any(record[key] != value for key, value in empty_expected.items()):
            return "{} cap-grid empty-pattern invariants changed".format(kind)
    return None


def _group_records(candidates):
    groups = []
    for record in candidates:
        key = tuple(record["pattern"])
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(record)
    return groups


def _histogram_matches_raw(record, pairs):
    counts = dict(pairs)
    return (
        len(pairs) == record["raw_num_values"]
        and pairs[-1][0] == record["raw_max_finite_value"]
        and sum(counts.values()) == record["raw_finite_count"]
        and sum(value * count for value, count in pairs)
        == record["raw_finite_sum"]
        and (
            record["raw_initial_dead_end"]
            or counts.get(record["raw_initial_h"])
            == record["raw_initial_value_count"]
        )
    )


def _histogram_matches_transform(record, pairs):
    cap = record["value_cap"]
    transformed = defaultdict(int)
    for value, count in pairs:
        transformed[value if cap < 0 else min(value, cap)] += count
    expected_initial = (
        None
        if record["raw_initial_dead_end"]
        else (
            record["raw_initial_h"]
            if cap < 0
            else min(record["raw_initial_h"], cap)
        )
    )
    return (
        len(transformed) == record["transformed_num_values"]
        and sum(value * count for value, count in transformed.items())
        == record["finite_sum"]
        and record["initial_h"] == expected_initial
    )


def _validate_groups(candidates, require_complete):
    """Validate normalized retained records containing histogram digests."""
    errors = []
    groups = []
    for record in candidates:
        if not isinstance(record, dict) or _validate_record(
            record, "candidate", retained=True
        ):
            errors.append("cap-grid group contains an invalid candidate")
            continue
        key = tuple(record["pattern"])
        if not groups or groups[-1][0] != key:
            if any(old_key == key for old_key, _ in groups):
                errors.append("cap-grid candidate pattern is noncontiguous")
            groups.append((key, []))
        groups[-1][1].append(record)
    source_owner = {}
    representatives = []
    for group_index, (pattern, variants) in enumerate(groups):
        sources = variants[0]["sources"]
        states = variants[0]["abstract_states"]
        budget = variants[0]["cofactor_width_budget"]
        for source in sources:
            if source in source_owner:
                errors.append("cap-grid source occurs in multiple patterns")
            source_owner[source] = pattern
        if any(
            record["sources"] != sources
            or record["abstract_states"] != states
            or record["cofactor_width_budget"] != budget
            for record in variants
        ):
            errors.append("cap-grid pattern identity changes across caps")
        statuses = [record["raw_num_values"] is None for record in variants]
        if any(statuses):
            if not all(statuses) or len(variants) != 1:
                errors.append(
                    "cap-grid pattern mixes materialized and unmaterialized records"
                )
            elif variants[0]["sources"] != ["cegar"] or variants[0]["value_cap"] != -1:
                errors.append("cap-grid unmaterialized CEGAR form changed")
            if group_index != len(groups) - 1:
                errors.append("unmaterialized cap-grid record is not terminal")
            continue
        caps = [record["value_cap"] for record in variants]
        finite_caps = [cap for cap in caps if cap >= 0]
        expected_caps = [
            cap
            for cap in GRID
            if cap < variants[0]["raw_max_finite_value"]
        ]
        group_complete = require_complete or group_index < len(groups) - 1
        if group_complete:
            if caps != expected_caps + [-1]:
                errors.append(
                    "complete cap-grid pattern does not contain the exact "
                    "producer cap prefix plus exact transform"
                )
        else:
            expected_sequence = expected_caps + [-1]
            if caps != expected_sequence[: len(caps)]:
                errors.append("cap-grid prefix skips/reorders a producer cap")
        widths = [record["cofactor_width"] for record in variants]
        if widths != sorted(widths):
            errors.append("cap-grid width decreases under terminal refinement")
        raw_identity = (
            variants[0]["raw_add_nodes"],
            variants[0]["raw_num_terminals"],
            variants[0]["raw_cofactor_width"],
            variants[0]["raw_width_upper_bound"],
            variants[0]["raw_num_values"],
            variants[0]["raw_max_finite_value"],
            variants[0]["raw_finite_sum"],
            variants[0]["raw_finite_count"],
            variants[0]["raw_dead_count"],
            variants[0]["raw_initial_dead_end"],
            variants[0]["raw_initial_h"],
            variants[0]["raw_initial_value_count"],
            variants[0]["raw_value_histogram"],
        )
        if any(
            (
                record["raw_add_nodes"],
                record["raw_num_terminals"],
                record["raw_cofactor_width"],
                record["raw_width_upper_bound"],
                record["raw_num_values"],
                record["raw_max_finite_value"],
                record["raw_finite_sum"],
                record["raw_finite_count"],
                record["raw_dead_count"],
                record["raw_initial_dead_end"],
                record["raw_initial_h"],
                record["raw_initial_value_count"],
                record["raw_value_histogram"],
            ) != raw_identity
            for record in variants
        ):
            errors.append("cap-grid raw identity changes across transforms")
        finite_sums = [record["finite_sum"] for record in variants]
        finite_values = [record["transformed_num_values"] for record in variants]
        initial_values = [
            record["initial_h"]
            for record in variants
            if not record["initial_dead_end"]
        ]
        add_nodes = [record["add_nodes"] for record in variants]
        terminals = [record["num_terminals"] for record in variants]
        upper_bounds = [record["width_upper_bound"] for record in variants]
        if finite_sums != sorted(finite_sums):
            errors.append("cap-grid finite sum decreases under refinement")
        if finite_values != sorted(finite_values):
            errors.append("cap-grid finite-value count decreases under refinement")
        if initial_values != sorted(initial_values):
            errors.append("cap-grid initial value decreases under refinement")
        if add_nodes != sorted(add_nodes) or terminals != sorted(terminals) or upper_bounds != sorted(upper_bounds):
            errors.append("cap-grid A/T/U decreases under terminal refinement")
        feasible = [record for record in variants if record["feasible"]]
        if feasible:
            representatives.append(feasible[-1])
            flags = [record["feasible"] for record in variants]
            if flags != sorted(flags, reverse=True):
                errors.append("cap-grid feasibility is nonmonotone")
    return errors, representatives, source_owner


def _normalize_wire_groups(candidates, require_complete):
    """Decode each once-per-pattern census and return bounded records."""
    errors = []
    groups = _group_records(candidates)
    normalized = []
    digest_by_pattern = {}
    for pattern, variants in groups:
        if any(_validate_record(item, "candidate", retained=False) for item in variants):
            errors.append("cap-grid wire group contains an invalid candidate")
            continue
        unmaterialized = variants[0]["raw_num_values"] is None
        if unmaterialized:
            if any(item["raw_value_histogram"] is not None for item in variants):
                errors.append("unmaterialized cap-grid group carries a histogram")
            normalized.extend(variants)
            continue
        histograms = [item["raw_value_histogram"] for item in variants]
        if not isinstance(histograms[0], str) or any(
            value is not None for value in histograms[1:]
        ):
            errors.append(
                "cap-grid raw histogram must occur only on a pattern's first candidate"
            )
            continue
        try:
            pairs, digest = decode_raw_value_histogram(histograms[0])
        except ValueError as err:
            errors.append("cap-grid raw histogram is invalid: {}".format(err))
            continue
        if any(not _histogram_matches_raw(item, pairs) for item in variants):
            errors.append("cap-grid raw histogram contradicts raw statistics")
            continue
        if any(not _histogram_matches_transform(item, pairs) for item in variants):
            errors.append("cap-grid transform contradicts exact raw histogram")
            continue
        digest_by_pattern[pattern] = digest
        normalized.extend(_with_histogram_digest(item, digest) for item in variants)
    retained_errors, representatives, source_owner = _validate_groups(
        normalized, require_complete
    )
    errors.extend(retained_errors)
    return errors, normalized, representatives, source_owner, digest_by_pattern


def _canonical_sha(value):
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _raw_pool_core(candidates):
    """Return the v1-normalized uncapped pool for cross-protocol equality."""
    result = []
    seen = set()
    for record in candidates:
        pattern = tuple(record["pattern"])
        if pattern in seen:
            continue
        seen.add(pattern)
        if record["raw_num_values"] is None:
            core = {
                "protocol": C.PDB_SELECTOR_POOL_PROTOCOL,
                "score_version": C.PDB_SELECTOR_SCORE_VERSION,
                "sources": record["sources"],
                "pattern": record["pattern"],
                "abstract_states": record["abstract_states"],
                "initial_dead_end": None,
                "initial_h": None,
                "finite_sum": None,
                "finite_count": None,
                "dead_count": None,
                "cofactor_width": None,
                "width_upper_bound": None,
            }
        else:
            core = {
                "protocol": C.PDB_SELECTOR_POOL_PROTOCOL,
                "score_version": C.PDB_SELECTOR_SCORE_VERSION,
                "sources": record["sources"],
                "pattern": record["pattern"],
                "abstract_states": record["abstract_states"],
                "initial_dead_end": record["raw_initial_dead_end"],
                "initial_h": (
                    None
                    if record["raw_initial_dead_end"]
                    else record["raw_initial_h"]
                ),
                "finite_sum": record["raw_finite_sum"],
                "finite_count": record["raw_finite_count"],
                "dead_count": record["raw_dead_count"],
                "cofactor_width": record["raw_cofactor_width"],
                "width_upper_bound": record["raw_width_upper_bound"],
            }
        result.append(core)
    return result


def parse_cap_selector_log(content, props):
    if CAP_PROTOCOL_HINT_RE.search(content) is None:
        try:
            C.parse_pdb_selector_log(content, props)
        except RecursionError:
            tools.add_unexplained_error(
                props, "selector JSON nesting exceeds the parser limit"
            )
        return

    errors = []
    records = []
    kinds = []
    event_kinds = []
    for line in content.splitlines():
        if "wbh PDB heuristic:" in line:
            event_kinds.append("final")
        if "PDB width-selector" not in line:
            continue
        match = SELECTOR_RE.fullmatch(line)
        if not match:
            errors.append("cap-grid selector line has a noncanonical prefix")
            continue
        kind, payload = match.groups()
        event_kinds.append(kind)
        try:
            record = _load(payload)
        except (TypeError, ValueError, RecursionError, json.JSONDecodeError) as err:
            errors.append("cap-grid {} JSON is malformed: {}".format(kind, err))
            continue
        error = _validate_record(record, kind, retained=False)
        if error:
            errors.append(error)
        kinds.append(kind)
        if error is None:
            records.append((kind, record))

    wire_candidates = [
        record for kind, record in records if kind == "candidate"
    ]
    wire_selected_records = [
        record for kind, record in records if kind == "selected"
    ]
    final_lines = [
        line for line in content.splitlines() if "wbh PDB heuristic:" in line
    ]
    final = None
    if len(final_lines) == 1:
        match = FINAL_RE.fullmatch(final_lines[0])
        if match:
            try:
                (
                    pattern_size,
                    selected_source,
                    abstract_states,
                    width_budget,
                    value_cap,
                    num_values,
                    width,
                    upper,
                ) = match.groups()
                numeric = (
                    pattern_size,
                    abstract_states,
                    width_budget,
                    value_cap,
                    num_values,
                    width,
                    upper,
                )
                if any(len(value.lstrip("-")) > 10 for value in numeric):
                    raise ValueError("numeric field exceeds bounded decimal width")
                final = {
                    "pattern_size": int(pattern_size),
                    "selected_source": selected_source,
                    "abstract_states": int(abstract_states),
                    "cofactor_width_budget": int(width_budget),
                    "value_cap": int(value_cap),
                    "num_values": int(num_values),
                    "cofactor_width": int(width),
                    "width_upper_bound": int(upper),
                }
            except (ValueError, OverflowError):
                errors.append("cap-grid final line has an invalid integer")
        else:
            errors.append("cap-grid final line is malformed")
    elif len(final_lines) > 1:
        errors.append("cap-grid has multiple PDB final lines")

    wire_selected = (
        wire_selected_records[0] if len(wire_selected_records) == 1 else None
    )
    pool_must_be_complete = wire_selected is not None or final is not None
    (
        group_errors,
        candidates,
        representatives,
        source_owner,
        digest_by_pattern,
    ) = _normalize_wire_groups(wire_candidates, pool_must_be_complete)
    errors.extend(group_errors)
    selected = None
    if wire_selected is not None:
        pattern = tuple(wire_selected["pattern"])
        if wire_selected["raw_value_histogram"] is not None:
            errors.append("cap-grid selected record repeats the raw histogram")
        digest = digest_by_pattern.get(pattern)
        if digest is None:
            errors.append("cap-grid selected record lacks a certified raw histogram")
        else:
            selected = _with_histogram_digest(wire_selected, digest)
            selected_error = _validate_record(
                selected, "selected", retained=True
            )
            if selected_error:
                errors.append(selected_error)
    complete = bool(candidates and selected is not None and final is not None)
    if kinds != ["candidate"] * len(wire_candidates) + ["selected"] * len(
        wire_selected_records
    ):
        errors.append("cap-grid records are not candidate+ then selected")
    expected_events = ["candidate"] * len(wire_candidates)
    if wire_selected_records:
        expected_events.append("selected")
    if final_lines:
        expected_events.append("final")
    if event_kinds != expected_events:
        errors.append("cap-grid final/selector event order is noncanonical")
    if len(wire_selected_records) > 1:
        errors.append("cap-grid has multiple selected records")
    if final is not None and selected is None:
        errors.append("cap-grid final exists without one selected record")
    budgets = {
        record["cofactor_width_budget"]
        for record in candidates + ([selected] if selected is not None else [])
    }
    if len(budgets) > 1:
        errors.append("cap-grid records do not share one width budget")

    seen_patterns = set()
    first_source_positions = []
    for record in candidates:
        pattern = tuple(record["pattern"])
        if pattern in seen_patterns:
            continue
        seen_patterns.add(pattern)
        if record["sources"]:
            first_source_positions.append(
                C.PDB_SELECTOR_SOURCES.index(record["sources"][0])
            )
    if (
        first_source_positions != sorted(first_source_positions)
        or len(first_source_positions) != len(set(first_source_positions))
    ):
        errors.append("cap-grid groups violate fixed first-source order")
    if candidates and "empty" not in candidates[0]["sources"]:
        errors.append("cap-grid prefix does not start with the empty pattern")
    if first_source_positions:
        latest_first_source = max(first_source_positions)
        if any(
            C.PDB_SELECTOR_SOURCES[position] not in source_owner
            for position in range(latest_first_source)
        ):
            errors.append("cap-grid prefix skips an earlier fixed-pool source")
    if pool_must_be_complete and set(source_owner) != set(C.PDB_SELECTOR_SOURCES):
        errors.append("complete cap-grid trace lacks the fixed source pool")

    if selected is not None:
        if not representatives:
            errors.append("complete cap-grid trace has no feasible transform")
        else:
            expected = min(representatives, key=C._selector_score_key)
            if selected != expected:
                errors.append(
                    "cap-grid selected record is not the best pattern's "
                    "strongest feasible transform"
                )
        if final is not None:
            comparisons = {
                "pattern_size": len(selected["pattern"]),
                "selected_source": selected["sources"][0],
                "abstract_states": selected["abstract_states"],
                "cofactor_width_budget": selected["cofactor_width_budget"],
                "value_cap": selected["value_cap"],
                "num_values": selected["transformed_num_values"],
                "cofactor_width": selected["cofactor_width"],
                "width_upper_bound": selected["width_upper_bound"],
            }
            if any(final.get(key) != value for key, value in comparisons.items()):
                errors.append("cap-grid final line disagrees with selected record")
        for field, expected in (
            ("cofactor_width", selected["cofactor_width"]),
            ("width_upper_bound", selected["width_upper_bound"]),
            ("num_values", selected["transformed_num_values"]),
            ("num_terminals", selected["num_terminals"]),
            ("add_nodes", selected["add_nodes"]),
            ("value_cap", selected["value_cap"]),
            ("heuristic_kind", "pdb_exact_width_cap_filter"),
            ("heuristic_size_bound", 100000),
        ):
            if field in props and props[field] != expected:
                errors.append(
                    "cap-grid selected {} disagrees with parsed property".format(
                        field
                    )
                )

    certified = complete and not errors
    validation_error = (
        None
        if certified
        else (
            " | ".join(dict.fromkeys(errors))
            if errors
            else "cap-grid selector trace is incomplete"
        )
    )
    props[C.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY] = complete
    props[C.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY] = certified
    props[C.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY] = validation_error
    props[C.PDB_SELECTOR_CANDIDATES_PROPERTY] = candidates
    props[C.PDB_SELECTOR_SELECTED_PROPERTY] = selected
    props[C.PDB_SELECTOR_FINAL_PROPERTY] = final
    props[C.PDB_SELECTOR_TRACE_SHA256_PROPERTY] = (
        _canonical_sha(
            {"candidates": candidates, "selected": selected, "final": final}
        )
        if certified
        else None
    )
    props[C.PDB_SELECTOR_POOL_SHA256_PROPERTY] = (
        _canonical_sha(
            [
                {
                    key: value
                    for key, value in record.items()
                    if key not in {
                        "cofactor_width_budget", "feasible", "rejection_reason"
                    }
                }
                for record in candidates
            ]
        )
        if certified
        else None
    )
    props[RAW_POOL_SHA256_PROPERTY] = (
        _canonical_sha(_raw_pool_core(candidates)) if certified else None
    )
    props["pdb_cap_selector_parser_protocol"] = PARSER_PROTOCOL
    if final is not None:
        props.update(
            {
                "pdb_final_format": "exact_width_cap_filter",
                "pdb_pattern_size": final["pattern_size"],
                "pdb_selected_source": final["selected_source"],
                "pdb_abstract_states": final["abstract_states"],
                "pdb_cofactor_width_budget": final["cofactor_width_budget"],
                "pdb_selected_value_cap": final["value_cap"],
                "pdb_final_num_values": final["num_values"],
                "pdb_final_cofactor_width": final["cofactor_width"],
                "pdb_final_width_upper_bound": final["width_upper_bound"],
            }
        )
    # Malformed records are never an explainable resource prefix. A clean
    # candidate-only or selected-without-final prefix remains explicitly
    # incomplete for the outcome analyzer to classify by terminal exit.
    if errors:
        for error in dict.fromkeys(errors):
            tools.add_unexplained_error(props, error)


def get_parser():
    parser = Parser()
    parser.add_function(parse_cap_selector_log, file="run.log")
    return parser
