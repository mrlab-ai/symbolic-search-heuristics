#!/usr/bin/env python3
"""Stdlib tests for the accepted P4/P5 public-properties projection."""

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import project_arrhenius_public_properties as projection


class PublicPropertiesProjectionTest(unittest.TestCase):
    def setUp(self):
        self.identity = ["algorithm", "domain", "problem.pddl"]
        self.key = "-".join(self.identity)
        self.source = {
            self.key: {
                "id": list(self.identity),
                "algorithm": self.identity[0],
                "domain": self.identity[1],
                "problem": self.identity[2],
                "benchmark_worktree": "/private/benchmarks",
                "repo": "/private/planner",
                "node": "private-node",
                "scheduler_account": "private-account",
                "coverage": 1,
                "planner_time": 1.25,
                "nested_scientific_value": {"counts": [1, 2, 3]},
            }
        }
        self.spec = projection._synthetic_spec(self.source)

    def assertProjectionError(self, function, *args, **kwargs):
        with self.assertRaises(projection.ProjectionError):
            function(*args, **kwargs)

    def test_exactly_four_fields_are_normalized(self):
        public = projection.project_properties(self.source, self.spec)
        source_record = self.source[self.key]
        public_record = public[self.key]
        changed = {
            field
            for field in source_record
            if projection.canonical_json_bytes(
                source_record[field], newline=False
            )
            != projection.canonical_json_bytes(public_record[field], newline=False)
        }
        self.assertEqual(changed, set(projection.NORMALIZED_FIELDS))
        for field, sentinel in projection.NORMALIZED_FIELDS.items():
            self.assertEqual(public_record[field], sentinel)
        self.assertEqual(public_record["coverage"], 1)
        self.assertEqual(public_record["planner_time"], 1.25)
        self.assertEqual(
            public_record["nested_scientific_value"], {"counts": [1, 2, 3]}
        )

    def test_projection_is_deterministic_under_insertion_reordering(self):
        first = projection.project_properties(self.source, self.spec)
        reordered_record = dict(reversed(list(self.source[self.key].items())))
        reordered = {self.key: reordered_record}
        second = projection.project_properties(reordered, self.spec)
        self.assertEqual(
            projection.canonical_json_bytes(first),
            projection.canonical_json_bytes(second),
        )

    def test_unknown_record_field_is_rejected(self):
        changed = copy.deepcopy(self.source)
        changed[self.key]["unexpected"] = 1
        self.assertProjectionError(
            projection.validate_properties_structure,
            changed,
            self.spec,
            projected=False,
        )

    def test_missing_record_field_is_rejected(self):
        changed = copy.deepcopy(self.source)
        del changed[self.key]["coverage"]
        self.assertProjectionError(
            projection.validate_properties_structure,
            changed,
            self.spec,
            projected=False,
        )

    def test_source_key_and_cell_identity_are_bound(self):
        changed = copy.deepcopy(self.source)
        changed[self.key]["algorithm"] = "different"
        # Construct a matching schema spec so this reaches the identity check.
        spec = projection._synthetic_spec(changed)
        self.assertProjectionError(
            projection.validate_properties_structure,
            changed,
            spec,
            projected=False,
        )

    def test_unreviewed_absolute_path_is_rejected(self):
        changed = copy.deepcopy(self.source)
        changed[self.key]["nested_scientific_value"] = "/private/unreviewed"
        spec = projection._synthetic_spec(changed)
        self.assertProjectionError(
            projection.validate_properties_structure,
            changed,
            spec,
            projected=False,
        )

    def test_embedded_packaging_identity_is_rejected(self):
        changed = copy.deepcopy(self.source)
        changed[self.key]["nested_scientific_value"] = (
            "trace from private-node completed"
        )
        spec = projection._synthetic_spec(changed)
        self.assertProjectionError(
            projection.project_properties,
            changed,
            spec,
        )

    def test_missing_or_changed_sentinel_is_rejected(self):
        public = projection.project_properties(self.source, self.spec)
        public[self.key]["node"] = "another-node"
        self.assertProjectionError(
            projection.validate_properties_structure,
            public,
            self.spec,
            projected=True,
        )

    def test_duplicate_keys_and_nonfinite_numbers_are_rejected(self):
        for raw in (
            b'{"record":1,"record":2}',
            b'{"record":{"nested":1,"nested":2}}',
            b'{"record":NaN}',
            b'{"record":Infinity}',
        ):
            with self.subTest(raw=raw):
                self.assertProjectionError(
                    projection.parse_json_bytes, raw, "adversarial JSON"
                )

    def test_invalid_utf8_and_nonobject_top_level_are_rejected(self):
        self.assertProjectionError(
            projection.parse_json_bytes, b'\xff', "invalid UTF-8"
        )
        for value in ([], "value", 1):
            with self.subTest(value=value):
                self.assertProjectionError(
                    projection.validate_properties_structure,
                    value,
                    self.spec,
                    projected=False,
                )

    def test_stable_read_checks_hash_size_symlink_and_link_count(self):
        raw = projection.canonical_json_bytes(self.source)
        identity = projection.FileIdentity(len(raw), projection._sha256(raw))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "properties"
            path.write_bytes(raw)
            self.assertEqual(
                projection.stable_read(path, identity=identity), raw
            )
            self.assertProjectionError(
                projection.stable_read,
                path,
                identity=projection.FileIdentity(len(raw) + 1, identity.sha256),
            )
            self.assertProjectionError(
                projection.stable_read,
                path,
                identity=projection.FileIdentity(len(raw), "0" * 64),
            )

            symlink = root / "symlink"
            symlink.symlink_to(path)
            self.assertProjectionError(
                projection.stable_read, symlink, identity=identity
            )

            hardlink = root / "hardlink"
            os.link(path, hardlink)
            self.assertProjectionError(
                projection.stable_read, path, identity=identity
            )
            self.assertProjectionError(
                projection.stable_read, hardlink, identity=identity
            )

    def test_projected_file_is_canonical_and_identity_pinned(self):
        public = projection.project_properties(self.source, self.spec)
        raw = projection.canonical_json_bytes(public)
        self.assertEqual(len(raw), self.spec.projected.size)
        self.assertEqual(projection._sha256(raw), self.spec.projected.sha256)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertNotIn(b"\n", raw[:-1])
        parsed = projection.parse_json_bytes(raw, "public properties")
        self.assertEqual(projection.canonical_json_bytes(parsed), raw)

    def test_logical_digest_ignores_source_order_but_not_values(self):
        second_identity = ["algorithm", "other", "other.pddl"]
        second_key = "-".join(second_identity)
        second = copy.deepcopy(self.source[self.key])
        second.update(
            {
                "id": second_identity,
                "domain": second_identity[1],
                "problem": second_identity[2],
            }
        )
        values = {self.key: self.source[self.key], second_key: second}
        reversed_values = dict(reversed(list(values.items())))
        self.assertEqual(
            projection.logical_properties_sha256(values),
            projection.logical_properties_sha256(reversed_values),
        )
        changed = copy.deepcopy(values)
        changed[self.key]["coverage"] = 0
        self.assertNotEqual(
            projection.logical_properties_sha256(values),
            projection.logical_properties_sha256(changed),
        )

    def test_artifact_comparison_allows_only_declared_digest_path(self):
        accepted = {
            "identity": {"properties_sha256": "1" * 64},
            "statistics": {"coverage": 1, "runtime": 1.0},
        }
        generated = copy.deepcopy(accepted)
        generated["identity"]["properties_sha256"] = "2" * 64
        removed = projection.compare_modulo_exclusions(
            generated,
            accepted,
            (("identity", "properties_sha256"),),
            "synthetic artifact",
        )
        self.assertEqual(
            [item["path"] for item in removed], ["identity.properties_sha256"]
        )

        changed_statistic = copy.deepcopy(generated)
        changed_statistic["statistics"]["coverage"] = 0
        self.assertProjectionError(
            projection.compare_modulo_exclusions,
            changed_statistic,
            accepted,
            (("identity", "properties_sha256"),),
            "synthetic artifact",
        )

    def test_artifact_comparison_is_type_strict(self):
        accepted = {
            "identity": {"properties_sha256": "1" * 64},
            "statistic": 1,
        }
        generated = {
            "identity": {"properties_sha256": "2" * 64},
            "statistic": 1.0,
        }
        self.assertProjectionError(
            projection.compare_modulo_exclusions,
            generated,
            accepted,
            (("identity", "properties_sha256"),),
            "synthetic artifact",
        )

    def test_preimported_analysis_dependency_is_rejected(self):
        name = "analyze_ms_caps_pilot"
        missing = object()
        previous = sys.modules.get(name, missing)
        sys.modules[name] = object()
        try:
            self.assertProjectionError(
                projection._reject_preimported_analysis_modules
            )
        finally:
            if previous is missing:
                del sys.modules[name]
            else:
                sys.modules[name] = previous

    def test_self_test(self):
        result = projection.self_test()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["protocol"], projection.PROJECTION_PROTOCOL)


if __name__ == "__main__":
    unittest.main()
