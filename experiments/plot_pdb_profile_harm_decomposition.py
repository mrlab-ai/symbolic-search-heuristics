#!/usr/bin/env python3
"""Plot the post-hoc harm decomposition as a deterministic PDF figure.

Reads the pinned per-pair points of the harm decomposition and draws the
unsplit ratio u = unionEffort(h) / effort(blind) against the fragmentation
factor on log axes.  Since effort(h) / effort(blind) = u * frag, the
anti-diagonals mark heuristic effort equal to and twice blind effort.
The PDF carries no timestamps and embeds TrueType fonts, so --check can
compare it byte for byte.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("pdf")
import matplotlib.pyplot as plt  # noqa: E402

import render_pdb_profile_semantic_union_paper as Common  # noqa: E402


RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_POINTS = (
    SCRIPT_DIR / "artifacts" / "pdb-profile-harm-decomposition" / "points-v1.json"
)
EXPECTED_POINTS_SHA256 = (
    "6a25fa29210d818407be7fecde08d6c01fffc6eae1210c0690fc9b373bc05f95"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "paper" / "generated" / "pdb-profile-harm-decomposition-v1.pdf"
)
MAX_POINTS_BYTES = 4 * 1024 * 1024
MAX_PDF_BYTES = 4 * 1024 * 1024


def _load(path):
    raw = Common._read_regular(path, MAX_POINTS_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_POINTS_SHA256:
        raise RenderError("points artifact is not the reviewed pin")
    sidecar = "{}  {}\n".format(digest, Path(path).name).encode("ascii")
    if Common._read_regular(Path(str(path) + ".sha256"), 256) != sidecar:
        raise RenderError("points sidecar differs from the pinned artifact")
    data = json.loads(raw.decode("ascii"))
    if raw != Common._canonical_json(data) + b"\n":
        raise RenderError("points artifact is not canonical")
    return data


def render(data):
    points = data["points"]
    if not points:
        raise RenderError("no points")
    plt.rcParams.update({
        "pdf.fonttype": 42,
        "font.family": "serif",
        "font.size": 7,
        "axes.linewidth": 0.5,
        "svg.hashsalt": "harm",
    })
    figure, axes = plt.subplots(figsize=(3.25, 2.0))
    helped = [(u, f) for u, f, above, _, _ in points if not above]
    hurt = [(u, f) for u, f, above, _, _ in points if above]
    for group, color, label in ((helped, "0.7", "effort at most blind"),
                                (hurt, "0.1", "effort above blind")):
        if group:
            xs, ys = zip(*group)
            axes.scatter(xs, ys, s=2.0, c=color, linewidths=0, label=label,
                         rasterized=False)
    axes.set_xscale("log")
    axes.set_yscale("log")
    lo_u = min(p[0] for p in points) / 1.2
    hi_u = max(p[0] for p in points) * 1.2
    for ratio, style in ((1.0, "-"), (2.0, "--")):
        xs = [lo_u, hi_u]
        axes.plot(xs, [ratio / x for x in xs], style, color="0.4", linewidth=0.6)
    axes.set_xlim(lo_u, hi_u)
    axes.set_ylim(min(p[1] for p in points) / 1.2, max(p[1] for p in points) * 1.2)
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    axes.xaxis.set_major_locator(FixedLocator([0.03, 0.1, 0.3, 1.0]))
    axes.yaxis.set_major_locator(FixedLocator([1.0, 2.0, 4.0]))
    for axis in (axes.xaxis, axes.yaxis):
        axis.set_minor_locator(NullLocator())
        axis.set_major_formatter(FuncFormatter(lambda value, _: "{:g}".format(value)))
    axes.set_xlabel("unsplit effort / blind effort")
    axes.set_ylabel("fragmentation")
    axes.legend(loc="upper left", frameon=False, markerscale=3, handletextpad=0.2)
    figure.tight_layout(pad=0.2)
    stream = io.BytesIO()
    figure.savefig(stream, format="pdf",
                   metadata={"CreationDate": None, "ModDate": None,
                             "Creator": None, "Producer": None})
    plt.close(figure)
    raw = stream.getvalue()
    if len(raw) > MAX_PDF_BYTES:
        raise RenderError("figure exceeds its size limit")
    return raw


def _write_atomic(path, raw):
    path = Path(path)
    if path.resolve() != DEFAULT_OUTPUT.resolve():
        raise RenderError("--write is restricted to the generated-paper path")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points", type=Path, default=DEFAULT_POINTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    raw = render(_load(args.points))
    if args.write:
        _write_atomic(args.output, raw)
    elif Common._read_regular(args.output, MAX_PDF_BYTES) != raw:
        raise RenderError("generated figure is stale")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RenderError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
