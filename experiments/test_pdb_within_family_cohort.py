"""Outcome-independent allocation, disjointness and hourly accounting tests."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import pdb_within_family_cohort as C
import pdb_within_family_monitor as M


class CohortTests(unittest.TestCase):
    def test_only_diagnosed_technical_pilot_rejections_are_recognized(self):
        result = {"status": "input-error", "returncode": 31,
                  "id": ["translator", "maintenance", "p00.pddl"],
                  "stdout": {"tail": "Parsing...\n\nFound the following duplicate objects: fra\n"}}
        self.assertTrue(C.diagnosed_pilot_input_rejection(result))
        for changed in (dict(result, returncode=-9), dict(result, status="infrastructure-error"),
                        dict(result, id=["translator", "blocks", "p00.pddl"]),
                        dict(result, stdout={"tail": "arbitrary parser error"})):
            self.assertFalse(C.diagnosed_pilot_input_rejection(changed))

    def test_balance_and_finite_reserves(self):
        for count in (19, 25, 30):
            families = C.G.FAMILIES[:count]
            allocations = C.allocations(families)
            specs = C.candidate_specs(families)
            self.assertEqual(len(specs), 650 + 5 * count)
            identities = {(r["role"], r["family"], r["index"]) for r in specs}
            self.assertEqual(len(identities), len(specs))
            for role, total in C.TARGETS.items():
                values = list(allocations[role].values())
                self.assertEqual(sum(values), total)
                self.assertLessEqual(max(values) - min(values), 1)
                for family in families:
                    rows = [r for r in specs if r["role"] == role and r["family"] == family]
                    self.assertEqual(sum(not r["reserve"] for r in rows), allocations[role][family])
                    self.assertEqual(sum(r["reserve"] for r in rows), 5)
                    self.assertTrue(all(r["index"] % 5 == r["level"] for r in rows))

    def test_invalid_family_sets(self):
        for families in ([], ["new"], ["blocks", "blocks"]):
            with self.assertRaises(ValueError):
                C.allocations(families)

    def test_structural_reserve_preserves_family_and_size(self):
        families = list(C.G.FAMILIES)
        rows = [dict(r, problem_file=f"{r['family']}/{r['role']}-{r['index']:03d}.pddl")
                for r in C.candidate_specs(families)]
        manifest = {"families": families, "records": rows}
        results = {("translator", r["family"], Path(r["problem_file"]).name):
                   {"status": "supported", "sas_sha256": "a" * 64} for r in rows}
        first = rows[0]
        identity = ("translator", first["family"], Path(first["problem_file"]).name)
        results[identity]["status"] = "unsupported"
        selected = C.select_tasks(manifest, results)
        self.assertEqual(len(selected["a"]), 650)
        self.assertEqual(set(selected), {"a"})
        reserves = [r for role in selected.values() for r in role if r["reserve"]]
        self.assertEqual(len(reserves), 1)
        self.assertEqual((reserves[0]["family"], reserves[0]["level"]),
                         (first["family"], first["level"]))
        extra = reserves[0]
        results[("translator", extra["family"], extra["problem"])]["status"] = "unsupported"
        selected = C.select_tasks(manifest, results)
        self.assertEqual(len(selected["a"]), 650)
        counts = C.level_allocations(manifest, results)["a"][first["family"]]
        self.assertEqual(list(counts.values()), [4, 5, 5, 4, 4])
        remaining = next(row for row in selected["a"]
                         if row["family"] == first["family"] and row["level"] == first["level"])
        results[("translator", remaining["family"], remaining["problem"])]["status"] = "unsupported"
        with self.assertRaisesRegex(ValueError, "finite structural pool insufficient"):
            C.select_tasks(manifest, results)

    def test_mystery_source_only_remainder_reallocation(self):
        families = [family for family in C.G.FAMILIES if family not in {"cavediving", "maintenance"}]
        rows = [dict(r, problem_file=f"{r['family']}/{r['role']}-{r['index']:03d}.pddl")
                for r in C.candidate_specs(families)]
        manifest = {"families": families, "records": rows}
        results = {("translator", r["family"], Path(r["problem_file"]).name):
                   {"status": "supported", "sas_sha256": "a" * 64} for r in rows}
        original = C.level_allocations(manifest, results)
        self.assertEqual(list(original["a"]["mystery"].values()), [5, 5, 5, 4, 4])
        for problem in ("a-005.pddl", "a-010.pddl"):
            results["translator", "mystery", problem]["status"] = "unsupported"
        amended = C.level_allocations(manifest, results)
        self.assertEqual(list(amended["a"]["mystery"].values()), [4, 5, 5, 5, 4])
        self.assertEqual([family for family in families if original["a"][family] != amended["a"][family]],
                         ["mystery"])
        selected = C.select_tasks(manifest, results)
        self.assertEqual(len(selected["a"]), 650)
        self.assertEqual(sum(row["family"] == "mystery" for row in selected["a"]), 23)

    def test_remainder_reallocation_requires_enough_supported_levels(self):
        families = list(C.G.FAMILIES)
        rows = [dict(r, problem_file=f"{r['family']}/{r['role']}-{r['index']:03d}.pddl")
                for r in C.candidate_specs(families)]
        manifest = {"families": families, "records": rows}
        results = {("translator", r["family"], Path(r["problem_file"]).name):
                   {"status": "supported", "sas_sha256": "a" * 64} for r in rows}
        first = sorted(families)[0]
        for row in rows:
            if row["family"] == first and row["index"] // 5 >= 4:
                results["translator", first, Path(row["problem_file"]).name]["status"] = "unsupported"
        with self.assertRaisesRegex(ValueError, "balanced-extras"):
            C.select_tasks(manifest, results)

    def test_freeze_loader_recomputes_size_allocations(self):
        families = list(C.G.FAMILIES)
        rows = [dict(r, problem_file=f"{r['family']}/{r['role']}-{r['index']:03d}.pddl")
                for r in C.candidate_specs(families)]
        manifest = {"families": families, "records": rows}
        results = {("translator", r["family"], Path(r["problem_file"]).name):
                   {"status": "supported", "sas_sha256": "a" * 64,
                    "id": ["translator", r["family"], Path(r["problem_file"]).name]} for r in rows}
        with tempfile.TemporaryDirectory(dir=C.G.ROOT / "data") as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            manifest_path.write_bytes(C.G.canonical(manifest))
            freeze = {"schema": C.SCHEMA + "/freeze", "performance_observed": False,
                      "scope": "fresh-instances-within-previously-studied-families",
                      "targets": C.TARGETS, "families": families,
                      "analysis": C.analysis_settings(families),
                      "planner_revision": "8148f798f13059ee881ad2471bd20cdd61d2ec18",
                      "pool_directory": str(root), "pool_manifest_sha256": C.W.file_sha(manifest_path),
                      "tasks": C.select_tasks(manifest, results),
                      "level_allocation_rule": C.LEVEL_ALLOCATION_RULE,
                      "level_allocations": C.level_allocations(manifest, results)}
            for field in ("source_summary", "source_launch", "source_poll"):
                path = root / (field + ".json")
                path.write_bytes(C.G.canonical({"records": list(results.values())} if field == "source_summary" else {}))
                freeze[field] = str(path)
                freeze[field + "_sha256"] = C.W.file_sha(path)
            path = root / "freeze.json"
            path.write_bytes(C.G.canonical(freeze))
            self.assertEqual(C.load_freeze(path, verify_code=False), freeze)
            freeze["level_allocations"]["a"][families[0]]["0"] += 1
            path.write_bytes(C.G.canonical(freeze))
            with self.assertRaisesRegex(ValueError, "size-level allocation changed"):
                C.load_freeze(path, verify_code=False)
            freeze["level_allocation_rule"] = "changed-rule"
            path.write_bytes(C.G.canonical(freeze))
            with self.assertRaisesRegex(ValueError, "fresh-instance freeze changed"):
                C.load_freeze(path, verify_code=False)

    def test_hourly_guard_makes_no_queries(self):
        with tempfile.TemporaryDirectory(dir=C.G.ROOT / "data") as directory:
            path = Path(directory) / "launch.json"
            path.write_text(json.dumps({"jobs": [{"accepted_utc": datetime.now(timezone.utc).isoformat()}]}))
            with mock.patch.object(M.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "hourly polling"):
                    M.poll(path)
            run.assert_not_called()

    def test_accounting_requires_exact_array_and_resources(self):
        launch = {"jobs": [{"job_id": "100", "array_elements": 2,
                            "script": "#SBATCH --job-name=test\n#SBATCH --time=00:35:00\n"}]}
        lines = [f"100_{i}|test|COMPLETED|0:0|fat|naiss2025-5-561-cpu|normal|9|3072Mc|00:35:00|n1|7"
                 for i in (1, 2)]
        raw = "\n".join(lines)
        good = M.check_accounting(launch, raw)
        self.assertTrue(good["all_completed_successfully"])
        self.assertTrue(good["resources_match"])
        for equivalent in ("3Gc", "27G", "27Gn", "27648M", "27648Mn"):
            self.assertTrue(M.check_accounting(launch, raw.replace("3072Mc", equivalent))["resources_match"])
        for different in ("26G", "28G", "27647M", "3G", "27Gc"):
            self.assertFalse(M.check_accounting(launch, raw.replace("3072Mc", different))["resources_match"])
        self.assertFalse(M.check_accounting(launch, lines[0])["all_completed_successfully"])
        self.assertFalse(M.check_accounting(launch, raw.replace("|9|", "|1|"))["resources_match"])
        self.assertFalse(M.check_accounting(launch, raw.replace("COMPLETED", "FAILED"))["all_completed_successfully"])
        for changed in (raw + "\n" + lines[0], raw.replace("100_2", "100_3")):
            with self.assertRaises(ValueError):
                M.check_accounting(launch, changed)

    def test_parsing_recovery_cannot_adopt_failed_or_active_translations(self):
        jobs = []
        lines = []
        for number, suffix, count, state in ((100, "01-build", 1, "COMPLETED"),
                                              (200, "02-start", 2, "COMPLETED"),
                                              (300, "03-parse", 1, "FAILED")):
            name = "source-" + suffix
            jobs.append({"job_id": str(number), "array_elements": count, "job_file": name,
                         "script": f"#SBATCH --job-name={name}\n#SBATCH --time=00:35:00\n"})
            for index in range(1, count + 1):
                code = "1:0" if state == "FAILED" else "0:0"
                lines.append(f"{number}_{index}|{name}|{state}|{code}|fat|naiss2025-5-561-cpu|normal|9|3072Mc|00:35:00|n1|7")
        raw = "\n".join(lines)
        poll = {"queries": {"accounting": {"returncode": 0, "stdout": raw}}}
        result = C.require_translation_jobs_complete({"jobs": jobs}, poll)
        self.assertFalse(result["all_completed_successfully"])
        for changed in (raw.replace("200_1|source-02-start|COMPLETED|0:0", "200_1|source-02-start|FAILED|1:0"),
                        raw.replace("300_1|source-03-parse|FAILED", "300_1|source-03-parse|RUNNING")):
            with self.assertRaises(ValueError):
                C.require_translation_jobs_complete({"jobs": jobs}, {"queries": {
                    "accounting": {"returncode": 0, "stdout": changed}}})


if __name__ == "__main__":
    unittest.main()
