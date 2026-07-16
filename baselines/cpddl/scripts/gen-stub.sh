#!/bin/bash

IN_H="$1"
VERSION_VAR="$3"

echo '#include "internal.h"'
echo '#include "pddl/libs_info.h"'
echo '#include "'$IN_H'"'
[ "$VERSION_VAR" != "" ] && echo "const char * const ${VERSION_VAR} = NULL;"
echo '#define ERROR PANIC("'$2'")'
grep -Pzo '(const )?[a-z][a-zA-Z0-9_]+ [*]*pddl[A-Z][a-zA-Z0-9]*\([^;]+' "$IN_H" \
         | awk 'BEGIN { RS = "\0" }
                { printf("%s\n{ ERROR;", $0) }
                /^(const )?[^ ]+ [*]+pddl/{ printf("return NULL;") }
                /^(int|long|unsigned|float|double|pddl_bool_t) pddl/{ printf("return -1;"); }
                { printf("}\n") }'

