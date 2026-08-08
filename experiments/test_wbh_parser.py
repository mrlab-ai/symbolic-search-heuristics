#!/usr/bin/env python3
"""Focused synthetic acceptance and fail-closed tests for wbh_parser."""
import copy
import json
import unittest

import wbh_parser


class FakeProperties(dict):
    def add_unexplained_error(self, message):
        self.setdefault("unexplained_errors", []).append(message)


def base_events():
    # The second image deliberately has three logical source buckets exact-
    # unioned into one physical BDD piece. This is valid contour batching.
    return [
        {
            "event": "schema",
            "version": 2,
            "node_count_convention": "inner_nodes_per_piece",
            "image_count_convention": "per_piece_attempted_completed",
            "expansion_count_convention": "completed_with_attempts",
        },
        {
            "event": "heuristic",
            "add_nodes": 3,
            "num_values": 2,
            "num_terminals": 2,
            "add_level_nodes": [1, 2],
            "width_upper_bound": 5,
        },
        {
            "event": "construction",
            "heuristic": "rectified_potential",
            "seconds": 0.25,
            "size_bound": 8,
            "value_cap": -1,
            "completed": True,
        },
        {
            "event": "expand",
            "g": 0,
            "h": 2,
            "completed": True,
            "piece_count": 1,
            "bdd_nodes": 5,
            "states": 7.0,
            "image_time": 0.1,
        },
        {
            "event": "expand",
            "g": 1,
            "h": 3,
            "completed": False,
            "piece_count": 2,
            "bdd_nodes": 7,
            "states": 8.0,
            "image_time": 0.2,
        },
        {
            "event": "image",
            "g": 0,
            "min_h": 1,
            "max_h": 1,
            "source_buckets": 1,
            "source_pieces": 1,
            "calls_attempted": 1,
            "calls_completed": 1,
            "zero_cost": False,
            "bdd_nodes": 4,
            "states": 6.0,
            "image_time": 0.1,
        },
        {
            "event": "image",
            "g": 1,
            "min_h": 1,
            "max_h": 4,
            "source_buckets": 3,
            "source_pieces": 1,
            "calls_attempted": 1,
            "calls_completed": 0,
            "zero_cost": False,
            "bdd_nodes": 6,
            "states": 7.0,
            "image_time": 0.2,
        },
        {
            "event": "partition",
            "g": 0,
            "layer_nodes": 3,
            "sum_bucket_nodes": 4,
            "num_buckets": 2,
        },
        {
            "event": "pruned_deadends",
            "g": 1,
            "states": 2.0,
            "bdd_nodes": 1,
        },
        {
            "event": "summary",
            "expanded_bdd_nodes": 5,
            "expanded_states": 7.0,
            "expanded_bdd_pieces": 1,
            "attempted_bdd_nodes": 12,
            "attempted_states": 15.0,
            "attempted_bdd_pieces": 3,
            "bucket_expansions": 1,
            "bucket_expansion_attempts": 2,
            "image_events": 2,
            "bucket_images": 1,
            "image_source_buckets": 4,
            "image_source_pieces": 2,
            "image_calls_attempted": 2,
            "image_calls_completed": 1,
            "batched_images": 1,
            "image_time": 0.3,
            "solved": False,
        },
    ]


def parse(events, suffix="", initial=None):
    content = "\n".join(json.dumps(event) for event in events) + suffix
    props = {} if initial is None else initial
    wbh_parser.parse_wbh_log(content, props)
    return props


def event(events, kind, occurrence=0):
    return [
        candidate for candidate in events if candidate.get("event") == kind
    ][occurrence]


class WbhParserTest(unittest.TestCase):
    def assert_rejected(self, events, error_fragment):
        props = parse(events)
        self.assertIs(props["raw_metrics_complete"], False)
        self.assertIs(props["piece_metrics_certified"], False)
        self.assertIn(error_fragment, props["metrics_validation_error"])
        return props

    def test_accepts_consistent_contour_batched_stream(self):
        props = parse(base_events())
        self.assertIs(props["raw_metrics_complete"], True)
        self.assertIs(props["piece_metrics_certified"], True)
        self.assertEqual(
            props["metrics_validation_protocol"],
            wbh_parser.METRICS_VALIDATION_PROTOCOL)
        self.assertNotIn("metrics_validation_error", props)
        self.assertEqual(props["expanded_bdd_nodes"], 5)
        self.assertEqual(props["attempted_bdd_nodes"], 12)
        self.assertEqual(props["expanded_bdd_pieces"], 1)
        self.assertEqual(props["image_source_buckets"], 4)
        self.assertEqual(props["image_source_pieces"], 2)
        self.assertEqual(props["image_calls_completed"], 1)
        self.assertEqual(props["batched_images"], 1)
        self.assertIs(props["expanded_buckets_single_piece"], True)

    def test_partial_stream_is_not_complete(self):
        events = base_events()[:-1]
        props = parse(events)
        self.assertIs(props["raw_metrics_complete"], False)
        self.assertIs(props["piece_metrics_certified"], True)
        self.assertEqual(props["expanded_bdd_nodes"], 5)

    def test_summary_cannot_override_events(self):
        events = copy.deepcopy(base_events())
        event(events, "summary")["expanded_bdd_nodes"] = 999
        props = self.assert_rejected(
            events, "summary.expanded_bdd_nodes=999")
        self.assertEqual(props["expanded_bdd_nodes"], 5)

    def test_accepts_consistent_done_and_effort(self):
        events = base_events()
        summary = events.pop()
        events.append({"event": "done", "effort": 5, "solution_cost": 5})
        summary["solved"] = True
        events.append(summary)
        props = parse(
            events, initial=FakeProperties(coverage=1, solution_cost=5))
        self.assertIs(props["raw_metrics_complete"], True)
        self.assertIs(props["piece_metrics_certified"], True)
        self.assertEqual(props["coverage"], 1)
        self.assertEqual(props["effort"], 5)
        self.assertEqual(props["solution_cost"], 5)

    def test_rejects_done_effort_mismatch(self):
        events = base_events()
        summary = events.pop()
        events.append({"event": "done", "effort": 4, "solution_cost": 5})
        summary["solved"] = True
        events.append(summary)
        self.assert_rejected(events, "done.effort=4")

    def test_done_cannot_override_planner_output_cost(self):
        events = base_events()
        summary = events.pop()
        events.append({"event": "done", "effort": 5, "solution_cost": 5})
        summary["solved"] = True
        events.append(summary)
        props = parse(
            events, initial=FakeProperties(coverage=1, solution_cost=6))
        self.assertIs(props["raw_metrics_complete"], False)
        self.assertIs(props["piece_metrics_certified"], False)
        self.assertIsNone(props["coverage"])
        self.assertEqual(props["solution_cost"], 6)
        self.assertNotIn("effort", props)
        self.assertIn(
            "done.solution_cost=5 != planner output 6",
            props["metrics_validation_error"])
        self.assertIn(
            "WBH outcome validation failed",
            props["unexplained_errors"][0])

    def test_summary_solved_must_agree_with_planner_coverage(self):
        props = parse(
            base_events(),
            initial=FakeProperties(coverage=1, solution_cost=5))
        self.assertIsNone(props["coverage"])
        self.assertIs(props["raw_metrics_complete"], False)
        self.assertIs(props["piece_metrics_certified"], False)
        self.assertIn(
            "summary.solved=False != planner coverage 1",
            props["metrics_validation_error"])

    def test_legacy_done_cannot_override_planner_output_cost(self):
        events = [
            {"event": "done", "effort": 7, "solution_cost": 5},
            {
                "event": "summary", "expanded_bdd_nodes": 1,
                "expanded_states": 2.0, "bucket_images": 1,
                "image_time": 0.1,
            },
        ]
        props = parse(
            events, initial=FakeProperties(coverage=1, solution_cost=6))
        self.assertIsNone(props["coverage"])
        self.assertEqual(props["solution_cost"], 6)
        self.assertNotIn("effort", props)
        self.assertIs(props["piece_metrics_certified"], False)
        self.assertIn(
            "legacy done.solution_cost=5 != planner output 6",
            props["metrics_validation_error"])
        self.assertIn(
            "WBH outcome validation failed",
            props["unexplained_errors"][0])

    def test_legacy_matching_done_preserves_planner_output_and_effort(self):
        events = [
            {"event": "done", "effort": 7, "solution_cost": 5},
            {
                "event": "summary", "expanded_bdd_nodes": 1,
                "expanded_states": 2.0, "bucket_images": 1,
                "image_time": 0.1,
            },
        ]
        props = parse(
            events, initial=FakeProperties(coverage=1, solution_cost=5))
        self.assertEqual(props["coverage"], 1)
        self.assertEqual(props["solution_cost"], 5)
        self.assertEqual(props["effort"], 7)
        self.assertIs(props["piece_metrics_certified"], False)
        self.assertNotIn("metrics_validation_error", props)

    def test_rejects_malformed_json_without_silent_certification(self):
        props = parse(base_events(), suffix="\n{")
        self.assertIs(props["raw_metrics_complete"], False)
        self.assertIs(props["piece_metrics_certified"], False)
        self.assertIn("malformed JSON", props["metrics_validation_error"])

    def test_rejects_duplicate_or_nonfinal_summary(self):
        events = base_events()
        events.append(copy.deepcopy(event(events, "summary")))
        self.assert_rejected(events, "at most one summary")

        events = base_events()
        events.append({
            "event": "partition", "g": 1, "layer_nodes": 1,
            "sum_bucket_nodes": 1, "num_buckets": 1,
        })
        self.assert_rejected(events, "summary event must be last")

    def test_rejects_wrong_json_type_instead_of_bool_as_int(self):
        events = copy.deepcopy(base_events())
        event(events, "expand")["bdd_nodes"] = True
        self.assert_rejected(events, "bdd_nodes=True is not int")

    def test_rejects_event_counter_invariants(self):
        mutations = (
            ("piece_count", "expand", "piece_count", 0, "must be positive"),
            ("negative_nodes", "expand", "bdd_nodes", -1, "must be nonnegative"),
            ("nonfinite_states", "expand", "states", float("nan"),
             "states=nan is not float"),
            ("overflow_states", "expand", "states", 10 ** 1000,
             "is not float"),
            ("zero_source_buckets", "image", "source_buckets", 0,
             "must be positive"),
            ("zero_source_pieces", "image", "source_pieces", 0,
             "must be positive"),
            ("completed_over_attempted", "image", "calls_completed", 2,
             "exceeds calls_attempted"),
            ("attempted_over_pieces", "image", "calls_attempted", 2,
             "exceeds source_pieces"),
            ("reversed_h_range", "image", "min_h", 2, "min_h exceeds max_h"),
        )
        for label, kind, key, value, fragment in mutations:
            with self.subTest(label=label):
                events = copy.deepcopy(base_events())
                target = event(events, kind)
                target[key] = value
                self.assert_rejected(events, fragment)

    def test_rejects_heuristic_and_construction_invariants(self):
        mutations = (
            ("width", "heuristic", "width_upper_bound", 6,
             "width_upper_bound"),
            ("levels", "heuristic", "add_level_nodes", [1, 1],
             "do not sum"),
            ("values", "heuristic", "num_values", 3,
             "num_values exceeds"),
            ("size", "construction", "size_bound", -1,
             "must be nonnegative"),
            ("cap", "construction", "value_cap", -2,
             "must be -1 or nonnegative"),
        )
        for label, kind, key, value, fragment in mutations:
            with self.subTest(label=label):
                events = copy.deepcopy(base_events())
                event(events, kind)[key] = value
                self.assert_rejected(events, fragment)

    def test_rejects_overflow_sized_partition_ratio_without_crashing(self):
        events = copy.deepcopy(base_events())
        event(events, "partition")["sum_bucket_nodes"] = 10 ** 1000
        self.assert_rejected(events, "partition[0] ratio is not finite")

    def test_rejects_schema_and_summary_inconsistencies(self):
        mutations = (
            ("version", "schema", "version", 3,
             "frozen v2 conventions"),
            ("schema", "schema", "node_count_convention", "forged",
             "frozen v2 conventions"),
            ("solved", "summary", "solved", True, "done presence"),
            ("calls", "summary", "image_calls_completed", 2,
             "summary.image_calls_completed"),
            ("batched", "summary", "batched_images", 2,
             "summary.batched_images"),
            ("states", "summary", "expanded_states", 70.0,
             "summary.expanded_states"),
        )
        for label, kind, key, value, fragment in mutations:
            with self.subTest(label=label):
                events = copy.deepcopy(base_events())
                event(events, kind)[key] = value
                self.assert_rejected(events, fragment)


if __name__ == "__main__":
    unittest.main()
