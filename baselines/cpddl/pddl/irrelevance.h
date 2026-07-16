/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_IRRELEVANCE_H__
#define __PDDL_IRRELEVANCE_H__

#include <pddl/strips.h>
#include <pddl/fdr.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */


/**
 * Performs irrelevance analysis and finds irrelevant fact, irrelevant
 * operators and also finds static facts (of course, static implies
 * irrelevant).
 * Facts in irrelevant_facts, and operators in irrelenvat_ops, are ignored
 * during the analysis.
 */
int pddlIrrelevanceAnalysis(const pddl_strips_t *strips,
                            pddl_iset_t *irrelevant_facts,
                            pddl_iset_t *irrelevant_ops,
                            pddl_iset_t *static_facts,
                            pddl_err_t *err);

/**
 * Irrelevance analysis working on FDR variables.
 */
int pddlIrrelevanceAnalysisFDR(const pddl_fdr_t *fdr,
                               pddl_iset_t *irrelevant_vars,
                               pddl_iset_t *irrelevant_ops,
                               pddl_err_t *err);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_IRRELEVANCE_H__ */
