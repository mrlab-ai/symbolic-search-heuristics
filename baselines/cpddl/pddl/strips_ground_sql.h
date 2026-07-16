/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_STRIPS_GROUND_SQL_H__
#define __PDDL_STRIPS_GROUND_SQL_H__

#include <pddl/common.h>
#include <pddl/pddl_struct.h>
#include <pddl/strips.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * Ground PDDL into STRIPS.
 */
int pddlStripsGroundSql(pddl_strips_t *strips,
                        const pddl_t *pddl,
                        const pddl_ground_config_t *cfg,
                        pddl_err_t *err);

int pddlStripsGroundSqlLayered(const pddl_t *pddl,
                               const pddl_ground_config_t *cfg,
                               int max_layers,
                               int max_atoms,
                               pddl_strips_t *strips,
                               pddl_ground_atoms_t *ground_atoms,
                               pddl_err_t *err);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_STRIPS_GROUND_SQL_H__ */
