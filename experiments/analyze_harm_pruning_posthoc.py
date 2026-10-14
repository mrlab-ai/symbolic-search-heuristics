#!/usr/bin/env python3
"""Post-hoc pruning view of the frozen harm-generality analysis.

Descriptive and post hoc; changes no frozen estimand or decision.  Uses the
frozen pairing of `analyze_pdb_profile_harm_generality.py` on the pinned
properties and adds the state ratio s = expanded states(h) / expanded
states(blind) of every pair.  It reports, per family and pooled, the medians
of s and of the unsplit ratio u over harmful (r > 1), helpful (r < 1) and
strongly harmful (r > 2) pairs; how often u exceeds s and how often harmful
pairs have u > 1; how many pairs are helpful among those with s < 0.1 and
those with s >= 0.8; the Spearman correlations of s with u and with the
fragmentation factor; the paired comparison of fragmentation between the
aligned and the unaligned M&S configuration with 10,000 states; and the
number of tasks that blind search solves but a heuristic configuration does
not, which no pair covers.  It also reports the medians, over harmful and
helpful pairs, of h(s_0) / C* and of the unshrunk share, the fraction of the
blind effort that lies in layers whose expanded part has as many BDD nodes as
the whole layer; counts the domains in which u exceeds s on most pairs; and it extracts the per-layer BDD sizes of one typical
harmful M&S pair, the one closest to the medians of the harmful M&S pairs in
log s, log u and log fragmentation.  Finally, it resamples the domains with
replacement (a domain-cluster bootstrap with a fixed seed) and reports 95%
percentile intervals of the share S of fragmentation in the harmful log
effort and of the median unsplit ratio of harmful pairs, per family and
pooled.  The oracle view compares, per family and pooled, the effort of
an unsplit search that knows C* and prunes by f, which expands exactly the
sets S_g^h and therefore has effort ratio u, with BDDA* (ratio r): pairs
with u < 1 and with r < 1, and the geometric means of u and r.  It also
counts the neutral pairs (r = 1) and those among them with u = frag = 1.

  analyze  write artifacts/pdb-profile-harm-generality/pruning-v1.json
  render   write paper/generated/pdb-profile-harm-pruning-v1.tex
  figure   write paper/generated/pdb-profile-harm-pruning-v1.pdf
  layers   write paper/generated/pdb-profile-harm-layers-v1.pdf
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import random
import statistics
from fractions import Fraction
from pathlib import Path

import analyze_pdb_profile_harm_generality as Frozen
import pdb_profile_harm_generality_protocol as P
import render_pdb_profile_semantic_union_paper as Common


RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
EXPECTED_PROPERTIES_SHA256 = (
    "451d10ee4c26e5115ca2d88fac50dc97ad8089c7c1782ffe0c014ae940eff105"
)
DEFAULT_ARTIFACT = Frozen.ARTIFACT_DIR / "pruning-v1.json"
EXPECTED_ARTIFACT_SHA256 = (
    "5115bdec967984f5e2b1f4943a2f1a233aabbdc91799882ebd1739a633b86f4d"
)
GENERATED = REPOSITORY_ROOT / "paper" / "generated"
DEFAULT_OUTPUT = GENERATED / "pdb-profile-harm-pruning-v1.tex"
DEFAULT_FIGURE = GENERATED / "pdb-profile-harm-pruning-v1.pdf"
DEFAULT_LAYERS = GENERATED / "pdb-profile-harm-layers-v1.pdf"
EXAMPLE_FAMILY = "ms"
LOW_STATE_RATIO = Fraction(1, 10)
HIGH_STATE_RATIO = Fraction(4, 5)
ALIGNED = "ms_aligned_10k"
UNALIGNED = "ms_unaligned_10k"
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_SEED = 20261013
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
MAX_TEX_BYTES = 16 * 1024
MAX_PDF_BYTES = 4 * 1024 * 1024


def _states(run):
    # Large state counts come from BDD model counting as doubles.
    value = run.get("expanded_states")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
        raise RenderError("run without positive expanded states")
    return Fraction(value)


def _median(values):
    return round(float(statistics.median(values)), 4) if values else None


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for k in range(start, end + 1):
            ranks[order[k]] = (start + end) / 2
        start = end + 1
    return ranks


def _spearman(xs, ys):
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return round(num / den, 4)


def _group(pairs):
    def view(selected):
        return {
            "pairs": len(selected),
            "s_median": _median([float(p["s"]) for p in selected]),
            "u_median": _median([float(p["u"]) for p in selected]),
        }
    def extra(selected):
        return {
            "h0_median": _median([float(p["h0"]) for p in selected]),
            "unshrunk_median": _median([float(p["unshrunk"]) for p in selected]),
        }
    return {
        "harmful_extra": extra([p for p in pairs if p["r"] > 1]),
        "helpful_extra": extra([p for p in pairs if p["r"] < 1]),
        "harmful": view([p for p in pairs if p["r"] > 1]),
        "helpful": view([p for p in pairs if p["r"] < 1]),
        "strong": view([p for p in pairs if p["r"] > P.STRONG_RATIO]),
    }


def _initial_h(run):
    first = [e for e in run["wbh_expansion_profile"] if e["g"] == 0]
    if len(first) != 1 or len(first[0]["active_h_values"]) != 1:
        raise RenderError("run without a unique initial bucket")
    return first[0]["active_h_values"][0]


def _unshrunk(blind, heur):
    blind_layers = {e["g"]: e["effort"] for e in blind["wbh_expansion_profile"]}
    unsplit = {l["g"]: l["bdd_nodes"] for l in heur["wbh_profile_layer_profiles"]
               if l.get("completed") is True}
    total = sum(blind_layers.values())
    same = sum(size for g, size in blind_layers.items() if unsplit.get(g) == size)
    return Fraction(same, total)


def _typical(pairs):
    # The harmful pair of the family closest to the family's harmful medians
    # in log space; ties are broken by configuration and task.
    harmful = [p for p in pairs
               if p["family"] == EXAMPLE_FAMILY and p["r"] > 1]
    if not harmful:
        raise RenderError("no harmful pair for the example")
    keys = ("s", "u", "f")
    medians = {k: statistics.median(math.log(float(p[k])) for p in harmful)
               for k in keys}
    return min(harmful, key=lambda p: (
        sum((math.log(float(p[k])) - medians[k]) ** 2 for k in keys),
        p["label"], p["domain"], p["problem"]))


def _example(runs, pairs):
    pair = _typical(pairs)
    label, domain, problem = pair["label"], pair["domain"], pair["problem"]
    blind = runs[(P.BLIND_LABEL, domain, problem)]
    heur = runs[(label, domain, problem)]
    blind_layers = {e["g"]: e["effort"] for e in blind["wbh_expansion_profile"]}
    expanded = {e["g"]: e for e in heur["wbh_expansion_profile"]}
    unsplit = {l["g"]: l["bdd_nodes"] for l in heur["wbh_profile_layer_profiles"]
               if l.get("completed") is True}
    if set(expanded) != set(unsplit) or not set(expanded) <= set(blind_layers):
        raise RenderError("the illustrative layers do not match")
    layers = [
        [g, blind_layers[g], unsplit[g], expanded[g]["effort"],
         expanded[g]["buckets"]]
        for g in sorted(expanded)
    ]
    return {
        "label": label, "domain": domain, "problem": problem,
        "cost": heur["cost"],
        "initial_h": max(expanded[0]["active_h_values"]),
        "r": round(float(pair["r"]), 4),
        "u": round(float(pair["u"]), 4),
        "f": round(float(pair["f"]), 4),
        "s": round(float(pair["s"]), 4),
        "layers": layers,
    }


def _bootstrap(pairs):
    """95% domain-cluster bootstrap intervals of S and of the median u."""
    by_domain = {}
    for p in pairs:
        by_domain.setdefault(p["domain"], []).append(
            (p["family"], p["r"] > 1, math.log(p["r"]), math.log(p["f"]),
             float(p["u"])))
    domains = sorted(by_domain)
    rng = random.Random(BOOTSTRAP_SEED)
    groups = ("ms", "pdb", "pot", "pooled")
    samples = {g: {"share": [], "u": []} for g in groups}
    for _ in range(BOOTSTRAP_SAMPLES):
        drawn = [rng.choice(domains) for _ in domains]
        for g in groups:
            harmful = [x for d in drawn for x in by_domain[d]
                       if x[1] and (g == "pooled" or x[0] == g)]
            log_r = sum(x[2] for x in harmful)
            if not harmful or log_r <= 0:
                continue
            samples[g]["share"].append(sum(x[3] for x in harmful) / log_r)
            samples[g]["u"].append(statistics.median(x[4] for x in harmful))

    def interval(values):
        values = sorted(values)
        return [round(values[int(0.025 * (len(values) - 1))], 4),
                round(values[int(0.975 * (len(values) - 1))], 4)]

    return {
        "samples": BOOTSTRAP_SAMPLES,
        "seed": BOOTSTRAP_SEED,
        "groups": {g: {"share": interval(samples[g]["share"]),
                       "harmful_u_median": interval(samples[g]["u"])}
                   for g in groups},
    }


def _geomean(values):
    return round(math.exp(statistics.mean(math.log(v) for v in values)), 4)


def _oracle(pairs):
    groups = {}
    for family in ("ms", "pdb", "pot", "pooled"):
        mine = pairs if family == "pooled" else [
            p for p in pairs if p["family"] == family]
        groups[family] = {
            "pairs": len(mine),
            "unsplit_below_one": sum(1 for p in mine if p["u"] < 1),
            "effort_below_one": sum(1 for p in mine if p["r"] < 1),
            "u_geomean": _geomean([float(p["u"]) for p in mine]),
            "r_geomean": _geomean([float(p["r"]) for p in mine]),
        }
    neutral = [p for p in pairs if p["r"] == 1]
    return {
        "groups": groups,
        "neutral": len(neutral),
        "neutral_unsplit_and_frag_one": sum(
            1 for p in neutral if p["u"] == 1 and p["f"] == 1),
    }


def analyze(properties):
    cohort, runs = Frozen._index_runs(properties)
    pairs = Frozen.pairs_from_runs(cohort, runs)
    for p in pairs:
        blind = runs[(P.BLIND_LABEL, p["domain"], p["problem"])]
        heur = runs[(p["label"], p["domain"], p["problem"])]
        p["s"] = _states(heur) / _states(blind)
        p["h0"] = _initial_h(heur) / Fraction(heur["cost"])
        p["unshrunk"] = _unshrunk(blind, heur)
    families = {}
    for family in ("ms", "pdb", "pot", "pooled"):
        mine = pairs if family == "pooled" else [
            p for p in pairs if p["family"] == family]
        families[family] = _group(mine)
    low = [p for p in pairs if p["s"] < LOW_STATE_RATIO]
    high = [p for p in pairs if p["s"] >= HIGH_STATE_RATIO]
    by_label = {}
    for p in pairs:
        by_label.setdefault(p["label"], {})[(p["domain"], p["problem"])] = p
    common = sorted(set(by_label[ALIGNED]) & set(by_label[UNALIGNED]))
    log_ratios = [
        math.log(by_label[ALIGNED][t]["f"] / by_label[UNALIGNED][t]["f"])
        for t in common]
    domains = {}
    for p in pairs:
        domains.setdefault(p["domain"], []).append(p)
    majority = sum(
        1 for mine in domains.values()
        if 2 * sum(1 for p in mine if p["u"] > p["s"]) > len(mine))
    blind_only = {}
    for label in P.LABELS[1:]:
        blind_only[label] = sum(
            1 for task in cohort
            if Frozen._solved(runs[(P.BLIND_LABEL, task.domain, task.problem)])
            and not Frozen._solved(runs[(label, task.domain, task.problem)]))
    return {
        "schema": "symbolic-search-heuristics/harm-generality-pruning/v1",
        "status": "post-hoc-descriptive",
        "properties_sha256": EXPECTED_PROPERTIES_SHA256,
        "pairs": len(pairs),
        "families": families,
        "u_above_s": sum(1 for p in pairs if p["u"] > p["s"]),
        "harmful": sum(1 for p in pairs if p["r"] > 1),
        "harmful_u_above_one": sum(1 for p in pairs if p["r"] > 1 and p["u"] > 1),
        "low_state_ratio": str(LOW_STATE_RATIO),
        "low_pairs": len(low),
        "low_helpful": sum(1 for p in low if p["r"] < 1),
        "high_state_ratio": str(HIGH_STATE_RATIO),
        "high_pairs": len(high),
        "high_helpful": sum(1 for p in high if p["r"] < 1),
        "spearman_s_u": _spearman([float(p["s"]) for p in pairs],
                                  [float(p["u"]) for p in pairs]),
        "spearman_s_f": _spearman([float(p["s"]) for p in pairs],
                                  [float(p["f"]) for p in pairs]),
        "aligned": {
            "tasks": len(common),
            "lower": sum(1 for x in log_ratios if x < 0),
            "higher": sum(1 for x in log_ratios if x > 0),
            "frag_ratio_geomean": round(math.exp(statistics.mean(log_ratios)), 4),
        },
        "blind_only": blind_only,
        "domains": len(domains),
        "domains_u_above_s": majority,
        "example": _example(runs, pairs),
        "bootstrap": _bootstrap(pairs),
        "oracle": _oracle(pairs),
        "points": [
            [p["label"], round(float(p["s"]), 6), round(float(p["u"]), 6),
             round(float(p["f"]), 6)]
            for p in sorted(pairs, key=lambda p: (p["label"], p["domain"],
                                                  p["problem"]))
        ],
    }


def command_analyze(args):
    raw_properties = Path(args.properties).read_bytes()
    if hashlib.sha256(raw_properties).hexdigest() != EXPECTED_PROPERTIES_SHA256:
        raise RenderError("properties differ from the pinned harm-generality run")
    artifact = analyze(json.loads(raw_properties))
    raw = Common._canonical_json(artifact) + b"\n"
    if DEFAULT_ARTIFACT.exists():
        raise RenderError("pruning artifact already exists")
    Frozen._write_atomic(DEFAULT_ARTIFACT, raw)
    digest = hashlib.sha256(raw).hexdigest()
    Frozen._write_atomic(
        str(DEFAULT_ARTIFACT) + ".sha256",
        "{}  {}\n".format(digest, DEFAULT_ARTIFACT.name).encode("ascii"))
    print(digest)
    return 0


def _load(path):
    raw = Common._read_regular(path, MAX_ARTIFACT_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_ARTIFACT_SHA256:
        raise RenderError("pruning artifact is not the reviewed pin")
    sidecar = "{}  {}\n".format(digest, Path(path).name).encode("ascii")
    if Common._read_regular(Path(str(path) + ".sha256"), 256) != sidecar:
        raise RenderError("pruning sidecar differs from the pinned artifact")
    return json.loads(raw.decode("ascii")), digest


def render(data, digest):
    macros = []
    for family, prefix in (("ms", "Ms"), ("pdb", "Pdb"), ("pot", "Pot"),
                           ("pooled", "All")):
        for view, name in (("harmful", "Hurt"), ("helpful", "Help"),
                           ("strong", "Strong")):
            record = data["families"][family][view]
            macros += [
                ("Prune{}{}Pairs".format(prefix, name), str(record["pairs"])),
                ("Prune{}{}States".format(prefix, name),
                 "{:.2f}".format(record["s_median"])),
                ("Prune{}{}Union".format(prefix, name),
                 "{:.2f}".format(record["u_median"])),
            ]
    aligned = data["aligned"]
    blind_only = sorted(data["blind_only"].values())
    macros += [
        ("PrunePairs", "\\num{{{}}}".format(data["pairs"])),
        ("PruneUnionAboveStates", "\\num{{{}}}".format(data["u_above_s"])),
        ("PruneHurtUnionAboveOne", str(data["harmful_u_above_one"])),
        ("PruneLowPairs", str(data["low_pairs"])),
        ("PruneLowHelpful", str(data["low_helpful"])),
        ("PruneHighPairs", str(data["high_pairs"])),
        ("PruneHighHelpful", str(data["high_helpful"])),
        ("PruneSpearmanUnion", "{:.2f}".format(data["spearman_s_u"])),
        ("PruneSpearmanFrag", "{:.2f}".format(data["spearman_s_f"])),
        ("PruneAlignedTasks", str(aligned["tasks"])),
        ("PruneAlignedLower", str(aligned["lower"])),
        ("PruneAlignedHigher", str(aligned["higher"])),
        ("PruneAlignedFragRatio",
         "{:.2f}".format(aligned["frag_ratio_geomean"])),
        ("PruneBlindOnlyMin", str(blind_only[0])),
        ("PruneBlindOnlyMax", str(blind_only[-1])),
        ("PruneDomains", str(data["domains"])),
        ("PruneHurtInitH", "{:.2f}".format(
            data["families"]["pooled"]["harmful_extra"]["h0_median"])),
        ("PruneHelpInitH", "{:.2f}".format(
            data["families"]["pooled"]["helpful_extra"]["h0_median"])),
        ("PruneHurtUnshrunk", "{:.0f}".format(
            100 * data["families"]["pooled"]["harmful_extra"]["unshrunk_median"])),
        ("PruneHelpUnshrunk", "{:.0f}".format(
            100 * data["families"]["pooled"]["helpful_extra"]["unshrunk_median"])),
        ("PruneDomainsUnionAboveStates", str(data["domains_u_above_s"])),
    ]
    oracle = data["oracle"]
    macros += [
        ("NeutralPairs", str(oracle["neutral"])),
        ("NeutralTrivial", str(oracle["neutral_unsplit_and_frag_one"])),
    ]
    for family, prefix in (("ms", "Ms"), ("pdb", "Pdb"), ("pot", "Pot"),
                           ("pooled", "All")):
        record = oracle["groups"][family]
        macros += [
            ("Oracle{}UnsplitBelow".format(prefix),
             "\\num{{{}}}".format(record["unsplit_below_one"])),
            ("Oracle{}EffortBelow".format(prefix),
             "\\num{{{}}}".format(record["effort_below_one"])),
            ("Oracle{}GeoU".format(prefix), "{:.2f}".format(record["u_geomean"])),
            ("Oracle{}GeoR".format(prefix), "{:.2f}".format(record["r_geomean"])),
        ]
    for family, prefix in (("ms", "Ms"), ("pdb", "Pdb"), ("pot", "Pot"),
                           ("pooled", "All")):
        record = data["bootstrap"]["groups"][family]
        macros += [
            ("Boot{}ShareLow".format(prefix), "{:.2f}".format(record["share"][0])),
            ("Boot{}ShareHigh".format(prefix), "{:.2f}".format(record["share"][1])),
            ("Boot{}UnionLow".format(prefix),
             "{:.2f}".format(record["harmful_u_median"][0])),
            ("Boot{}UnionHigh".format(prefix),
             "{:.2f}".format(record["harmful_u_median"][1])),
        ]
    example = data["example"]
    layers = example["layers"]
    unpruned = [l for l in layers if l[2] == l[1]]
    enlarged = [l for l in layers if l[2] > l[1]]
    if example["cost"] != int(example["cost"]):
        raise RenderError("the example has a fractional cost")
    if [l[0] for l in unpruned] != list(range(len(unpruned))):
        raise RenderError("unpruned layers of the example are not a prefix")
    macros += [
        ("ExCost", "{:d}".format(int(example["cost"]))),
        ("ExInitH", str(example["initial_h"])),
        ("ExR", "{:.2f}".format(example["r"])),
        ("ExU", "{:.2f}".format(example["u"])),
        ("ExFrag", "{:.2f}".format(example["f"])),
        ("ExS", "{:.2f}".format(example["s"])),
        ("ExUnprunedLayers", str(len(unpruned))),
        ("ExMaxBuckets", str(max(l[4] for l in layers))),
        ("ExMaxUnprunedFrag",
         "{:.1f}".format(max(l[3] / l[2] for l in unpruned))),
        ("ExEnlargedFirst", str(enlarged[0][0])),
        ("ExEnlargedLast", str(enlarged[-1][0])),
        ("ExMaxEnlarged", "{:.1f}".format(max(l[2] / l[1] for l in enlarged))),
    ]
    lines = [
        "% Generated post hoc from the harm-generality pruning summary.",
        "% Descriptive only; changes no frozen estimand or decision.",
        "% Summary SHA-256: {}".format(digest),
    ] + [Common._macro(name, value) for name, value in macros]
    raw = ("\n".join(lines) + "\n").encode("ascii")
    if len(raw) > MAX_TEX_BYTES:
        raise RenderError("generated TeX exceeds its size limit")
    return raw


def render_figure(data):
    import matplotlib

    matplotlib.use("pdf")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

    points = data["points"]
    if not points:
        raise RenderError("no points")
    plt.rcParams.update({
        "pdf.fonttype": 42,
        "font.family": "serif",
        "font.size": 7,
        "axes.linewidth": 0.5,
    })
    lo_s = min(p[1] for p in points) / 1.2
    hi_s = max(p[1] for p in points) * 1.2
    figure, panels = plt.subplots(1, 2, figsize=(3.3, 1.45), sharex=True)
    for axes, index, ylabel, ticks in (
            (panels[0], 2, "unsplit ratio $u$", [0.01, 0.1, 1.0]),
            (panels[1], 3, "fragmentation", [1.0, 2.0, 4.0, 8.0])):
        helped = [(p[1], p[index]) for p in points if p[2] * p[3] <= 1]
        hurt = [(p[1], p[index]) for p in points if p[2] * p[3] > 1]
        for group, color, label in ((helped, "0.7", "effort at most blind"),
                                    (hurt, "0.1", "effort above blind")):
            if group:
                xs, ys = zip(*group)
                axes.scatter(xs, ys, s=1.2, c=color, linewidths=0, label=label)
        lo_y = min(p[index] for p in points) / 1.2
        hi_y = max(p[index] for p in points) * 1.2
        if index == 2:
            lo_y = min(lo_y, lo_s)
            axes.plot([lo_s, hi_s], [lo_s, hi_s], "-", color="0.4",
                      linewidth=0.6)
        axes.set_xscale("log")
        axes.set_yscale("log")
        axes.set_xlim(lo_s, hi_s)
        axes.set_ylim(lo_y, hi_y)
        axes.set_ylabel(ylabel, labelpad=1)
        axes.set_xlabel("state ratio $s$", labelpad=1)
        axes.xaxis.set_major_locator(FixedLocator([1e-4, 1e-2, 1.0]))
        axes.yaxis.set_major_locator(FixedLocator(ticks))
        for axis in (axes.xaxis, axes.yaxis):
            axis.set_minor_locator(NullLocator())
        axes.xaxis.set_major_formatter(FuncFormatter(
            lambda value, _: "1" if value == 1 else
            "$10^{{{}}}$".format(int(round(math.log10(value))))))
        axes.yaxis.set_major_formatter(
            FuncFormatter(lambda value, _: "{:g}".format(value)))
    figure.tight_layout(pad=0.2, w_pad=0.6)
    stream = io.BytesIO()
    figure.savefig(stream, format="pdf",
                   metadata={"CreationDate": None, "ModDate": None,
                             "Creator": None, "Producer": None})
    plt.close(figure)
    raw = stream.getvalue()
    if len(raw) > MAX_PDF_BYTES:
        raise RenderError("figure exceeds its size limit")
    return raw


def render_layers(data):
    import matplotlib

    matplotlib.use("pdf")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

    layers = data["example"]["layers"]
    plt.rcParams.update({
        "pdf.fonttype": 42,
        "font.family": "serif",
        "font.size": 7,
        "axes.linewidth": 0.5,
    })
    figure, axes = plt.subplots(figsize=(3.3, 1.3))
    gs = [l[0] for l in layers]
    for index, style, label in ((1, "-", "blind layer $L_g$"),
                                (2, "--", "unsplit $S_g^h$"),
                                (3, ":", "buckets of layer $g$")):
        axes.plot(gs, [l[index] for l in layers], style, color="0.1",
                  linewidth=0.9, label=label)
    axes.set_yscale("log")
    axes.set_xlim(gs[0], gs[-1])
    axes.set_ylim(1, 2 * max(max(l[1:4]) for l in layers))
    axes.set_xlabel("$g$", labelpad=1)
    axes.set_ylabel("BDD nodes", labelpad=1)
    axes.yaxis.set_major_locator(FixedLocator([1, 100, 10000]))
    axes.yaxis.set_minor_locator(NullLocator())
    axes.yaxis.set_major_formatter(FuncFormatter(
        lambda value, _: "$10^{{{}}}$".format(int(round(math.log10(value))))))
    axes.legend(loc="lower center", bbox_to_anchor=(0.55, 0.0), frameon=False,
                fontsize=6, handlelength=2.2, borderaxespad=0.2)
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


def _emit(args, raw, default, maximum):
    if args.check:
        if Common._read_regular(args.output, maximum) != raw:
            raise RenderError("generated output is stale")
        return 0
    if Path(args.output).resolve() != default.resolve():
        raise RenderError("--write is restricted to the generated-paper path")
    Frozen._write_atomic(args.output, raw)
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--properties", type=Path, default=Frozen.DEFAULT_PROPERTIES)
    for name, default in (("render", DEFAULT_OUTPUT), ("figure", DEFAULT_FIGURE),
                          ("layers", DEFAULT_LAYERS)):
        r = sub.add_parser(name)
        r.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
        r.add_argument("--output", type=Path, default=default)
        modes = r.add_mutually_exclusive_group(required=True)
        modes.add_argument("--write", action="store_true")
        modes.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "analyze":
        return command_analyze(args)
    data, digest = _load(args.artifact)
    if args.command == "render":
        return _emit(args, render(data, digest), DEFAULT_OUTPUT, MAX_TEX_BYTES)
    if args.command == "figure":
        return _emit(args, render_figure(data), DEFAULT_FIGURE, MAX_PDF_BYTES)
    return _emit(args, render_layers(data), DEFAULT_LAYERS, MAX_PDF_BYTES)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RenderError, Frozen.AnalysisError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
