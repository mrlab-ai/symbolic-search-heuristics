#!/usr/bin/env python3
"""Run 7 cells of the CPDDL GHSETA* study per Slurm array index.

Usage: run_cells.py COHORT_DIR INDEX.  Cells are ordered task-major with a
fixed shuffle.  The pinned binary and both PDDL files are verified by SHA-256
before each run; runs get 300 seconds of CPU time and 8 GiB of address space.
"""
import hashlib, json, os, random, re, resource, subprocess, sys, time
from pathlib import Path

BINARY = Path("/nobackup/proj/disk/dfsplan/personal/jendrik/cpddl-cache/"
              "fea354d6c0b880aa/baselines/cpddl/bin/pddl-symba")
BINARY_SHA256 = "dee50c341ee7959c070a3eeaa7b2f29f5c9ab8a558777d71cff8edd7babc22fb"
BENCH = Path("/nobackup/proj/disk/dfsplan/personal/jendrik/downward-benchmarks-wbh")
PER_TASK = 7
CPU_SECONDS = 300
MEMORY_BYTES = 8 * 1024 ** 3


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 5))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))


def parse(text, wbh):
    costs = re.findall(r"Plan Cost: (\d+)", text)
    nodes = re.findall(r"(?<!Avg\. )(?<!Fw )(?<!Bw )Expanded BDD Nodes: (\d+)\s", text)
    record = {"cost": int(costs[-1]) if costs else None,
              "expanded_bdd_nodes": int(nodes[-1]) if nodes else None}
    if wbh is not None:
        expand_nodes = expand_states = layer_nodes = layer_states = 0
        expansions = layers = 0
        done = None
        malformed = 0
        for line in wbh.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                # A run killed by its limits may leave a truncated last line.
                malformed += 1
                continue
            if event.get("dir") != "fw":
                continue
            if event["event"] == "expand":
                expansions += 1
                expand_nodes += event["nodes"]
                expand_states += event["states"]
            elif event["event"] == "layer":
                layers += 1
                layer_nodes += event["nodes"]
                layer_states += event["states"]
            elif event["event"] == "done":
                done = event
        record.update({"wbh_expansions": expansions,
                       "wbh_expand_nodes": expand_nodes,
                       "wbh_expand_states": expand_states,
                       "wbh_layers": layers,
                       "wbh_layer_nodes": layer_nodes,
                       "wbh_layer_states": layer_states,
                       "wbh_done": done,
                       "wbh_malformed_lines": malformed})
    return record


def main():
    cohort_dir = Path(sys.argv[1]).resolve()
    index = int(sys.argv[2])
    tasks = json.load(open(cohort_dir / "tasks.json"))
    configs = json.load(open(cohort_dir / "configs.json"))
    if sha256(BINARY) != BINARY_SHA256:
        sys.exit("planner binary differs from the pin")
    cells = [(t, c) for t in range(len(tasks)) for c in range(len(configs))]
    random.Random("cpddl-ghseta-" + cohort_dir.name).shuffle(cells)
    for t, c in cells[index * PER_TASK:(index + 1) * PER_TASK]:
        task = tasks[t]
        label, args, profiled = configs[c]
        domain = BENCH / task["domain_file"]
        problem = BENCH / task["problem_file"]
        if (sha256(domain) != task["domain_sha256"]
                or sha256(problem) != task["problem_sha256"]):
            sys.exit("benchmark bytes changed")
        run = cohort_dir / "runs" / label / "{}__{}".format(
            task["domain"], task["problem"])
        run.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env.pop("PDDL_WBH_LOG", None)
        if profiled:
            env["PDDL_WBH_LOG"] = str(run / "wbh.jsonl")
        start = time.time()
        with open(run / "run.log", "w") as log:
            try:
                code = subprocess.call(
                    [str(BINARY)] + args + [str(domain), str(problem)],
                    cwd=run, stdout=log, stderr=subprocess.STDOUT, env=env,
                    preexec_fn=limits, timeout=CPU_SECONDS + 120)
            except subprocess.TimeoutExpired:
                code = "wall-timeout"
        wall = time.time() - start
        text = (run / "run.log").read_text(errors="replace")
        wbh = None
        if profiled and (run / "wbh.jsonl").exists():
            wbh = (run / "wbh.jsonl").read_text()
        record = parse(text, wbh)
        solved = code == 0 and record["cost"] is not None
        record.update({"domain": task["domain"], "problem": task["problem"],
                       "label": label, "args": args, "profiled": profiled,
                       "exit_code": code, "solved": solved,
                       "wall_seconds": wall})
        json.dump(record, open(run / "cell.json", "w"))


if __name__ == "__main__":
    main()
