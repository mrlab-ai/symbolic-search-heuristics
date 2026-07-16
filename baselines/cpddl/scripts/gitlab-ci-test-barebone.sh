#!/bin/bash

./bin/pddl pddl-data/test-seq/depot/pfile1 >/dev/null

./bin/pddl pddl-data/test-seq/depot/pfile1 -o /dev/null

./bin/pddl-lplan pddl-data/test-seq/depot/pfile1 \
        --lplan-o -  | grep -q "Cost: 10$"

./bin/pddl-lplan pddl-data/test-seq/depot/pfile1 \
        --pddl-compile-in-lmg \
        --lplan astar \
        --lplan-h hmax \
        --lplan-o - | grep -q "Cost: 10$"

./bin/pddl-lplan pddl-data/ipc-2014/seq-opt/citycar/p2-2-2-1-2 \
        --lplan-o - | grep -q "Cost 46$"

./bin/pddl-lplan pddl-data/various/miconic-fulladl/f2-3.pddl \
        --lplan astar \
        --lplan-o - | grep -q "Cost 6$"

./bin/pddl pddl-data/ipc-2014/seq-opt/citycar/p2-2-2-1-2 \
        --gplan astar \
        --gplan-o - | grep -q "Cost 46$"

./bin/pddl pddl-data/various/miconic-fulladl/f2-3.pddl \
        --gplan astar \
        --gplan-o - | grep -q "Cost 6$"

./bin/pddl pddl-data/test-seq/driverlog/pfile1 \
        --gplan astar \
        --gplan-h lmc \
        --gplan-out - | grep -q "Cost: 7$"
