"""Downward Lab parser for the width-bounded-heuristics JSON-lines log (PR5).

Provides get_parser(), returning a Parser that reads the per-run wbh.jsonl
(written by the wbh_log search option) and the planner stdout, and sets the
attributes:
  coverage, solution_cost, total_time, effort, peak_bdd_nodes,
  partition_ratio_max, partition_ratio_geomean, width_upper_bound, num_values,
  add_nodes, construction_time, expanded_bdd_nodes, bucket_images, image_time,
  num_pruned_deadends, and pruned_deadend_states.

Version-2 logs self-identify CUDD inner-node counts (Cudd_DagSize - 1 per
stored BDD). For blind multi-piece frontiers they are sums over pieces, not
the size of an exact-union BDD. Logs without a schema event are explicitly
labeled legacy CUDD DagSize; their blind piece counts are not reconstructible.
Partition ratios describe each generated image passed to the heuristic
partitioner; they are not aggregated complete cost layers.
"""
import json
import math


def parse_wbh_log(content, props):
    schema = None
    expands = []
    images = []
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
        if kind == "schema":
            schema = event
        elif kind == "expand":
            expands.append(event)
        elif kind == "image":
            images.append(event)
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
    if schema is not None:
        props["wbh_schema_version"] = schema["version"]
        props["node_count_convention"] = schema["node_count_convention"]
        props["image_count_convention"] = schema["image_count_convention"]
        props["expansion_count_convention"] = schema.get(
            "expansion_count_convention", "missing")
        required_summary = {
            "expanded_bdd_pieces", "attempted_bdd_pieces",
            "bucket_expansions", "bucket_expansion_attempts",
            "image_source_pieces", "image_calls_attempted",
            "image_calls_completed",
        }
        props["piece_metrics_certified"] = (
            schema.get("version") == 2
            and schema.get("node_count_convention")
            == "inner_nodes_per_piece"
            and schema.get("image_count_convention")
            == "per_piece_attempted_completed"
            and schema.get("expansion_count_convention")
            == "completed_with_attempts"
            and all("piece_count" in e and "completed" in e for e in expands)
            and all(
                {"source_pieces", "calls_attempted", "calls_completed"}
                <= set(e) for e in images)
            and (summary is None or required_summary <= set(summary)))
    else:
        # Archives produced before schema v2 logged Cudd_DagSize (including a
        # terminal per BDD) and did not record blind frontier piece counts.
        # Do not silently reinterpret those values as inner-node work.
        props["wbh_schema_version"] = 1
        props["node_count_convention"] = "legacy_cudd_dag_size"
        props["image_count_convention"] = "legacy_expand_event_count"
        props["expansion_count_convention"] = "legacy_attempts_unmarked"
        props["piece_metrics_certified"] = False

    if done is not None:
        props["effort"] = done["effort"]
        props["solution_cost"] = done["solution_cost"]
    if expands:
        completed_expands = [
            e for e in expands if e.get("completed", True)]
        props["peak_bdd_nodes"] = max(e["bdd_nodes"] for e in expands)
        props["attempted_bdd_nodes"] = sum(
            e["bdd_nodes"] for e in expands)
        props["attempted_states"] = sum(e["states"] for e in expands)
        props["bucket_expansion_attempts"] = len(expands)
        if all("piece_count" in e for e in expands):
            props["attempted_bdd_pieces"] = sum(
                e["piece_count"] for e in expands)
        # Paper-defined expansion and effort metrics exclude failed attempts.
        props["expanded_bdd_nodes"] = sum(
            e["bdd_nodes"] for e in completed_expands)
        props["expanded_states"] = sum(
            e["states"] for e in completed_expands)
        props["bucket_expansions"] = len(completed_expands)
        if all("piece_count" in e for e in completed_expands):
            props["expanded_bdd_pieces"] = sum(
                e["piece_count"] for e in completed_expands)
        props["bucket_images"] = len(expands)
        props["image_time"] = sum(e["image_time"] for e in expands)
    if images:
        props["image_events"] = len(images)
        props["bucket_images"] = sum(
            e.get("calls_completed", 1) for e in images)
        props["image_source_buckets"] = sum(
            e["source_buckets"] for e in images)
        props["image_source_pieces"] = sum(
            e.get("source_pieces", 1) for e in images)
        props["image_calls_attempted"] = sum(
            e.get("calls_attempted", 1) for e in images)
        props["image_calls_completed"] = sum(
            e.get("calls_completed", 1) for e in images)
        props["batched_images"] = sum(
            e["source_buckets"] > 1 for e in images)
        props["image_time"] = sum(e["image_time"] for e in images)
    if summary is not None:
        props["expanded_bdd_nodes"] = summary["expanded_bdd_nodes"]
        props["expanded_states"] = summary["expanded_states"]
        if "expanded_bdd_pieces" in summary:
            props["expanded_bdd_pieces"] = summary["expanded_bdd_pieces"]
        props["bucket_expansions"] = summary.get(
            "bucket_expansions", summary["bucket_images"])
        if "attempted_bdd_nodes" in summary:
            props["attempted_bdd_nodes"] = summary["attempted_bdd_nodes"]
            props["attempted_states"] = summary["attempted_states"]
            props["attempted_bdd_pieces"] = summary[
                "attempted_bdd_pieces"]
            props["bucket_expansion_attempts"] = summary[
                "bucket_expansion_attempts"]
        props["image_events"] = summary.get(
            "image_events", summary["bucket_images"])
        props["bucket_images"] = summary["bucket_images"]
        props["image_source_buckets"] = summary.get(
            "image_source_buckets", summary["bucket_images"])
        if "image_source_pieces" in summary:
            props["image_source_pieces"] = summary["image_source_pieces"]
        if "image_calls_attempted" in summary:
            props["image_calls_attempted"] = summary[
                "image_calls_attempted"]
        if "image_calls_completed" in summary:
            props["image_calls_completed"] = summary[
                "image_calls_completed"]
        props["batched_images"] = summary.get("batched_images", 0)
        props["image_time"] = summary["image_time"]
    if (props["piece_metrics_certified"]
            and "expanded_bdd_pieces" in props
            and "bucket_expansions" in props):
        # This certifies when the stored piece-sum equals a single BDD per
        # logical expansion. It does not claim anything about shared nodes
        # across different expansions.
        props["expanded_buckets_single_piece"] = (
            props["expanded_bdd_pieces"] == props["bucket_expansions"])
    if heuristic is not None:
        props["width_upper_bound"] = heuristic["width_upper_bound"]
        props["num_values"] = heuristic["num_values"]
        if "num_terminals" in heuristic:
            props["num_terminals"] = heuristic["num_terminals"]
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
