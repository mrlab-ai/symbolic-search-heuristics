/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef ___PDDL_PROFILE_H__
#define ___PDDL_PROFILE_H__

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

void pddlProfileStart(int slot);
void pddlProfileStop(int slot);
void pddlProfilePrint(void);

#define PROF(slot) pddlProfileStart(slot)
#define PROFE(slot) pddlProfileStop(slot)
#define PROF_PRINT pddlProfilePrint();

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* ___PDDL_PROFILE_H__ */
