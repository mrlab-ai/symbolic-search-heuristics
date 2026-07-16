/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_CASCADING_TABLE_H__
#define __PDDL_CASCADING_TABLE_H__

#include <pddl/iset.h>
#include <pddl/iarr.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

typedef struct pddl_cascading_table pddl_cascading_table_t;

/**
 * Free allocated memory.
 */
void pddlCascadingTableDel(pddl_cascading_table_t *t);

/**
 * Creates a deep copy of the given table.
 */
pddl_cascading_table_t *pddlCascadingTableClone(const pddl_cascading_table_t *);

/**
 * Creates a new table from the given mutex group.
 */
pddl_cascading_table_t *pddlCascadingTableNewLeaf(int id, int size);

/**
 * Merges two tables into another one.
 */
pddl_cascading_table_t *pddlCascadingTableMerge(pddl_cascading_table_t *t1,
                                                pddl_cascading_table_t *t2);

/**
 * Further abstract the table.
 * The array abstractions maps IDs between 0 and t->size - 1 to new IDs from
 * the same range or to negative number if such state should be pruned.
 */
void pddlCascadingTableAbstract(pddl_cascading_table_t *t, const int *abstr);

/**
 * Returns value corresponding to the given state.
 */
int pddlCascadingTableValueFromState(pddl_cascading_table_t *t,
                                     const int *state);

/**
 * Returns the number of states represented in the table.
 */
int pddlCascadingTableSize(const pddl_cascading_table_t *t);

/**
 * Returns value on the given index.
 */
int pddlCascadingTableLeafValue(const pddl_cascading_table_t *t, int idx);

/**
 * Returns value for the given left/right values.
 */
int pddlCascadingTableMergeValue(const pddl_cascading_table_t *t,
                                 int left_value,
                                 int right_value);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_CASCADING_TABLE_H__ */
