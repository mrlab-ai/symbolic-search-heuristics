#!/bin/bash

if [ "$1" = "" ]; then
    echo "Usage: $0 vX.Y"
fi

git archive --format=tar.gz --output=cpddl-${1}.tar.gz ${1}
