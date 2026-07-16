"""Benchmark suite for the width-bounded-heuristics experiments (PR5).

Optimal-track IPC 1998-2023 STRIPS domains. Following Speck et al. (2020) and
matching the assumptions of the paper, we exclude:
  * conditional effects and axioms (not covered by the potential/PDB families
    here, and changing SymK's default mutex handling);
  * zero-cost operators (the theory assumes positive costs; the heuristic
    search asserts this). Zero-cost operators occur inside otherwise-included
    domains (e.g. openstacks, parcprinter, pegsol, tetris), so they are
    filtered per task at run time by the heuristic configs (which skip such
    tasks) rather than per domain. This makes our suite a strict subset of the
    Fiser et al. (2024) suite -- note this delta in the experiment README.

`suite()` returns the domain list; the dry-run suite is `SMOKE`.
"""

# Canonical optimal-track STRIPS domains present in aibasel/downward-benchmarks.
SUITE_OPTIMAL_STRIPS = [
    "airport",
    "barman-opt11-strips", "barman-opt14-strips",
    "blocks",
    "childsnack-opt14-strips",
    "depot",
    "driverlog",
    "elevators-opt08-strips", "elevators-opt11-strips",
    "floortile-opt11-strips", "floortile-opt14-strips",
    "freecell",
    "ged-opt14-strips",
    "grid",
    "gripper",
    "hiking-opt14-strips",
    "logistics00", "logistics98",
    "miconic",
    "movie",
    "mprime",
    "mystery",
    "nomystery-opt11-strips",
    "openstacks-opt08-strips", "openstacks-opt11-strips",
    "openstacks-opt14-strips",
    "organic-synthesis-opt18-strips",
    "parcprinter-08-strips", "parcprinter-opt11-strips",
    "parking-opt11-strips", "parking-opt14-strips",
    "pathways",
    "pegsol-08-strips", "pegsol-opt11-strips",
    "pipesworld-notankage", "pipesworld-tankage",
    "psr-small",
    "rovers",
    "satellite",
    "scanalyzer-08-strips", "scanalyzer-opt11-strips",
    "snake-opt18-strips",
    "sokoban-opt08-strips", "sokoban-opt11-strips",
    "storage",
    "termes-opt18-strips",
    "tetris-opt14-strips",
    "tidybot-opt11-strips", "tidybot-opt14-strips",
    "tpp",
    "transport-opt08-strips", "transport-opt11-strips",
    "transport-opt14-strips",
    "trucks-strips",
    "visitall-opt11-strips", "visitall-opt14-strips",
    "woodworking-opt08-strips", "woodworking-opt11-strips",
    "zenotravel",
]

# Small end-to-end dry-run suite (used by exp_q1 --dry / local runs).
SMOKE = ["gripper:prob01.pddl", "miconic:s1-2.pddl"]


def suite():
    return list(SUITE_OPTIMAL_STRIPS)
