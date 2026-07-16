/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_LIFTED_MGROUP_HTABLE_H__
#define __PDDL_LIFTED_MGROUP_HTABLE_H__

#include <pddl/extarr.h>
#include <pddl/lifted_mgroup.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_lifted_mgroup_htable {
    pddl_htable_t *htable; /*!< Hash table of all lifted mgroups */
    pddl_extarr_t *mgroup; /*!< Extensible array holding htable's elements */
    int mgroup_size; /*!< Number of stored mgroups */
};
typedef struct pddl_lifted_mgroup_htable pddl_lifted_mgroup_htable_t;


/**
 * Initialize empty hash table.
 */
void pddlLiftedMGroupHTableInit(pddl_lifted_mgroup_htable_t *h);

/**
 * Free allocated memory.
 */
void pddlLiftedMGroupHTableFree(pddl_lifted_mgroup_htable_t *h);

/**
 * Adds the given mutex group to the hash table and returns its ID.
 */
int pddlLiftedMGroupHTableAdd(pddl_lifted_mgroup_htable_t *h,
                              const pddl_lifted_mgroup_t *mg);

/**
 * Returns mutex group with the given ID.
 */
const pddl_lifted_mgroup_t *pddlLiftedMGroupHTableGet(
                                const pddl_lifted_mgroup_htable_t *h, int id);


#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_LIFTED_MGROUP_HTABLE_H__ */
