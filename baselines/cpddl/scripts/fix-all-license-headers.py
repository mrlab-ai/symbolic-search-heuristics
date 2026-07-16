#!/usr/bin/env python3

import sys
import os
import re

HEADER = '''/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */
'''


for fn in sys.argv[1:]:
    print(fn)
    d = open(fn, 'r').read()
    if d.startswith('/***\n'):
        idx = 4
        while d[idx:idx + 4] != ' */\n':
            idx += 1
        d = d[idx+4:].lstrip()
        d = HEADER + '\n' + d
    open(fn, 'w').write(d)
