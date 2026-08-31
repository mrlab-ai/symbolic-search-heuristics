#!/usr/bin/env python3
"""Fail-closed parser for a deterministic direct PDB identity."""

from __future__ import annotations

import hashlib
import re


PARSER_PROTOCOL = "pdb-direct-pattern-identity-v2"
_PREFIX = r"(?:\[t=(?:0|[1-9]\d*)\.\d{6}s, (?:0|[1-9]\d*) KB\] )?"
PATTERN_RE = re.compile(
    r"^" + _PREFIX
    + r"PDB pattern selection="
    + r"(bdd_prefix|goal_prefix|goal_fill|cegar|cegar_fallback_goal_fill) "
    + r"\((0|[1-9]\d*) vars, <= 100000 abstract states\): "
    + r"\[([0-9, ]*)\]$"
)
FINAL_RE = re.compile(
    r"^" + _PREFIX
    + r"wbh PDB heuristic: pattern_size=(0|[1-9]\d*), "
    + r"values=(0|[1-9]\d*)"
    + r"(?:, value_cap=(0|[1-9]\d*|-[1-9]\d*))?, "
    + r"cofactor_width=(0|[1-9]\d*), "
    + r"width_upper_bound=(0|[1-9]\d*)$"
)


class PatternParseError(RuntimeError):
    pass


def parse_identity(content: str):
    matches = [
        match for line in content.splitlines()
        if (match := PATTERN_RE.fullmatch(line))
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise PatternParseError("direct PDB pattern identity is repeated")
    mode = matches[0].group(1)
    declared = int(matches[0].group(2))
    payload = matches[0].group(3)
    if payload == "":
        pattern = []
    else:
        if not re.fullmatch(r"(?:0|[1-9]\d*)(?:, (?:0|[1-9]\d*))*", payload):
            raise PatternParseError("direct PDB pattern list is noncanonical")
        pattern = [int(value) for value in payload.split(", ")]
    if (
        len(pattern) != declared
        or len(pattern) != len(set(pattern))
        or pattern != sorted(pattern)
        or any(value > 1000000 for value in pattern)
    ):
        raise PatternParseError("direct PDB pattern identity is invalid")

    final_matches = [
        match for line in content.splitlines()
        if (match := FINAL_RE.fullmatch(line))
    ]
    if len(final_matches) != 1:
        raise PatternParseError(
            "direct PDB final identity is missing or repeated"
        )
    final = final_matches[0]
    pattern_size, values, value_cap, width, upper = final.groups()
    numeric = [int(pattern_size), int(values), int(width), int(upper)]
    if any(value > 9223372036854775807 for value in numeric):
        raise PatternParseError("direct PDB final identity is out of range")
    parsed = {
        "mode": mode,
        "state_budget": 100000,
        "pattern": pattern,
        "pattern_size": numeric[0],
        "pattern_sha256": hashlib.sha256(
            ("[" + ",".join(str(value) for value in pattern) + "]")
            .encode("ascii")
        ).hexdigest(),
        "num_values": numeric[1],
        "value_cap": None if value_cap is None else int(value_cap),
        "cofactor_width": numeric[2],
        "width_upper_bound": numeric[3],
    }
    if (
        parsed["pattern_size"] != len(pattern)
        or parsed["num_values"] < 1
        or parsed["cofactor_width"] < 1
        or parsed["width_upper_bound"] < parsed["cofactor_width"]
        or (mode != "goal_fill" and parsed["value_cap"] is not None)
    ):
        raise PatternParseError("direct PDB final identity is invalid")
    return parsed


def parse_pattern(content: str):
    """Return only the pattern, preserving the original public API."""
    matches = [
        match for line in content.splitlines()
        if (match := PATTERN_RE.fullmatch(line))
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise PatternParseError("direct PDB pattern identity is repeated")
    declared = int(matches[0].group(2))
    payload = matches[0].group(3)
    if payload == "":
        pattern = []
    else:
        if not re.fullmatch(r"(?:0|[1-9]\d*)(?:, (?:0|[1-9]\d*))*", payload):
            raise PatternParseError("direct PDB pattern list is noncanonical")
        pattern = [int(value) for value in payload.split(", ")]
    if (
        len(pattern) != declared
        or len(pattern) != len(set(pattern))
        or pattern != sorted(pattern)
        or any(value > 1000000 for value in pattern)
    ):
        raise PatternParseError("direct PDB pattern identity is invalid")
    return pattern


def _add_error(props, message):
    try:
        from lab import tools
    except ImportError:
        props.setdefault("unexplained_errors", []).append(message)
    else:
        tools.add_unexplained_error(props, message)


def parse_goal_fill_pattern(content, props) -> None:
    props["pdb_fixed_pattern_parser_protocol"] = PARSER_PROTOCOL
    try:
        pattern = parse_pattern(content)
        identity = (
            parse_identity(content)
            if any(FINAL_RE.fullmatch(line) for line in content.splitlines())
            else None
        )
    except PatternParseError as err:
        props["pdb_fixed_pattern_certified"] = False
        props["pdb_fixed_pattern_validation_error"] = str(err)
        _add_error(props, str(err))
        return
    props["pdb_fixed_pattern_present"] = pattern is not None
    props["pdb_fixed_pattern_certified"] = pattern is not None
    props["pdb_fixed_pattern_validation_error"] = None
    props["pdb_fixed_pattern"] = pattern
    props["pdb_fixed_pattern_size"] = (
        None if pattern is None else len(pattern)
    )
    props["pdb_fixed_pattern_mode"] = (
        None if pattern is None else (
            identity["mode"] if identity is not None else "goal_fill"
        )
    )
    props["pdb_fixed_pattern_final"] = identity
    props["pdb_fixed_pattern_sha256"] = (
        None if pattern is None else (
            identity["pattern_sha256"] if identity is not None else hashlib.sha256(
                ("[" + ",".join(str(value) for value in pattern) + "]")
                .encode("ascii")
            ).hexdigest()
        )
    )
    requested_by_algorithm = {
        "pdb_bdd_prefix_shadow": "bdd_prefix",
        "pdb_goal_prefix_shadow": "goal_prefix",
        "pdb_goal_fill_shadow": "goal_fill",
        "pdb_cegar_shadow": "cegar",
        "pdb_goal_fill_cap8_shadow": "goal_fill",
        # Historical fixed-pattern interventions remain parser compatible.
        "pdb_goal_fill_gamer": "goal_fill",
        "pdb_goal_fill_fd": "goal_fill",
    }
    algorithm = props.get("algorithm")
    requested = requested_by_algorithm.get(algorithm)
    observed = props["pdb_fixed_pattern_mode"]
    fallback = observed == "cegar_fallback_goal_fill"
    props["pdb_fixed_pattern_requested_mode"] = requested
    props["pdb_fixed_pattern_observed_mode"] = observed
    props["pdb_fixed_pattern_fallback"] = fallback
    if requested is not None and not (
        observed == requested or (requested == "cegar" and fallback)
    ):
        message = "direct PDB pattern mode disagrees with its algorithm"
        props["pdb_fixed_pattern_certified"] = False
        props["pdb_fixed_pattern_validation_error"] = message
        _add_error(props, message)
    expected_cap = 8 if algorithm == "pdb_goal_fill_cap8_shadow" else None
    if identity is not None and requested is not None and (
        identity["value_cap"] != expected_cap
    ):
        message = "direct PDB value cap disagrees with its algorithm"
        props["pdb_fixed_pattern_certified"] = False
        props["pdb_fixed_pattern_validation_error"] = message
        _add_error(props, message)


def get_parser():
    from lab.parser import Parser

    parser = Parser()
    parser.add_function(parse_goal_fill_pattern, file="run.log")
    return parser
