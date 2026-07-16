/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_ASNETS_POLICY_DISTRIBUTION_H__
#define __PDDL_ASNETS_POLICY_DISTRIBUTION_H__

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_asnets_policy_distribution {
    /** Number of applicable operators */
    int op_size;
    int op_alloc;
    /** Array of applicable operators */
    int *op_id;
    /** Array of probabilities/confidence of the corresponding operator
     *  being selected by the policy */
    float *prob;
};
typedef struct pddl_asnets_policy_distribution
    pddl_asnets_policy_distribution_t;

/**
 * Initialize empty distribution
 */
void pddlASNetsPolicyDistributionInit(pddl_asnets_policy_distribution_t *d);

/**
 * Free allocated memory
 */
void pddlASNetsPolicyDistributionFree(pddl_asnets_policy_distribution_t *d);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_ASNETS_POLICY_DISTRIBUTION_H__ */
