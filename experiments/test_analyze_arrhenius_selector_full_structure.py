import copy
import io
import json
import math
import unittest
from collections import Counter
from contextlib import redirect_stdout
from unittest import mock

import experiments.analyze_arrhenius_selector_full_structure as structure


TASKS = [("domain", "p{:02d}.pddl".format(index)) for index in range(6)]
SELECTOR_8 = "pdb_selector_k8"
SELECTOR_16 = "pdb_selector_k16"
CONFIGS = (
    (structure.full.BLIND, "blind-search"),
    (SELECTOR_8, "selector-8-search"),
    (SELECTOR_16, "selector-16-search"),
    (structure.full.CEGAR, "cegar-search"),
    (structure.full.MS_CAP32_BUILD60, "ms-build60-search"),
)


def _base_record(label, task, index):
    return {
        "algorithm": label,
        "domain": task[0],
        "problem": task[1],
        "planner_exit_code": 0,
        "wbh_schema_version": 2,
        "piece_metrics_certified": True,
        "metrics_validation_error": None,
        "raw_metrics_complete": True,
        "partition_ratio_max": float((1, 2, 2, 4, 5, 6)[index]),
        "partition_ratio_geomean": float((0.5, 1.5, 2, 3, 4, 5)[index]),
    }


def _set_tuple(record, values, completed=True):
    width, add_nodes, num_values, num_terminals, upper = values
    record.update(
        {
            "cofactor_width": width,
            "add_nodes": add_nodes,
            "num_values": num_values,
            "num_terminals": num_terminals,
            "width_upper_bound": upper,
        }
    )
    if completed:
        record["construction_completed"] = True


def _selector_candidates(budget):
    make = structure.full.heldout.pilot_analyzer._synthetic_selector_candidate
    return [
        make(["empty"], [], 1, budget, initial_h=0, width=1, upper=1),
        make(
            ["bdd_prefix", "goal_prefix", "goal_fill"],
            [0],
            2,
            budget,
            initial_h=5,
            width=4,
            upper=7,
        ),
        make(["cegar"], [1], 100001, budget),
    ]


def _attach_certified_pool(record, budget):
    candidates = _selector_candidates(budget)
    record.update(
        {
            "pdb_selector_trace_complete": True,
            "pdb_selector_trace_certified": True,
            "pdb_selector_validation_error": None,
            "pdb_selector_candidates": candidates,
            "pdb_selector_pool_sha256": (
                structure.full.heldout.common.pdb_selector_pool_sha256(candidates)
            ),
        }
    )


def _make_fixture():
    contract = {"configs": list(CONFIGS)}
    tuples = (
        (2, 2, 1, 2, 4),
        (3, 3, 2, 2, 5),
        (3, 4, 2, 3, 7),
        (5, 5, 3, 3, 8),
        (6, 6, 3, 4, 10),
        (7, 7, 4, 4, 11),
    )
    matrix = {}
    for label, _search in CONFIGS:
        for index, task in enumerate(TASKS):
            record = _base_record(label, task, index)
            if label == structure.full.BLIND:
                record.pop("partition_ratio_max")
                record.pop("partition_ratio_geomean")
            elif label in (SELECTOR_8, SELECTOR_16):
                budget = 8 if label == SELECTOR_8 else 16
                if index <= 2:
                    _attach_certified_pool(record, budget)
                if index <= 1:
                    _set_tuple(record, tuples[index])
                elif index == 2:
                    record["cofactor_width"] = tuples[index][0]
                    record["planner_exit_code"] = 23
                    record["raw_metrics_complete"] = False
                    record.pop("partition_ratio_max")
                    record.pop("partition_ratio_geomean")
                elif index == 3:
                    record.update(
                        {
                            "planner_exit_code": 23,
                            "raw_metrics_complete": False,
                            "pdb_selector_trace_complete": False,
                            "pdb_selector_trace_certified": False,
                            "pdb_selector_validation_error": "incomplete",
                            "pdb_selector_candidates": _selector_candidates(budget)[:1],
                            "pdb_selector_pool_sha256": None,
                        }
                    )
                    record.pop("partition_ratio_max")
                    record.pop("partition_ratio_geomean")
                else:
                    record.update(
                        {
                            "planner_exit_code": 21,
                            "wbh_schema_version": 1,
                            "piece_metrics_certified": False,
                            "raw_metrics_complete": False,
                        }
                    )
                    record.pop("partition_ratio_max")
                    record.pop("partition_ratio_geomean")
            elif label == structure.full.CEGAR:
                if index < 5:
                    _set_tuple(record, tuples[index])
                if index == 2:
                    # Complete WBH log, but a resource terminal outcome.
                    record["planner_exit_code"] = 23
                elif index == 3:
                    record["planner_exit_code"] = 23
                    record["raw_metrics_complete"] = False
                elif index == 4:
                    record.pop("construction_completed")
                    record["planner_exit_code"] = 23
                    record["raw_metrics_complete"] = False
                    record.pop("partition_ratio_max")
                    record.pop("partition_ratio_geomean")
                elif index == 5:
                    record.update(
                        {
                            "planner_exit_code": 21,
                            "wbh_schema_version": 1,
                            "piece_metrics_certified": False,
                            "raw_metrics_complete": False,
                        }
                    )
                    record.pop("partition_ratio_max")
                    record.pop("partition_ratio_geomean")
            else:
                if index < 5:
                    _set_tuple(record, tuples[index])
                else:
                    record["construction_completed"] = False
                    record.pop("partition_ratio_max")
                    record.pop("partition_ratio_geomean")
            matrix[(label, task)] = record
    return matrix, list(TASKS), contract


def _build(matrix=None, tasks=None, contract=None):
    if matrix is None:
        matrix, tasks, contract = _make_fixture()
    return structure.build_diagnostic(
        matrix,
        tasks,
        contract,
        "0123456789abcdef" * 4,
        "0123456789abcdef0123456789abcdef01234567",
        "abcdef0123456789" * 4,
    )


def _config(result, label):
    return next(item for item in result["configs"] if item["label"] == label)


class StructuralDiagnosticTest(unittest.TestCase):
    def test_boundary_and_noninferential_role_are_explicit(self):
        result = _build()
        self.assertEqual(result["schema"], structure.SCHEMA)
        self.assertEqual(result["decision_label"], structure.DECISION_LABEL)
        self.assertFalse(result["interpretation"]["theorem_validation"])
        self.assertEqual(result["interpretation"]["causal_claims"], "none")
        encoded = structure.full.canonical_json(result)
        self.assertNotIn("p_value", encoded)
        self.assertNotIn("confidence_interval", encoded)
        self.assertNotIn("blind_normalized_effort\":{", encoded)

    def test_direct_tuple_census_sources_and_exclusions(self):
        result = _build()
        blind = _config(result, structure.full.BLIND)["direct_W_A_V_T_U"]
        self.assertEqual((blind["eligible_cells"], blind["observed_cells"]), (0, 0))

        cegar = _config(result, structure.full.CEGAR)["direct_W_A_V_T_U"]
        self.assertEqual((cegar["eligible_cells"], cegar["observed_cells"]), (6, 5))
        self.assertEqual(
            cegar["observation_source_counts"],
            {
                "completed_construction": 4,
                "heuristic_event_only_resource_prefix": 1,
            },
        )
        self.assertEqual(cegar["unobserved_reason_counts"]["presearch_outcome"], 1)
        self.assertEqual(cegar["summaries"]["W"]["observed"], 5)
        self.assertEqual(cegar["summaries"]["U_over_W"]["observed"], 5)

        selector = _config(result, SELECTOR_8)["direct_W_A_V_T_U"]
        self.assertEqual(selector["observed_cells"], 2)
        self.assertEqual(
            selector["unobserved_reason_counts"][
                "selector_width_only_resource_prefix"
            ],
            1,
        )
        self.assertEqual(selector["unobserved_reason_counts"]["presearch_outcome"], 2)
        self.assertEqual(
            selector["unobserved_reason_counts"]["resource_before_direct_tuple"],
            1,
        )

        fallback = _config(
            result, structure.full.MS_CAP32_BUILD60
        )["direct_W_A_V_T_U"]
        self.assertEqual(
            fallback["unobserved_reason_counts"]["construction_fallback"], 1
        )

    def test_candidate_pool_deduplicates_configs_and_counts_sources(self):
        pool = _build()["selector_candidate_pool"]
        self.assertEqual(pool["certified_trace_cells"], 6)
        self.assertEqual(pool["observed_unique_task_pool_hashes"], 3)
        self.assertEqual(pool["repeated_certified_trace_cells_deduplicated"], 3)
        self.assertEqual(
            pool["deduplicated_candidate_counts"],
            {"materialized": 6, "total": 9, "unmaterialized": 3},
        )
        self.assertEqual(
            pool["represented_source_counts"],
            {"materialized": 12, "total": 15, "unmaterialized": 3},
        )
        cegar = next(
            item for item in pool["source_status_counts"] if item["source"] == "cegar"
        )
        self.assertEqual(cegar["unmaterialized_task_pools"], 3)
        self.assertEqual(pool["materialized_summaries"]["W"]["observed"], 6)

    def test_candidate_pool_accepts_canonical_json_key_order_only(self):
        matrix, tasks, contract = _make_fixture()
        for label in (SELECTOR_8, SELECTOR_16):
            for task in tasks[:3]:
                record = matrix[(label, task)]
                record["pdb_selector_candidates"] = json.loads(
                    json.dumps(record["pdb_selector_candidates"], sort_keys=True)
                )
        pool = _build(matrix, tasks, contract)["selector_candidate_pool"]
        self.assertEqual(pool["certified_trace_cells"], 6)

    def test_candidate_pool_rejects_changed_field_set_after_serialization(self):
        for mutation in ("missing", "extra"):
            with self.subTest(mutation=mutation):
                matrix, tasks, contract = _make_fixture()
                candidate = matrix[(SELECTOR_8, tasks[0])][
                    "pdb_selector_candidates"
                ][0]
                if mutation == "missing":
                    candidate.pop("rejection_reason")
                else:
                    candidate["unexpected"] = None
                with self.assertRaisesRegex(
                    structure.AnalysisError, "candidate field set changed"
                ):
                    _build(matrix, tasks, contract)

    def test_partition_strata_and_terminal_histograms(self):
        cegar = _config(_build(), structure.full.CEGAR)["partition_ratios"]
        complete = cegar["raw_complete_logs_not_necessarily_complete_searches"]
        prefix = cegar["certified_resource_prefixes"]
        self.assertEqual((complete["eligible_logs"], complete["logs_with_partition_ratios"]), (3, 3))
        self.assertEqual((prefix["eligible_logs"], prefix["logs_with_partition_ratios"]), (1, 1))
        self.assertEqual(
            complete["partition_ratio_census_unit"],
            "one-certified-log-with-partition-ratios",
        )
        self.assertEqual(
            sum(row["count"] for row in complete["partition_ratio_census"]),
            3,
        )
        self.assertEqual(
            sum(row["count"] for row in prefix["partition_ratio_census"]),
            1,
        )
        complete_outcomes = {item["code"]: item["count"] for item in complete["terminal_outcome_counts"]}
        self.assertEqual(complete_outcomes[23], 1)
        self.assertEqual(complete["paired_direct_tuple_and_ratio_cells"], 3)
        self.assertEqual(
            complete["paired_census_unit"],
            "one-raw-complete-cell-with-direct-tuple-and-partition-ratios",
        )
        census = complete["paired_W_U_partition_ratio_census"]
        self.assertEqual(sum(row["count"] for row in census), 3)
        self.assertEqual(
            census,
            sorted(
                census,
                key=lambda row: (
                    row["W"],
                    row["U"],
                    row["partition_ratio_max"],
                    row["partition_ratio_geomean"],
                ),
            ),
        )
        self.assertTrue(all("domain" not in row and "problem" not in row for row in census))
        projected = Counter()
        for row in census:
            projected[
                (row["partition_ratio_max"], row["partition_ratio_geomean"])
            ] += row["count"]
        ratio_census = {
            (row["partition_ratio_max"], row["partition_ratio_geomean"]): row[
                "count"
            ]
            for row in complete["partition_ratio_census"]
        }
        self.assertEqual(dict(projected), ratio_census)
        correlations = complete["cross_task_descriptive_confounded_correlations"]
        self.assertEqual(correlations["W_vs_partition_ratio_max"]["n"], 3)
        self.assertNotIn("cross_task_descriptive_confounded_correlations", prefix)

    def test_zero_ratio_is_observed_not_missing(self):
        matrix, tasks, contract = _make_fixture()
        record = matrix[(structure.full.CEGAR, tasks[0])]
        record["partition_ratio_max"] = 0
        record["partition_ratio_geomean"] = 0.0
        complete = _config(_build(matrix, tasks, contract), structure.full.CEGAR)[
            "partition_ratios"
        ]["raw_complete_logs_not_necessarily_complete_searches"]
        self.assertEqual(complete["logs_with_partition_ratios"], 3)
        self.assertEqual(complete["summaries"]["partition_ratio_max"]["minimum"], 0.0)

    def test_jointly_missing_ratios_mean_no_positive_layer_event(self):
        matrix, tasks, contract = _make_fixture()
        record = matrix[(structure.full.CEGAR, tasks[0])]
        record.pop("partition_ratio_max")
        record.pop("partition_ratio_geomean")
        complete = _config(_build(matrix, tasks, contract), structure.full.CEGAR)[
            "partition_ratios"
        ]["raw_complete_logs_not_necessarily_complete_searches"]
        self.assertEqual(complete["eligible_logs"], 3)
        self.assertEqual(complete["logs_with_partition_ratios"], 2)
        self.assertEqual(complete["logs_without_partition_ratios"], 1)

    def test_ratio_census_aggregates_across_distinct_direct_tuples(self):
        matrix, tasks, contract = _make_fixture()
        first = matrix[(structure.full.CEGAR, tasks[0])]
        second = matrix[(structure.full.CEGAR, tasks[1])]
        second["partition_ratio_max"] = first["partition_ratio_max"]
        second["partition_ratio_geomean"] = first["partition_ratio_geomean"]
        complete = _config(_build(matrix, tasks, contract), structure.full.CEGAR)[
            "partition_ratios"
        ]["raw_complete_logs_not_necessarily_complete_searches"]
        aggregate = next(
            row
            for row in complete["partition_ratio_census"]
            if row["partition_ratio_max"] == first["partition_ratio_max"]
            and row["partition_ratio_geomean"]
            == first["partition_ratio_geomean"]
        )
        self.assertEqual(aggregate["count"], 2)
        paired = [
            row
            for row in complete["paired_W_U_partition_ratio_census"]
            if row["partition_ratio_max"] == first["partition_ratio_max"]
            and row["partition_ratio_geomean"]
            == first["partition_ratio_geomean"]
        ]
        self.assertEqual(len(paired), 2)
        self.assertEqual(sum(row["count"] for row in paired), 2)

    def test_partial_ratio_pair_is_rejected(self):
        matrix, tasks, contract = _make_fixture()
        matrix[(structure.full.CEGAR, tasks[0])].pop("partition_ratio_geomean")
        with self.assertRaisesRegex(structure.AnalysisError, "jointly present"):
            _build(matrix, tasks, contract)

    def test_ratio_max_smaller_than_geomean_is_rejected(self):
        matrix, tasks, contract = _make_fixture()
        record = matrix[(structure.full.CEGAR, tasks[0])]
        record["partition_ratio_max"] = 0.25
        record["partition_ratio_geomean"] = 0.5
        with self.assertRaisesRegex(structure.AnalysisError, "must be >="):
            _build(matrix, tasks, contract)

    def test_nonfinite_negative_and_boolean_ratios_are_rejected(self):
        for value, fragment in (
            (float("inf"), "finite and nonnegative"),
            (-0.1, "finite and nonnegative"),
            (True, "exact int/float"),
        ):
            with self.subTest(value=value):
                matrix, tasks, contract = _make_fixture()
                matrix[(structure.full.CEGAR, tasks[0])]["partition_ratio_max"] = value
                with self.assertRaisesRegex(structure.AnalysisError, fragment):
                    _build(matrix, tasks, contract)

    def test_geomean_roundoff_is_accepted_but_material_inversion_is_rejected(self):
        matrix, tasks, contract = _make_fixture()
        record = matrix[(structure.full.CEGAR, tasks[0])]
        record["partition_ratio_max"] = 3.0
        record["partition_ratio_geomean"] = math.exp(math.log(3.0))
        _build(matrix, tasks, contract)

        matrix, tasks, contract = _make_fixture()
        record = matrix[(structure.full.CEGAR, tasks[0])]
        record["partition_ratio_max"] = 3.0
        record["partition_ratio_geomean"] = 3.001
        with self.assertRaisesRegex(structure.AnalysisError, "must be >="):
            _build(matrix, tasks, contract)

    def test_partial_and_tampered_direct_tuples_are_rejected(self):
        mutations = (
            ("num_terminals", None, "tuple is partial"),
            ("cofactor_width", 1, "W >= T"),
            ("add_nodes", -1, "A >= 0"),
            ("width_upper_bound", 99, "U = A"),
            ("num_values", 3, "W >= T"),
        )
        for field, value, fragment in mutations:
            with self.subTest(field=field):
                matrix, tasks, contract = _make_fixture()
                record = matrix[(structure.full.CEGAR, tasks[0])]
                if value is None:
                    record.pop(field)
                else:
                    record[field] = value
                with self.assertRaisesRegex(structure.AnalysisError, fragment):
                    _build(matrix, tasks, contract)

    def test_zero_width_and_noninteger_tuple_are_rejected(self):
        for field, value, fragment in (
            ("cofactor_width", 0, "W >= T"),
            ("add_nodes", 2.0, "exact integers"),
        ):
            matrix, tasks, contract = _make_fixture()
            matrix[(structure.full.CEGAR, tasks[0])][field] = value
            with self.assertRaisesRegex(structure.AnalysisError, fragment):
                _build(matrix, tasks, contract)

    def test_width_only_prefix_is_selector_resource_exception_only(self):
        matrix, tasks, contract = _make_fixture()
        record = matrix[(structure.full.CEGAR, tasks[0])]
        for field in structure.DIRECT_FIELDS[1:]:
            record.pop(field)
        record.pop("construction_completed")
        record["planner_exit_code"] = 23
        record["raw_metrics_complete"] = False
        with self.assertRaisesRegex(structure.AnalysisError, "tuple is partial"):
            _build(matrix, tasks, contract)

    def test_no_construction_resource_exceptions_require_incomplete_prefixes(self):
        matrix, tasks, contract = _make_fixture()
        full_tuple = matrix[(structure.full.CEGAR, tasks[4])]
        full_tuple["raw_metrics_complete"] = True
        with self.assertRaisesRegex(structure.AnalysisError, "no valid completed"):
            _build(matrix, tasks, contract)

        matrix, tasks, contract = _make_fixture()
        width_only = matrix[(SELECTOR_8, tasks[2])]
        width_only["raw_metrics_complete"] = True
        with self.assertRaisesRegex(
            structure.AnalysisError, "requires an incomplete certified resource prefix"
        ):
            _build(matrix, tasks, contract)

    def test_ratio_requires_certified_schema2_and_accepted_prefix(self):
        cases = (
            ({"piece_metrics_certified": False}, "certified piece metrics"),
            ({"metrics_validation_error": "bad"}, "metrics validation error"),
            ({"wbh_schema_version": 1}, "WBH schema 2"),
            (
                {"raw_metrics_complete": False, "planner_exit_code": 11},
                "neither raw-complete",
            ),
        )
        for changes, fragment in cases:
            with self.subTest(changes=changes):
                matrix, tasks, contract = _make_fixture()
                matrix[(structure.full.CEGAR, tasks[0])].update(changes)
                with self.assertRaisesRegex(structure.AnalysisError, fragment):
                    _build(matrix, tasks, contract)

    def test_partition_ratio_rejects_blind_and_heuristic_only_cells(self):
        matrix, tasks, contract = _make_fixture()
        blind = matrix[(structure.full.BLIND, tasks[0])]
        blind["partition_ratio_max"] = 1.0
        blind["partition_ratio_geomean"] = 1.0
        with self.assertRaisesRegex(
            structure.AnalysisError, "nonblind completed construction"
        ):
            _build(matrix, tasks, contract)

        matrix, tasks, contract = _make_fixture()
        prefix = matrix[(structure.full.CEGAR, tasks[4])]
        prefix["partition_ratio_max"] = 1.0
        prefix["partition_ratio_geomean"] = 1.0
        with self.assertRaisesRegex(
            structure.AnalysisError, "nonblind completed construction"
        ):
            _build(matrix, tasks, contract)

    def test_candidate_hash_and_materialization_tampering_are_rejected(self):
        matrix, tasks, contract = _make_fixture()
        matrix[(SELECTOR_8, tasks[0])]["pdb_selector_pool_sha256"] = "0" * 64
        with self.assertRaisesRegex(structure.AnalysisError, "pool hash disagrees"):
            _build(matrix, tasks, contract)

        matrix, tasks, contract = _make_fixture()
        candidate = matrix[(SELECTOR_8, tasks[0])]["pdb_selector_candidates"][-1]
        candidate["width_upper_bound"] = 1
        with self.assertRaisesRegex(structure.AnalysisError, "invalid selector candidate"):
            _build(matrix, tasks, contract)

    def test_same_task_multiple_pool_hashes_are_rejected(self):
        matrix, tasks, contract = _make_fixture()
        record = matrix[(SELECTOR_16, tasks[0])]
        record["pdb_selector_candidates"][1]["cofactor_width"] = 5
        record["pdb_selector_pool_sha256"] = (
            structure.full.heldout.common.pdb_selector_pool_sha256(
                record["pdb_selector_candidates"]
            )
        )
        with self.assertRaisesRegex(structure.AnalysisError, "multiple certified pool hashes"):
            _build(matrix, tasks, contract)

    def test_uncertified_selector_prefix_is_not_a_pool(self):
        pool = _build()["selector_candidate_pool"]
        self.assertEqual(pool["observed_tasks"], 3)
        self.assertEqual(pool["unobserved_tasks"], 3)

    def test_spearman_average_ties_zero_variance_and_small_n(self):
        perfect = structure.spearman_average_ties(
            [1, 2, 2, 4], [10, 20, 20, 40]
        )
        self.assertEqual(perfect, {"n": 4, "coefficient": 1.0, "null_reason": None})
        constant = structure.spearman_average_ties([1, 1, 1], [1, 2, 3])
        self.assertEqual(constant["n"], 3)
        self.assertIsNone(constant["coefficient"])
        self.assertEqual(constant["null_reason"], "zero-rank-variance")
        singleton = structure.spearman_average_ties([1], [2])
        self.assertEqual(
            singleton,
            {"n": 1, "coefficient": None, "null_reason": "fewer-than-two-pairs"},
        )

    def test_shuffled_matrix_is_byte_deterministic(self):
        matrix, tasks, contract = _make_fixture()
        first = _build(matrix, tasks, contract)
        shuffled = dict(reversed(list(matrix.items())))
        second = _build(shuffled, tasks, contract)
        self.assertEqual(
            structure.full.canonical_json(first), structure.full.canonical_json(second)
        )

    def test_matrix_identity_tampering_is_rejected(self):
        matrix, tasks, contract = _make_fixture()
        matrix[(structure.full.CEGAR, tasks[0])]["problem"] = "changed.pddl"
        with self.assertRaisesRegex(structure.AnalysisError, "task identity changed"):
            _build(matrix, tasks, contract)

    def test_ordinary_cli_uses_all_canonical_identity_gates(self):
        matrix, tasks, contract = _make_fixture()
        records = list(matrix.values())
        artifact_sha = "0123456789abcdef" * 4
        revision = "0123456789abcdef0123456789abcdef01234567"
        properties_sha = "abcdef0123456789" * 4
        with (
            mock.patch.object(
                structure.full,
                "load_selection_artifact",
                return_value=({"synthetic": True}, artifact_sha),
            ) as load_selection,
            mock.patch.object(
                structure.full, "require_reviewed_pins", return_value=revision
            ) as reviewed,
            mock.patch.object(
                structure.full, "validate_selection_artifact", return_value=contract
            ) as validate_selection,
            mock.patch.object(structure.full, "validate_runner_contract") as runner_gate,
            mock.patch.object(
                structure.full,
                "load_and_validate_tasks",
                return_value=(tasks, [], ["domain"]),
            ) as task_gate,
            mock.patch.object(structure.full, "load_properties", return_value=records) as load_props,
            mock.patch.object(structure.full, "validate_records", return_value=matrix) as record_gate,
            mock.patch.object(
                structure.full,
                "logical_properties_sha256",
                return_value=properties_sha,
            ) as properties_gate,
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    structure.main(["properties.json", "--selection", "selection.json"]),
                    0,
                )
        parsed = json.loads(output.getvalue())
        self.assertEqual(
            parsed["input_identity"]["properties_canonical_sha256"], properties_sha
        )
        load_selection.assert_called_once()
        reviewed.assert_called_once_with(artifact_sha)
        validate_selection.assert_called_once()
        runner_gate.assert_called_once_with(
            contract, expected_artifact_sha256=artifact_sha
        )
        task_gate.assert_called_once()
        load_props.assert_called_once()
        record_gate.assert_called_once_with(
            records, tasks, contract, artifact_sha, revision
        )
        properties_gate.assert_called_once_with(records)


if __name__ == "__main__":
    unittest.main()
