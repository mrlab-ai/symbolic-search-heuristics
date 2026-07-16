#!/bin/bash

./bin/pddl-symba pddl-data/test-seq/driverlog/pfile1 \
        --symba bi \
        --symba-out - | grep -q "Cost: 7$"

./bin/pddl pddl-data/ipc-2011/seq-opt/barman/pfile01-001 \
        --pddl-compile-in-lmg \
        --h2 \
        --P-opm op-fact=2,prune-method=max \
        --gplan astar \
        --gplan-out - | grep "Cost: 90$"
