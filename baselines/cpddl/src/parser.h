/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_PARSER_H__
#define __PDDL_PARSER_H__

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

#include "pddl/pddl_struct.h"

int pddlParseDomain(pddl_t *pddl, const char *fn, pddl_err_t *err);
int pddlParseProblem(pddl_t *pddl, const char *fn, pddl_err_t *err);


#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_PARSER_H__ */
