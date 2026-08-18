#!/usr/bin/env python3
"""Build and verify the analysis-only anonymous P4/P5 source snapshot.

The snapshot is a deterministic uncompressed tar archive containing an exact
allowlist of historical P4/P5 analysis sources and accepted aggregate JSON.
It contains no Git metadata.  Five allocation literals and one institutional
compute-node pattern are replaced by public sentinels.  The historical
``git rev-parse HEAD`` lookup is replaced by an explicit P4/P5 analysis-stage
binding, and both runner ``main`` entry points fail immediately: this tree is
for numerical/scientific reanalysis, never experiment launch.

Private audit identity and public identity are deliberately separate.  This
builder pins the exact historical commits, blob object IDs, raw sizes, and raw
SHA-256 digests, but the public MANIFEST.json records only transformed-file
identities and a public content digest.  Historical 40-hex revision values
necessarily remain in scientific provenance fields and validation contracts;
their exact multiset is checked.  Consequently the archive is free of
personal/machine/account/path tokens but is not unlinkable to published Git
objects.  Matching repository objects must remain unpublished during blind
review.
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
import tempfile


SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY = SCRIPT_DIR.parent
SNAPSHOT_ROOT = "arrhenius-public-analysis-source"
MANIFEST_NAME = "MANIFEST.json"
SNAPSHOT_PROTOCOL = "arrhenius-public-analysis-source-snapshot/v1"
P4_ARTIFACT_FREEZE = "da50f09886bed8c09c73ec5358e49cdde2ce0832"
P5_ANALYSIS_FREEZE = "3255868fcf059c1e94f0377fb98a0d1551349f9f"
PUBLIC_ACCOUNT = "artifact-account"
PUBLIC_NODE = "artifact-node"


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileIdentity:
    size: int
    sha256: str


@dataclass(frozen=True)
class SourceEntry:
    path: str
    mode: int
    p5_blob_sha1: str
    private: FileIdentity
    public: FileIdentity
    rewrites: tuple[str, ...] = ()
    p4_blob_sha1: str | None = None


def _entry(
    path,
    mode,
    p5_blob,
    private_size,
    private_sha256,
    public_size,
    public_sha256,
    rewrites=(),
    p4_blob=None,
):
    return SourceEntry(
        path,
        mode,
        p5_blob,
        FileIdentity(private_size, private_sha256),
        FileIdentity(public_size, public_sha256),
        tuple(rewrites),
        p4_blob,
    )


# These pins are the private historical audit contract.  They are not copied
# into the public snapshot manifest.  A p4_blob_sha1 means the byte-exact P5
# source must also exist under that identical blob identity at the P4 freeze.
SOURCE_ENTRIES = (
    _entry(
        "experiments/analyze_arrhenius_selector_pilot.py",
        0o644,
        "cce9aa6cf7e166f89574506db4b34d732b44da16",
        176939,
        "6b9aa46c2670e89727ceee6d8ae9922d21c8bd818a770327219abd9cfb026f84",
        177085,
        "439cbd1b0c0d980e2d3677235b581365d749ec5eff14a3b24dcdb75b936a1948",
        ("allocation", "analysis-stage-gate"),
        "cce9aa6cf7e166f89574506db4b34d732b44da16",
    ),
    _entry(
        "experiments/analyze_arrhenius_selector_validation.py",
        0o644,
        "fbe745b93e039cf78b650f7a4ff09bc9c8f19094",
        105283,
        "3c85051dfa14383d785b4daf7f00e907fea6522940c02f7973862c4e3308e22d",
        105429,
        "c8a9750bcd915611b5c1ec5287b0ee97e01d46c2b683700f0cb8b65bc5468799",
        ("allocation", "analysis-stage-gate"),
    ),
    _entry(
        "experiments/analyze_ms_caps_pilot.py",
        0o755,
        "cb29417e075cbf955163949995117f84f94692f0",
        43903,
        "d49b311d8daa375956b8adde5a4e8fdb7a45760656acea147f2bb1ebb4026f20",
        43903,
        "d49b311d8daa375956b8adde5a4e8fdb7a45760656acea147f2bb1ebb4026f20",
        (),
        "cb29417e075cbf955163949995117f84f94692f0",
    ),
    _entry(
        "experiments/artifacts/arrhenius-selector-heldout-p5/analysis-v3.json",
        0o644,
        "451b0b7e0cf116123dfb4f2bc3bad33f8c44b02e",
        30647,
        "7c598f068164224272b8ba035b987973f35d0d45e695f90c9083931790908cea",
        30647,
        "7c598f068164224272b8ba035b987973f35d0d45e695f90c9083931790908cea",
    ),
    _entry(
        "experiments/artifacts/arrhenius-selector-screen-p4/certified-report-v2.json",
        0o644,
        "46eb936084a814ebcb361b392bdde40ee03ad06b",
        58870,
        "e75daadefc6cf3cad3121ffb28959659dbc78523970945d575a97b18a319252c",
        58870,
        "e75daadefc6cf3cad3121ffb28959659dbc78523970945d575a97b18a319252c",
        (),
        "46eb936084a814ebcb361b392bdde40ee03ad06b",
    ),
    _entry(
        "experiments/artifacts/arrhenius-selector-screen-p4/selection-v3.json",
        0o644,
        "efec56125c6b8463179710185b31a3050d3d9051",
        30744,
        "d35a1df68eebbd099fe81f86e6e0f6a96ce770572574f9ae013ab4eb0b2c8eb2",
        30744,
        "d35a1df68eebbd099fe81f86e6e0f6a96ce770572574f9ae013ab4eb0b2c8eb2",
        (),
        "efec56125c6b8463179710185b31a3050d3d9051",
    ),
    _entry(
        "experiments/exp_arrhenius_common.py",
        0o644,
        "7c91e967190892e62fcdf55f297f50576ac517d0",
        130255,
        "1cf7065f61d89d157f4e3ebe49153d75d929ef839c05209861504ad34e2178b6",
        130537,
        "cafb5e763d2bf77df3a1d01f7b77d6ad428dded467d425ea30ce5a173f4d5b7e",
        ("allocation-default", "stage-revision", "node-host-pattern"),
        "7c91e967190892e62fcdf55f297f50576ac517d0",
    ),
    _entry(
        "experiments/exp_arrhenius_selector_pilot.py",
        0o644,
        "f9b8f6ec74cba0bfe98570559d254743fe8d2b9d",
        72125,
        "11d15a6e1e414a37e8c4009a2292cae8dccbd367e6324eacb9a17b2307f6129e",
        72229,
        "eda31b671ba558dd3efd36535dd9d2c6a45de248c62d667e64d432b2921e8cf8",
        ("allocation", "runner-main-disabled"),
        "f9b8f6ec74cba0bfe98570559d254743fe8d2b9d",
    ),
    _entry(
        "experiments/exp_arrhenius_selector_validation.py",
        0o644,
        "2a21434a0bbc51e7aafaa1937293a2fedc1d734a",
        116713,
        "86e8efe98be412bde636663fd0ea579dc5792a9407ce68eb313c40b6a94a8582",
        116817,
        "fc71d9a136d1b67adfaa5a38242b0a7e4f5e37c3c3f3a0054aeadc1ad5337d8a",
        ("allocation", "runner-main-disabled"),
    ),
    _entry(
        "experiments/heuristic_finalists_validation_suite.txt",
        0o644,
        "848015ce20beea1d1f585944207f4e97138d9352",
        3971,
        "08e20e6e37e7a2a3a1bf395766b748e3b3ec74a5c626c67c3c759381b1f4e1c5",
        3971,
        "08e20e6e37e7a2a3a1bf395766b748e3b3ec74a5c626c67c3c759381b1f4e1c5",
    ),
    _entry(
        "experiments/requirements.txt",
        0o644,
        "0947ffcc1b58d604221a36835c9b75adb57b8e89",
        269,
        "7408736632aaa534614e319322fe09a5ca9bb8e0874d7b6e7096a940e4bcfb63",
        269,
        "7408736632aaa534614e319322fe09a5ca9bb8e0874d7b6e7096a940e4bcfb63",
        (),
        "0947ffcc1b58d604221a36835c9b75adb57b8e89",
    ),
    _entry(
        "experiments/selector_pilot_suite.txt",
        0o644,
        "2df4c338b53062d4e64dbc8a77e978b5a72b71dd",
        1708,
        "b83d2ce1e5b4474550cd033bd5cb7726a8f86296745ee34be1c66fdb0239ae2c",
        1708,
        "b83d2ce1e5b4474550cd033bd5cb7726a8f86296745ee34be1c66fdb0239ae2c",
        (),
        "2df4c338b53062d4e64dbc8a77e978b5a72b71dd",
    ),
    _entry(
        "experiments/suite_cost_manifest.py",
        0o644,
        "9ec0e7f3827acba7318dbd1437c7af4b14bbcd5d",
        23420,
        "7ab321838bc8d01ac42bbd37a0c9707ed401bbea41cd9ae7527a242b5c1ec2f8",
        23420,
        "7ab321838bc8d01ac42bbd37a0c9707ed401bbea41cd9ae7527a242b5c1ec2f8",
        (),
        "9ec0e7f3827acba7318dbd1437c7af4b14bbcd5d",
    ),
    _entry(
        "experiments/suite_wbh_operator_costs.json",
        0o644,
        "476176af26f8828eac4031de9d8c8c4a3c10ac24",
        990374,
        "7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168",
        990374,
        "7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168",
        (),
        "476176af26f8828eac4031de9d8c8c4a3c10ac24",
    ),
    _entry(
        "experiments/suite_wbh_operator_costs.json.sha256",
        0o644,
        "e8ad2f819b0d0b24e672727e99998846465207bd",
        96,
        "a57735f84c28436b279b6550f9581839128ca8d805436d40f9709d2d3bfd6fcd",
        96,
        "a57735f84c28436b279b6550f9581839128ca8d805436d40f9709d2d3bfd6fcd",
        (),
        "e8ad2f819b0d0b24e672727e99998846465207bd",
    ),
    _entry(
        "experiments/validate_wbh_log.py",
        0o644,
        "7318d4df2cebd488c5a2d968841c09b51fa77b09",
        17567,
        "956f796a2ff9d977ef7113947e5f0f8ac656015ea9804ab11d7287acdc186da1",
        17567,
        "956f796a2ff9d977ef7113947e5f0f8ac656015ea9804ab11d7287acdc186da1",
        (),
        "7318d4df2cebd488c5a2d968841c09b51fa77b09",
    ),
    _entry(
        "experiments/wbh_parser.py",
        0o644,
        "326662354675f72333cfd7dde3e532ef8fa0f3f1",
        18485,
        "6197bbd52e258ca309f442530d8475b1254229a7ee43fe4bc32ae4ca34052436",
        18485,
        "6197bbd52e258ca309f442530d8475b1254229a7ee43fe4bc32ae4ca34052436",
        (),
        "326662354675f72333cfd7dde3e532ef8fa0f3f1",
    ),
)

ENTRY_BY_PATH = {entry.path: entry for entry in SOURCE_ENTRIES}
if len(ENTRY_BY_PATH) != len(SOURCE_ENTRIES):
    raise AssertionError("duplicate source path")


P4_PROPERTIES = FileIdentity(
    10714087,
    "6b7bfa9515105825e775e33356f61764ed1c555c5273514b87be591ab369529b",
)
P5_PROPERTIES = FileIdentity(
    7966555,
    "4267f384cc6e23d634796fe33efd0054c103d8186df3d4f4fb44f7613c2ce45b",
)
ANALYSIS_OUTPUTS = {
    "p4_selection": FileIdentity(
        30744,
        "249f3a28001c5cce5041c44e5fce2bec2e774861d5f04e41dcb0226ac5d6dba3",
    ),
    "p4_report": FileIdentity(
        58870,
        "36b94e95b0c110e42ef96c935efcc15e628c679b8eaa0ab6004690b1b8db85a3",
    ),
    "p5_analysis": FileIdentity(
        30647,
        "770c778d115f3d8950cd0a3ee3279ad46abc9f598180608e1111f339dfd1edbb",
    ),
}
ANALYSIS_EXCLUSIONS = {
    "p4_selection": (("pilot", "properties_canonical_sha256"),),
    "p4_report": (
        ("identity", "pilot", "properties_canonical_sha256"),
        ("identity", "selection_artifact_raw_sha256"),
    ),
    "p5_analysis": (("execution", "properties_canonical_sha256"),),
}


# Exact transformed-tree 40-hex inventory.  The first six values are real
# scientific/protocol provenance.  The last four are analyzer self-test data.
HISTORICAL_OID_COUNTS = {
    "165b6d2ee29d5d7b6e1bf4c52540c393ba19b54f": 3,
    "48d6a00d482de2384a9e751f9343df58bf5582be": 8,
    "58a3f742d7ac63f391d06c237573f14ad590c187": 7,
    "a52488637a1c054b26dac93fe2eb1a556110a2dd": 3,
    "d6d98ad42f3976cd5cf0c9b17d8fa255354fbfbf": 6,
    "ec8399257de93e0739046a187af4bed0b85e19ce": 3,
}
SYNTHETIC_OID_COUNTS = {
    "0123456789abcdef0123456789abcdef01234567": 2,
    "1234567890abcdef1234567890abcdef12345678": 1,
    "89abcdef0123456789abcdef0123456789abcdef": 3,
    "fedcba9876543210fedcba9876543210fedcba98": 1,
}
EXPECTED_OID_COUNTS = Counter(HISTORICAL_OID_COUNTS) + Counter(
    SYNTHETIC_OID_COUNTS
)
OID_PATTERN = re.compile(rb"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])")


PRIVATE_TOKEN_PATTERNS = {
    "personal-name": re.compile(rb"(?i)\bjendrik\b"),
    "private-filesystem": re.compile(
        rb"(?i)/(?:nobackup|home|users)/[^\x00\r\n\"']+"
    ),
    "email-address": re.compile(
        rb"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b"
    ),
    "scheduler-allocation": re.compile(
        rb"(?i)\b(?:naiss|snic)[a-z0-9-]*\d[a-z0-9-]*\b"
    ),
    "institution-host": re.compile(
        rb"(?i)\b(?:[a-z0-9-]+\.)*naiss(?:\\?\.)se\b"
    ),
    "compute-node": re.compile(
        rb"(?i)\b(?:n\d{3,}|arrhenius\d+(?:\\?\.[a-z0-9-]+)+)\b"
    ),
    "scheduler-job": re.compile(
        rb"(?i)\b(?:slurm-\d+|job[_ -]?id\s*[=:]\s*\d+)\b"
    ),
}


ORIGINAL_REVISION_BLOCK = b'''REV = subprocess.run(
    ["git", "-C", str(REPO), "rev-parse", "HEAD"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()'''
PUBLIC_REVISION_BLOCK = b'''_PUBLIC_ANALYSIS_PROTOCOL_REVISIONS = {
    "p4": "d6d98ad42f3976cd5cf0c9b17d8fa255354fbfbf",
    "p5": "a52488637a1c054b26dac93fe2eb1a556110a2dd",
}
_PUBLIC_ANALYSIS_STAGE = os.environ.get("WBH_PUBLIC_ANALYSIS_STAGE")
if _PUBLIC_ANALYSIS_STAGE not in _PUBLIC_ANALYSIS_PROTOCOL_REVISIONS:
    raise RuntimeError(
        "public source snapshot requires WBH_PUBLIC_ANALYSIS_STAGE=p4 or p5"
    )
REV = _PUBLIC_ANALYSIS_PROTOCOL_REVISIONS[_PUBLIC_ANALYSIS_STAGE]'''
ORIGINAL_NODE_PATTERN = (
    b'r"arrhenius\\d+\\.hpc\\.arrhenius\\.naiss\\.se|n\\d+", node'
)
PUBLIC_NODE_PATTERN = b'r"artifact-node", node'
ORIGINAL_RUNNER_MAIN = b"def main(argv=None):\n"
PUBLIC_RUNNER_MAIN = b'''def main(argv=None):
    raise ProtocolError(
        "public numerical-reanalysis snapshot: runner entry point disabled"
    )
'''


def _public_analyzer_main(stage):
    return '''def main(argv=None):
    if common._PUBLIC_ANALYSIS_STAGE != {!r}:
        raise AnalysisError(
            "public source snapshot requires {} analysis stage"
        )
'''.format(stage, stage).encode("ascii")


# Filled with exact identities after the canonical manifest/archive format.
# They are deliberately constants rather than values learned from an output.
PUBLIC_CONTENT_SHA256 = (
    "8d0f34d6e05f73ffa55d29327e0bef4cd1ddffb1b7f80afed6718233c87e3a2d"
)
PUBLIC_MANIFEST_IDENTITY = FileIdentity(
    5616,
    "dbb739c6b012a1aef365cee6275916d39fb446b503b217ac6572fd749dcdf125",
)
PUBLIC_ARCHIVE_IDENTITY = FileIdentity(
    1853440,
    "4abbda181734bbe37b89c9aab53771b4e78875c6e4a11280a919fc9bdd671602",
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_json_bytes(value, *, newline=True):
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as err:
        raise SnapshotError("value is not canonical finite JSON: {}".format(err))
    return raw + (b"\n" if newline else b"")


def _reject_duplicate_keys(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            raise SnapshotError("duplicate JSON key {!r}".format(key))
        value[key] = child
    return value


def parse_json_bytes(raw, label):
    def reject_constant(value):
        raise SnapshotError("{} has non-finite constant {}".format(label, value))

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except SnapshotError:
        raise
    except (UnicodeError, json.JSONDecodeError) as err:
        raise SnapshotError("cannot parse {}: {}".format(label, err)) from err
    canonical_json_bytes(value, newline=False)
    return value


def _check_identity(raw, identity, label):
    actual = FileIdentity(len(raw), _sha256(raw))
    if actual != identity:
        raise SnapshotError(
            "{} identity changed: expected {}/{}, got {}/{}".format(
                label,
                identity.size,
                identity.sha256,
                actual.size,
                actual.sha256,
            )
        )


def _fingerprint(status):
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_nlink,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def stable_read(path, *, identity=None, label="input"):
    path = Path(os.path.abspath(Path(path).expanduser()))
    try:
        before = path.lstat()
    except OSError as err:
        raise SnapshotError("cannot inspect {} {}: {}".format(label, path, err))
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise SnapshotError(
            "{} must be a single-link regular non-symlink file".format(label)
        )
    if not hasattr(os, "O_NOFOLLOW"):
        raise SnapshotError("stable read requires O_NOFOLLOW")
    descriptor = -1
    try:
        descriptor = os.open(
            path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        )
        opened = os.fstat(descriptor)
        if _fingerprint(opened) != _fingerprint(before):
            raise SnapshotError("{} changed before read".format(label))
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        if _fingerprint(os.fstat(descriptor)) != _fingerprint(before):
            raise SnapshotError("{} changed during read".format(label))
    except OSError as err:
        raise SnapshotError("cannot stably read {}: {}".format(label, err)) from err
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        after = path.lstat()
    except OSError as err:
        raise SnapshotError("{} disappeared: {}".format(label, err))
    if _fingerprint(after) != _fingerprint(before):
        raise SnapshotError("{} path identity changed after read".format(label))
    raw = b"".join(chunks)
    if identity is not None:
        _check_identity(raw, identity, label)
    return raw


def _git(args):
    command = ["git", "-C", str(REPOSITORY)] + list(args)
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as err:
        raise SnapshotError("historical Git read failed: {}".format(err)) from err
    return result.stdout


def _git_source(revision, path):
    if revision not in (P4_ARTIFACT_FREEZE, P5_ANALYSIS_FREEZE):
        raise SnapshotError("unreviewed historical revision")
    if path not in ENTRY_BY_PATH:
        raise SnapshotError("unreviewed historical source path")
    commit = _git(["rev-parse", "{}^{{commit}}".format(revision)]).decode().strip()
    if commit != revision:
        raise SnapshotError("historical commit identity changed")
    raw = _git(["cat-file", "blob", "{}:{}".format(revision, path)])
    line = _git(["ls-tree", revision, "--", path]).decode("ascii").strip()
    match = re.fullmatch(r"(100644|100755) blob ([0-9a-f]{40})\t(.+)", line)
    if not match or match.group(3) != path:
        raise SnapshotError("historical tree entry changed for {}".format(path))
    return raw, int(match.group(1)[-3:], 8), match.group(2)


def _load_and_attest_private_sources(source_loader=_git_source):
    private = {}
    for entry in SOURCE_ENTRIES:
        raw, mode, blob = source_loader(P5_ANALYSIS_FREEZE, entry.path)
        if mode != entry.mode or blob != entry.p5_blob_sha1:
            raise SnapshotError("P5 tree identity changed for {}".format(entry.path))
        _check_identity(raw, entry.private, "private P5 source {}".format(entry.path))
        if entry.p4_blob_sha1 is not None:
            p4_raw, p4_mode, p4_blob = source_loader(
                P4_ARTIFACT_FREEZE, entry.path
            )
            if (
                p4_mode != entry.mode
                or p4_blob != entry.p4_blob_sha1
                or p4_raw != raw
                or entry.p4_blob_sha1 != entry.p5_blob_sha1
            ):
                raise SnapshotError(
                    "P4/P5 shared historical source differs for {}".format(entry.path)
                )
        private[entry.path] = raw
    return private


def _replace_exact(raw, before, after, *, count, name, path):
    actual = raw.count(before)
    if actual != count:
        raise SnapshotError(
            "{} rewrite occurrence drift in {}: expected {}, got {}".format(
                name, path, count, actual
            )
        )
    return raw.replace(before, after)


def _apply_rewrites(path, raw):
    if path in {
        "experiments/analyze_arrhenius_selector_pilot.py",
        "experiments/analyze_arrhenius_selector_validation.py",
        "experiments/exp_arrhenius_selector_pilot.py",
        "experiments/exp_arrhenius_selector_validation.py",
    }:
        raw = _replace_exact(
            raw,
            b"naiss2025-5-561-cpu",
            PUBLIC_ACCOUNT.encode("ascii"),
            count=1,
            name="allocation",
            path=path,
        )
    analyzer_stages = {
        "experiments/analyze_arrhenius_selector_pilot.py": "p4",
        "experiments/analyze_arrhenius_selector_validation.py": "p5",
    }
    if path in analyzer_stages:
        raw = _replace_exact(
            raw,
            ORIGINAL_RUNNER_MAIN,
            _public_analyzer_main(analyzer_stages[path]),
            count=1,
            name="analysis-stage-gate",
            path=path,
        )
    if path == "experiments/exp_arrhenius_common.py":
        raw = _replace_exact(
            raw,
            b"naiss2025-5-382-cpu",
            PUBLIC_ACCOUNT.encode("ascii"),
            count=1,
            name="allocation-default",
            path=path,
        )
        raw = _replace_exact(
            raw,
            ORIGINAL_REVISION_BLOCK,
            PUBLIC_REVISION_BLOCK,
            count=1,
            name="stage-revision",
            path=path,
        )
        raw = _replace_exact(
            raw,
            ORIGINAL_NODE_PATTERN,
            PUBLIC_NODE_PATTERN,
            count=1,
            name="node-host-pattern",
            path=path,
        )
    if path in {
        "experiments/exp_arrhenius_selector_pilot.py",
        "experiments/exp_arrhenius_selector_validation.py",
    }:
        raw = _replace_exact(
            raw,
            ORIGINAL_RUNNER_MAIN,
            PUBLIC_RUNNER_MAIN,
            count=1,
            name="runner-main-disabled",
            path=path,
        )
    return raw


def _scan_private_tokens(files):
    hits = []
    for path, raw in sorted(files.items()):
        path_raw = path.encode("utf-8")
        for name, pattern in PRIVATE_TOKEN_PATTERNS.items():
            if pattern.search(path_raw) or pattern.search(raw):
                hits.append((path, name))
    if hits:
        raise SnapshotError(
            "private-token scan failed: {}".format(
                ", ".join("{}:{}".format(path, name) for path, name in hits)
            )
        )


def _scan_oid_inventory(files):
    counts = Counter()
    for raw in files.values():
        counts.update(match.decode("ascii") for match in OID_PATTERN.findall(raw))
    if counts != EXPECTED_OID_COUNTS:
        raise SnapshotError("embedded 40-hex identity inventory changed")
    return {
        "historical_occurrences": sum(HISTORICAL_OID_COUNTS.values()),
        "historical_unique": len(HISTORICAL_OID_COUNTS),
        "synthetic_occurrences": sum(SYNTHETIC_OID_COUNTS.values()),
        "synthetic_unique": len(SYNTHETIC_OID_COUNTS),
        "total_occurrences": sum(counts.values()),
        "total_unique": len(counts),
    }


def _build_public_payloads(source_loader=_git_source):
    private = _load_and_attest_private_sources(source_loader)
    public = {}
    for entry in SOURCE_ENTRIES:
        raw = _apply_rewrites(entry.path, private[entry.path])
        _check_identity(raw, entry.public, "public source {}".format(entry.path))
        public[entry.path] = raw
    _scan_private_tokens(public)
    _scan_oid_inventory(public)
    return public


def _public_inventory():
    return [
        {
            "mode": "{:04o}".format(entry.mode),
            "path": entry.path,
            "rewrites": list(entry.rewrites),
            "sha256": entry.public.sha256,
            "size": entry.public.size,
        }
        for entry in SOURCE_ENTRIES
    ]


def _content_sha256():
    return _sha256(canonical_json_bytes(_public_inventory(), newline=False))


def _manifest_value():
    return {
        "analysis": {
            "excluded_identity_paths": {
                name: [".".join(path) for path in ANALYSIS_EXCLUSIONS[name]]
                for name in sorted(ANALYSIS_EXCLUSIONS)
            },
            "output_identities": {
                name: {
                    "sha256": identity.sha256,
                    "size": identity.size,
                }
                for name, identity in sorted(ANALYSIS_OUTPUTS.items())
            },
            "purpose": "numerical-and-scientific-reanalysis-only",
        },
        "content_sha256": PUBLIC_CONTENT_SHA256,
        "historical_provenance": {
            "blind_review_requirement": (
                "All matching source objects, refs, artifacts, projected records, "
                "forks, caches, and object-lookup services must remain unpublished "
                "and inaccessible for the duration of blind review."
            ),
            "embedded_40_hex_tokens": {
                "historical_occurrences": 30,
                "historical_unique": 6,
                "synthetic_self_test_occurrences": 7,
                "synthetic_self_test_unique": 4,
            },
            "private_audit_contract": (
                "The builder pins exact historical commits, blob objects, raw sizes, "
                "and raw SHA-256 identities; those private pins are intentionally "
                "absent from this anonymous public manifest."
            ),
            "warning": (
                "Historical revision values remain in scientific provenance and "
                "validation fields, so this snapshot is not cryptographically "
                "unlinkable to repository objects if those objects are public."
            ),
        },
        "launch_entry_points": {
            "runners": [
                "experiments/exp_arrhenius_selector_pilot.py",
                "experiments/exp_arrhenius_selector_validation.py",
            ],
            "status": "intentionally-disabled",
            "supported_claim": "numerical/scientific reanalysis only; no launch",
        },
        "private_token_scan": {
            "expected_hits": 0,
            "patterns": sorted(PRIVATE_TOKEN_PATTERNS),
        },
        "projected_properties": {
            "p4": {
                "sha256": P4_PROPERTIES.sha256,
                "size": P4_PROPERTIES.size,
            },
            "p5": {
                "sha256": P5_PROPERTIES.sha256,
                "size": P5_PROPERTIES.size,
            },
            "protocol": "arrhenius-public-properties/exact-four-field-normalization/v1",
        },
        "runtime": {
            "python": "3.9.25",
            "requirements_path": "experiments/requirements.txt",
            "requirements_sha256": ENTRY_BY_PATH[
                "experiments/requirements.txt"
            ].public.sha256,
        },
        "schema": SNAPSHOT_PROTOCOL,
        "source_files": _public_inventory(),
    }


def _manifest_bytes():
    if _content_sha256() != PUBLIC_CONTENT_SHA256:
        raise SnapshotError("public content identity constant changed")
    raw = canonical_json_bytes(_manifest_value())
    _check_identity(raw, PUBLIC_MANIFEST_IDENTITY, "public manifest")
    return raw


def _all_payloads(source_loader=_git_source):
    files = _build_public_payloads(source_loader)
    files[MANIFEST_NAME] = _manifest_bytes()
    _scan_private_tokens(files)
    _scan_oid_inventory(files)
    return files


def _directory_names(file_paths):
    directories = {SNAPSHOT_ROOT}
    for path in file_paths:
        pure = PurePosixPath(SNAPSHOT_ROOT) / path
        for parent in pure.parents:
            if parent.as_posix() == ".":
                continue
            directories.add(parent.as_posix())
    return directories


def _tar_info(name, *, mode, size=0, directory=False):
    info = tarfile.TarInfo(name)
    info.mode = mode
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.size = 0 if directory else size
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.linkname = ""
    return info


def _assemble_archive(files):
    stream = io.BytesIO()
    with tarfile.open(
        fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT
    ) as archive:
        members = []
        for directory in _directory_names(files):
            members.append((directory, True, None))
        for path, raw in files.items():
            members.append(
                (
                    "{}/{}".format(SNAPSHOT_ROOT, path),
                    False,
                    raw,
                )
            )
        for name, directory, raw in sorted(members):
            if directory:
                archive.addfile(_tar_info(name, mode=0o755, directory=True))
            else:
                relative = name[len(SNAPSHOT_ROOT) + 1 :]
                mode = 0o644 if relative == MANIFEST_NAME else ENTRY_BY_PATH[
                    relative
                ].mode
                archive.addfile(
                    _tar_info(name, mode=mode, size=len(raw)), io.BytesIO(raw)
                )
    return stream.getvalue()


def build_snapshot_bytes(*, source_loader=_git_source, enforce_identity=True):
    raw = _assemble_archive(_all_payloads(source_loader))
    if enforce_identity:
        _check_identity(raw, PUBLIC_ARCHIVE_IDENTITY, "public source archive")
    return raw


def _expected_payload_identities():
    result = {entry.path: (entry.mode, entry.public) for entry in SOURCE_ENTRIES}
    result[MANIFEST_NAME] = (0o644, PUBLIC_MANIFEST_IDENTITY)
    return result


def verify_snapshot_bytes(raw, *, enforce_archive_identity=True):
    if enforce_archive_identity:
        _check_identity(raw, PUBLIC_ARCHIVE_IDENTITY, "public source archive")
    expected_files = _expected_payload_identities()
    expected_directories = _directory_names(expected_files)
    files = {}
    seen = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            for member in archive:
                if member.name in seen:
                    raise SnapshotError("duplicate archive member {}".format(member.name))
                seen.add(member.name)
                if (
                    member.uid != 0
                    or member.gid != 0
                    or member.uname != ""
                    or member.gname != ""
                    or member.mtime != 0
                    or member.linkname != ""
                    or member.pax_headers
                ):
                    raise SnapshotError(
                        "noncanonical archive metadata for {}".format(member.name)
                    )
                if member.isdir():
                    if (
                        member.name not in expected_directories
                        or member.mode != 0o755
                        or member.size != 0
                        or member.type != tarfile.DIRTYPE
                    ):
                        raise SnapshotError(
                            "unexpected directory member {}".format(member.name)
                        )
                    continue
                prefix = SNAPSHOT_ROOT + "/"
                if not member.name.startswith(prefix):
                    raise SnapshotError("archive member escapes snapshot root")
                relative = member.name[len(prefix) :]
                if (
                    relative not in expected_files
                    or not member.isreg()
                    or member.type != tarfile.REGTYPE
                ):
                    raise SnapshotError(
                        "unexpected/non-regular archive member {}".format(member.name)
                    )
                expected_mode, identity = expected_files[relative]
                if member.mode != expected_mode:
                    raise SnapshotError("archive mode changed for {}".format(relative))
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise SnapshotError("cannot read archive member {}".format(relative))
                payload = extracted.read()
                _check_identity(payload, identity, "archive member {}".format(relative))
                files[relative] = payload
    except SnapshotError:
        raise
    except (tarfile.TarError, OSError, EOFError) as err:
        raise SnapshotError("cannot parse source archive: {}".format(err)) from err
    if seen != {
        *expected_directories,
        *("{}/{}".format(SNAPSHOT_ROOT, path) for path in expected_files),
    }:
        raise SnapshotError("archive member allowlist changed")
    if set(files) != set(expected_files):
        raise SnapshotError("archive file allowlist changed")
    manifest_raw = files[MANIFEST_NAME]
    manifest = parse_json_bytes(manifest_raw, MANIFEST_NAME)
    if canonical_json_bytes(manifest) != manifest_raw or manifest != _manifest_value():
        raise SnapshotError("public manifest is noncanonical or changed")
    _scan_private_tokens(files)
    oid_summary = _scan_oid_inventory(files)
    return files, manifest, oid_summary


def verify_snapshot_file(path):
    raw = stable_read(path, identity=PUBLIC_ARCHIVE_IDENTITY, label="source archive")
    return verify_snapshot_bytes(raw)


def _write_new(path, raw):
    path = Path(os.path.abspath(Path(path).expanduser()))
    if path.suffix != ".tar":
        raise SnapshotError("output must use the .tar suffix")
    try:
        parent = path.parent.resolve(strict=True)
        parent_status = parent.lstat()
    except OSError as err:
        raise SnapshotError("cannot inspect output parent: {}".format(err))
    if not stat.S_ISDIR(parent_status.st_mode):
        raise SnapshotError("output parent is not a directory")
    path = parent / path.name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(path, flags, 0o644)
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short archive write")
            view = view[written:]
        os.fchmod(descriptor, 0o644)
        os.fsync(descriptor)
    except OSError as err:
        raise SnapshotError("cannot create source archive: {}".format(err)) from err
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    stable_read(path, identity=PUBLIC_ARCHIVE_IDENTITY, label="new source archive")
    return path


def build_snapshot_file(path):
    raw = build_snapshot_bytes()
    output = _write_new(path, raw)
    verify_snapshot_file(output)
    return output


def _materialize(files, destination):
    root = Path(destination) / SNAPSHOT_ROOT
    root.mkdir(mode=0o755)
    for directory in sorted(_directory_names(files), key=lambda value: (value.count("/"), value)):
        if directory == SNAPSHOT_ROOT:
            continue
        relative = directory[len(SNAPSHOT_ROOT) + 1 :]
        (root / relative).mkdir(mode=0o755)
    for relative, raw in sorted(files.items()):
        mode = 0o644 if relative == MANIFEST_NAME else ENTRY_BY_PATH[relative].mode
        target = root / relative
        descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            mode,
        )
        try:
            view = memoryview(raw)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short snapshot write")
                view = view[written:]
            os.fchmod(descriptor, mode)
        finally:
            os.close(descriptor)
    return root


def _runtime_attestation(python, requirements_raw):
    requirements = ENTRY_BY_PATH["experiments/requirements.txt"]
    _check_identity(
        requirements_raw, requirements.public, "public runtime requirements"
    )
    pins = {}
    for line in requirements_raw.decode("ascii").splitlines():
        if line.count("==") != 1:
            raise SnapshotError("requirements pin format changed")
        name, version = line.split("==")
        pins[name] = version
    code = (
        "import json,platform;from importlib import metadata;"
        "pins=json.loads({!r});"
        "print(json.dumps({{'python':platform.python_version(),"
        "'packages':{{k:metadata.version(k) for k in pins}}}},"
        "sort_keys=True,separators=(',',':')))"
    ).format(json.dumps(pins, sort_keys=True))
    try:
        result = subprocess.run(
            [str(python), "-I", "-c", code],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PYTHONDONTWRITEBYTECODE": "1"},
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as err:
        raise SnapshotError("runtime attestation failed: {}".format(err)) from err
    if result.stderr:
        raise SnapshotError("runtime attestation wrote stderr")
    value = parse_json_bytes(result.stdout, "runtime attestation")
    if value != {"python": "3.9.25", "packages": pins}:
        raise SnapshotError("Python/package environment differs from requirements")
    return value


def _pop_digest(value, path):
    current = value
    for key in path[:-1]:
        if not isinstance(current, dict) or key not in current:
            raise SnapshotError("missing excluded path {}".format(".".join(path)))
        current = current[key]
    leaf = path[-1]
    if not isinstance(current, dict) or leaf not in current:
        raise SnapshotError("missing excluded path {}".format(".".join(path)))
    removed = current.pop(leaf)
    if not isinstance(removed, str) or not re.fullmatch(r"[0-9a-f]{64}", removed):
        raise SnapshotError("excluded path is not a SHA-256")
    return removed


def compare_modulo_exclusions(actual, accepted, exclusions, label):
    actual = copy.deepcopy(actual)
    accepted = copy.deepcopy(accepted)
    removed = []
    for path in exclusions:
        removed.append(
            {
                "path": ".".join(path),
                "generated": _pop_digest(actual, path),
                "accepted": _pop_digest(accepted, path),
            }
        )
    if canonical_json_bytes(actual, newline=False) != canonical_json_bytes(
        accepted, newline=False
    ):
        raise SnapshotError(
            "{} differs outside declared digest identities".format(label)
        )
    return removed


def _run_analysis(python, script, arguments, *, stage, cwd):
    environment = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "WBH_ACCOUNT": PUBLIC_ACCOUNT,
        "WBH_PUBLIC_ANALYSIS_STAGE": stage,
    }
    try:
        result = subprocess.run(
            [str(python), str(script)] + [str(value) for value in arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=environment,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as err:
        raise SnapshotError("historical analysis failed: {}".format(err)) from err
    if result.stderr:
        raise SnapshotError("historical analysis wrote stderr")
    return result.stdout


def verify_analysis(archive, p4_properties, p5_properties, *, python=sys.executable):
    archive_files, _, _ = verify_snapshot_file(archive)
    p4_properties = Path(os.path.abspath(Path(p4_properties).expanduser()))
    p5_properties = Path(os.path.abspath(Path(p5_properties).expanduser()))
    python = Path(os.path.abspath(Path(python).expanduser()))
    stable_read(p4_properties, identity=P4_PROPERTIES, label="public P4 properties")
    stable_read(p5_properties, identity=P5_PROPERTIES, label="public P5 properties")
    runtime = _runtime_attestation(
        python, archive_files["experiments/requirements.txt"]
    )
    with tempfile.TemporaryDirectory() as directory:
        root = _materialize(archive_files, directory)
        experiments = root / "experiments"
        generated_raw = {
            "p4_selection": _run_analysis(
                python,
                experiments / "analyze_arrhenius_selector_pilot.py",
                [p4_properties, "--emit-selection-artifact"],
                stage="p4",
                cwd=root,
            ),
            "p4_report": _run_analysis(
                python,
                experiments / "analyze_arrhenius_selector_pilot.py",
                [p4_properties, "--emit-reporting-json"],
                stage="p4",
                cwd=root,
            ),
            "p5_analysis": _run_analysis(
                python,
                experiments / "analyze_arrhenius_selector_validation.py",
                [
                    p5_properties,
                    "--selection",
                    experiments
                    / "artifacts/arrhenius-selector-screen-p4/selection-v3.json",
                ],
                stage="p5",
                cwd=root,
            ),
        }
        accepted_paths = {
            "p4_selection": experiments
            / "artifacts/arrhenius-selector-screen-p4/selection-v3.json",
            "p4_report": experiments
            / "artifacts/arrhenius-selector-screen-p4/certified-report-v2.json",
            "p5_analysis": experiments
            / "artifacts/arrhenius-selector-heldout-p5/analysis-v3.json",
        }
        excluded = {}
        for name in sorted(generated_raw):
            _check_identity(
                generated_raw[name], ANALYSIS_OUTPUTS[name], "generated {}".format(name)
            )
            generated = parse_json_bytes(generated_raw[name], name)
            accepted = parse_json_bytes(
                accepted_paths[name].read_bytes(), "accepted {}".format(name)
            )
            excluded[name] = compare_modulo_exclusions(
                generated,
                accepted,
                ANALYSIS_EXCLUSIONS[name],
                name,
            )
        # PYTHONDONTWRITEBYTECODE and analysis-only behavior must leave the
        # materialized allowlisted tree byte-exact and free of extra files.
        actual_files = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }
        expected_files = {
            path: raw for path, raw in archive_files.items()
        }
        if actual_files != expected_files:
            raise SnapshotError("analysis modified the public source snapshot")
    return {
        "excluded_identities": excluded,
        "p4_records": 1000,
        "p5_records": 644,
        "protocol": SNAPSHOT_PROTOCOL,
        "runtime": runtime,
        "status": "accepted-artifact-equivalent",
    }


def self_test():
    first = build_snapshot_bytes()
    second = build_snapshot_bytes()
    if first != second:
        raise AssertionError("duplicate source builds differ")
    files, manifest, oids = verify_snapshot_bytes(first)
    if manifest["launch_entry_points"]["status"] != "intentionally-disabled":
        raise AssertionError("launch entry points are not disabled")
    changed = dict(files)
    victim = "experiments/analyze_ms_caps_pilot.py"
    changed[victim] += b"\ncontact=tester@example.invalid\n"
    try:
        _scan_private_tokens(changed)
    except SnapshotError:
        pass
    else:
        raise AssertionError("extra private token was accepted")
    return {
        "archive_sha256": _sha256(first),
        "archive_size": len(first),
        "files": len(files),
        "oid_inventory": oids,
        "protocol": SNAPSHOT_PROTOCOL,
        "status": "PASS",
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Build/verify the analysis-only public P4/P5 source snapshot."
    )
    parser.add_argument("--self-test", action="store_true")
    subparsers = parser.add_subparsers(dest="command")
    build = subparsers.add_parser("build")
    build.add_argument("output", type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("archive", type=Path)
    analysis = subparsers.add_parser("verify-analysis")
    analysis.add_argument("archive", type=Path)
    analysis.add_argument("p4_properties", type=Path)
    analysis.add_argument("p5_properties", type=Path)
    analysis.add_argument("--python", default=sys.executable, type=Path)
    args = parser.parse_args(argv)
    if args.self_test and args.command is not None:
        parser.error("--self-test does not accept a subcommand")
    if not args.self_test and args.command is None:
        parser.error("a subcommand or --self-test is required")
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        result = self_test()
    elif args.command == "build":
        output = build_snapshot_file(args.output)
        result = {
            "archive": str(output),
            "sha256": PUBLIC_ARCHIVE_IDENTITY.sha256,
            "size": PUBLIC_ARCHIVE_IDENTITY.size,
            "status": "built-and-verified",
        }
    elif args.command == "verify":
        files, manifest, oids = verify_snapshot_file(args.archive)
        result = {
            "content_sha256": manifest["content_sha256"],
            "files": len(files),
            "oid_inventory": oids,
            "sha256": PUBLIC_ARCHIVE_IDENTITY.sha256,
            "size": PUBLIC_ARCHIVE_IDENTITY.size,
            "status": "verified",
        }
    else:
        result = verify_analysis(
            args.archive,
            args.p4_properties,
            args.p5_properties,
            python=args.python,
        )
    print(canonical_json_bytes(result).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SnapshotError as err:
        print("snapshot error: {}".format(err), file=sys.stderr)
        sys.exit(2)
