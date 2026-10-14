#!/usr/bin/env python3
"""Parse the per-iteration summaries of unsplit f-bounded symbolic search.

The planner writes one line per iteration to its log:

  WBH unsplit f-bound iteration: index=I, bound=B, expanded_bdd_nodes=N,
  expanded_layers=L, solved=true|false

The parser records the number of iterations, the bound, nodes and solved
flag of the last iteration, and the node sum over all iterations.  Runs of
other configurations get zero iterations and no other properties.
"""

from __future__ import annotations

import re

ITERATION = re.compile(
    r"WBH unsplit f-bound iteration: index=(\d+), bound=(\d+), "
    r"expanded_bdd_nodes=(\d+), expanded_layers=(\d+), solved=(true|false)"
)


def parse_iterations(content, props):
    rows = ITERATION.findall(content)
    props["unsplit_iterations"] = len(rows)
    if not rows:
        return
    indices = [int(row[0]) for row in rows]
    if indices != list(range(1, len(rows) + 1)):
        props["unsplit_parse_error"] = "iteration indices are not 1..k"
        return
    last = rows[-1]
    props["unsplit_final_bound"] = int(last[1])
    props["unsplit_final_nodes"] = int(last[2])
    props["unsplit_final_solved"] = last[4] == "true"
    props["unsplit_iteration_nodes_sum"] = sum(int(row[2]) for row in rows)


def get_parser():
    from lab.parser import Parser

    parser = Parser()
    parser.add_function(parse_iterations, file="run.log")
    return parser


if __name__ == "__main__":
    sample = (
        "WBH unsplit f-bound iteration: index=1, bound=5, "
        "expanded_bdd_nodes=10, expanded_layers=3, solved=false\n"
        "WBH unsplit f-bound iteration: index=2, bound=7, "
        "expanded_bdd_nodes=30, expanded_layers=7, solved=true\n"
    )
    props = {}
    parse_iterations(sample, props)
    expected = {
        "unsplit_iterations": 2, "unsplit_final_bound": 7,
        "unsplit_final_nodes": 30, "unsplit_final_solved": True,
        "unsplit_iteration_nodes_sum": 40,
    }
    if props != expected:
        raise SystemExit("self-test failed: {}".format(props))
    print("self-test passed")
