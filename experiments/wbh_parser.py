"""Downward Lab parser for the width-bounded-heuristics JSON-lines log (PR5).

Provides get_parser(), returning a Parser that reads the per-run wbh.jsonl
(written by the wbh_log search option) and the planner stdout, and sets the
attributes:
  coverage, solution_cost, total_time, effort, peak_bdd_nodes,
  frag_ratio_max, frag_ratio_geomean, width_upper_bound, num_values,
  add_nodes, num_pruned_deadends.

Node counts use CUDD's Cudd_DagSize convention, which includes the constant
node(s); the width theory counts inner nodes. We do not adjust here -- the
adjustment (subtracting constants) is documented and, since it is a constant
offset per BDD, does not affect the frag ratios or cross-config comparisons on
the same manager (pitfall #1).
"""
import json
import math


def parse_wbh_log(content, props):
    expands = []
    partitions = []
    heuristic = None
    done = None
    pruned = 0
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # A run killed by the time/memory limit can leave a truncated final
            # line; skip malformed lines rather than aborting the whole parse.
            continue
        kind = event.get("event")
        if kind == "expand":
            expands.append(event)
        elif kind == "partition":
            partitions.append(event)
        elif kind == "heuristic":
            heuristic = event
        elif kind == "done":
            done = event
        elif kind == "pruned_deadends":
            pruned += 1

    if done is not None:
        props["effort"] = done["effort"]
        props["solution_cost"] = done["solution_cost"]
    if expands:
        props["peak_bdd_nodes"] = max(e["bdd_nodes"] for e in expands)
    if heuristic is not None:
        props["width_upper_bound"] = heuristic["width_upper_bound"]
        props["num_values"] = heuristic["num_values"]
        props["add_nodes"] = heuristic["add_nodes"]
    props["num_pruned_deadends"] = pruned

    ratios = [
        p["sum_bucket_nodes"] / p["layer_nodes"]
        for p in partitions if p["layer_nodes"] > 0
    ]
    if ratios:
        props["frag_ratio_max"] = max(ratios)
        log_mean = sum(math.log(r) for r in ratios if r > 0) / len(ratios)
        props["frag_ratio_geomean"] = math.exp(log_mean)


def parse_coverage(content, props):
    props["coverage"] = 1 if "Solution found" in content else 0


def get_parser():
    from lab.parser import Parser
    parser = Parser()
    # Planner-level attributes from stdout (SymK prints "Plan cost:" and the
    # driver prints "Total time:").
    parser.add_pattern(
        "solution_cost", r"Plan cost: (\d+)", type=int, required=False)
    parser.add_pattern(
        "total_time", r"Total time: (.+)s", type=float, required=False)
    parser.add_function(parse_coverage, file="run.log")
    parser.add_function(parse_wbh_log, file="wbh.jsonl")
    return parser
