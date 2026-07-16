#!/usr/bin/env python3
"""Generate the Pi_n task family of Speck et al. (ICAPS 2020) in PDDL.

This is the family on which BDDA* with the perfect heuristic is exponentially
worse than blind forward search, and (paper Thm. thm-lb) on which h* has width
2^n. Blind forward search keeps each layer linear in size, while a heuristic
that separates the v_i pairs blows up the g = 2n bucket.

Structure (paper Sec. "Exponential Width Is Necessary"):
  - boolean variables v_1..v_{2n} and x_0..x_{2n+1}; initially only x_0 holds;
  - for i in 1..2n, operators o_i and o_i_bar with precondition
    x_{i-1} and not x_i set x_i (o_i additionally sets v_i true; o_i_bar leaves
    v_i false);
  - once x_{2n} holds, a goal operator g_i (i in 1..n) with precondition
    x_{2n} and v_i and v_{n+i} achieves the goal x_{2n+1}.
All operator costs are 1 (positive costs, as the theory assumes).

Usage: python3 misc/gen_pin.py OUTPUT_DIR [n_min n_max]
Writes pin-domain.pddl (shared) and pin-nNN.pddl problems.
"""
import sys
from pathlib import Path

DOMAIN_TEMPLATE = """(define (domain pin)
  (:requirements :strips)
  (:predicates {predicates})
  {actions}
)
"""


def prop(name):
    return f"({name})"


def gen_domain(n):
    xs = [f"x{i}" for i in range(2 * n + 2)]
    vs = [f"v{i}" for i in range(1, 2 * n + 1)]
    predicates = " ".join(prop(p) for p in xs + vs)

    actions = []
    for i in range(1, 2 * n + 1):
        # o_i sets x_i and v_i; o_i_bar sets only x_i.
        actions.append(
            f"""(:action o{i}
    :precondition (and (x{i - 1}) (not (x{i})))
    :effect (and (x{i}) (v{i})))""")
        actions.append(
            f"""(:action o{i}_bar
    :precondition (and (x{i - 1}) (not (x{i})))
    :effect (and (x{i})))""")
    for i in range(1, n + 1):
        actions.append(
            f"""(:action g{i}
    :precondition (and (x{2 * n}) (v{i}) (v{n + i}))
    :effect (and (x{2 * n + 1})))""")
    return DOMAIN_TEMPLATE.format(
        predicates=predicates, actions="\n  ".join(actions))


def gen_problem(n):
    goal = f"x{2 * n + 1}"
    return f"""(define (problem pin-n{n})
  (:domain pin)
  (:init (x0))
  (:goal (and ({goal})))
)
"""


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    n_min = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    n_max = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    for n in range(n_min, n_max + 1):
        # Each n needs its own domain (predicate/action counts depend on n).
        (out / f"pin-n{n:02d}-domain.pddl").write_text(gen_domain(n))
        (out / f"pin-n{n:02d}.pddl").write_text(gen_problem(n))
        print(f"wrote pin-n{n:02d} (2n+2={2 * n + 2} x-vars, {2 * n} v-vars)")


if __name__ == "__main__":
    main()
