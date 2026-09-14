"""Keep the generated-instance result branch separate from unseen-family evidence."""

import copy
import unittest

import check_submission_ready as Submission
import render_terminal_incidence_results as R
import render_within_family_results as W
from test_render_terminal_incidence_results import fixture as legacy_fixture


def fixture(passed=True):
    prior = legacy_fixture(a_pass=passed, direct_pass=False if passed else None,
                           b_pass=False if passed else None)
    a = prior["confirmation_a"]
    a.pop("all_prior")
    return {"design": "within-family-v1", "a_pass": passed, "confirmation_a": a,
            "source": {"families": [f"synthetic-{i}" for i in range(30)], "tasks": 650,
                       "candidate_status_counts": {"supported": 800}, "freeze": {}}}


class WithinRendererTests(unittest.TestCase):
    def test_pass_and_failure_have_no_invented_selector_results(self):
        for passed in (True, False):
            evidence = fixture(passed)
            outcome = R.classify(evidence)
            self.assertEqual(outcome.a_pass, passed)
            self.assertIsNone(outcome.direct_pass)
            self.assertIsNone(outcome.b_pass)
            rendered = R.render(evidence)
            self.assertEqual(rendered, W.render(evidence))
            self.assertIn("not unseen families", rendered)
            self.assertIn("remain untested", rendered)
            self.assertNotIn("all-prior-unrepresented stratum used", rendered)
            self.assertNotIn("improves complete symbolic search", rendered)
            title = R._title(outcome)
            Submission._validate_terminal_incidence_integration(
                f"\\title{{{title}}}", f"\\title{{{title}: Supplementary Material}}", rendered, evidence)
            with self.assertRaises(Submission.SubmissionReadinessError):
                Submission._validate_terminal_incidence_integration(
                    f"\\title{{{title}}}", f"\\title{{{title}: Supplementary Material}}",
                    rendered + "% altered\n", evidence)

    def test_claim_flip_and_unseen_stratum_are_rejected(self):
        evidence = fixture()
        changed = copy.deepcopy(evidence)
        changed["a_pass"] = False
        with self.assertRaises(R.RenderError):
            W.render(changed)
        changed = copy.deepcopy(evidence)
        changed["confirmation_a"]["all_prior"] = {}
        with self.assertRaises(R.RenderError):
            W.render(changed)
        changed = copy.deepcopy(evidence)
        changed["confirmation_b"] = {"pass": True}
        with self.assertRaises(R.RenderError):
            W.render(changed)

    def test_every_baseline_and_gate_is_still_required(self):
        for name in R.BASELINES:
            changed = fixture()
            changed["confirmation_a"]["baselines"][name]["bootstrap_lower"] = {"numerator": 0, "denominator": 1}
            with self.assertRaises(R.RenderError):
                W.render(changed)
        for field, value in (("comparison_tasks", 299), ("comparison_families", 24),
                             ("target_strict_pairs", 599)):
            changed = fixture()
            changed["confirmation_a"][field] = value
            with self.assertRaises(R.RenderError):
                W.render(changed)

    def test_non_numeric_source_text_cannot_enter_tex(self):
        changed = fixture()
        changed["source"]["candidate_status_counts"]["supported"] = "\\input{elsewhere}"
        with self.assertRaises(R.RenderError):
            W.render(changed)


if __name__ == "__main__":
    unittest.main()
