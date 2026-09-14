#!/usr/bin/env python3
"""Generate new, reproducible PDDL instances in previously studied families.

This module does not run a heuristic or inspect planner performance. Pilot
instances are for generator/translation feasibility only and cannot enter A/B.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import jj_cached_revision as JJ
from pdb_terminal_incidence_confirmation_inventory import ALL_PRIOR_FAMILIES


ROOT = Path(__file__).resolve().parent
KIT = ROOT / "data" / "pddl-generators-within-v1"
KIT_REVISION = "d5c22c9ab21ecaf90db82daf2a0537973c661009"
KIT_URL = "https://github.com/AI-Planning/pddl-generators"
TEMP_ROOT = ROOT / "data" / "pdb-within-family-generation-tmp"
SCHEMA = "pdb-terminal-incidence-within-family-generated-instances/v1"
FAMILIES = (
    "agricola", "barman", "blocks", "cavediving", "childsnack", "depot",
    "driverlog", "floortile", "freecell", "grid", "hiking", "logistics",
    "maintenance", "miconic", "mprime", "mystery", "nomystery", "parking",
    "pathways", "rovers", "satellite", "schedule", "snake", "storage",
    "tetris", "tpp", "transport", "visitall", "woodworking", "zenotravel",
)
BUILD_TARGETS = {
    "blocksworld": "4ops", "depots": "depots", "driverlog": "dlgen",
    "freecell": "freecell", "logistics": "logistics", "maintenance": "maintenance",
    "miconic": "miconic", "mprime": "mprime", "mystery": "mystery",
    "nomystery": "build", "pathways": "generator", "rovers": "rovgen",
    "satellite": "satgen", "schedule": "generator", "storage": "generator",
    "tpp": "tpp", "visitall": "grid", "zenotravel": "ztravel",
}


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def instance_fingerprint(raw: bytes) -> str:
    """Ignore comments, formatting and the nonsemantic problem identifier."""
    text = re.sub(r";[^\n]*", "", raw.decode("utf-8")).lower()
    tokens = re.findall(r"\(|\)|[^\s()]+", text)
    if tokens[:4] != ["(", "define", "(", "problem"] or len(tokens) < 7:
        raise ValueError("generator did not produce a PDDL problem")
    depth = 0
    for token in tokens:
        depth += (token == "(") - (token == ")")
        if depth < 0:
            raise ValueError("unbalanced PDDL output")
    if depth != 0 or tokens[-1] != ")":
        raise ValueError("unbalanced PDDL output")
    tokens[4] = "problem-name"
    return sha(canonical(tokens))


def seed_for(role: str, family: str, index: int, attempt: int = 0) -> int:
    if role not in {"pilot", "a", "b"} or family not in FAMILIES:
        raise ValueError("unknown generator role or family")
    if index < 0 or attempt < 0:
        raise ValueError("negative generator index")
    key = f"within-family-v1\0{role}\0{family}\0{index}\0{attempt}"
    return 1 + int(sha(key.encode("ascii"))[:15], 16) % (2**31 - 2)


def specification(family: str, level: int, seed: int, destination: Path) -> dict:
    """Five size settings per family, based on the kit's documented IPC ranges."""
    if family not in FAMILIES or level not in range(5) or seed <= 0:
        raise ValueError("invalid generator specification")
    directory = {"blocks": "blocksworld", "depot": "depots"}.get(family, family)
    source = KIT / directory
    domain = source / "domain.pddl"
    domain_output = None
    problem_output = None
    n = level

    def py(name, *args):
        return [sys.executable, "-B", str(source / name), *map(str, args)]

    def binary(name, *args):
        return [str(source / name), *map(str, args)]

    if family == "agricola":
        command = py("GenAgricola.py", 1 + n, seed)
    elif family == "barman":
        cocktails = 2 + n
        command = py("barman-generator.py", cocktails, 3 + n, 2 * cocktails + 1, seed)
    elif family == "blocks":
        domain = source / "4ops" / "domain.pddl"
        command = binary("blocksworld", 4, 10 + 2 * n, seed)
    elif family == "cavediving":
        domain_output = destination / "generated-domain.pddl"
        problem_output = destination / "generated-problem.pddl"
        branches = ":".join(["2"] * (2 + n))
        command = py(
            "generator/generator.py", "-domain_file", domain_output,
            "-problem_file", problem_output, "-problem_name", "fresh",
            "-cave_branches", branches, "-objectives", branches,
            "-strips", "True", "-order_tanks", "True", "-other_action_cost", 1,
            "-neg_link_prob", 0.25, "-seed", seed,
        )
    elif family == "childsnack":
        command = py("child-snack-generator.py", "pool", seed, 6 + 2 * n, 2, 0.4, 1.3)
    elif family == "depot":
        command = binary("depots", "-e", 2, "-i", 2, "-t", 2, "-p", 6 + 2 * n,
                         "-h", 4, "-c", 4 + 2 * n, "-s", seed)
    elif family == "driverlog":
        command = binary("dlgen", seed, 6 + 2 * n, 2 + n // 2, 3 + 2 * n, 2 + n // 2)
    elif family == "floortile":
        command = py("floortile-generator.py", "fresh", 3 + n, 3, 2, "seq", seed)
    elif family == "freecell":
        command = binary("freecell", "-f", 2, "-c", 4 + n // 2, "-s", 4,
                         "-0", 3 + n, "-1", 3 + n, "-2", 3 + n, "-3", 3 + n,
                         "-i", 4 + n // 2, "-r", seed)
    elif family == "grid":
        command = py("generate.py", 4 + n, 4 + n, "--shapes", 2,
                     "--keys", 4 + n, "--locks", 4 + n, "--prob-goal", 1,
                     "--seed", seed)
    elif family == "hiking":
        couples = 3 + n // 2
        command = py("generator.py", couples, couples + 2, 4 + 2 * n, seed)
    elif family == "logistics":
        command = binary("logistics", "-a", 2, "-c", 3 + n // 2, "-s", 3,
                         "-p", 4 + 2 * n, "-r", seed)
    elif family == "maintenance":
        # The upstream C program reads argv[7] as the seed and ignores argv[6].
        command = binary("maintenance", 6 + 2 * n, 10 + 5 * n, 1, 4, 2, 0, seed)
    elif family == "miconic":
        command = binary("miconic", "-f", 8 + 4 * n, "-p", 4 + 2 * n, "-r", seed)
    elif family in {"mprime", "mystery"}:
        command = binary(family, "-l", 6 + 2 * n, "-f", 8 + 2 * n, "-s", 3,
                         "-v", 2, "-c", 3 + n, "-r", seed)
    elif family == "nomystery":
        command = binary("build/nomystery", "-l", 6 + n, "-p", 5 + n,
                         "-c", 1.5, "-s", seed)
    elif family == "parking":
        curbs = 6 + n
        command = ["/usr/bin/perl", str(source / "parking-generator.pl"),
                   "fresh", str(curbs), str(2 * (curbs - 1)), "seq", str(seed)]
    elif family == "pathways":
        domain_output = destination / "generated-domain.pddl"
        problem_output = destination / "generated-problem.pddl"
        command = py("wrapper.py", "--seed", seed, "--reactions", 36 + 24 * n,
                     "--goals", 3 + 2 * n, "--initial-substances", 5 + 2 * n,
                     domain_output, problem_output)
    elif family == "rovers":
        command = binary("rovgen", seed, 2 + n // 2, 6 + 2 * n, 3 + n, 3 + n, 5 + 2 * n)
    elif family == "satellite":
        command = binary("satgen", seed, 2 + n // 2, 3, 3 + n, 10 + 4 * n, 6 + 2 * n)
    elif family == "schedule":
        command = binary("schedule", "-p", 4 + 2 * n, "-s", 2, "-c", 4,
                         "-w", 3, "-o", 2, "-Q", 50, "-W", 30, "-E", 50,
                         "-R", 30, "-T", 50, "-Y", 30, "-r", seed)
    elif family == "snake":
        size = 5 + n
        command = py("generate.py", f"empty-{size}x{size}", 1, 3, "40%", seed, "pddl")
    elif family == "storage":
        crates = 4 + 2 * n
        problem_output = destination / "generated-problem.pddl"
        command = binary("storage", "-o", (crates + 3) // 4, "-c", crates,
                         "-n", 2, "-s", 2 * crates, "-d", 2, "-e", seed,
                         problem_output)
    elif family == "tetris":
        command = py("generator.py", 6 + 2 * n, 4, seed)
    elif family == "tpp":
        problem_output = destination / "generated-problem.pddl"
        command = binary("tpp", "-s", seed, "-m", 2 + n, "-p", 5 + 2 * n,
                         "-t", 2, "-d", 1, "-l", 2, problem_output)
    elif family == "transport":
        command = py("city-generator.py", 8 + 2 * n, 1000, 4, 50,
                     2 + n // 2, 5 + 2 * n, seed)
    elif family == "visitall":
        command = binary("grid", "-n", 5 + n, "-r", 0.5, "-u", 0, "-s", seed)
    elif family == "woodworking":
        command = py("create_woodworking_instance.py", 1.2, 3 + 2 * n, 1, seed)
    elif family == "zenotravel":
        command = binary("ztravel", seed, 4 + n, 2 + n // 2, 4 + 2 * n)
    else:
        raise ValueError(f"missing specification for {family}")
    return {"command": command, "domain": domain,
            "domain_output": domain_output, "problem_output": problem_output}


def generate_one(family: str, level: int, seed: int) -> tuple[bytes, bytes, list[str]]:
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="instance-", dir=TEMP_ROOT) as temporary:
        destination = Path(temporary)
        spec = specification(family, level, seed, destination)
        environment = dict(os.environ, PYTHONHASHSEED="0", PYTHONNOUSERSITE="1",
                           PYTHONDONTWRITEBYTECODE="1", LC_ALL="C", LANG="C")
        for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
            environment.pop(name, None)
        result = subprocess.run(spec["command"], cwd=destination, env=environment,
                                capture_output=True, timeout=180)
        if result.returncode:
            raise ValueError(f"{family} generator exit {result.returncode}: "
                             + (result.stderr + result.stdout)[-2000:].decode("utf-8", "replace"))
        domain = (spec["domain_output"] or spec["domain"]).read_bytes()
        problem = (spec["problem_output"].read_bytes()
                   if spec["problem_output"] else result.stdout)
        instance_fingerprint(problem)
        if re.search(rb"\(\s*define\s*\(\s*domain\s+", domain, re.I) is None:
            raise ValueError(f"{family} has no PDDL domain")
        command = [arg.replace(str(destination), "GENERATOR_TEMP")
                   .replace(str(KIT), "GENERATOR_KIT")
                   .replace(sys.executable, "PINNED_PYTHON") for arg in spec["command"]]
        return domain, problem, command


def attest_kit() -> dict:
    revision = JJ.resolve_pinned_commit(KIT, KIT_REVISION)
    entries = JJ.list_tree(KIT, revision)
    paths = [entry.path for entry in entries if entry.file_type == "file"]
    result = subprocess.run(
        [str(JJ.JJ_EXECUTABLE), "--no-pager", "--repository", str(KIT),
         "diff", "--from", revision, "--to", "@", "--summary", "--", *paths],
        cwd=KIT, capture_output=True, text=True,
    )
    if result.returncode:
        raise ValueError("cannot verify generator sources: " + result.stderr[-2000:])
    changed = result.stdout.strip()
    if changed:
        raise ValueError("generator sources differ from their pinned revision: " + changed)
    sources = {path: sha((KIT / path).read_bytes()) for path in paths}
    return {"url": KIT_URL, "revision": revision, "source_sha256": sources,
            "source_manifest_sha256": sha(canonical(sources)),
            "python_version": sys.version, "python_sha256": sha(Path(sys.executable).read_bytes()),
            "python_hash_seed": 0}


def build() -> None:
    attest_kit()
    for directory, target in BUILD_TARGETS.items():
        result = subprocess.run(["make", "-C", str(KIT / directory), target],
                                capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise ValueError(f"build failed for {directory}:\n{result.stdout}\n{result.stderr}")
        print(f"built {directory}", flush=True)


def pilot(output: Path) -> None:
    kit = attest_kit()
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for family in FAMILIES:
        if family not in ALL_PRIOR_FAMILIES:
            raise ValueError("a family is not represented in prior studies")
        for index, level in enumerate((0, 2, 4)):
            seed = seed_for("pilot", family, index)
            row = {"family": family, "role": "pilot", "index": index,
                   "level": level, "seed": seed}
            try:
                first = generate_one(family, level, seed)
                second = generate_one(family, level, seed)
                if first != second:
                    raise ValueError("same-seed generation is not byte-identical")
                domain, problem, command = first
                directory = output / family
                directory.mkdir(exist_ok=True)
                domain_name = f"p{index:02d}-domain.pddl"
                problem_name = f"p{index:02d}.pddl"
                for name, raw in ((domain_name, domain), (problem_name, problem)):
                    with (directory / name).open("xb") as stream:
                        stream.write(raw)
                row.update({"status": "generated", "command": command,
                            "domain_file": f"{family}/{domain_name}",
                            "problem_file": f"{family}/{problem_name}",
                            "domain_sha256": sha(domain), "problem_sha256": sha(problem),
                            "instance_fingerprint": instance_fingerprint(problem)})
                print(f"generated {family} level {level}", flush=True)
            except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                row.update({"status": "generation-error", "error": str(error)})
                print(f"generation error {family} level {level}: {error}", flush=True)
            rows.append(row)
    manifest = {"schema": SCHEMA, "role": "pilot", "kit": kit, "records": rows,
                "records_sha256": sha(canonical(rows)), "performance_observed": False}
    with (output / "manifest.json").open("xb") as stream:
        stream.write(canonical(manifest))
    print(f"Pilot generation: {sum(r['status'] == 'generated' for r in rows)}/{len(rows)}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("build")
    probe = subparsers.add_parser("pilot")
    probe.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "build":
        build()
    else:
        pilot(args.output.resolve())


if __name__ == "__main__":
    main()
