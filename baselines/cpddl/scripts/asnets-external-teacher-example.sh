#!/bin/bash

#
# In the configuration file, set
#   teacher = "external-fd"
#   teacher_external_cmd = ["/bin/bash", "/path/to/this/script.sh"]
#

FD_PATH=/home/danfis/dev/FD/fast-downward/builds/release/bin/downward
rm -f plan.sas
cat | \
    timeout 5s $FD_PATH \
            --search 'astar(lmcut())' \
            --internal-plan-file plan.sas >/dev/null 2>&1
if [ -f plan.sas ]; then
    cat plan.sas
    rm -f plan.sas
fi
exit 0
