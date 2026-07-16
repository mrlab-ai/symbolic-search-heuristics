/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_MG_STRIPS_H__
#define __PDDL_MG_STRIPS_H__

#include <pddl/strips.h>
#include <pddl/mutex_pair.h>
#include <pddl/mgroup.h>
#include <pddl/fdr.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_mg_strips {
    pddl_strips_t strips; /*!< Planning task */
    pddl_mgroups_t mg; /*!< Exactly-one mutex groups covering all facts */
};
typedef struct pddl_mg_strips pddl_mg_strips_t;


/**
 * Initialize {mg_strips} from the given STRIPS-represented task {strips}
 * and the given mutex groups.
 * After the initialization, it is guaranteed that:
 * 1. Fact IDs are preserved, but {mg_strips} may have some additional
 *    facts: Every fact from {strips} is present in {mg_strips} with
 *    exactly the same ID. However, there might be some additional facts in
 *    {mg_strips}
 * 2. Operator IDs are preserved: {mg_strips} has the same operators as
 *    {strips} and with the same IDs.
 * 3. All input mutex groups that are subset of some other mutex group are
 *    ignored.
 * 4. All non-redundant input mutex groups are trasnfered into exactly-one
 *    mutex groups: It is either proved that the mutex group is
 *    exactly-one, or it is made exactly-one by adding an auxiliary fact
 *    (in FDR we would call it "none-of-those" fact).
 */
void pddlMGStripsInit(pddl_mg_strips_t *mg_strips,
                      const pddl_strips_t *strips,
                      const pddl_mgroups_t *mgroups);

/**
 * Initialize {mg_strips} as a deep-copy of {in}.
 */
void pddlMGStripsInitCopy(pddl_mg_strips_t *mg_strips,
                          const pddl_mg_strips_t *in);

/**
 * Initialize {mg_strips} from the given FDR-encoded task.
 * After the initialization, it is guaranteed that:
 * 1. Fact IDs are preserved: ID of every fact in {mg_strips} is that same
 *    as the global-ID of the corresponding fact from {fdr}.
 * 2. Operator IDs are preserved: ID of each operator in {mg_strips} is the
 *    same as the ID of the corresponding operator in {fdr}..
 * 3. Each mutex group correspond to an FDR variable, and mutex groups in
 *    {mg_strips} have the same IDs as their corresponding FDR variable
 *    (i.e., they are stored in the same order).
 * 4. Fact's .neg_of property is set to reflect binary variables.
 */
void pddlMGStripsInitFDR(pddl_mg_strips_t *mg_strips, const pddl_fdr_t *fdr);

/**
 * Free allocated memory.
 */
void pddlMGStripsFree(pddl_mg_strips_t *mg_strips);

/**
 * Remove specified facts and operators.
 * This may change IDs of facts and operators.
 */
void pddlMGStripsReduce(pddl_mg_strips_t *mg_strips,
                        const pddl_iset_t *del_facts,
                        const pddl_iset_t *del_ops);

/**
 * Change the order of mutex groups within .mg so that the mutex group with
 * index i will be moved at index reorder[i].
 */
void pddlMGStripsReorderMGroups(pddl_mg_strips_t *mg_strips,
                                const int *reorder);

double pddlMGStripsNumStatesApproxMC(const pddl_mg_strips_t *mg_strips,
                                     const pddl_mutex_pairs_t *mutex,
                                     const char *approxmc_bin,
                                     int fix_fact);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_MG_STRIPS_H__ */
