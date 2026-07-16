/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_TS_H__
#define __PDDL_TS_H__

#include <pddl/strips.h>
#include <pddl/strips_fact_cross_ref.h>
#include <pddl/mutex_pair.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * Transition system.
 */
struct pddl_ts {
    int num_states; /*!< Number of states */
    pddl_iset_t *tr; /*!< Adjecancy matrix of states with set of labels
                         on each edge */
    int init_state; /*!< ID of the init state */
};
typedef struct pddl_ts pddl_ts_t;

#define PDDL_TS_FOR_EACH_TRANSITION(TS, STATE_FROM, STATE_TO, TR) \
    for ((STATE_FROM) = 0, (TR) = (TS)->tr; \
            (STATE_FROM) < (TS)->num_states; ++(STATE_FROM)) \
        for ((STATE_TO) = 0; (STATE_TO) < (TS)->num_states; \
                ++(STATE_TO), (TR) += 1)

#define PDDL_TS_FOR_EACH_NONEMPTY_TRANSITION(TS, STATE_FROM, STATE_TO, TR) \
    for ((STATE_FROM) = 0, (TR) = (TS)->tr; \
            (STATE_FROM) < (TS)->num_states; ++(STATE_FROM)) \
        for ((STATE_TO) = 0; (STATE_TO) < (TS)->num_states; \
                ++(STATE_TO), (TR) += 1) \
            if (pddlISetSize(TR) > 0)

#define PDDL_TS_FOR_EACH_NONEMPTY_TRANSITION_FROM(TS, FROM, STATE_TO, TR) \
    for ((STATE_TO) = 0, (TR) = (TS)->tr + (FROM) * (TS)->num_states; \
            (STATE_TO) < (TS)->num_states; ++(STATE_TO), (TR) += 1) \
        if (pddlISetSize(TR) > 0)

#define PDDL_TS_FOR_EACH_NONEMPTY_TRANSITION_TO(TS, TO, FROM, TR) \
    for ((FROM) = 0, (TR) = (TS)->tr + (FROM) * (TS)->num_states + (TO); \
            (FROM) < (TS)->num_states; ++(FROM), (TR) += (TS)->num_states) \
        if (pddlISetSize(TR) > 0)


/**
 * Initialize a transition system with num_states states.
 */
void pddlTSInit(pddl_ts_t *ts, int num_states);

/**
 * Free allocated memory.
 */
void pddlTSFree(pddl_ts_t *ts);

/**
 * Adds transition from s1 to s2 with label l
 */
void pddlTSAddTransition(pddl_ts_t *ts, int s1, int s2, int l);

/**
 * Initialize transition system as a projection to the given fam-group.
 * TODO: Explain how the projection looks like because we are not computing
 *       actual "full" projection.
 */
void pddlTSInitProjToFAMGroup(pddl_ts_t *ts,
                              const pddl_strips_t *strips,
                              const pddl_strips_fact_cross_ref_t *cr,
                              const pddl_iset_t *famgroup);

/**
 * Create a condensation of ts.
 */
void pddlTSCondensate(pddl_ts_t *cond, const pddl_ts_t *ts);

/**
 * Prune states that are not reachable from the specified state.
 */
void pddlTSPruneUnreachableStates(pddl_ts_t *ts, int state);

/**
 * Returns transition leading from abstract state from to abstract state
 * to.
 */
_pddl_inline const pddl_iset_t *pddlTSTransition(const pddl_ts_t *ts,
                                                 int from, int to)
{
    return ts->tr + from * ts->num_states + to;
}

_pddl_inline pddl_iset_t *pddlTSTransitionW(pddl_ts_t *ts, int from, int to)
{
    return ts->tr + from * ts->num_states + to;
}

void pddlTSPrintDebug(const pddl_ts_t *ts, FILE *fout);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_TS_H__ */
