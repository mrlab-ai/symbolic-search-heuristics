#!/usr/bin/env python3
"""Schema validator for width-bounded-heuristics JSON-lines logs (PR1).

Parses every line of a --wbh-log file and checks that each event has exactly
the expected keys and value types. Exits non-zero on the first violation.

Usage: python3 experiments/validate_wbh_log.py <log-file> [<log-file> ...]
"""
import json
import sys

SCHEMA = {
    "expand": {"g": int, "h": int, "bdd_nodes": int, "states": float,
               "image_time": float},
    "partition": {"g": int, "layer_nodes": int, "sum_bucket_nodes": int,
                  "num_buckets": int},
    "heuristic": {"add_nodes": int, "num_values": int,
                  "add_level_nodes": list, "width_upper_bound": int},
    "pruned_deadends": {"g": int, "states": float, "bdd_nodes": int},
    "done": {"effort": int, "solution_cost": int},
}


def validate_line(path, lineno, line):
    obj = json.loads(line)
    event = obj.get("event")
    if event not in SCHEMA:
        raise ValueError(f"{path}:{lineno}: unknown event {event!r}")
    expected = SCHEMA[event]
    keys = set(obj.keys()) - {"event"}
    if keys != set(expected):
        raise ValueError(
            f"{path}:{lineno}: {event} keys {sorted(keys)} != "
            f"{sorted(expected)}")
    for key, typ in expected.items():
        val = obj[key]
        # JSON ints are valid where floats are expected.
        ok = isinstance(val, typ) or (typ is float and isinstance(val, int))
        if not ok:
            raise ValueError(
                f"{path}:{lineno}: {event}.{key}={val!r} is not {typ.__name__}")
    return event


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    total = 0
    for path in sys.argv[1:]:
        counts = {}
        with open(path) as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                event = validate_line(path, lineno, line)
                counts[event] = counts.get(event, 0) + 1
                total += 1
        print(f"OK {path}: {counts}")
    print(f"Validated {total} lines.")


if __name__ == "__main__":
    main()
