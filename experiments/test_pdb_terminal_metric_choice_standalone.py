#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import subprocess
import sys
import textwrap
import types
import unittest
from unittest import mock

import pdb_cap_selector_parser as CapParser
import pdb_terminal_metric_choice_protocol as P
import pdb_terminal_metric_choice_standalone as Standalone
from test_pdb_cap_selector_parser import fixture, render
from test_pdb_terminal_metric_choice_protocol import (
    fake_calibration, fake_planner, fake_snapshot,
    fake_standalone_source_binding,
)


def structural_record() -> dict:
    candidates, selected, final = fixture()
    del selected, final
    for candidate in candidates:
        candidate["cofactor_width_budget"] = 32
        candidate["feasible"] = candidate["cofactor_width"] <= 32
        candidate["rejection_reason"] = (
            None if candidate["feasible"] else "cofactor_width_budget"
        )
    errors, normalized, representatives, _, _ = (
        CapParser._normalize_wire_groups(candidates, True)
    )
    assert not errors
    best = min(representatives, key=CapParser.C._selector_score_key)
    selected = next(
        copy.deepcopy(candidate) for candidate in candidates
        if candidate["pattern"] == best["pattern"]
        and candidate["value_cap"] == best["value_cap"]
    )
    selected["raw_value_histogram"] = None
    final = {
        "pattern_size": len(selected["pattern"]),
        "selected_source": selected["sources"][0],
        "abstract_states": selected["abstract_states"],
        "cofactor_width_budget": 32,
        "value_cap": selected["value_cap"],
        "num_values": selected["transformed_num_values"],
        "cofactor_width": selected["cofactor_width"],
        "width_upper_bound": selected["width_upper_bound"],
    }
    props = {}
    CapParser.parse_cap_selector_log(render(candidates, selected, final), props)
    assert "unexplained_errors" not in props
    return props


def cap_records(snapshot: dict) -> list[dict]:
    structural = structural_record()
    result = []
    for row in Standalone.plain_reference_rows(snapshot):
        result.append({**copy.deepcopy(structural), **row})
    return result


class StandaloneTest(unittest.TestCase):
    def test_protocol_and_standalone_import_without_loading_b(self):
        code = textwrap.dedent("""
            import importlib.abc
            import os
            import sys
            sys.path.insert(0, {path!r})
            class BlockEvidence(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path, target=None):
                    forbidden = (
                        "terminal_incidence_confirmation_a",
                        "terminal_incidence_confirmation_b",
                        "terminal_incidence_confirmation_source",
                    )
                    if any(token in fullname for token in forbidden):
                        raise RuntimeError("A/B/V7 imported before calibration")
                    return None
            sys.meta_path.insert(0, BlockEvidence())
            real_open = os.open
            blocked = {blocked!r}
            blocked_prefixes = {blocked_prefixes!r}
            def is_blocked(path):
                try:
                    text = os.fspath(path)
                except TypeError:
                    return False
                absolute = os.path.abspath(text)
                return absolute in blocked or any(
                    absolute.startswith(prefix + os.sep)
                    for prefix in blocked_prefixes
                )
            def guarded_open(path, *args, **kwargs):
                if is_blocked(path):
                    raise RuntimeError("artifact read during import")
                return real_open(path, *args, **kwargs)
            os.open = guarded_open
            def audit(event, args):
                if event == "open" and args and is_blocked(args[0]):
                    raise RuntimeError("artifact read during import")
            sys.addaudithook(audit)
            import pdb_terminal_metric_choice_protocol
            import pdb_terminal_metric_choice_standalone
        """).format(
            path=str(P.SCRIPT_DIR.resolve()),
            blocked={
                str(P.BASE_B_PROPERTIES_PATH.resolve()),
                str((
                    P.SCRIPT_DIR / "data" /
                    "exp_pdb_terminal_incidence_confirmation_a-eval" /
                    "properties"
                ).resolve()),
            },
            blocked_prefixes={
                str(P.ARTIFACT_DIR.resolve()),
                str(P.BASE_CONFIRMATION_ARTIFACT_DIR.resolve()),
            },
        )
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-c", code],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_invalid_calibration_prevents_every_b_access(self):
        calibration = fake_calibration()
        calibration["observations"][0]["selected_identity"] = {"pattern": []}
        calibration["observations_sha256"] = hashlib.sha256(
            P.canonical_json(calibration["observations"])
        ).hexdigest()
        with mock.patch.object(
            P, "load_canonical", return_value=(b"{}\n", calibration),
        ), mock.patch.object(
            P, "snapshot_sealed_b"
        ) as snapshot, mock.patch.object(
            Standalone, "sealed_b_records"
        ) as sealed, self.assertRaisesRegex(P.ProtocolError, "forbidden"):
            Standalone.produce()
        snapshot.assert_not_called()
        sealed.assert_not_called()

    def test_live_b_reader_requires_parse_fetch_properties_chain(self):
        digest_parse = "5" * 64
        digest_fetch = "6" * 64
        digest_properties = "7" * 64

        class AuditError(RuntimeError):
            pass

        fake_audit = types.SimpleNamespace(
            PARSE_RECEIPT=P.BASE_B_PARSE_RECEIPT_PATH,
            FETCH_RECEIPT=P.BASE_B_FETCH_RECEIPT_PATH,
            EVAL_PROPERTIES=P.BASE_B_PROPERTIES_PATH,
            ExecutionAuditError=AuditError,
            load_parse_receipt=lambda verify_live: (digest_parse, {}),
            load_fetch_receipt=lambda verify_live: (digest_fetch, {
                "parse_receipt_sha256": digest_parse,
                "properties_sha256": digest_properties,
            }),
        )
        loaded = types.SimpleNamespace(raw=b"[]", sha256=digest_properties)
        with mock.patch.dict(
            sys.modules,
            {"audit_pdb_terminal_incidence_confirmation_b": fake_audit},
        ), mock.patch.object(
            Standalone.CampaignIO, "read_regular_exact", return_value=loaded,
        ):
            records, binding = Standalone.sealed_b_records()
        self.assertEqual(records, [])
        P.validate_standalone_source_binding(binding)

        fake_audit.load_fetch_receipt = lambda verify_live: (digest_fetch, {
            "parse_receipt_sha256": "0" * 64,
            "properties_sha256": digest_properties,
        })
        with mock.patch.dict(
            sys.modules,
            {"audit_pdb_terminal_incidence_confirmation_b": fake_audit},
        ), mock.patch.object(
            Standalone.CampaignIO, "read_regular_exact", return_value=loaded,
        ), self.assertRaisesRegex(Standalone.StandaloneError, "fetch seal"):
            Standalone.sealed_b_records()

        fake_audit.load_fetch_receipt = lambda verify_live: (digest_fetch, {
            "parse_receipt_sha256": digest_parse,
            "properties_sha256": "0" * 64,
        })
        with mock.patch.dict(
            sys.modules,
            {"audit_pdb_terminal_incidence_confirmation_b": fake_audit},
        ), mock.patch.object(
            Standalone.CampaignIO, "read_regular_exact", return_value=loaded,
        ), self.assertRaisesRegex(Standalone.StandaloneError, "fetch seal"):
            Standalone.sealed_b_records()

    def test_rotating_cap_slots_are_selected_by_frozen_mapping(self):
        snapshot = fake_snapshot()
        records = cap_records(snapshot)
        slots = {((row["run_id"] - 1) % 9) + 1 for row in records}
        self.assertEqual(slots, {7, 8, 9})
        evidence = Standalone.build_evidence(
            records, snapshot, fake_planner(), fake_standalone_source_binding()
        )
        P.validate_standalone_evidence(evidence, snapshot, fake_planner())
        self.assertEqual(len(evidence["records"]), P.COHORT_TASKS)

    def test_outcome_fields_cannot_change_projected_evidence(self):
        snapshot = fake_snapshot()
        records = cap_records(snapshot)
        first = Standalone.build_evidence(
            records, snapshot, fake_planner(), fake_standalone_source_binding()
        )
        for index, record in enumerate(records):
            record.update({
                "coverage": index % 2,
                "total_time": float(index),
                "planner_exit_code": 99 - (index % 3),
                "search_time": float(index) / 2,
            })
        second = Standalone.build_evidence(
            records, snapshot, fake_planner(), fake_standalone_source_binding()
        )
        self.assertEqual(P.canonical_json(first), P.canonical_json(second))

    def test_missing_duplicate_and_mapping_changes_fail(self):
        snapshot = fake_snapshot()
        records = cap_records(snapshot)
        cases = [
            records[:-1],
            records + [copy.deepcopy(records[0])],
            [{**records[0], "run_id": records[0]["run_id"] + 1}, *records[1:]],
        ]
        for case in cases:
            with self.subTest(length=len(case)), self.assertRaises(
                Standalone.StandaloneError
            ):
                Standalone.build_evidence(
                    case, snapshot, fake_planner(),
                    fake_standalone_source_binding(),
                )

    def test_uncertified_or_tampered_pool_fails(self):
        snapshot = fake_snapshot()
        records = cap_records(snapshot)
        for mutation in ("pdb_selector_trace_certified", "pdb_selector_candidates"):
            changed = copy.deepcopy(records)
            if mutation == "pdb_selector_trace_certified":
                changed[0][mutation] = False
            else:
                changed[0][mutation][0]["pattern"] = [99]
            with self.subTest(mutation=mutation), self.assertRaises(
                Standalone.StandaloneError
            ):
                Standalone.build_evidence(
                    changed, snapshot, fake_planner(),
                    fake_standalone_source_binding(),
                )


if __name__ == "__main__":
    unittest.main()
