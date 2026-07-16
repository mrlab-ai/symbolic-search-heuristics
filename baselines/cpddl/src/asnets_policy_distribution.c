/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/asnets_policy_distribution.h"

void pddlASNetsPolicyDistributionInit(pddl_asnets_policy_distribution_t *d)
{
    ZEROIZE(d);
}

void pddlASNetsPolicyDistributionFree(pddl_asnets_policy_distribution_t *d)
{
    if (d->op_id != NULL)
        FREE(d->op_id);
    if (d->prob != NULL)
        FREE(d->prob);
}
