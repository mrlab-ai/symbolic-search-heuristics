"""Downward Lab parser for the width-bounded-heuristics JSON-lines log (PR5).

Provides get_parser(), returning a Parser that reads the per-run wbh.jsonl
(written by the wbh_log search option) and the planner stdout, and sets the
attributes:
  coverage, solution_cost, total_time, effort, peak_bdd_nodes,
  partition_ratio_max, partition_ratio_geomean, width_upper_bound, num_values,
  add_nodes, construction_time, expanded_bdd_nodes, bucket_images, image_time,
  num_pruned_deadends, and pruned_deadend_states.

Node counts use CUDD's Cudd_DagSize convention, which includes the constant
node(s); the width theory counts inner nodes. We do not adjust here -- the
adjustment (subtracting constants) is documented and, since it is a constant
offset per BDD, does not affect cross-config comparisons on the same manager.
Partition ratios describe each generated image passed to the heuristic
partitioner; they are not aggregated complete cost layers.
"""
import json
import math


def parse_wbh_log(content, props):
    expands = []
    partitions = []
    heuristic = None
    construction = None
    summary = None
    done = None
    pruned_events = 0
    pruned_states = 0.0
    pruned_bdd_nodes = 0
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
        elif kind == "construction":
            construction = event
        elif kind == "summary":
            summary = event
        elif kind == "done":
            done = event
        elif kind == "pruned_deadends":
            pruned_events += 1
            pruned_states += event.get("states", 0)
            pruned_bdd_nodes += event.get("bdd_nodes", 0)
    props["raw_metrics_complete"] = summary is not None

    if done is not None:
        props["effort"] = done["effort"]
        props["solution_cost"] = done["solution_cost"]
    if expands:
        props["peak_bdd_nodes"] = max(e["bdd_nodes"] for e in expands)
        # These raw totals remain available when no solution (and hence no
        # paper-definition effort event) was produced.
        props["expanded_bdd_nodes"] = sum(e["bdd_nodes"] for e in expands)
        props["expanded_states"] = sum(e["states"] for e in expands)
        props["bucket_images"] = len(expands)
        props["image_time"] = sum(e["image_time"] for e in expands)
    if summary is not None:
        props["expanded_bdd_nodes"] = summary["expanded_bdd_nodes"]
        props["expanded_states"] = summary["expanded_states"]
        props["bucket_images"] = summary["bucket_images"]
        props["image_time"] = summary["image_time"]
    if heuristic is not None:
        props["width_upper_bound"] = heuristic["width_upper_bound"]
        props["num_values"] = heuristic["num_values"]
        props["add_nodes"] = heuristic["add_nodes"]
    if construction is not None:
        props["heuristic_kind"] = construction["heuristic"]
        props["construction_time"] = construction["seconds"]
        props["heuristic_size_bound"] = construction["size_bound"]
        props["value_cap"] = construction["value_cap"]
        props["construction_completed"] = construction["completed"]
    props["num_pruned_deadends"] = pruned_events
    props["pruned_deadend_states"] = pruned_states
    props["pruned_deadend_bdd_nodes"] = pruned_bdd_nodes

    ratios = [
        p["sum_bucket_nodes"] / p["layer_nodes"]
        for p in partitions if p["layer_nodes"] > 0
    ]
    if ratios:
        ratio_max = max(ratios)
        if any(r == 0 for r in ratios):
            ratio_geomean = 0
        else:
            log_mean = sum(math.log(r) for r in ratios) / len(ratios)
            ratio_geomean = math.exp(log_mean)
        props["partition_ratio_max"] = ratio_max
        props["partition_ratio_geomean"] = ratio_geomean
        # Backward-compatible aliases for archived report scripts.
        props["frag_ratio_max"] = ratio_max
        props["frag_ratio_geomean"] = ratio_geomean


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
