/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef REPORT_H
#define REPORT_H
void reportLiftedMGroups(const pddl_t *pddl, pddl_err_t *err);
void reportMGroups(const pddl_t *pddl,
                   const pddl_strips_t *strips,
                   pddl_err_t *err);
#endif
