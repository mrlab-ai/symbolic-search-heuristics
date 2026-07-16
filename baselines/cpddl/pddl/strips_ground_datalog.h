/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_STRIPS_GROUND_DATALOG_H__
#define __PDDL_STRIPS_GROUND_DATALOG_H__

#include <pddl/common.h>
#include <pddl/pddl_struct.h>
#include <pddl/strips.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * Ground PDDL into STRIPS.
 */
int pddlStripsGroundDatalog(pddl_strips_t *strips,
                            const pddl_t *pddl,
                            const pddl_ground_config_t *cfg,
                            pddl_err_t *err);

/**
 * Ground PDDL into STRIPS using the Gringo grounder from the external
 * libraly clingo that must be compiled-in.
 */
int pddlStripsGroundGringo(pddl_strips_t *strips,
                           const pddl_t *pddl,
                           const pddl_ground_config_t *cfg,
                           pddl_err_t *err);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_STRIPS_GROUND_DATALOG_H__ */
