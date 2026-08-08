"""Source universe for the width-bounded-heuristics experiments (PR5).

The 59 domains below enumerate 1697 optimal-track IPC 1998--2023 tasks used by
the archived sweeps. They are not all axiom-free after translation: Pathways'
ADL disjunctions become normalized axioms. The frozen source manifest records
this separately from operator cost. The common SymK heuristic population is
the 1377 tasks that are both positive-cost and free of normalized axioms:
290 zero-cost tasks and 30 Pathways tasks with normalized axioms are excluded.

Prospective held-out screens first filter tasks by that supported population,
then retain the 46 domains with at least two supported tasks. Eligibility is
derived from the frozen manifest, not from planner outcomes. `suite()` still
returns the complete 59-domain source universe so archived and broad-baseline
protocols remain reproducible;
the dry-run suite is `SMOKE`.
"""

# Canonical optimal-track domains present in aibasel/downward-benchmarks.
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
