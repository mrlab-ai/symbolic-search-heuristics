#!/usr/bin/env python3
"""Create a finite, structurally screened fresh-instance confirmation cohort."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import subprocess

import jj_cached_revision as JJ
import pdb_terminal_incidence_confirmation_inventory as Inventory
import pdb_within_family_instances as G
import pdb_within_family_monitor as Monitor
import pdb_within_family_source_worker as W


SCHEMA = "pdb-terminal-incidence-within-family-cohort/v1"
TARGETS = {"a": 650, "b": 300}
RESERVES_PER_LEVEL = 1
MAX_DUPLICATE_ATTEMPTS = 16
ARTIFACTS = G.ROOT / "artifacts/pdb-within-family-confirmation-v1"
PILOT = G.ROOT / "data/pdb-within-family-generator-pilot-v2"
FREEZE = ARTIFACTS / "cohort-freeze.json"


def load_completed_source(summary_path, launch_path, poll_path, manifest_path):
    """Independently check the retained source report against its raw evidence."""
    launch = json.loads(launch_path.read_bytes())
    poll = json.loads(poll_path.read_bytes())
    if poll["launch_sha256"] != W.file_sha(launch_path):
        raise ValueError("source launch/poll identity changed")
    accounting = poll["queries"]["accounting"]
    if accounting["returncode"] != 0:
        raise ValueError("source accounting query did not succeed")
    validation = Monitor.check_accounting(launch, accounting["stdout"])
    if not validation["all_completed_successfully"] or not validation["resources_match"]:
        raise ValueError("source pipeline is not successfully complete")
    summary = json.loads(summary_path.read_bytes())
    manifest = json.loads(manifest_path.read_bytes())
    if (summary["performance_observed"] is not False
            or summary["generator_manifest_sha256"] != W.file_sha(manifest_path)
            or manifest["records_sha256"] != G.sha(G.canonical(manifest["records"]))):
        raise ValueError("source/generator report changed")
    properties_path = summary_path.parent / "properties"
    if W.file_sha(properties_path) != summary["properties_sha256"]:
        raise ValueError("source properties changed")
    properties = json.loads(properties_path.read_bytes())
    rows = {("translator", r["family"], Path(r["problem_file"]).name): r
            for r in manifest["records"]}
    seen = set()
    results = {}
    experiment = Path(launch["experiment"])
    for props in properties.values():
        identity = tuple(props["id"])
        if identity not in rows or identity in seen or props.get("unexplained_errors"):
            raise ValueError("source matrix identity or parser error")
        seen.add(identity)
        row = rows[identity]
        result = props["source_result"]
        for kind in ("domain", "problem"):
            expected = row[f"{kind}_sha256"]
            if result[f"{kind}_sha256"] != expected:
                raise ValueError("source result input hash changed")
        # Lab's run_dir is relative to the experiment directory.
        run_dir = experiment / props["run_dir"]
        if not run_dir.resolve().is_relative_to(experiment.resolve()):
            raise ValueError("source run directory escaped its experiment")
        if json.loads((run_dir / "source-result.json").read_bytes()) != result:
            raise ValueError("source result differs from parsed report")
        if result["config_sha256"] != W.file_sha(run_dir / "source-config.json"):
            raise ValueError("source run configuration changed")
        if result["status"] in {"supported", "unsupported"}:
            sas = W.Translate.parse_and_hash_sas(run_dir / "output.sas")
            if any(sas[field] != result[field] for field in sas):
                raise ValueError("serialized source evidence changed")
            with (run_dir / "normalization.json").open("rb") as stream:
                normalization = W.Translate.read_normalization_evidence(stream.fileno())
            if normalization != result["normalization"]:
                raise ValueError("normalization evidence changed")
            reasons = W.support_reasons(sas["sas"], normalization["num_normalized_axioms"])
            if reasons != result["support_reasons"] or bool(reasons) != (result["status"] == "unsupported"):
                raise ValueError("source support classification changed")
        elif result["status"] not in {"memory-excluded", "time-excluded", "wall-excluded"}:
            raise ValueError("unresolved source failure")
        results[identity] = result
    if seen != set(rows) or len(summary["records"]) != len(rows):
        raise ValueError("source census incomplete")
    if {tuple(r["id"]): r for r in summary["records"]} != results:
        raise ValueError("source summary differs from the checked census")
    return manifest, results


def allocations(families):
    families = tuple(sorted(families))
    if not families or len(families) != len(set(families)) or not set(families) <= set(G.FAMILIES):
        raise ValueError("invalid supported family set")
    return {role: {family: total // len(families) + (index < total % len(families))
                   for index, family in enumerate(families)}
            for role, total in TARGETS.items()}


def analysis_settings(families):
    return {"minimum_eligible_tasks": 300, "minimum_comparison_tasks": 300,
            "minimum_families": min(25, len(families)),
            "minimum_target_strict_pairs": 600,
            "minimum_concordance": [13, 20], "minimum_advantage": [1, 50],
            "bootstrap_replicates": 100000, "bootstrap_seed": 20260901,
            "horizon": 16, "unseen_family_gate": False}


def candidate_specs(families):
    quotas = allocations(families)
    result = []
    for role in TARGETS:
        for family in sorted(families):
            count = quotas[role][family]
            for level in range(5):
                required = sum(i % 5 == level for i in range(count))
                for ordinal in range(required + RESERVES_PER_LEVEL):
                    result.append({"role": role, "family": family, "level": level,
                                   "index": 5 * ordinal + level,
                                   "reserve": ordinal >= required})
    return result


def exclusion_inventory():
    # This validates the prior ledgers and exact source checkout before hashing.
    inventory = Inventory.load_inventory()
    sources = Inventory._enumerate_source_paths(Inventory.DEFAULT_BENCHMARKS, inventory.directories)
    records = []
    for source in sources:
        path = Inventory.DEFAULT_BENCHMARKS / source.problem_file
        raw = path.read_bytes()
        if G.sha(raw) != source.problem_sha256:
            raise ValueError("prior problem changed while fingerprinting")
        records.append({"path": str(path), "problem_sha256": source.problem_sha256,
                        "instance_fingerprint": G.instance_fingerprint(raw)})
    for manifest_path in sorted(G.ROOT.glob("data/pdb-within-family-generator-pilot-v*/manifest.json")):
        manifest = json.loads(manifest_path.read_bytes())
        for row in manifest["records"]:
            if row["status"] != "generated":
                continue
            path = manifest_path.parent / row["problem_file"]
            raw = path.read_bytes()
            if G.sha(raw) != row["problem_sha256"]:
                raise ValueError("pilot problem changed")
            records.append({"path": str(path), "problem_sha256": row["problem_sha256"],
                            "instance_fingerprint": G.instance_fingerprint(raw)})
    return records


def generator_build_evidence():
    kit = G.attest_kit()
    extra = {}
    for directory in G.BUILD_TARGETS:
        for path in sorted((G.KIT / directory).rglob("*")):
            if path.is_file() and path.suffix != ".pyc":
                relative = path.relative_to(G.KIT).as_posix()
                if relative not in kit["source_sha256"]:
                    extra[relative] = W.file_sha(path)
    kit["compiled_and_generated_build_files_sha256"] = extra
    kit["perl_sha256"] = W.file_sha("/usr/bin/perl")
    kit["compiler_version"] = subprocess.check_output(["g++", "--version"], text=True)
    return kit


def source_closure(*names):
    """Hash the local Python import closure, including reused pure analyses."""
    pending = list(names)
    manifest = {}
    while pending:
        name = pending.pop()
        if name in manifest:
            continue
        path = G.ROOT / name
        raw = path.read_bytes()
        manifest[name] = G.sha(raw)
        for node in ast.walk(ast.parse(raw, filename=name)):
            imports = ([entry.name for entry in node.names] if isinstance(node, ast.Import)
                       else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for module in imports:
                imported = module.split(".")[0] + ".py"
                if (G.ROOT / imported).is_file():
                    pending.append(imported)
    return dict(sorted(manifest.items()))


def select_tasks(manifest, results):
    selected = {role: [] for role in TARGETS}
    for role, family_quotas in allocations(manifest["families"]).items():
        for family, total in family_quotas.items():
            for level in range(5):
                required = sum(index % 5 == level for index in range(total))
                candidates = sorted((row for row in manifest["records"]
                                     if (row["role"], row["family"], row["level"]) == (role, family, level)),
                                    key=lambda row: row["index"])
                supported = [row for row in candidates if results[(
                    "translator", family, Path(row["problem_file"]).name)]["status"] == "supported"]
                if len(supported) < required:
                    raise ValueError(f"finite structural pool insufficient for {role}/{family}/level-{level}")
                for row in supported[:required]:
                    result = results[("translator", family, Path(row["problem_file"]).name)]
                    selected[role].append(dict(row, domain=family, problem=Path(row["problem_file"]).name,
                                               source_result_sha256=G.sha(G.canonical(result)),
                                               sas_sha256=result["sas_sha256"]))
        selected[role].sort(key=lambda row: (row["family"], row["index"]))
        if len(selected[role]) != TARGETS[role]:
            raise ValueError("frozen cohort size changed")
    return selected


def freeze(pool, summary, launch, poll, output):
    manifest, results = load_completed_source(summary, launch, poll, pool / "manifest.json")
    tasks = select_tasks(manifest, results)
    all_tasks = tasks["a"] + tasks["b"]
    for field in ("problem_sha256", "instance_fingerprint", "seed"):
        if len({row[field] for row in all_tasks}) != len(all_tasks):
            raise ValueError(f"A/B overlap in {field}")
    for row in all_tasks:
        for kind in ("domain", "problem"):
            if W.file_sha(pool / row[f"{kind}_file"]) != row[f"{kind}_sha256"]:
                raise ValueError("generated input changed before freeze")
    code = source_closure("pdb_within_family_cohort.py", "exp_pdb_within_family_a_v1.py",
                          "pdb_within_family_a_analysis.py", "pdb_within_family_run_guard.py")
    revision = JJ.parent_commit(G.ROOT.parent)
    for name, expected in code.items():
        if JJ.tracked_file_sha256(G.ROOT.parent, revision, "experiments/" + name) != expected:
            raise ValueError("freeze requires a committed, matching analysis code closure")
    value = {
        "schema": SCHEMA + "/freeze", "scope": "fresh-instances-within-previously-studied-families",
        "pool_directory": str(pool), "pool_manifest_sha256": W.file_sha(pool / "manifest.json"),
        "source_summary": str(summary), "source_summary_sha256": W.file_sha(summary),
        "source_launch": str(launch), "source_launch_sha256": W.file_sha(launch),
        "source_poll": str(poll), "source_poll_sha256": W.file_sha(poll),
        "families": manifest["families"], "tasks": tasks, "targets": TARGETS,
        "source_status_counts": dict(Counter(r["status"] for r in results.values())),
        "analysis": analysis_settings(manifest["families"]),
        "code_commit": revision, "code_sha256": code, "performance_observed": False,
        "planner_revision": "8148f798f13059ee881ad2471bd20cdd61d2ec18",
    }
    Monitor.publish(output, value)
    print(f"Frozen {len(tasks['a'])} A and {len(tasks['b'])} B tasks in {len(manifest['families'])} families")


def load_freeze(path=FREEZE, *, verify_code=True):
    value = json.loads(path.read_bytes())
    if (value["schema"] != SCHEMA + "/freeze" or value["performance_observed"] is not False
            or value["scope"] != "fresh-instances-within-previously-studied-families"
            or value["targets"] != TARGETS
            or value["analysis"] != analysis_settings(value["families"])
            or value["planner_revision"] != "8148f798f13059ee881ad2471bd20cdd61d2ec18"):
        raise ValueError("fresh-instance freeze changed")
    for role, count in TARGETS.items():
        if len(value["tasks"][role]) != count:
            raise ValueError("fresh-instance cohort count changed")
        if Counter(r["family"] for r in value["tasks"][role]) != allocations(value["families"])[role]:
            raise ValueError("fresh-instance family allocation changed")
    pool = Path(value["pool_directory"])
    if W.file_sha(pool / "manifest.json") != value["pool_manifest_sha256"]:
        raise ValueError("fresh-instance pool manifest changed")
    for field in ("source_summary", "source_launch", "source_poll"):
        if W.file_sha(value[field]) != value[field + "_sha256"]:
            raise ValueError(f"frozen source evidence changed: {field}")
    if verify_code:
        for name, expected in value["code_sha256"].items():
            if W.file_sha(G.ROOT / name) != expected:
                raise ValueError(f"frozen scientific code changed: {name}")
    return value


def generate(output, pilot_summary, pilot_launch, pilot_poll):
    pilot_manifest, results = load_completed_source(
        pilot_summary, pilot_launch, pilot_poll, PILOT / "manifest.json")
    counts = {family: Counter(r["status"] for identity, r in results.items() if identity[1] == family)
              for family in G.FAMILIES}
    families = sorted(family for family, statuses in counts.items() if statuses == {"supported": 3})
    if not families:
        raise ValueError("no family passed the structural pilot")
    excluded = exclusion_inventory()
    seen_raw = {row["problem_sha256"] for row in excluded}
    seen_fingerprints = {row["instance_fingerprint"] for row in excluded}
    kit = generator_build_evidence()
    output.mkdir(parents=True, exist_ok=False)
    Monitor.publish(output / "exclusion-inventory.json", excluded)
    records = []
    rejected = []
    for spec in candidate_specs(families):
        row = dict(spec)
        for attempt in range(MAX_DUPLICATE_ATTEMPTS):
            seed = G.seed_for(row["role"], row["family"], row["index"], attempt)
            first = G.generate_one(row["family"], row["level"], seed)
            if first != G.generate_one(row["family"], row["level"], seed):
                raise ValueError(f"non-reproducible generation: {row}, seed {seed}")
            domain, problem, command = first
            fingerprint = G.instance_fingerprint(problem)
            if G.sha(problem) in seen_raw or fingerprint in seen_fingerprints:
                rejection = dict(row, seed=seed, attempt=attempt, reason="duplicate-problem",
                                 problem_sha256=G.sha(problem), instance_fingerprint=fingerprint)
                rejected.append(rejection)
                with (output / "rejected-generations.jsonl").open("ab") as stream:
                    stream.write(G.canonical(rejection))
                continue
            directory = output / row["family"]
            directory.mkdir(exist_ok=True)
            prefix = f"{row['role']}-{row['index']:03d}"
            for kind, raw in (("domain", domain), ("problem", problem)):
                name = prefix + ("-domain.pddl" if kind == "domain" else ".pddl")
                with (directory / name).open("xb") as stream:
                    stream.write(raw)
                row[f"{kind}_file"] = f"{row['family']}/{name}"
                row[f"{kind}_sha256"] = G.sha(raw)
            row.update(status="generated", seed=seed, attempt=attempt, command=command,
                       instance_fingerprint=fingerprint)
            seen_raw.add(G.sha(problem))
            seen_fingerprints.add(fingerprint)
            records.append(row)
            with (output / "generated-records.jsonl").open("ab") as stream:
                stream.write(G.canonical(row))
            break
        else:
            raise ValueError(f"finite duplicate retry budget exhausted: {spec}")
        if len(records) % 25 == 0:
            print(f"Generated and repeated {len(records)} fresh candidate tasks", flush=True)
    if generator_build_evidence() != kit:
        raise ValueError("generator source/build changed during generation")
    manifest = {"schema": SCHEMA, "role": "candidate-pool", "families": families,
                "targets": TARGETS, "allocations": allocations(families),
                "reserves_per_level": RESERVES_PER_LEVEL, "max_duplicate_attempts": MAX_DUPLICATE_ATTEMPTS,
                "kit": kit, "records": records, "records_sha256": G.sha(G.canonical(records)),
                "rejected_generations": rejected, "pilot_family_statuses": counts,
                "pilot_summary_sha256": W.file_sha(pilot_summary),
                "pilot_launch_sha256": W.file_sha(pilot_launch), "pilot_poll_sha256": W.file_sha(pilot_poll),
                "exclusion_inventory_sha256": W.file_sha(output / "exclusion-inventory.json"),
                "performance_observed": False}
    Monitor.publish(output / "manifest.json", manifest)
    print(f"Fresh candidate pool: {len(records)} tasks in {len(families)} families", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--output", type=Path, required=True)
    gen.add_argument("--pilot-summary", type=Path, required=True)
    gen.add_argument("--pilot-launch", type=Path, required=True)
    gen.add_argument("--pilot-poll", type=Path, required=True)
    lock = sub.add_parser("freeze")
    lock.add_argument("--pool", type=Path, required=True)
    lock.add_argument("--summary", type=Path, required=True)
    lock.add_argument("--launch", type=Path, required=True)
    lock.add_argument("--poll", type=Path, required=True)
    lock.add_argument("--output", type=Path, default=FREEZE)
    args = parser.parse_args()
    if args.action == "generate":
        generate(args.output.resolve(), args.pilot_summary.resolve(), args.pilot_launch.resolve(),
                 args.pilot_poll.resolve())
    else:
        freeze(args.pool.resolve(), args.summary.resolve(), args.launch.resolve(), args.poll.resolve(),
               args.output.resolve())


if __name__ == "__main__":
    main()
