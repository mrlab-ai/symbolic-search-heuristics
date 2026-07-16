#!/bin/bash

major_ver=$(cat pddl/version.h | grep PDDL_VERSION_MAJOR | grep -o '[0-9]\+$')
minor_ver=$(cat pddl/version.h | grep PDDL_VERSION_MINOR | grep -o '[0-9]\+$')
version="${major_ver}.${minor_ver}"

rootdir="$1"
libs="$2"

includedir="\${prefix}"
libdir="\${prefix}"

cat <<EOF
prefix=${rootdir}
includedir=${includedir}
libdir=${libdir}

Name: cpddl
Description: Library for automated planning
Version: ${version}
Cflags: -I\${includedir}
Libs: -L\${libdir} -lpddl ${libs}
EOF
