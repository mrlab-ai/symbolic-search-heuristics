/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_FDR_PART_STATE_H__
#define __PDDL_FDR_PART_STATE_H__

#include <pddl/fdr_var.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_fdr_fact {
    int var;
    int val;
};
typedef struct pddl_fdr_fact pddl_fdr_fact_t;

struct pddl_fdr_part_state {
    pddl_fdr_fact_t *fact;
    int fact_size;
    int fact_alloc;
};
typedef struct pddl_fdr_part_state pddl_fdr_part_state_t;

/**
 * Initialize empty partial state.
 */
void pddlFDRPartStateInit(pddl_fdr_part_state_t *ps);

/**
 * Initialize the partial state as a copy of src.
 */
void pddlFDRPartStateInitCopy(pddl_fdr_part_state_t *dst,
                              const pddl_fdr_part_state_t *src);

/**
 * Free allocated memory.
 */
void pddlFDRPartStateFree(pddl_fdr_part_state_t *ps);

/**
 * Set the specified fact.
 */
void pddlFDRPartStateSet(pddl_fdr_part_state_t *ps, int var, int val);

/**
 * Remove assignment to the specified variable.
 */
void pddlFDRPartStateUnset(pddl_fdr_part_state_t *ps, int var);

/**
 * Returns value set to the variable var or -1.
 */
int pddlFDRPartStateGet(const pddl_fdr_part_state_t *ps, int var);

/**
 * Returns true if variable var is set in the partial state.
 */
pddl_bool_t pddlFDRPartStateIsSet(const pddl_fdr_part_state_t *ps, int var);

/**
 * Returns true if the partial state is consistent with the given state.
 */
pddl_bool_t pddlFDRPartStateIsConsistentWithState(const pddl_fdr_part_state_t *ps,
                                                  const int *state);

/**
 * Returns true if ps1 is consistent with ps2, i.e., if for every variable
 * defined in ps1, ps2 has the same value.
 */
pddl_bool_t pddlFDRPartStateIsConsistentWithPartState(const pddl_fdr_part_state_t *ps1,
                                                      const pddl_fdr_part_state_t *ps2);

/**
 * Returns the number of fact from {ps} appearing in {state}.
 */
int pddlFDRPartStateStateIntersectionSize(const pddl_fdr_part_state_t *ps,
                                          const int *state);

/**
 * Write partial state to the given state.
 */
void pddlFDRPartStateApplyToState(const pddl_fdr_part_state_t *ps, int *state);

/**
 * Compare function for partial states.
 */
int pddlFDRPartStateCmp(const pddl_fdr_part_state_t *p1,
                        const pddl_fdr_part_state_t *p2);

/**
 * Remap the facts.
 */
void pddlFDRPartStateRemapFacts(pddl_fdr_part_state_t *ps,
                                const pddl_fdr_vars_remap_t *remap);


/**
 * Remap variable IDs
 */
void pddlFDRPartStateRemapVars(pddl_fdr_part_state_t *ps, const int *remap);

/**
 * Converts the partial state to the set of global IDs.
 */
void pddlFDRPartStateToGlobalIDs(const pddl_fdr_part_state_t *ps,
                                 const pddl_fdr_vars_t *vars,
                                 pddl_iset_t *global_ids);

/**
 * a = a \setminus b
 */
void pddlFDRPartStateMinus(pddl_fdr_part_state_t *a,
                           const pddl_fdr_part_state_t *b);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_FDR_PART_STATE_H__ */
