#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import unittest
from types import SimpleNamespace
from unittest import mock

import pdb_terminal_metric_choice_calibration as Calibration
import pdb_terminal_metric_choice_protocol as P


SHA = "a" * 64


def _digest(label):
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def fake_tasks(start=0, count=P.COHORT_TASKS):
    tasks = []
    for index in range(start, start + count):
        directory = "domain-{:03d}".format(index // 10)
        problem = "p{:03d}.pddl".format(index)
        family = "family-{:02d}".format(index // 10)
        domain_file = directory + "/domain.pddl"
        problem_file = directory + "/" + problem
        task = {
            "candidate_index": index,
            "directory": directory,
            "family": family,
            "problem": problem,
            "domain_file": domain_file,
            "problem_file": problem_file,
            "domain_sha256": _digest(directory),
            "problem_sha256": _digest("problem-{}".format(index)),
            "canonical_path": problem_file,
            "is_shadow_family": family in P.V12_SHADOW_FAMILIES,
            "is_shadow_unrepresented": family not in P.V12_SHADOW_FAMILIES,
            "is_all_prior_represented": family in P.V12_ALL_PRIOR_FAMILIES,
            "is_all_prior_unrepresented": (
                family not in P.V12_ALL_PRIOR_FAMILIES
            ),
        }
        task["aliases"] = [{
            field: task[field] for field in P.V12_ALIAS_FIELDS
        }]
        tasks.append(task)
    return tasks


def _projection(role, tasks):
    indices = [task["candidate_index"] for task in tasks]
    return {
        "role": role,
        "records": tasks,
        "candidate_indices_sha256": _digest(
            P.canonical_json(indices).decode("ascii")
        ),
        "source_projection_sha256": _digest(
            P.canonical_json(tasks).decode("ascii")
        ),
    }


def _v12_bindings(confirmation, guided):
    code_manifest = _digest("code")
    translator = {
        "src/translate/module_{:02d}.py".format(index): _digest(
            "translator-{:02d}".format(index)
        )
        for index in range(P.V12_TRANSLATOR_FILE_COUNT)
    }
    full = {
        **translator, P.V12_CODE_MANIFEST_RELATIVE: code_manifest,
        "experiments/v12-full.py": _digest("full"),
    }
    preflight = {
        **translator, P.V12_CODE_MANIFEST_RELATIVE: code_manifest,
        "experiments/v12-preflight.py": _digest("preflight"),
    }
    combined = dict(sorted({**full, **preflight}.items()))
    outcomes = {
        "input-rejected": 689, "resource-excluded": 0, "success": 951,
    }
    support_status = {
        "indeterminate": 0, "supported": 950, "unsupported": 690,
    }
    support_exclusions = {
        reason: (
            689 if reason == "translation-input-rejected"
            else 1 if reason == "no-serialized-operators"
            else 0
        )
        for reason in P.V12_SUPPORT_EXCLUSION_REASONS
    }
    resource_counts = {"memory": 0, "time": 0}
    exclusions = {}
    values = {
        field: _digest(field) for field in P.V12_BINDING_FIELDS
        if field.endswith("_sha256") or field.endswith("_sha256_digest")
    }
    values.update({
        "schema": P.V12_ADAPTER_SCHEMA,
        "campaign": "v12-full-census",
        "benchmark_revision": "48d6a00d482de2384a9e751f9343df58bf5582be",
        "seal_repository_commit_id": "3" * 40,
        "preflight_campaign": "v12-preflight",
        "preflight_source_repository_commit_id": "1" * 40,
        "preflight_seal_repository_commit_id": "2" * 40,
        "preflight_full_launch_authorized": True,
        "code_manifest_sha256": code_manifest,
        "preflight_code_manifest_sha256": code_manifest,
        "translator_source_sha256": _digest(P.canonical_json([
            {"path": path, "sha256": translator[path]}
            for path in sorted(translator)
        ]).decode("ascii")),
        "inventory_families_count": 95,
        "translation_attempts_count": 1640,
        "all_records_count": 1640,
        "eligible_records_count": 950,
        "confirmation_a_count": 650,
        "guided_b_count": P.COHORT_TASKS,
        "outcome_counts": outcomes,
        "outcome_counts_sha256": _digest(
            P.canonical_json(outcomes).decode("ascii")
        ),
        "support_status_counts": support_status,
        "support_status_counts_sha256": _digest(
            P.canonical_json(support_status).decode("ascii")
        ),
        "support_exclusion_counts": support_exclusions,
        "support_exclusion_counts_sha256": _digest(
            P.canonical_json(support_exclusions).decode("ascii")
        ),
        "resource_exclusion_counts": resource_counts,
        "resource_exclusion_counts_sha256": _digest(
            P.canonical_json(resource_counts).decode("ascii")
        ),
        "resource_exclusions_by_family": exclusions,
        "resource_exclusions_by_family_sha256": _digest(
            P.canonical_json(exclusions).decode("ascii")
        ),
        "full_tracked_file_sha256": full,
        "full_tracked_file_sha256_digest": _digest(
            P.canonical_json(full).decode("ascii")
        ),
        "preflight_tracked_file_sha256": preflight,
        "preflight_tracked_file_sha256_digest": _digest(
            P.canonical_json(preflight).decode("ascii")
        ),
        "combined_tracked_file_sha256": combined,
        "combined_tracked_file_sha256_digest": _digest(
            P.canonical_json(combined).decode("ascii")
        ),
        "confirmation_a_candidate_indices_sha256": confirmation[
            "candidate_indices_sha256"
        ],
        "confirmation_a_source_projection_sha256": confirmation[
            "source_projection_sha256"
        ],
        "guided_b_candidate_indices_sha256": guided[
            "candidate_indices_sha256"
        ],
        "guided_b_source_projection_sha256": guided[
            "source_projection_sha256"
        ],
    })
    return values


def fake_snapshot():
    guided = _projection("guided-b", fake_tasks())
    confirmation = _projection("confirmation-a", fake_tasks(300, 650))
    bindings = _v12_bindings(confirmation, guided)
    planner = fake_planner()
    a_freeze_sha = _digest("a-freeze")
    authorization = {
        "guided_study_authorized": True,
        "receipt_sha256": _digest("a-receipt"),
        "first_output_sha256": _digest("a-output"),
        "second_output_sha256": _digest("a-output"),
        "input_properties_sha256": _digest("a-properties"),
        "fetch_receipt_sha256": _digest("a-fetch"),
        "execution_receipt_sha256": _digest("a-execution"),
        "hardware": {
            "hardware_attestation_schema": (
                "symbolic-search-heuristics/execution-hardware/v1"
            ),
            "hardware_attestation_files": P.BASE_A_CELL_COUNT,
            "hardware_records_sha256": _digest("hardware"),
            "processor_model_counts": {"Synthetic CPU": P.BASE_A_CELL_COUNT},
            "architecture_counts": {"x86_64": P.BASE_A_CELL_COUNT},
        },
        "receipt_schema": P.BASE_A_RECEIPT_SCHEMA,
        "analysis_protocol": P.BASE_A_ANALYSIS_PROTOCOL,
        "benchmark_revision": bindings["benchmark_revision"],
        "cost_attestation_sha256": bindings["attestation_sha256"],
        "source_audit_launch_receipt_sha256": bindings["launch_receipt_sha256"],
        "source_audit_execution_receipt_sha256": bindings[
            "execution_receipt_sha256"
        ],
        "receipt_path": P.BASE_A_RECEIPT_PATH.relative_to(P.REPO).as_posix(),
        "receipt_pin_path": P.BASE_A_RECEIPT_PIN_PATH.relative_to(
            P.REPO
        ).as_posix(),
        "first_output_path": P.BASE_A_FIRST_OUTPUT_PATH.relative_to(
            P.REPO
        ).as_posix(),
        "second_output_path": P.BASE_A_SECOND_OUTPUT_PATH.relative_to(
            P.REPO
        ).as_posix(),
        "confirmation_a_freeze_path": P.BASE_A_FREEZE_PATH.relative_to(
            P.REPO
        ).as_posix(),
        "confirmation_a_freeze_repository_revision": "4" * 40,
        "confirmation_a_cohort_manifest_sha256": confirmation[
            "source_projection_sha256"
        ],
        "source_audit_provenance": P._expected_v12_run_provenance(
            bindings, a_freeze_sha
        ),
        "planner_identity": P.planner_identity(planner),
    }
    return {
        "schema": P.BASE_SNAPSHOT_SCHEMA,
        "base_b_freeze_path": P.BASE_B_FREEZE_PATH.relative_to(P.REPO).as_posix(),
        "base_b_freeze_sha256": _digest("b-freeze"),
        "base_b_freeze_repository_revision": "5" * 40,
        "base_b_experiment_source_sha256": {
            relative: SHA for relative in P.BASE_B_EXPERIMENT_SOURCE_FILES
        },
        "base_b_planner": P.planner_identity(planner),
        "benchmark_revision": bindings["benchmark_revision"],
        "confirmation_a_authorization": authorization,
        "confirmation_a_freeze": {
            "path": P.BASE_A_FREEZE_PATH.relative_to(P.REPO).as_posix(),
            "sha256": a_freeze_sha,
            "repository_revision": "4" * 40,
        },
        "source_audit_v12": {
            "schema": P.V12_SOURCE_SCHEMA,
            "source_seal_revision": bindings["seal_repository_commit_id"],
            "bindings": bindings,
            "guided_b": guided,
        },
        "confirmation_a_cohort": confirmation,
    }


def rebind_v12_cohort(snapshot, role):
    if role == "guided-b":
        cohort = snapshot["source_audit_v12"]["guided_b"]
        binding_prefix = "guided_b"
    elif role == "confirmation-a":
        cohort = snapshot["confirmation_a_cohort"]
        binding_prefix = "confirmation_a"
    else:
        raise AssertionError("unknown test cohort role")
    cohort["source_projection_sha256"] = hashlib.sha256(
        P.canonical_json(cohort["records"])
    ).hexdigest()
    snapshot["source_audit_v12"]["bindings"][
        binding_prefix + "_source_projection_sha256"
    ] = cohort["source_projection_sha256"]
    if role == "confirmation-a":
        snapshot["confirmation_a_authorization"][
            "confirmation_a_cohort_manifest_sha256"
        ] = cohort["source_projection_sha256"]


def set_v12_task_family(task, family):
    task["family"] = family
    task["is_shadow_family"] = family in P.V12_SHADOW_FAMILIES
    task["is_shadow_unrepresented"] = family not in P.V12_SHADOW_FAMILIES
    task["is_all_prior_represented"] = family in P.V12_ALL_PRIOR_FAMILIES
    task["is_all_prior_unrepresented"] = (
        family not in P.V12_ALL_PRIOR_FAMILIES
    )
    for alias in task["aliases"]:
        alias["family"] = family


def set_v12_task_directory(task, directory):
    task["directory"] = directory
    task["domain_file"] = directory + "/domain.pddl"
    task["problem_file"] = directory + "/" + task["problem"]
    task["canonical_path"] = task["problem_file"]
    task["domain_sha256"] = _digest(directory)
    task["aliases"] = [{
        field: task[field] for field in P.V12_ALIAS_FIELDS
    }]


def fake_calibration(planner=None):
    rows = []
    for task_id, _ in P.CALIBRATION_TASK_SPECS:
        for mode in P.MODES:
            row = {"task_id": task_id, "mode": mode, "trace_status": "complete",
                   "probe_completed_layers": 16}
            for field in Calibration.EXPOSED_FIELDS:
                if field not in row:
                    if field.endswith("before_kb"):
                        row[field] = 100
                    elif field.endswith("after_kb"):
                        row[field] = 105
                    elif field.endswith("delta_kb"):
                        row[field] = 5
                    else:
                        row[field] = 0.1
            rows.append(row)
    return Calibration.build_receipt(rows, planner or fake_planner())


def fake_planner():
    return {
        "schema": P.PLANNER_MANIFEST_SCHEMA,
        "revision": P.REQUIRED_PLANNER_REVISION,
        "selector_base_revision": P.REQUIRED_SELECTOR_COMMIT,
        "cache_name": "dual-selector-ccc93bed",
        "downward_sha256": "1" * 64,
        "preprocess_sha256": "2" * 64,
        "tree_manifest_sha256": "3" * 64,
        "build_options": list(P.BUILD_OPTIONS),
        "driver_path": "fast-downward.py", "driver_sha256": "4" * 64,
        "downward_path": "builds/release_no_lp/bin/downward",
        "preprocess_path": "builds/release_no_lp/bin/preprocess",
        "option_matrix_sha256": P.option_matrix_digest(),
        "searches": [
            {"mode": mode, "search": P.SEARCHES[mode]} for mode in P.MODES
        ],
        "dual_trace_schema": P.DUAL_TRACE_SCHEMA,
    }


def fake_standalone(snapshot=None):
    snapshot = snapshot or fake_snapshot()
    pool = [
        {"pattern_index": 0, "sources": ["empty"], "pattern": [],
         "abstract_states": 1, "within_state_budget": True},
        {"pattern_index": 1, "sources": ["bdd_prefix"], "pattern": [0],
         "abstract_states": 2, "within_state_budget": True},
        {"pattern_index": 2, "sources": ["goal_prefix"], "pattern": [1],
         "abstract_states": 100001, "within_state_budget": False},
        {"pattern_index": 3, "sources": ["goal_fill"], "pattern": [2],
         "abstract_states": 100001, "within_state_budget": False},
        {"pattern_index": 4, "sources": ["cegar"], "pattern": [3],
         "abstract_states": 100001, "within_state_budget": False},
    ]
    pool_sha = hashlib.sha256(P.canonical_json(pool)).hexdigest()
    representatives = [{
        "pattern_index": 0, "sources": ["empty"], "pattern": [],
        "value_cap": None, "initial_dead_end": False, "initial_h": 0,
        "finite_sum": 0, "finite_count": 1, "dead_count": 0,
        "abstract_states": 1, "cofactor_width": 1,
        "reference_feasible": True,
    }, {
        "pattern_index": 1, "sources": ["bdd_prefix"], "pattern": [0],
        "value_cap": 0, "initial_dead_end": False, "initial_h": 0,
        "finite_sum": 0, "finite_count": 2, "dead_count": 0,
        "abstract_states": 2, "cofactor_width": 1,
        "reference_feasible": True,
    }]
    records = [{
        "domain": row["directory"], "problem": row["problem"],
        "family": row["family"],
        "reference_identity": {
            "pattern_index": 0, "sources": ["empty"], "pattern": [],
            "value_cap": None,
        },
        "reference_representatives": representatives,
        "reference_representatives_sha256": hashlib.sha256(
            P.canonical_json(representatives)
        ).hexdigest(),
        "normalized_pool": pool, "normalized_pool_sha256": pool_sha,
    } for row in P.guided_b_tasks(snapshot)]
    return {
        "schema": P.STANDALONE_SCHEMA,
        "base_b_freeze_sha256": snapshot["base_b_freeze_sha256"],
        "cohort_manifest_sha256": P.guided_b_projection_sha256(snapshot),
        "producer": {
            "planner_manifest": fake_planner(),
            "planner_manifest_sha256": hashlib.sha256(
                P.canonical_json_line(fake_planner())
            ).hexdigest(),
            "option_matrix_sha256": P.option_matrix_digest(),
            "reference_rule": (
                "strongest-K32-feasible-cap-per-pattern-then-score-v1"
            ),
        },
        "sealed_b_input": fake_standalone_source_binding(),
        "records": records,
        "records_sha256": hashlib.sha256(P.canonical_json(records)).hexdigest(),
    }


def fake_standalone_source_binding():
    return {
        "parse_receipt_path": P.BASE_B_PARSE_RECEIPT_PATH.relative_to(
            P.REPO
        ).as_posix(),
        "parse_receipt_sha256": "5" * 64,
        "fetch_receipt_path": P.BASE_B_FETCH_RECEIPT_PATH.relative_to(
            P.REPO
        ).as_posix(),
        "fetch_receipt_sha256": "6" * 64,
        "properties_path": P.BASE_B_PROPERTIES_PATH.relative_to(P.REPO).as_posix(),
        "properties_sha256": "7" * 64,
    }


def fake_freeze():
    snapshot = fake_snapshot()
    calibration = fake_calibration()
    standalone = fake_standalone(snapshot)
    return P.build_freeze(
        freeze_repository_revision="6" * 40,
        base_snapshot=snapshot, calibration_receipt=calibration,
        calibration_receipt_path=P.CALIBRATION_RECEIPT_PATH.relative_to(
            P.REPO
        ).as_posix(),
        calibration_receipt_sha256=hashlib.sha256(
            P.canonical_json_line(calibration)
        ).hexdigest(),
        planner_manifest=fake_planner(), standalone_evidence=standalone,
        standalone_evidence_path=P.STANDALONE_K32_PATH.relative_to(
            P.REPO
        ).as_posix(),
        standalone_evidence_sha256=hashlib.sha256(
            P.canonical_json_line(standalone)
        ).hexdigest(),
        source_hashes={path: SHA for path in P.SOURCE_FILES},
        scheduler_time_limit="01:40:00", scheduler_memory="26G",
    )


class ProtocolTest(unittest.TestCase):
    def test_static_design_pins_base_a_cell_count(self):
        with mock.patch.object(P, "BASE_A_CELL_COUNT", 2599):
            with self.assertRaisesRegex(P.ProtocolError, "static design changed"):
                P.validate_static_design()

    def test_analysis_v4_consumes_confirmation_a_v4_namespace(self):
        self.assertEqual(
            P.ANALYSIS_PROTOCOL,
            "pdb-terminal-metric-choice-analysis-v4",
        )
        self.assertEqual(
            P.BASE_A_RECEIPT_PATH.name, "analysis-execution-receipt-v4.json"
        )
        self.assertEqual(
            P.BASE_A_RECEIPT_PIN_PATH.name,
            "analysis-execution-receipt-v4.sha256",
        )
        self.assertEqual(P.BASE_A_FIRST_OUTPUT_PATH.name, "analysis-v4.json")
        self.assertEqual(P.BASE_A_SECOND_OUTPUT_PATH.name, "analysis-v4-repeat.json")

    def test_exact_task_major_cyclic_triads(self):
        tasks = fake_tasks()
        rows = P.task_major_cell_mapping(tasks)
        self.assertEqual(len(rows), 900)
        self.assertEqual({row["array_task"] for row in rows}, set(range(1, 301)))
        for task in range(1, 301):
            triad = [row for row in rows if row["array_task"] == task]
            self.assertEqual([row["run_id"] for row in triad], list(P.triad_cells(task)))
            self.assertEqual(set(row["algorithm"] for row in triad), set(P.MODES))
        family_zero = [row for row in rows if row["family"] == "family-00"]
        starts = [
            row["algorithm"] for row in family_zero if row["triad_position"] == 0
        ]
        self.assertEqual(starts[:4], [P.MODES[0], P.MODES[1], P.MODES[2], P.MODES[0]])

    def test_freeze_binds_all_inputs(self):
        freeze = fake_freeze()
        P.validate_freeze(freeze, verify_live_sources=False)
        self.assertEqual(freeze["design"]["cell_count"], 900)
        self.assertEqual(freeze["design"]["array_throttle"], 0)
        mutated = copy.deepcopy(freeze)
        mutated["planner"]["selector_base_revision"] = "0" * 40
        with self.assertRaises(P.ProtocolError):
            P.validate_freeze(mutated, verify_live_sources=False)

    def test_requires_a_authorization(self):
        snapshot = fake_snapshot()
        snapshot["confirmation_a_authorization"]["guided_study_authorized"] = False
        with self.assertRaisesRegex(P.ProtocolError, "does not authorize"):
            P.validate_base_snapshot(snapshot)

    def test_requires_exact_a_v4_authorization_metadata(self):
        mutations = {
            "receipt_schema": P.BASE_A_RECEIPT_SCHEMA.replace("/v4/", "/v2/"),
            "analysis_protocol": P.BASE_A_ANALYSIS_PROTOCOL.replace("v4", "v2"),
        }
        for field, value in mutations.items():
            snapshot = fake_snapshot()
            snapshot["confirmation_a_authorization"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                P.ProtocolError, "authorization metadata"
            ):
                P.validate_base_snapshot(snapshot)

    def test_requires_a_execution_and_hardware_provenance(self):
        snapshot = fake_snapshot()
        snapshot["confirmation_a_authorization"][
            "execution_receipt_sha256"
        ] = "not-a-digest"
        with self.assertRaises(P.ProtocolError):
            P.validate_base_snapshot(snapshot)

        snapshot = fake_snapshot()
        snapshot["confirmation_a_authorization"]["hardware"][
            "hardware_attestation_files"
        ] -= 1
        with self.assertRaisesRegex(P.ProtocolError, "hardware"):
            P.validate_base_snapshot(snapshot)

    def test_snapshot_requires_exact_confirmation_b_source_closure(self):
        snapshot = fake_snapshot()
        base_sources = snapshot["base_b_experiment_source_sha256"]
        self.assertEqual(
            set(base_sources),
            set(P.BASE_B_EXPERIMENT_SOURCE_FILES),
        )
        base_sources.pop(next(iter(base_sources)))
        with self.assertRaisesRegex(P.ProtocolError, "source closure"):
            P.validate_base_snapshot(snapshot)

    def test_snapshot_authorized_import_guards_static_b_source_contract(self):
        drifted = SimpleNamespace(
            EXPERIMENT_SOURCE_FILES=P.BASE_B_EXPERIMENT_SOURCE_FILES[:-1]
        )
        with mock.patch.object(
            P, "_lazy_base_protocol", return_value=drifted
        ), self.assertRaisesRegex(P.ProtocolError, "contract drifted"):
            P.snapshot_sealed_b(fake_calibration())

    def test_snapshot_uses_canonical_embedded_v12_a_b_materials(self):
        expected = fake_snapshot()
        source = expected["source_audit_v12"]
        authorization = copy.deepcopy(expected["confirmation_a_authorization"])
        live_authorization = copy.deepcopy(authorization)
        for field in tuple(live_authorization):
            if field.endswith("_path"):
                live_authorization[field] = P.REPO / live_authorization[field]
        b_freeze = {
            "freeze_repository_revision": expected[
                "base_b_freeze_repository_revision"
            ],
            "experiment_source_sha256": expected[
                "base_b_experiment_source_sha256"
            ],
            "planner": expected["base_b_planner"],
            "confirmation_a_authorization": authorization,
            "source_audit": source,
        }
        b_materials = SimpleNamespace(
            source_audit=source,
            bindings=source["bindings"],
            confirmation_a_candidate_indices_sha256=source["bindings"][
                "confirmation_a_candidate_indices_sha256"
            ],
            confirmation_a_source_projection_sha256=source["bindings"][
                "confirmation_a_source_projection_sha256"
            ],
        )
        a_freeze = {
            "freeze_repository_revision": expected[
                "confirmation_a_freeze"
            ]["repository_revision"],
            "source_audit": {
                "confirmation_a": expected["confirmation_a_cohort"],
            },
            "planner": expected["base_b_planner"],
        }
        a_materials = SimpleNamespace(
            bindings=source["bindings"],
            candidate_indices_sha256=expected["confirmation_a_cohort"][
                "candidate_indices_sha256"
            ],
            source_projection_sha256=expected["confirmation_a_cohort"][
                "source_projection_sha256"
            ],
        )
        base = SimpleNamespace(
            EXPERIMENT_SOURCE_FILES=P.BASE_B_EXPERIMENT_SOURCE_FILES,
            FREEZE_PATH=P.BASE_B_FREEZE_PATH,
            BENCHMARK_REVISION=expected["benchmark_revision"],
            validate_protocol_without_sources=lambda: None,
            _load_freeze=lambda path: (b_freeze, b_materials),
            load_confirmation_a_authorization=lambda *paths: live_authorization,
            _validate_confirmation_a_source_link=lambda auth, materials: None,
            SourceValidation=SimpleNamespace(
                _load_freeze=lambda path: (a_freeze, a_materials)
            ),
            sha256_file=lambda path: (
                expected["confirmation_a_freeze"]["sha256"]
                if path == P.BASE_A_FREEZE_PATH
                else expected["base_b_freeze_sha256"]
            ),
        )
        with mock.patch.object(P, "_lazy_base_protocol", return_value=base):
            self.assertEqual(
                P.snapshot_sealed_b(fake_calibration()), expected
            )

    def test_six_field_planner_identity_is_exactly_shared(self):
        mutations = {
            "revision": "0" * 40,
            "cache_name": "different-cache",
            "build_options": ["different-build"],
            "downward_sha256": "0" * 64,
            "preprocess_sha256": "0" * 64,
            "tree_manifest_sha256": "0" * 64,
        }
        for field, value in mutations.items():
            snapshot = fake_snapshot()
            snapshot["base_b_planner"][field] = value
            with self.subTest(field=field), self.assertRaises(P.ProtocolError):
                P.validate_base_snapshot(snapshot)
        planner = fake_planner()
        planner["revision"] = "0" * 40
        with self.assertRaisesRegex(P.ProtocolError, "planner manifest"):
            P.validate_planner_manifest(planner)

    def test_v12_projection_and_authorization_links_are_exact(self):
        snapshot = fake_snapshot()
        P.validate_base_snapshot(snapshot)
        mutations = (
            ("guided_b_source_projection_sha256", "0" * 64),
            ("confirmation_a_source_projection_sha256", "0" * 64),
            ("combined_tracked_file_sha256_digest", "0" * 64),
        )
        for field, value in mutations:
            changed = copy.deepcopy(snapshot)
            changed["source_audit_v12"]["bindings"][field] = value
            with self.subTest(field=field), self.assertRaises(P.ProtocolError):
                P.validate_base_snapshot(changed)
        changed = copy.deepcopy(snapshot)
        changed["confirmation_a_authorization"]["source_audit_provenance"][
            "source_audit_campaign"
        ] = "historical-reuse"
        with self.assertRaisesRegex(P.ProtocolError, "metadata"):
            P.validate_base_snapshot(changed)
        changed = copy.deepcopy(snapshot)
        changed["source_audit_v12"]["guided_b"]["records"][0][
            "candidate_index"
        ] = 300
        with self.assertRaises(P.ProtocolError):
            P.validate_base_snapshot(changed)

    def test_v12_translator_digest_is_recomputed(self):
        snapshot = fake_snapshot()
        snapshot["source_audit_v12"]["bindings"][
            "translator_source_sha256"
        ] = "0" * 64
        with self.assertRaisesRegex(P.ProtocolError, "translator source"):
            P.validate_base_snapshot(snapshot)

    def test_v12_translator_closure_is_identical_in_both_runs(self):
        snapshot = fake_snapshot()
        bindings = snapshot["source_audit_v12"]["bindings"]
        preflight = bindings["preflight_tracked_file_sha256"]
        preflight.pop(next(
            path for path in preflight if path.startswith("src/translate/")
        ))
        bindings["preflight_tracked_file_sha256_digest"] = hashlib.sha256(
            P.canonical_json(dict(sorted(preflight.items())))
        ).hexdigest()
        with self.assertRaisesRegex(P.ProtocolError, "translator source"):
            P.validate_base_snapshot(snapshot)

    def test_v12_eligible_count_tracks_supported_not_success(self):
        snapshot = fake_snapshot()
        bindings = snapshot["source_audit_v12"]["bindings"]
        self.assertEqual(bindings["eligible_records_count"], 950)
        self.assertEqual(bindings["support_status_counts"]["supported"], 950)
        self.assertEqual(bindings["outcome_counts"]["success"], 951)
        self.assertEqual(
            bindings["support_exclusion_counts"]["no-serialized-operators"],
            1,
        )
        P.validate_base_snapshot(snapshot)

    def test_v12_classification_binding_fields_are_mandatory(self):
        fields = {
            "inventory_families_count", "translation_attempts_count",
            "support_status_counts", "support_status_counts_sha256",
            "support_exclusion_counts", "support_exclusion_counts_sha256",
            "resource_exclusion_counts", "resource_exclusion_counts_sha256",
        }
        self.assertTrue(fields <= set(P.V12_BINDING_FIELDS))
        for field in fields:
            snapshot = fake_snapshot()
            del snapshot["source_audit_v12"]["bindings"][field]
            with self.subTest(field=field), self.assertRaisesRegex(
                P.ProtocolError, "binding shape"
            ):
                P.validate_base_snapshot(snapshot)

    def test_v12_classification_binding_counts_are_exact(self):
        for field, value in (
            ("inventory_families_count", 0),
            ("translation_attempts_count", 1639),
        ):
            snapshot = fake_snapshot()
            snapshot["source_audit_v12"]["bindings"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                P.ProtocolError, "source authorization"
            ):
                P.validate_base_snapshot(snapshot)

    def test_v12_inventory_covers_all_embedded_canonical_families(self):
        snapshot = fake_snapshot()
        snapshot["source_audit_v12"]["bindings"][
            "inventory_families_count"
        ] = 94
        with self.assertRaisesRegex(P.ProtocolError, "family count is too small"):
            P.validate_base_snapshot(snapshot)

    def test_v12_classification_summaries_are_recomputed_and_coherent(self):
        mutations = {
            "support_status_counts": {
                "indeterminate": 0, "supported": 949, "unsupported": 691,
            },
            "support_exclusion_counts": {
                reason: 689 if reason == "translation-input-rejected" else 0
                for reason in P.V12_SUPPORT_EXCLUSION_REASONS
            },
            "resource_exclusion_counts": {"memory": 1, "time": 0},
        }
        for field, value in mutations.items():
            snapshot = fake_snapshot()
            bindings = snapshot["source_audit_v12"]["bindings"]
            bindings[field] = value
            bindings[field + "_sha256"] = hashlib.sha256(
                P.canonical_json(value)
            ).hexdigest()
            with self.subTest(field=field), self.assertRaisesRegex(
                P.ProtocolError, "classification summary is incoherent"
            ):
                P.validate_base_snapshot(snapshot)

    def test_v12_code_manifest_is_bound_in_both_tracked_closures(self):
        tracked_fields = (
            "full_tracked_file_sha256",
            "preflight_tracked_file_sha256",
        )
        for field in tracked_fields:
            snapshot = fake_snapshot()
            snapshot["source_audit_v12"]["bindings"][field][
                P.V12_CODE_MANIFEST_RELATIVE
            ] = "0" * 64
            with self.subTest(field=field), self.assertRaisesRegex(
                P.ProtocolError, "code-manifest closure"
            ):
                P.validate_base_snapshot(snapshot)

    def test_v12_fixed_family_ledgers_define_projection_flags(self):
        flag_pairs = (
            ("is_shadow_family", "is_shadow_unrepresented"),
            ("is_all_prior_represented", "is_all_prior_unrepresented"),
        )
        for first, second in flag_pairs:
            snapshot = fake_snapshot()
            task = P.guided_b_tasks(snapshot)[0]
            task[first] = not task[first]
            task[second] = not task[second]
            rebind_v12_cohort(snapshot, "guided-b")
            with self.subTest(flags=(first, second)), self.assertRaisesRegex(
                P.ProtocolError, "source task changed"
            ):
                P.validate_base_snapshot(snapshot)

    def test_v12_cohort_directory_family_ledger_is_consistent(self):
        snapshot = fake_snapshot()
        guided = P.guided_b_tasks(snapshot)
        set_v12_task_directory(guided[10], guided[0]["directory"])
        rebind_v12_cohort(snapshot, "guided-b")
        with self.assertRaisesRegex(
            P.ProtocolError, "guided-b directory-to-family ledger"
        ):
            P.validate_base_snapshot(snapshot)

    def test_v12_task_and_alias_directories_are_canonical_safe_relative(self):
        invalid_directories = (
            "domain-000/.",
            "./domain-000",
            "domain-000/",
            "domain-000//nested",
            "domain-000/../domain-000",
            "/domain-000",
            ".",
        )
        for location, error in (
            ("task", "source task path is unsafe"),
            ("alias", "source alias path is unsafe"),
        ):
            for directory in invalid_directories:
                snapshot = fake_snapshot()
                task = P.guided_b_tasks(snapshot)[0]
                source = task if location == "task" else task["aliases"][0]
                source["directory"] = directory
                rebind_v12_cohort(snapshot, "guided-b")
                with self.subTest(
                    location=location, directory=directory
                ), self.assertRaisesRegex(P.ProtocolError, error):
                    P.validate_base_snapshot(snapshot)

    def test_v12_a_b_directory_family_ledgers_agree(self):
        snapshot = fake_snapshot()
        a_task = snapshot["confirmation_a_cohort"]["records"][0]
        b_task = P.guided_b_tasks(snapshot)[0]
        set_v12_task_directory(a_task, b_task["directory"])
        rebind_v12_cohort(snapshot, "confirmation-a")
        with self.assertRaisesRegex(P.ProtocolError, "A/B directory-to-family"):
            P.validate_base_snapshot(snapshot)

    def test_v12_confirmation_a_family_and_novelty_floors(self):
        snapshot = fake_snapshot()
        tasks = snapshot["confirmation_a_cohort"]["records"]
        for position, task in enumerate(tasks):
            set_v12_task_family(task, "a-floor-{:02d}".format(position % 27))
            set_v12_task_directory(task, "a-floor-dir-{:03d}".format(position))
        rebind_v12_cohort(snapshot, "confirmation-a")
        with self.assertRaisesRegex(
            P.ProtocolError, "confirmation-a family/novelty floor"
        ):
            P.validate_base_snapshot(snapshot)

        snapshot = fake_snapshot()
        tasks = snapshot["confirmation_a_cohort"]["records"]
        families = sorted(P.V12_SHADOW_FAMILIES) + [
            "a-novel-00", "a-novel-01",
        ]
        for position, task in enumerate(tasks):
            set_v12_task_family(task, families[position % len(families)])
            set_v12_task_directory(task, "a-novel-dir-{:03d}".format(position))
        rebind_v12_cohort(snapshot, "confirmation-a")
        with self.assertRaisesRegex(
            P.ProtocolError, "confirmation-a family/novelty floor"
        ):
            P.validate_base_snapshot(snapshot)

    def test_v12_guided_b_family_and_novelty_floors(self):
        snapshot = fake_snapshot()
        tasks = P.guided_b_tasks(snapshot)
        for position, task in enumerate(tasks):
            set_v12_task_family(task, "b-floor-{:02d}".format(position % 29))
            set_v12_task_directory(task, "b-floor-dir-{:03d}".format(position))
        rebind_v12_cohort(snapshot, "guided-b")
        with self.assertRaisesRegex(
            P.ProtocolError, "guided-b family/novelty floor"
        ):
            P.validate_base_snapshot(snapshot)

        snapshot = fake_snapshot()
        tasks = P.guided_b_tasks(snapshot)
        families = sorted(P.V12_SHADOW_FAMILIES) + [
            "b-novel-00", "b-novel-01", "b-novel-02", "b-novel-03",
        ]
        for position, task in enumerate(tasks):
            set_v12_task_family(task, families[position % len(families)])
            set_v12_task_directory(task, "b-novel-dir-{:03d}".format(position))
        rebind_v12_cohort(snapshot, "guided-b")
        with self.assertRaisesRegex(
            P.ProtocolError, "guided-b family/novelty floor"
        ):
            P.validate_base_snapshot(snapshot)

    def test_v12_guided_b_per_family_cap_is_enforced(self):
        snapshot = fake_snapshot()
        tasks = P.guided_b_tasks(snapshot)
        for position, task in enumerate(tasks):
            family = (
                "b-cap-00" if position < 13
                else "b-cap-{:02d}".format(1 + (position - 13) % 29)
            )
            set_v12_task_family(task, family)
            set_v12_task_directory(task, "b-cap-dir-{:03d}".format(position))
        rebind_v12_cohort(snapshot, "guided-b")
        with self.assertRaisesRegex(
            P.ProtocolError, "guided-b family/novelty floor"
        ):
            P.validate_base_snapshot(snapshot)

    def test_confirmation_a_outputs_must_be_byte_identical(self):
        snapshot = fake_snapshot()
        snapshot["confirmation_a_authorization"][
            "second_output_sha256"
        ] = "0" * 64
        with self.assertRaisesRegex(P.ProtocolError, "metadata"):
            P.validate_base_snapshot(snapshot)

    def test_all_embedded_revisions_are_exactly_40_hex(self):
        paths = (
            ("base_b_freeze_repository_revision",),
            ("confirmation_a_freeze", "repository_revision"),
            ("source_audit_v12", "bindings",
             "preflight_source_repository_commit_id"),
            ("source_audit_v12", "bindings",
             "preflight_seal_repository_commit_id"),
            ("source_audit_v12", "bindings", "seal_repository_commit_id"),
        )
        for path in paths:
            for length in (39, 41):
                snapshot = fake_snapshot()
                target = snapshot
                for field in path[:-1]:
                    target = target[field]
                target[path[-1]] = "a" * length
                with self.subTest(path=path, length=length), self.assertRaises(
                    P.ProtocolError
                ):
                    P.validate_base_snapshot(snapshot)
        for length in (39, 41):
            freeze = fake_freeze()
            freeze["freeze_repository_revision"] = "a" * length
            with self.subTest(direct=length), self.assertRaises(P.ProtocolError):
                P.validate_freeze(freeze, verify_live_sources=False)

    def test_standalone_sealed_b_paths_are_exact(self):
        evidence = fake_standalone()
        for field in (
            "parse_receipt_path", "fetch_receipt_path", "properties_path",
        ):
            mutated = copy.deepcopy(evidence)
            mutated["sealed_b_input"][field] = "experiments/elsewhere"
            with self.subTest(field=field), self.assertRaises(P.ProtocolError):
                P.validate_standalone_evidence(
                    mutated, fake_snapshot(), fake_planner()
                )

    def test_freeze_repository_revision_is_mandatory(self):
        freeze = fake_freeze()
        del freeze["freeze_repository_revision"]
        with self.assertRaises(P.ProtocolError):
            P.validate_freeze(freeze, verify_live_sources=False)

    def test_scheduler_resources_are_post_calibration_and_cover_triads(self):
        recommendation = fake_calibration()["resource_recommendation"]
        P.validate_frozen_resources("01:30:00", "24G", recommendation)
        for time_limit, memory in (("01:29:59", "26G"), ("01:40:00", "23G")):
            with self.assertRaises(P.ProtocolError):
                P.validate_frozen_resources(time_limit, memory, recommendation)

        high = {
            "minimum_selector_wall_seconds": 2000,
            "minimum_selector_peak_delta_kb": 30 * 1024 * 1024,
        }
        with self.assertRaises(P.ProtocolError):
            P.validate_frozen_resources("01:40:00", "26G", high)
        P.validate_frozen_resources("01:40:00", "30G", high)

    def test_calibration_recommendation_is_exactly_reconstructed(self):
        receipt = fake_calibration()
        receipt["resource_recommendation"][
            "minimum_selector_wall_seconds"
        ] += 1
        with self.assertRaisesRegex(P.ProtocolError, "recommendation changed"):
            P.validate_calibration_receipt(receipt)

    def test_calibration_rejects_outcome_identity(self):
        receipt = fake_calibration()
        receipt["observations"][0]["selected_identity"] = {"pattern": []}
        receipt["observations_sha256"] = hashlib.sha256(
            P.canonical_json(receipt["observations"])
        ).hexdigest()
        with self.assertRaisesRegex(P.ProtocolError, "forbidden"):
            P.validate_calibration_receipt(receipt)


if __name__ == "__main__":
    unittest.main()
