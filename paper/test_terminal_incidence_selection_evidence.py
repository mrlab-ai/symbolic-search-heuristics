"""Exercise report mappings against the actual analyzers on synthetic cells."""

from __future__ import annotations

import copy
import unittest
from collections import Counter
from unittest import mock

import render_terminal_incidence_results as R
import terminal_incidence_evidence as E
import terminal_incidence_selection_evidence as S


class SelectionProjectionTests(unittest.TestCase):
    def test_actual_direct_analyzer_mapping_preserves_gate_and_mechanism(self):
        E._imports()
        import test_pdb_terminal_metric_choice_analyzer as F
        for different in (0, 100):
            result = F.AnalyzerTest().analyze(F.fake_records(differing_tasks=different))
            normalized = S.normalize_direct(result)
            R._validate_direct(normalized, {
                "b_tasks": 300, "b_families": result["primary_i_vs_mj"]["families"],
            })
            self.assertIs(R._direct_gate(normalized), result["pass"])
            self.assertEqual(normalized["differing_winners"]["tasks"], different)
            self.assertEqual(normalized["mechanism"]["same_candidate_tasks"], 300 - different)

    def test_actual_b_analyzer_mapping_accounts_for_every_configuration(self):
        E._imports()
        import test_pdb_terminal_incidence_confirmation_b_analysis as F
        tasks = [(f"synthetic-{index}", "p.pddl") for index in range(300)]
        sources = {task: {"family": f"family-{index % 30}"}
                   for index, task in enumerate(tasks)}
        matrix = F._matrix(tasks, matched=1000)
        accounting = [{
            "algorithm": label, "domain": task[0], "problem": task[1],
            "family": sources[task]["family"], "coverage": cell["record"]["coverage"],
            "par2": F.A._fraction_record(cell["par2"]),
        } for (label, task), cell in matrix.items()]
        with mock.patch.object(F.A, "validate_matrix", return_value=(
            matrix, tasks, sources, Counter(), accounting,
        )), mock.patch.object(F.P, "BOOTSTRAP_REPLICATES", 100):
            result = F.A.analyze_records([])
        normalized = S.normalize_b(result)
        R._validate_b(normalized, {"b_tasks": 300, "b_families": 30})
        self.assertIs(R._b_gate(normalized), result["gates"]["pass"])
        self.assertEqual(normalized["configurations"]["incidence_guided"]["coverage"], 300)
        self.assertEqual(normalized["configurations"]["cap_aware_k32"]["coverage"], 0)
        self.assertEqual(normalized["complete_pairs"], 300)
        changed = copy.deepcopy(result)
        changed["matrix"]["accounting_rows"].pop()
        with self.assertRaisesRegex(E.EvidenceError, "incomplete"):
            S.normalize_b(changed)
        changed = copy.deepcopy(result)
        changed["matrix"]["accounting_rows"].append(accounting[0])
        with self.assertRaisesRegex(E.EvidenceError, "duplicate"):
            S.normalize_b(changed)


if __name__ == "__main__":
    unittest.main()
