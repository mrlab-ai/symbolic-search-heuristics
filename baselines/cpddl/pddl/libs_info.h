/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_LIBS_INFO_H__
#define __PDDL_LIBS_INFO_H__

#include <pddl/config.h>
#include <pddl/common.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

extern const char * const pddl_bliss_version;
extern const char * const pddl_cudd_version;
extern const char * const pddl_sqlite_version;
extern const char * const pddl_cplex_version;
extern const char * const pddl_cplex_api_version;
extern const char * const pddl_cp_optimizer_version;
extern const char * const pddl_gurobi_version;
extern const char * const pddl_gurobi_api_version;
extern const char * const pddl_highs_version;
extern const char * const pddl_dynet_version;

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_LIBS_INFO_H__ */
