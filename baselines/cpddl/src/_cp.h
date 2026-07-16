/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL__CP_H__
#define __PDDL__CP_H__

#define OBJ_SAT 0
#define OBJ_MIN_COUNT_DIFF 1

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

int *pddlCPSolGet(pddl_cp_sol_t *sol, int sol_id);
void pddlCPSolAdd(const pddl_cp_t *cp, pddl_cp_sol_t *sol, const int *isol);
int *pddlCPSolAddEmpty(const pddl_cp_t *cp, pddl_cp_sol_t *sol);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL__CP_H__ */
