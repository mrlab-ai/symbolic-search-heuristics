/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_RED_BLACK_FDR_H__
#define __PDDL_RED_BLACK_FDR_H__

#include <pddl/fdr.h>
#include <pddl/black_mgroup.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_red_black_fdr_config {
    int relax_red_vars;
    pddl_black_mgroups_config_t mgroup;
};
typedef struct pddl_red_black_fdr_config pddl_red_black_fdr_config_t;

#define PDDL_RED_BLACK_FDR_CONFIG_INIT \
    { \
        0, /* .relax_red_vars */ \
        PDDL_BLACK_MGROUPS_CONFIG_INIT, /* .mgroup */ \
    }

int pddlRedBlackFDRInitFromStrips(pddl_fdr_t *fdr,
                                  const pddl_strips_t *strips,
                                  const pddl_mgroups_t *mgroup,
                                  const pddl_mutex_pairs_t *mutex,
                                  const pddl_red_black_fdr_config_t *cfg,
                                  pddl_err_t *err);

int pddlRedBlackCheck(const pddl_fdr_t *fdr, pddl_err_t *err);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_RED_BLACK_FDR_H__ */
