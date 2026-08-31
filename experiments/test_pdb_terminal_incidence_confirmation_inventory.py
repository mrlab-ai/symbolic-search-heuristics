#!/usr/bin/env python3
"""Adversarial tests for the outcome-independent confirmation inventory."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pdb_terminal_incidence_confirmation_inventory as I


class ConfirmationInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = I.load_inventory()

    def test_universal_and_residual_counts_are_frozen(self):
        inventory = self.inventory
        self.assertEqual(len(inventory.directories), 147)
        self.assertEqual(inventory.all_path_count, 4088)
        self.assertEqual(inventory.all_unique_problem_hash_count, 3625)
        self.assertEqual(inventory.residue_path_count, 1733)
        self.assertEqual(len(inventory.prior_identity_ledger), 2157)
        self.assertEqual(len(inventory.residue_identities), 1733)
        self.assertEqual(inventory.name_overlap_after_hash_filter_count, 0)
        self.assertEqual(inventory.prior_identity_overlap_count, 0)
        self.assertEqual(inventory.prior_problem_hash_overlap_count, 0)
        self.assertEqual(len(inventory.candidates), 1640)
        self.assertEqual(len(inventory.residue_directories), 79)
        self.assertEqual(
            len({candidate.directory for candidate in inventory.candidates}),
            78,
        )
        self.assertEqual(len(inventory.residue_families), 43)
        self.assertEqual(len(inventory.represented_shadow_families), 23)
        self.assertEqual(len(inventory.shadow_unrepresented_families), 20)
        self.assertEqual(len(inventory.represented_all_prior_families), 30)
        self.assertEqual(len(inventory.all_prior_unrepresented_families), 13)

    def test_every_inventory_digest_is_pinned(self):
        self.assertEqual(dict(self.inventory.digests), {
            "alias_groups": I.ALIAS_GROUPS_SHA256,
            "all_path_records": I.ALL_PATH_RECORDS_SHA256,
            "all_prior_families": I.ALL_PRIOR_FAMILY_SEQUENCE_SHA256,
            "all_prior_unrepresented_families":
                I.ALL_PRIOR_UNREPRESENTED_FAMILY_SEQUENCE_SHA256,
            "all_unique_problem_hashes":
                I.ALL_UNIQUE_PROBLEM_HASHES_SHA256,
            "candidate_records": I.CANDIDATE_RECORDS_SHA256,
            "cost_problem_hashes": I.COST_PROBLEM_HASHES_SHA256,
            "directories": I.DIRECTORY_SEQUENCE_SHA256,
            "family_map": I.FAMILY_MAP_SHA256,
            "prior_problem_hashes": I.PRIOR_PROBLEM_HASHES_SHA256,
            "prior_identities": I.PRIOR_IDENTITIES_SHA256,
            "prior_identity_ledger": I.PRIOR_IDENTITY_LEDGER_SHA256,
            "prior_directory_family_map":
                I.PRIOR_DIRECTORY_FAMILY_MAP_SHA256,
            "prior_family_ledger": I.PRIOR_FAMILY_LEDGER_SHA256,
            "represented_all_prior_families":
                I.REPRESENTED_ALL_PRIOR_FAMILY_SEQUENCE_SHA256,
            "residue_identities": I.RESIDUE_IDENTITIES_SHA256,
            "residue_path_records": I.RESIDUE_PATH_RECORDS_SHA256,
            "shadow_families": I.SHADOW_FAMILY_SEQUENCE_SHA256,
            "shadow_unrepresented_families":
                I.SHADOW_UNREPRESENTED_FAMILY_SEQUENCE_SHA256,
            "shadow_problem_hashes": I.SHADOW_PROBLEM_HASHES_SHA256,
        })
        with self.assertRaisesRegex(I.InventoryError, "candidate digest"):
            I._require_digest("candidate", "0" * 64, "1" * 64)

    def test_candidates_and_alias_ledgers_are_canonical(self):
        inventory = self.inventory
        self.assertEqual(
            inventory.candidates,
            tuple(sorted(inventory.candidates, key=I._candidate_sort_key)),
        )
        self.assertEqual(
            len({candidate.problem_sha256 for candidate in inventory.candidates}),
            len(inventory.candidates),
        )
        self.assertEqual(len(inventory.alias_groups), 1640)
        duplicate_groups = [
            group for group in inventory.alias_groups if len(group.aliases) > 1
        ]
        self.assertEqual(len(duplicate_groups), 75)
        self.assertEqual(
            sum(len(group.aliases) - 1 for group in inventory.alias_groups),
            93,
        )
        for group in inventory.alias_groups:
            self.assertEqual(group.problem_sha256, group.canonical.problem_sha256)
            self.assertEqual(group.canonical, group.aliases[0])
            self.assertEqual(
                group.aliases,
                tuple(sorted(group.aliases, key=I._source_key)),
            )
            self.assertTrue(all(
                alias.problem_sha256 == group.problem_sha256
                for alias in group.aliases
            ))

    def test_duplicate_hash_chooses_lexicographically_first_path(self):
        problem_hash = "a" * 64
        domain_hash = "b" * 64

        def candidate(directory, problem, problem_file, domain_file):
            return I.Candidate(
                directory=directory,
                family="family",
                problem=problem,
                domain_file=domain_file,
                problem_file=problem_file,
                domain_sha256=domain_hash,
                problem_sha256=problem_hash,
            )

        later = candidate("z-dir", "p01.pddl", "z-dir/p.pddl", "z-dir/d.pddl")
        first = candidate("a-dir", "p02.pddl", "a-dir/p.pddl", "a-dir/d.pddl")
        candidates, groups = I._canonicalize((later, first))
        self.assertEqual(candidates, (first,))
        self.assertEqual(groups[0].canonical, first)
        self.assertEqual(groups[0].aliases, (first, later))

    def test_duplicate_hash_cannot_cross_conservative_families(self):
        records = tuple(I.Candidate(
            directory=directory,
            family=family,
            problem="p.pddl",
            domain_file=directory + "/domain.pddl",
            problem_file=directory + "/p.pddl",
            domain_sha256="b" * 64,
            problem_sha256="a" * 64,
        ) for directory, family in (("a", "one"), ("b", "two")))
        with self.assertRaisesRegex(I.InventoryError, "crosses"):
            I._canonicalize(records)

    def test_every_prior_problem_hash_is_excluded(self):
        cost = set(I._load_frozen_problem_hashes(
            I.COST_MANIFEST_PATH,
            I.COST_MANIFEST_SHA256,
            I.EXPECTED_COST_RECORDS,
        ))
        shadow = set(I._load_frozen_problem_hashes(
            I.SHADOW_ATTESTATION_PATH,
            I.SHADOW_ATTESTATION_SHA256,
            I.EXPECTED_SHADOW_RECORDS,
        ))
        prior = cost | shadow
        residual_hashes = {
            alias.problem_sha256
            for group in self.inventory.alias_groups
            for alias in group.aliases
        }
        self.assertEqual(len(prior), 1985)
        self.assertFalse(cost & shadow)
        self.assertFalse(prior & residual_hashes)

    def test_prior_identity_ledger_is_complete_and_source_bound(self):
        ledger = self.inventory.prior_identity_ledger
        identities = {
            I.TaskIdentity(record.directory, record.problem)
            for record in ledger
        }
        self.assertEqual(len(ledger), 2157)
        self.assertEqual(len(identities), 2157)
        self.assertEqual(
            sum(record.source_artifact == I.COST_MANIFEST_PATH.name
                for record in ledger),
            1697,
        )
        self.assertEqual(
            sum(record.source_artifact == I.SHADOW_ATTESTATION_PATH.name
                for record in ledger),
            460,
        )
        self.assertTrue(all(
            record.domain_file is not None
            and record.problem_file is not None
            and record.domain_file.startswith(record.directory + "/")
            and record.problem_file.startswith(record.directory + "/")
            for record in ledger
        ))
        residual_alias_identities = {
            I.TaskIdentity(alias.directory, alias.problem)
            for group in self.inventory.alias_groups
            for alias in group.aliases
        }
        self.assertEqual(
            residual_alias_identities,
            set(self.inventory.residue_identities),
        )
        self.assertFalse(identities & residual_alias_identities)

    def test_all_prior_family_ledger_is_complete(self):
        identity_ledger = self.inventory.prior_identity_ledger
        family_ledger = self.inventory.prior_family_ledger
        self.assertEqual(len(family_ledger), 2157)
        self.assertEqual(len(I.PRIOR_DIRECTORY_TO_FAMILY), 105)
        self.assertEqual(
            {record.directory for record in identity_ledger},
            set(I.PRIOR_DIRECTORY_TO_FAMILY),
        )
        self.assertEqual(len(I.ALL_PRIOR_FAMILIES), 52)
        self.assertEqual(
            set(I.ALL_PRIOR_FAMILIES),
            {record.family for record in family_ledger},
        )
        for identity, family in zip(identity_ledger, family_ledger):
            self.assertEqual(family.source_artifact, identity.source_artifact)
            self.assertEqual(family.directory, identity.directory)
            self.assertEqual(family.problem, identity.problem)
            self.assertEqual(family.problem_sha256, identity.problem_sha256)
            self.assertEqual(
                family.family,
                I.PRIOR_DIRECTORY_TO_FAMILY[family.directory],
            )
        self.assertEqual(
            self.inventory.all_prior_unrepresented_families,
            I.ALL_PRIOR_UNREPRESENTED_FAMILIES,
        )
        self.assertEqual(I.ALL_PRIOR_UNREPRESENTED_FAMILIES, (
            "assembly",
            "citycar",
            "data-network",
            "flashfill",
            "folding",
            "labyrinth",
            "optical-telegraphs",
            "petri-net-alignment",
            "philosophers",
            "recharging-robots",
            "ricochet-robots",
            "settlers",
            "spider",
        ))

    def test_prior_family_map_tampering_is_rejected(self):
        missing = dict(I.PRIOR_DIRECTORY_TO_FAMILY)
        missing.pop(next(iter(missing)))
        with (
            mock.patch.object(I, "PRIOR_DIRECTORY_TO_FAMILY", missing),
            self.assertRaisesRegex(I.InventoryError, "incomplete or overbroad"),
        ):
            I._build_prior_family_ledger(
                self.inventory.prior_identity_ledger
            )
        changed = dict(I.PRIOR_DIRECTORY_TO_FAMILY)
        directory = next(iter(changed))
        changed[directory] = "tampered-family"
        with (
            mock.patch.object(I, "PRIOR_DIRECTORY_TO_FAMILY", changed),
            self.assertRaisesRegex(I.InventoryError, "provenance changed"),
        ):
            I._build_prior_family_ledger(
                self.inventory.prior_identity_ledger
            )

    def test_exclusion_removes_every_alias_of_a_prior_hash(self):
        old_hash = "a" * 64
        new_hash = "b" * 64

        def source(directory, problem_hash):
            return I.SourcePath(
                directory=directory,
                problem="p.pddl",
                problem_file=directory + "/p.pddl",
                domain_file=directory + "/domain.pddl",
                domain_sha256="c" * 64,
                problem_sha256=problem_hash,
            )

        residue = I._exclude_prior_paths(
            (source("old-a", old_hash), source("old-b", old_hash),
             source("new", new_hash)),
            set(),
            {old_hash},
        )
        self.assertEqual([record.problem_sha256 for record in residue], [new_hash])

    def test_name_only_leakage_is_excluded(self):
        record = I.SourcePath(
            directory="same-name",
            problem="p.pddl",
            problem_file="same-name/p.pddl",
            domain_file="same-name/domain.pddl",
            domain_sha256="c" * 64,
            problem_sha256="b" * 64,
        )
        residue = I._exclude_prior_paths(
            (record,),
            {I.TaskIdentity("same-name", "p.pddl")},
            {"a" * 64},
        )
        self.assertEqual(residue, ())

    def test_hash_only_leakage_is_excluded(self):
        record = I.SourcePath(
            directory="new-name",
            problem="new.pddl",
            problem_file="new-name/new.pddl",
            domain_file="new-name/domain.pddl",
            domain_sha256="c" * 64,
            problem_sha256="a" * 64,
        )
        residue = I._exclude_prior_paths(
            (record,),
            {I.TaskIdentity("old-name", "old.pddl")},
            {"a" * 64},
        )
        self.assertEqual(residue, ())

    def test_family_map_is_explicit_complete_and_conservative(self):
        self.assertEqual(
            set(self.inventory.residue_directories),
            set(I.DIRECTORY_TO_FAMILY),
        )
        self.assertEqual(len(I.DIRECTORY_TO_FAMILY), 79)
        self.assertEqual(len(set(I.DIRECTORY_TO_FAMILY.values())), 43)
        changed = dict(I.DIRECTORY_TO_FAMILY)
        changed.pop(next(iter(changed)))
        with (
            mock.patch.object(I, "DIRECTORY_TO_FAMILY", changed),
            self.assertRaisesRegex(I.InventoryError, "incomplete or overbroad"),
        ):
            I._validate_family_map(self.inventory.residue_directories)

    def test_candidate_exposes_source_and_prior_family_provenance(self):
        for candidate in self.inventory.candidates:
            self.assertEqual(candidate.canonical_path, candidate.problem_file)
            self.assertEqual(
                candidate.is_shadow_family,
                candidate.family in I.SHADOW_FAMILIES,
            )
            self.assertEqual(
                candidate.is_shadow_unrepresented,
                candidate.family not in I.SHADOW_FAMILIES,
            )
            self.assertEqual(
                candidate.is_all_prior_represented,
                candidate.family in I.ALL_PRIOR_FAMILIES,
            )
            self.assertEqual(
                candidate.is_all_prior_unrepresented,
                candidate.family in I.ALL_PRIOR_UNREPRESENTED_FAMILIES,
            )
        self.assertEqual(
            set(self.inventory.represented_shadow_families)
            | set(self.inventory.shadow_unrepresented_families),
            set(self.inventory.residue_families),
        )
        self.assertFalse(
            set(self.inventory.represented_shadow_families)
            & set(self.inventory.shadow_unrepresented_families)
        )
        self.assertEqual(
            set(self.inventory.represented_all_prior_families)
            | set(self.inventory.all_prior_unrepresented_families),
            set(self.inventory.residue_families),
        )
        self.assertFalse(
            set(self.inventory.represented_all_prior_families)
            & set(self.inventory.all_prior_unrepresented_families)
        )

    def test_wrong_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with mock.patch.object(
                I,
                "_repository_state",
                return_value=("0" * 40, str(root), ""),
            ):
                with self.assertRaisesRegex(I.InventoryError, "wrong revision"):
                    I.validate_benchmark_checkout(root)

    def test_dirty_checkout_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with mock.patch.object(
                I,
                "_repository_state",
                return_value=(I.BENCHMARK_REVISION, str(root), "?? new.pddl"),
            ):
                with self.assertRaisesRegex(I.InventoryError, "dirty"):
                    I.validate_benchmark_checkout(root)

    def test_prior_artifact_byte_change_is_rejected(self):
        with mock.patch.object(I, "sha256_file", return_value="0" * 64):
            with self.assertRaisesRegex(I.InventoryError, "bytes changed"):
                I._load_frozen_problem_hashes(
                    I.COST_MANIFEST_PATH,
                    I.COST_MANIFEST_SHA256,
                    I.EXPECTED_COST_RECORDS,
                )

    def test_prior_identity_tampering_is_rejected(self):
        common = {
            "domain": "airport",
            "problem": "p.pddl",
            "domain_sha256": "a" * 64,
            "problem_sha256": "b" * 64,
        }
        changed_name = dict(common)
        changed_name["problem"] = ""
        with self.assertRaisesRegex(I.InventoryError, "identity record"):
            I._normalize_prior_records(
                [changed_name], "artifact.json", paths_required=False
            )
        changed_path = dict(common)
        changed_path.update({
            "domain_file": "other/domain.pddl",
            "problem_file": "airport/p.pddl",
        })
        with self.assertRaisesRegex(I.InventoryError, "source path"):
            I._normalize_prior_records(
                [changed_path], "artifact.json", paths_required=True
            )


if __name__ == "__main__":
    unittest.main()
