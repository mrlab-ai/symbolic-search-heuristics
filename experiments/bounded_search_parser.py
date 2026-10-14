#!/usr/bin/env python3
"""Parse the two phases of bounded symbolic search.

Fast Downward's iterated search logs "Best solution cost so far: C" after
every phase that improves the best plan, and symbolic search logs
"Exclusive plan cost bound: U" when it starts with the bound of the first
phase.  The parser records the first and the last best cost, the bound, and
the inner BDD nodes of all completed expansions of the symbolic search
(summed over the expand events of its wbh_log, which also covers searches
that prove the bound optimal and thus log no done event).
"""

from __future__ import annotations

import json
import re

BEST = re.compile(r"Best solution cost so far: (\d+)")
BOUND = re.compile(r"Exclusive plan cost bound: (\d+)")


def parse_log(content, props):
    costs = [int(value) for value in BEST.findall(content)]
    bounds = [int(value) for value in BOUND.findall(content)]
    props["bounded_best_costs"] = costs
    if costs:
        props["bounded_first_cost"] = costs[0]
        props["bounded_final_cost"] = costs[-1]
    if len(bounds) == 1:
        props["bounded_bound"] = bounds[0]
    elif bounds:
        props["bounded_parse_error"] = "several symbolic bounds"


def parse_expansions(content, props):
    nodes = 0
    for line in content.splitlines():
        if '"event":"expand"' not in line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            props["bounded_parse_error"] = "malformed expand event"
            return
        if event.get("completed") is True:
            nodes += int(event["bdd_nodes"])
    props["bounded_expanded_nodes"] = nodes


def get_parser():
    from lab.parser import Parser

    parser = Parser()
    parser.add_function(parse_log, file="run.log")
    parser.add_function(parse_expansions, file="wbh.jsonl")
    return parser


if __name__ == "__main__":
    props = {}
    parse_log("Best solution cost so far: 17\nExclusive plan cost bound: 17\n"
              "Best solution cost so far: 11\n", props)
    parse_expansions('{"event":"expand","completed":true,"bdd_nodes":5}\n'
                     '{"event":"expand","completed":false,"bdd_nodes":7}\n'
                     '{"event":"image","bdd_nodes":9}\n', props)
    expected = {"bounded_best_costs": [17, 11], "bounded_first_cost": 17,
                "bounded_final_cost": 11, "bounded_bound": 17,
                "bounded_expanded_nodes": 5}
    if props != expected:
        raise SystemExit("self-test failed: {}".format(props))
    print("self-test passed")
