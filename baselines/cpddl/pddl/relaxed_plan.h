/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_RELAXED_PLAN_H__
#define __PDDL_RELAXED_PLAN_H__

#include <pddl/iarr.h>
#include <pddl/strips.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * Counts fact conflicts in the given relaxed plan, i.e., operators from
 * plan are applied in non-relaxed semantics as if the preconditions are
 * satisfied, but for every fact that is not satisfied +1 is added into the
 * conflict counter. Moreover, for every goal that is not satisfied
 * +1*goal_conflict_weight is added.
 * The array fact_conflicts must have at least number-of-facts elemts and
 * it must be zeroized by the caller.
 */
void pddlRelaxedPlanCountConflictsStrips(const pddl_iarr_t *plan,
                                         const pddl_iset_t *init,
                                         const pddl_iset_t *goal,
                                         const pddl_strips_ops_t *ops,
                                         int goal_conflict_weight,
                                         int *fact_conflicts);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_RELAXED_PLAN_H__ */
