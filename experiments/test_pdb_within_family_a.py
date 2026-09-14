"""Exercise the real Lab/solver/parser path without observing cohort outcomes."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from lab.environments import LocalEnvironment

import exp_pdb_within_family_a_v1 as Runner
import pdb_within_family_a_analysis as A
import pdb_within_family_a_seal as Seal
import pdb_within_family_cohort as C
import pdb_within_family_run_guard as Guard
import pdb_within_family_source_worker as SourceWorker


class FreshPredictionTests(unittest.TestCase):
    def test_real_pipeline_and_analysis_reject_mismatched_evidence(self):
        with tempfile.TemporaryDirectory(prefix="within-a-test-", dir=C.G.ROOT / "data") as temporary:
            root = Path(temporary)
            pool = root / "inputs"
            pool.mkdir()
            (pool / "domain.pddl").write_text(
                "(define (domain d) (:requirements :strips) (:predicates (p) (q) (r)) "
                "(:action first :parameters () :precondition (p) :effect (and (not (p)) (q))) "
                "(:action second :parameters () :precondition (q) :effect (and (not (q)) (r))))")
            (pool / "problem.pddl").write_text(
                "(define (problem test) (:domain d) (:init (p)) (:goal (r)))")
            translator = Runner.Source.CACHE / "src/translate"
            source_config = {
                "id": ["translator", "blocks", "problem.pddl"], "planner_revision": Runner.Source.REVISION,
                "translator_sha256": {p.relative_to(translator).as_posix(): Guard.sha(p)
                                      for p in translator.rglob("*.py")},
                "worker_sha256": {name: Guard.sha(C.G.ROOT / name) for name in Runner.Source.WORKERS},
                "python_sha256": Guard.sha(sys.executable),
                "domain_sha256": Guard.sha(pool / "domain.pddl"),
                "problem_sha256": Guard.sha(pool / "problem.pddl"),
            }
            source_config_path = pool / "source-config.json"
            source_config_path.write_bytes(C.G.canonical(source_config))
            previous = Path.cwd()
            try:
                os.chdir(pool)
                self.assertEqual(SourceWorker.run(source_config_path, translator), 0)
            finally:
                os.chdir(previous)
            source = json.loads((pool / "source-result.json").read_bytes())
            self.assertEqual(source["status"], "supported")
            row = {"domain": "blocks", "family": "blocks", "problem": "problem.pddl",
                   "domain_file": "domain.pddl", "problem_file": "problem.pddl",
                   "domain_sha256": source_config["domain_sha256"],
                   "problem_sha256": source_config["problem_sha256"], "sas_sha256": source["sas_sha256"],
                   "source_result_sha256": C.G.sha(C.G.canonical(source))}
            freeze = {"pool_directory": str(pool), "planner_revision": Runner.Source.REVISION,
                      "families": ["blocks"], "tasks": {"a": [row]}, "code_sha256": {},
                      "code_commit": "0" * 40,
                      "scope": "synthetic-test-only", "analysis": C.analysis_settings(["blocks"])}
            freeze_path = root / "freeze.json"
            freeze_path.write_bytes(C.G.canonical(freeze))
            with mock.patch.object(C, "FREEZE", freeze_path):
                exp = Runner.FreshExperiment(freeze, path=root / "experiment",
                                             environment=LocalEnvironment(processes=1),
                                             revision_cache=Runner.Source.CACHE.parent)
                Runner.add_parsers(exp)
                # Share the already attested solver cache in this small smoke
                # test; production copies it. Inputs are still regular copies.
                exp._add_code = lambda: exp.add_resource("", exp.cached.path,
                    exp.cached.get_relative_exp_path().rstrip("/"), symlink=True)
                exp._cache_revisions = lambda: None  # Already attested above.
                exp.build()
            self.assertEqual(len(exp.runs), 4)
            for run in exp.runs:
                path = Path(run.path)
                with (path / "driver.log").open("wb") as stdout, (path / "driver.err").open("wb") as stderr:
                    result = subprocess.run([sys.executable, "-B", str(path / "run")], cwd=path,
                                            stdout=stdout, stderr=stderr, timeout=30)
                self.assertEqual(result.returncode, 0, (path / "driver.err").read_text())
                evidence_path = path / "execution-evidence.json"
                details = "\n".join((path / name).read_text()[-4000:] for name in ("driver.log", "run.err") if (path / name).exists())
                self.assertTrue(evidence_path.exists(), details)
                self.assertEqual(json.loads(evidence_path.read_bytes())["returncode"], 0, details)
            exp.parse()
            records = []
            for run in exp.runs:
                path = Path(run.path)
                record = json.loads((path / "static-properties").read_bytes())
                record.update(json.loads((path / "properties").read_bytes()))
                records.append(record)
            A.verify_run_evidence(records, freeze, root / "experiment")
            result = A.analyze_records(records, freeze, Guard.sha(freeze_path))
            self.assertEqual(result["matrix"]["cells"], 4)
            self.assertEqual(result["eligible_tasks"], 1)
            self.assertFalse(result["gates"]["pass"])
            self.assertTrue(result["scheduler_audit_required_before_selector_launch"])
            sys.path.insert(0, str(C.G.ROOT.parent / "paper"))
            import terminal_incidence_evidence as PaperEvidence
            normalized = PaperEvidence.normalize_a(result, include_prior=False)
            PaperEvidence.R._validate_a(normalized, {"a_tasks": 1, "a_families": 1}, include_prior=False)
            self.assertFalse(PaperEvidence.R._a_gate(normalized, include_prior=False))
            self.assertNotIn("all_prior", normalized)
            self.assertEqual(C.G.canonical(result), C.G.canonical(
                A.analyze_records(copy.deepcopy(records), freeze, Guard.sha(freeze_path))))
            properties = root / "experiment-eval/properties"
            properties.parent.mkdir()
            properties.write_bytes(C.G.canonical({str(i): row for i, row in enumerate(records)}))
            launch_path = root / "launch.json"
            poll_path = root / "poll.json"
            launch = {"experiment": str(root / "experiment"), "jobs": []}
            accounting = []
            for index, (step, elements) in enumerate((("build", 1), ("start", 2), ("parse", 1),
                                                       ("fetch", 1), ("report", 1), ("analyze", 1)), 1):
                name = f"synthetic-{index:02d}-{step}"
                launch["jobs"].append({"job_id": str(index), "job_file": str(root / name),
                                       "array_elements": elements,
                                       "script": f"#SBATCH --time=01:45:00\n#SBATCH --job-name={name}\n"})
                for element in range(1, elements + 1):
                    accounting.append(f"{index}_{element}|{name}|COMPLETED|0:0|fat|"
                                      "naiss2025-5-561-cpu|normal|9|3Gc|01:45:00|synthetic|1")
            launch_path.write_bytes(C.G.canonical(launch))
            poll = {"launch_sha256": Guard.sha(launch_path), "queries": {"accounting": {
                "returncode": 0, "stdout": "\n".join(accounting)}}}
            poll_path.write_bytes(C.G.canonical(poll))
            with mock.patch.object(C, "FREEZE", freeze_path), mock.patch.object(C, "load_freeze", return_value=freeze), \
                    mock.patch.object(C, "TARGETS", {"a": 1}), mock.patch.object(Runner, "OUTPUT", root / "experiment"):
                A.run_twice(properties, root / "analysis")
                sealed, _ = Seal.validate_completed(launch_path, poll_path, root / "analysis")
                self.assertFalse(sealed["selector_experiments_authorized"])
                self.assertEqual(sealed["scheduler_queries_made_by_seal"], 0)
                seal_path = root / "seal.json"
                seal_path.write_bytes(C.G.canonical(sealed))
                self.assertEqual(Seal.load_seal(seal_path)[0], sealed)
                poll["queries"]["accounting"]["stdout"] = "\n".join(accounting).replace("COMPLETED", "FAILED", 1)
                poll_path.write_bytes(C.G.canonical(poll))
                with self.assertRaisesRegex(ValueError, "not successfully complete"):
                    Seal.validate_completed(launch_path, poll_path, root / "analysis")
                with self.assertRaisesRegex(ValueError, "evidence changed"):
                    Seal.load_seal(seal_path)
            with self.assertRaisesRegex(ValueError, "incomplete"):
                A.analyze_records(records[:-1], freeze, Guard.sha(freeze_path))
            for field, value in (("component_options", ["--search", "sym_fw()"]),
                                 ("problem_source_sha256", "0" * 64),
                                 ("within_family_freeze_sha256", "0" * 64)):
                changed = copy.deepcopy(records)
                changed[0][field] = value
                with self.assertRaisesRegex(ValueError, "changed"):
                    A.analyze_records(changed, freeze, Guard.sha(freeze_path))
            changed = copy.deepcopy(records)
            changed[0]["execution_evidence"]["wall_timeout"] = True
            with self.assertRaisesRegex(ValueError, "execution guard"):
                A.analyze_records(changed, freeze, Guard.sha(freeze_path))


if __name__ == "__main__":
    unittest.main()
