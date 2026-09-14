#!/usr/bin/env python3
"""Lab experiment: four frozen PDBs on 650 fresh within-family instances."""

import importlib.metadata
import json
import os
from pathlib import Path
import sys

from downward.experiment import FastDownwardAlgorithm, FastDownwardExperiment, FastDownwardRun
from downward.reports.absolute import AbsoluteReport
from downward.suites import Task
from lab.parser import Parser

import exp_pdb_within_family_source_pilot_v1 as Source
import jj_cached_revision as JJ
import pdb_fixed_pattern_parser as PatternParser
import pdb_profile_comparison_parser as ProfileParser
import pdb_terminal_incidence_confirmation_a_protocol as Legacy
import pdb_within_family_cohort as C
from pdb_within_family_parse_context import initialize_static
import pdb_within_family_run_guard as Guard
import wbh_parser


ROOT = C.G.ROOT
OUTPUT = ROOT / "data/exp_pdb_within_family_a_v1"
DRIVER_OPTIONS = ["--overall-time-limit", "1800s", "--overall-memory-limit", "24576M",
                  "--build", "release_no_lp"]
CONFIGS = Legacy.CONFIGS


def planner_files(cache):
    paths = {cache / "fast-downward.py", cache / "builds/release_no_lp/bin/downward",
             cache / "builds/release_no_lp/bin/preprocess"}
    for directory in ("driver", "src/translate", "builds/release_no_lp/bin/translate"):
        paths.update((cache / directory).rglob("*.py"))
    original = {path.relative_to(cache / "src/translate").as_posix(): Guard.sha(path)
                for path in (cache / "src/translate").rglob("*.py")}
    built = {path.relative_to(cache / "builds/release_no_lp/bin/translate").as_posix(): Guard.sha(path)
             for path in (cache / "builds/release_no_lp/bin/translate").rglob("*.py")}
    if built != original:
        raise ValueError("built translator differs from the source-screening translator")
    return {path.relative_to(cache).as_posix(): Guard.sha(path) for path in sorted(paths)}


def parse_execution(content, props):
    record = json.loads(content)
    expected = {"schema": Guard.SCHEMA, "id": props["id"],
                "config_sha256": props["execution_config_sha256"],
                "freeze_sha256": props["within_family_freeze_sha256"],
                "inputs_and_planner_verified_before_and_after": True, "wall_timeout": False,
                "returncode": props.get("planner_exit_code")}
    for field, value in expected.items():
        if record.get(field) != value or type(record.get(field)) is not type(value):
            raise ValueError(f"scientific execution guard rejected {field}: {record.get(field)!r} != {value!r}")
    props["execution_evidence"] = record


class FreshExperiment(FastDownwardExperiment):
    def __init__(self, freeze, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.freeze = freeze
        self.freeze_sha = Guard.sha(C.FREEZE)
        self.cached = JJ.JjCachedFastDownwardRevision(Source.CACHE.parent, ROOT.parent,
                                                     freeze["planner_revision"], ["release_no_lp"])
        self.planner_attestation = self.cached.attest()
        self.planner_manifest = planner_files(self.cached.path)
        self.set_property("planner_attestation", self.planner_attestation)
        self.set_property("scientific_code_sha256", freeze["code_sha256"])
        self.add_resource("guard", ROOT / "pdb_within_family_run_guard.py")
        self.add_new_file("freeze", "cohort-freeze.json", C.G.canonical(freeze).decode("ascii"))
        for label, search in CONFIGS:
            self._algorithms[label] = FastDownwardAlgorithm(label, self.cached, DRIVER_OPTIONS,
                                                            ["--search", search])

    def _get_tasks(self):
        pool = Path(self.freeze["pool_directory"])
        return [Task(row["domain"], row["problem"], pool / row["problem_file"],
                     domain_file=pool / row["domain_file"], properties={
                         "domain": row["domain"], "problem": row["problem"], "family": row["family"],
                         "domain_source_path": row["domain_file"], "problem_source_path": row["problem_file"],
                         "domain_source_sha256": row["domain_sha256"],
                         "problem_source_sha256": row["problem_sha256"],
                         "source_sas_sha256": row["sas_sha256"],
                         "source_result_sha256": row["source_result_sha256"],
                     }) for row in self.freeze["tasks"]["a"]]

    def _add_runs(self):
        for index, task in enumerate(self._get_tasks()):
            labels = [label for label, _ in CONFIGS]
            rotation = index % len(labels)
            # Adjacent task blocks; cyclic order avoids always running one PDB first.
            for label in labels[rotation:] + labels[:rotation]:
                run = FastDownwardRun(self, self._algorithms[label], task)
                for resource in run.resources:
                    resource.symlink = False
                config = {"id": [label, task.domain, task.problem], "freeze_sha256": self.freeze_sha,
                          "driver_options": DRIVER_OPTIONS, "search": dict(CONFIGS)[label],
                          "planner_files_sha256": self.planner_manifest,
                          "domain_sha256": task.properties["domain_source_sha256"],
                          "problem_sha256": task.properties["problem_source_sha256"],
                          "source_sas_sha256": task.properties["source_sas_sha256"],
                          "source_result_sha256": task.properties["source_result_sha256"],
                          "python_sha256": Guard.sha(sys.executable),
                          "guard_sha256": Guard.sha(ROOT / "pdb_within_family_run_guard.py")}
                run.add_new_file("execution_config", "execution-config.json", C.G.canonical(config).decode("ascii"))
                command, options = run.commands["planner"]
                run.commands["planner"] = (
                    [sys.executable, "-B", "{guard}", "--config", "{execution_config}", "--", *command],
                    dict(options, time_limit=1900, wall_time_limit=2000, memory_limit=26000),
                )
                run.set_property("within_family_freeze_sha256", self.freeze_sha)
                run.set_property("execution_config_sha256", C.G.sha(C.G.canonical(config)))
                run.set_property("planner_revision", self.freeze["planner_revision"])
                run.set_property("planner_binary_sha256", self.planner_attestation["downward_sha256"])
                run.set_property("preprocess_binary_sha256", self.planner_attestation["preprocess_sha256"])
                run.set_property("planner_time_limit", 1800)
                run.set_property("planner_memory_limit", 24576)
                run.set_property("analysis_horizon", 16)
                self.add_run(run)


def add_parsers(exp):
    exp.add_parser(exp.EXITCODE_PARSER)
    exp.add_parser(exp.TRANSLATOR_PARSER)
    exp.add_parser(exp.SINGLE_SEARCH_PARSER)
    context = Parser()
    context.add_function(initialize_static, file="run.log")
    exp.add_parser(context)
    exp.add_parser(wbh_parser.get_parser())
    exp.add_parser(ProfileParser.get_parser())
    exp.add_parser(PatternParser.get_parser())
    execution = Parser()
    execution.add_function(parse_execution, file="execution-evidence.json")
    exp.add_parser(execution)
    exp.add_parser(exp.PLANNER_PARSER)


def make_experiment():
    import pdb_within_family_a_analysis as Analysis

    freeze = C.load_freeze()
    for line in (ROOT / "requirements-pdb-terminal-incidence-shadow.txt").read_text().splitlines():
        name, version = line.split("==")
        if importlib.metadata.version(name) != version:
            raise ValueError(f"Python dependency changed: {name}")
    environment = Source.RecordedEnvironment(
        partition="fat", qos="normal", cpus_per_task=9, memory_per_cpu="3G",
        time_limit_per_task="01:45:00", randomize_task_order=False,
        extra_options="#SBATCH --account=naiss2025-5-561-cpu\n#SBATCH --no-requeue",
        export=["PATH", "PYTHONNOUSERSITE=1", "PYTHONDONTWRITEBYTECODE=1", "PYTHONHASHSEED=0"],
        setup="unset PYTHONPATH PYTHONHOME VIRTUAL_ENV\nexport LC_ALL=C LANG=C",
    )
    exp = FreshExperiment(freeze, path=OUTPUT, environment=environment, revision_cache=Source.CACHE.parent)
    add_parsers(exp)
    exp.add_step("build", exp.build)
    exp.add_step("start", exp.start_runs)
    exp.add_step("parse", exp.parse)
    exp.add_fetcher(name="fetch")
    exp.add_report(AbsoluteReport(attributes=["error", "coverage", "total_time", "planner_time",
                                             "planner_memory", "construction_completed"]),
                   name="report", outfile="outcomes.html")
    # Analysis validates the complete raw matrix itself. Its result cannot
    # authorize selector runs before the subsequent hourly scheduler audit.
    exp.add_step("analyze", Analysis.run_twice, Path(str(OUTPUT) + "-eval/properties"))
    return exp


if __name__ == "__main__":
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(__doc__ + "\nSteps: build start parse fetch report analyze; --all runs the pipeline.")
        raise SystemExit(0)
    if not os.environ.get("SLURM_JOB_ID") and any(arg in {"--all", "build", "start", "1", "2"} for arg in sys.argv[1:]):
        for path in (OUTPUT, Path(str(OUTPUT) + "-eval"), Path(str(OUTPUT) + "-grid-steps")):
            if path.exists():
                raise SystemExit(f"refusing to overwrite existing campaign: {path}")
    make_experiment().run_steps()
