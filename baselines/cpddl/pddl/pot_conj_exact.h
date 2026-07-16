/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

/**
 * Potential Heuristics over Conjunctions
 * ---------------------------------------
 */

#ifndef __PDDL_POT_CONJ_EXACT_H__
#define __PDDL_POT_CONJ_EXACT_H__

#include <pddl/fdr_conj_exact.h>
#include <pddl/hpot.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_pot_conj_exact_pc_conj {
    /** Conjunction expressed as a partial state in the input FDR task */
    pddl_fdr_part_state_t fdr;
    /** The corresponding binary variable in the P^C FDR task */
    int pc_var;
};
typedef struct pddl_pot_conj_exact_pc_conj pddl_pot_conj_exact_pc_conj_t;

struct pddl_pot_conj_exact {
    /** Number of variables in the input FDR task */
    int var_size;
    /** Potential functions over conjunctions, i.e., in the P^C task */
    pddl_pot_solutions_t pot;

    /** Variables in the P^C_exact FDR task */
    pddl_fdr_vars_t pc_vars;
    /** Set of conjunctions from the P^C_exact task*/
    pddl_pot_conj_exact_pc_conj_t *pc_conj;
    int pc_conj_size;
};
typedef struct pddl_pot_conj_exact pddl_pot_conj_exact_t;

/**
 * Compute potential heuristics over P^{conjs}_exact.
 * The {cfg} configuration must have .fdr set.
 * The conjunctions must be over global IDs of cfg->fdr facts.
 * Return 0 on success, -1 on error.
 */
int pddlPotConjExactInit(pddl_pot_conj_exact_t *pot,
                         const pddl_set_iset_t *conjs,
                         const pddl_hpot_config_t *cfg,
                         pddl_err_t *err);

/**
 * Free allocated memory
 */
void pddlPotConjExactFree(pddl_pot_conj_exact_t *pot);

/**
 * Evaluate potential function in the given FDR state.
 */
int pddlPotConjExactEvalMaxFDRState(const pddl_pot_conj_exact_t *pot,
                                    const pddl_fdr_vars_t *vars,
                                    const int *state);


struct pddl_pot_conj_exact_find_config {
    /** Time limit in seconds. Default: 20 minutes */
    double time_limit;
    /** Maximum number of improvement epochs. Default: 10 */
    int max_epochs;
    /** Maximum considered dimension of conjunctions. Default: 8 */
    int max_conj_dim;
    /** Maximum number of conjunctions tested within one epoch.
     *  Default: unlimited */
    int max_num_conjs;
    /** Log progress every {log_freq} seconds. Default: 1 second */
    double log_freq;
    /** Time limit for each LP used for computation of potential functions.
     *  Default: 30 seconds */
    double lp_time_limit;
    /** Whenever improvement is achieved, write the complete set of
     *  conjunctions into the file {write_progress_prefix}.{epoch_idx}
     *  where {epoch_idx} is index of the epoch formatted as %04d.
     *  Default: NULL, i.e., turned off */
    const char *write_progress_prefix;
};
typedef struct pddl_pot_conj_exact_find_config pddl_pot_conj_exact_find_config_t;

#define PDDL_POT_CONJ_EXACT_FIND_CONFIG_INIT \
    { \
        20. * 60., /* .time_limit */ \
        10, /* .max_epochs */ \
        8, /* .max_conj_dim */ \
        INT_MAX, /* .max_num_conjs */ \
        1., /* .log_freq */ \
        30., /* .lp_time_limit */ \
        NULL, /* .write_progress_prefix */ \
    }

void pddlPotConjExactFindConfigLog(const pddl_pot_conj_exact_find_config_t *cfg,
                                   pddl_err_t *err);

/**
 * Find conjunctions improving one-dimensional potential heuritic and add
 * these conjunctions into {conjs}. If {conjs} is non-empty, conjunctions
 * from {conjs} are always used, i.e., {conjs} is input/output argument.
 */
int pddlPotConjExactFind(pddl_set_iset_t *conjs,
                         int *best_hvalue,
                         double *best_objval,
                         const pddl_fdr_t *fdr,
                         const pddl_mutex_pairs_t *mutex,
                         const pddl_pot_conj_exact_find_config_t *cfg,
                         const pddl_hpot_config_t *pot_cfg,
                         pddl_err_t *err);

/**
 * Loads the set of conjunctions and the best h-value stored in the given
 * file. It is assumed the file was written by the pddlPotConjExactFind()
 * function.
 */
int pddlPotConjExactLoadFromFile(pddl_set_iset_t *conjs,
                                 int *best_hvalue,
                                 const pddl_fdr_t *fdr,
                                 const char *filename,
                                 pddl_err_t *err);

int pddlPotConjExactMaxInitHValueBase(const pddl_fdr_t *fdr,
                                      const pddl_mutex_pairs_t *mutex,
                                      pddl_err_t *err);
int pddlPotConjExactMaxInitHValueOnePair(const pddl_fdr_t *fdr,
                                         const pddl_mutex_pairs_t *mutex,
                                         pddl_err_t *err);
int pddlPotConjExactMaxInitHValueOneTriple(const pddl_fdr_t *fdr,
                                           const pddl_mutex_pairs_t *mutex,
                                           pddl_err_t *err);
int pddlPotConjExactMaxInitHValueTwoPairs(const pddl_fdr_t *fdr,
                                          const pddl_mutex_pairs_t *mutex,
                                          pddl_err_t *err);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_POT_CONJ_EXACT_H__ */
