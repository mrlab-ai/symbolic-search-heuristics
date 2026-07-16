/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_TRANSITION_H__
#define __PDDL_TRANSITION_H__

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_transition {
    int from;
    int to;
};
typedef struct pddl_transition pddl_transition_t;

struct pddl_transitions {
    pddl_transition_t *trans;
    int trans_size;
    int trans_alloc;
};
typedef struct pddl_transitions pddl_transitions_t;

/**
 * Initialize an empty set of transitions.
 */
void pddlTransitionsInit(pddl_transitions_t *ts);

/**
 * Free allocated memory.
 */
void pddlTransitionsFree(pddl_transitions_t *ts);

/**
 * Make the set empty.
 */
void pddlTransitionsEmpty(pddl_transitions_t *ts);

/**
 * Adds transition to the set.
 */
void pddlTransitionsAdd(pddl_transitions_t *ts, int from, int to);

/**
 * Add transitions from src at the end of the list ts.
 */
void pddlTransitionsUnion(pddl_transitions_t *ts,
                          const pddl_transitions_t *src);


/**
 * Sort the transitions
 */
void pddlTransitionsSort(pddl_transitions_t *ts);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_TRANSITION_H__ */
