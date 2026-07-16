/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_BLACK_MGROUP_H__
#define __PDDL_BLACK_MGROUP_H__

#include <pddl/strips.h>
#include <pddl/mgroup.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_black_mgroups_config {
    pddl_bool_t lp_add_2cycles; /*!< Add all 2-cycles into LP (default: true) */
    pddl_bool_t lp_add_3cycles; /*!< Add all 3-cycles into LP (default: false) */
    pddl_bool_t weight_facts_with_relaxed_plan; /*!< Use projections to a relaxed
                                                     plan to weight facts */
    pddl_bool_t weight_facts_with_conflicts;
    int num_solutions; /*!< Max number of solutions that should be inferred
                            (default: 1)*/
};
typedef struct pddl_black_mgroups_config pddl_black_mgroups_config_t;

#define PDDL_BLACK_MGROUPS_CONFIG_INIT \
    { \
        pddl_true, /* .lp_add_2cycles */ \
        pddl_false, /* .lp_add_2cycles */ \
        pddl_false, /* .weight_facts_with_relaxed_plan */ \
        pddl_false, /* .weight_facts_with_conflicts */ \
        1, /* .num_solutions */ \
    }

struct pddl_black_mgroup {
    pddl_iset_t mgroup;
    pddl_iset_t mutex_facts;
};
typedef struct pddl_black_mgroup pddl_black_mgroup_t;

struct pddl_black_mgroups {
    pddl_black_mgroup_t *mgroup;
    int mgroup_size;
    int mgroup_alloc;
};
typedef struct pddl_black_mgroups pddl_black_mgroups_t;

void pddlBlackMGroupsInfer(pddl_black_mgroups_t *bmgroups,
                           const pddl_strips_t *strips,
                           const pddl_mgroups_t *mgroups,
                           const pddl_mutex_pairs_t *mutex,
                           const pddl_black_mgroups_config_t *cfg,
                           pddl_err_t *err);

void pddlBlackMGroupsFree(pddl_black_mgroups_t *bmgroups);

void pddlBlackMGroupsPrint(const pddl_strips_t *strips,
                           const pddl_black_mgroups_t *bmgroups,
                           FILE *fout);
#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_BLACK_MGROUP_H__ */
