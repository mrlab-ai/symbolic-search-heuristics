#!/usr/bin/env python3
"""Fail-closed parser for the deterministic goal-fill PDB identity."""

from __future__ import annotations

import re


PARSER_PROTOCOL = "pdb-goal-fill-pattern-identity-v1"
_PREFIX = r"(?:\[t=(?:0|[1-9]\d*)\.\d{6}s, (?:0|[1-9]\d*) KB\] )?"
PATTERN_RE = re.compile(
    r"^" + _PREFIX
    + r"PDB pattern selection=goal_fill "
    + r"\((0|[1-9]\d*) vars, <= 100000 abstract states\): "
    + r"\[([0-9, ]*)\]$"
)


class PatternParseError(RuntimeError):
    pass


def parse_pattern(content: str):
    matches = [
        match for line in content.splitlines()
        if (match := PATTERN_RE.fullmatch(line))
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise PatternParseError("goal-fill pattern identity is repeated")
    declared = int(matches[0].group(1))
    payload = matches[0].group(2)
    if payload == "":
        pattern = []
    else:
        if not re.fullmatch(r"(?:0|[1-9]\d*)(?:, (?:0|[1-9]\d*))*", payload):
            raise PatternParseError("goal-fill pattern list is noncanonical")
        pattern = [int(value) for value in payload.split(", ")]
    if (
        len(pattern) != declared
        or len(pattern) != len(set(pattern))
        or pattern != sorted(pattern)
        or any(value > 1000000 for value in pattern)
    ):
        raise PatternParseError("goal-fill pattern identity is invalid")
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


def get_parser():
    from lab.parser import Parser

    parser = Parser()
    parser.add_function(parse_goal_fill_pattern, file="run.log")
    return parser
