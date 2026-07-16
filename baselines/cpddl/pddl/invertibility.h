/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_INVERTIBILITY_H__
#define __PDDL_INVERTIBILITY_H__

#include <pddl/mg_strips.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

int pddlRSEInvertibleFacts(const pddl_strips_t *strips,
                           const pddl_mgroups_t *fam_groups,
                           pddl_iset_t *invertible_facts,
                           pddl_err_t *err);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_INVERTIBILITY_H__ */
