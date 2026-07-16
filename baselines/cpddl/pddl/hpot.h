/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_HPOT_H__
#define __PDDL_HPOT_H__

#include <pddl/pot.h>
#include <pddl/task.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

enum pddl_hpot_type {
    PDDL_HPOT_OPT_STATE_TYPE = 1,
    PDDL_HPOT_OPT_ALL_SYNTACTIC_STATES_TYPE,
    PDDL_HPOT_OPT_ALL_STATES_MUTEX_TYPE,
    PDDL_HPOT_OPT_SAMPLED_STATES_TYPE,
    PDDL_HPOT_OPT_ENSEMBLE_SAMPLED_STATES_TYPE,
    PDDL_HPOT_OPT_ENSEMBLE_DIVERSIFICATION_TYPE,
    PDDL_HPOT_OPT_ENSEMBLE_ALL_STATES_MUTEX_TYPE,
    _PDDL_HPOT_TYPE_SIZE,
};
typedef enum pddl_hpot_type pddl_hpot_type_t;

/**
 * Maximize the h-value for the given state
 */
struct pddl_hpot_config_opt_state {
    /** State for which to optimize. If NULL, initial state is used. */
    const int *fdr_state;
};
typedef struct pddl_hpot_config_opt_state pddl_hpot_config_opt_state_t;

#define _PDDL_HPOT_CONFIG_OPT_STATE_INIT \
    { \
        NULL, /* .fdr_state */ \
    }
    

/**
 * Additional state constraint configuration.
 * It first finds maximum objective value for the specified state s and then
 * adds the constraint enforcing this objective value multiplied by .coef
 * for s.
 */
struct pddl_hpot_config_add_state_constr {
    /** Add constraint maximizing h-value for the initial state. default: false */
    pddl_bool_t init_state;
    /** If set to non-NULL, add the constraint maximizing h-value for the
     *  given state. default: NULL */
    const int *fdr_state;
    /** Coefficient used for the added state constraint. default: 1 */
    double coef;
    /** If true, hmax0 configuration is not used for finding maximal
     *  objective value for the state even if .hmax0 is set true in
     *  pddl_hpot_config_t. default: false */
    pddl_bool_t ignore_hmax0;
};
typedef struct pddl_hpot_config_add_state_constr
    pddl_hpot_config_add_state_constr_t;

#define _PDDL_HPOT_CONFIG_ADD_STATE_CONSTR \
    { \
        pddl_false, /* .init_state */ \
        NULL, /* .fdr_state */ \
        1., /* .coef */ \
        pddl_false, /* .ignore_hmax0 */ \
    }

/**
 * Maximize the average h-value over all syntactic states
 */
struct pddl_hpot_config_opt_all_syntactic_states {
    /** Additional state constraint */
    pddl_hpot_config_add_state_constr_t add_state_constr;
};
typedef struct pddl_hpot_config_opt_all_syntactic_states
    pddl_hpot_config_opt_all_syntactic_states_t;

#define _PDDL_HPOT_CONFIG_OPT_ALL_SYNTACTIC_STATES_INIT \
    { \
        _PDDL_HPOT_CONFIG_ADD_STATE_CONSTR, /* .add_state_constr */ \
    }

/**
 * Maximize the average h-value over reachable states estimated using
 * mutexes.
 */
struct pddl_hpot_config_opt_all_states_mutex {
    /** TODO */
    int mutex_size;
    /** Additional state constraint */
    pddl_hpot_config_add_state_constr_t add_state_constr;
};
typedef struct pddl_hpot_config_opt_all_states_mutex
    pddl_hpot_config_opt_all_states_mutex_t;

#define _PDDL_HPOT_CONFIG_OPT_ALL_STATES_MUTEX_INIT \
    { \
        2, /* .mutex_size */ \
        _PDDL_HPOT_CONFIG_ADD_STATE_CONSTR, /* .add_state_constr */ \
    }

/**
 * Maximize the average h-value over the sampled states.
 */
struct pddl_hpot_config_opt_sampled_states {
    /** Number of sampled states. default: 1000 */
    int num_samples;
    /** True if random walk should be used. default: true */
    pddl_bool_t use_random_walk;
    /** Sample states by uniform sampling over syntactic states. default: false */
    pddl_bool_t use_syntactic_samples;
    /** Sample (syntactic) states while removing mutex states */
    pddl_bool_t use_mutex_samples;
    /** Additional state constraint */
    pddl_hpot_config_add_state_constr_t add_state_constr;
};
typedef struct pddl_hpot_config_opt_sampled_states
    pddl_hpot_config_opt_sampled_states_t;

#define _PDDL_HPOT_CONFIG_OPT_SAMPLED_STATES_INIT \
    { \
        1000, /* .num_samples */ \
        pddl_true, /* .use_random_walk */ \
        pddl_false, /* .use_syntactic_samples */ \
        pddl_false, /* .use_mutex_samples */ \
        _PDDL_HPOT_CONFIG_ADD_STATE_CONSTR, /* .add_state_constr */ \
    }

/**
 * Ensemble each maximizing for a sampled state
 */
struct pddl_hpot_config_opt_ensemble_sampled_states {
    /** Number of sampled states. default: 1000 */
    int num_samples;
    /** True if random walk should be used. default: true */
    pddl_bool_t use_random_walk;
    /** Sample states by uniform sampling over syntactic states. default: false */
    pddl_bool_t use_syntactic_samples;
    /** Sample (syntactic) states while removing mutex states */
    pddl_bool_t use_mutex_samples;
};
typedef struct pddl_hpot_config_opt_ensemble_sampled_states
    pddl_hpot_config_opt_ensemble_sampled_states_t;

#define _PDDL_HPOT_CONFIG_OPT_ENSEMBLE_SAMPLED_STATES_INIT \
    { \
        1000, /* .num_samples */ \
        pddl_true, /* .use_random_walk */ \
        pddl_false, /* .use_syntactic_samples */ \
        pddl_false, /* .mutex */ \
    }

/**
 * Ensemble constructed with the diversification algorithm
 */
struct pddl_hpot_config_opt_ensemble_diversification {
    /** Number of sampled states. default: 1000 */
    int num_samples;
    /** True if random walk should be used. default: true */
    pddl_bool_t use_random_walk;
    /** Sample states by uniform sampling over syntactic states. default: false */
    pddl_bool_t use_syntactic_samples;
    /** Sample (syntactic) states while removing mutex states. default: false */
    pddl_bool_t use_mutex_samples;
};
typedef struct pddl_hpot_config_opt_ensemble_diversification
    pddl_hpot_config_opt_ensemble_diversification_t;

#define _PDDL_HPOT_CONFIG_OPT_ENSEMBLE_DIVERSIFICATION_INIT \
    { \
        1000, /* .num_samples */ \
        pddl_true, /* .use_random_walk */ \
        pddl_false, /* .use_syntactic_samples */ \
        pddl_false, /* .mutex */ \
    }

/**
 * Ensemble constructed with the diversification algorithm
 */
struct pddl_hpot_config_opt_ensemble_all_states_mutex {
    /** TODO */
    int cond_size;
    /** TODO */
    int mutex_size;
    /** Number of sampled states conditioned on random sets of facts.
     *  default: 0, i.e., disabled */
    int num_rand_samples;
};
typedef struct pddl_hpot_config_opt_ensemble_all_states_mutex
    pddl_hpot_config_opt_ensemble_all_states_mutex_t;

#define _PDDL_HPOT_CONFIG_OPT_ENSEMBLE_ALL_STATES_MUTEX_INIT \
    { \
        1, /* .cond_size */ \
        2, /* .mutex_size */ \
        0, /* .num_rand_samples */ \
    }

struct pddl_hpot_config {
    /** Type of the potential heuristic(s). Default: max h-value for the
     *  initial state. */
    pddl_hpot_type_t type;
    /** Input FDR planning task */
    const pddl_fdr_t *fdr;
    /** Input MG-Strips representation of the corresponding .fdr task */
    const pddl_mg_strips_t *mg_strips;
    /** Input set of mutexes */
    const pddl_mutex_pairs_t *mutex;
    /** If true, disambiguation is used. default: true */
    pddl_bool_t disambiguation;
    /** If true, weak disambiguation is used. default: false */
    pddl_bool_t weak_disambiguation;
    /** Infer operator potentials. default: false */
    pddl_bool_t op_pot;
    /** Infer real-valued operator potentials. default: false */
    pddl_bool_t op_pot_real;
    /** Infer potentials so that max(h^P,0) is consistent and admissible.
     *  default: false*/
    pddl_bool_t hmax0;
    /** Time limit for each round of LP solver. default: disabled */
    float lp_time_limit;

    pddl_hpot_config_opt_state_t opt_state;
    pddl_hpot_config_opt_all_syntactic_states_t opt_all_syntactic_states;
    pddl_hpot_config_opt_all_states_mutex_t opt_all_states_mutex;
    pddl_hpot_config_opt_sampled_states_t opt_sampled_states;
    pddl_hpot_config_opt_ensemble_sampled_states_t opt_ensemble_sampled_states;
    pddl_hpot_config_opt_ensemble_diversification_t opt_ensemble_diversification;
    pddl_hpot_config_opt_ensemble_all_states_mutex_t opt_ensemble_all_states_mutex;

    /** Next configuration in case more than one potential functions (or
     *  ensembles) should be found -- .fdr, .mg_strips and .mutex needs to
     *  be set in the first configuration struct and then it is
     *  automatically used in all subsequent ones. */
    struct pddl_hpot_config *next;
};
typedef struct pddl_hpot_config pddl_hpot_config_t;

#define PDDL_HPOT_CONFIG_INIT \
    { \
        PDDL_HPOT_OPT_STATE_TYPE, \
        NULL, /* .fdr */ \
        NULL, /* .mg_strips */ \
        NULL, /* .mutex */ \
        pddl_true, /* .disambiguation */ \
        pddl_false, /* .weak_disambiguation */ \
        pddl_false, /* .op_pot */ \
        pddl_false, /* .op_pot_real */ \
        pddl_false, /* .hmax0 */ \
        -1., /* .lp_time_limit */ \
        _PDDL_HPOT_CONFIG_OPT_STATE_INIT, /* .opt_state */ \
        _PDDL_HPOT_CONFIG_OPT_ALL_SYNTACTIC_STATES_INIT, /* .opt_all_syntactic_states */ \
        _PDDL_HPOT_CONFIG_OPT_ALL_STATES_MUTEX_INIT, /* .opt_all_states_mutex */ \
        _PDDL_HPOT_CONFIG_OPT_SAMPLED_STATES_INIT, /* .opt_sampled_states */ \
        _PDDL_HPOT_CONFIG_OPT_ENSEMBLE_SAMPLED_STATES_INIT, /* .opt_ensemble_sampled_states */ \
        _PDDL_HPOT_CONFIG_OPT_ENSEMBLE_DIVERSIFICATION_INIT, /* .opt_ensemble_diversification */ \
        _PDDL_HPOT_CONFIG_OPT_ENSEMBLE_ALL_STATES_MUTEX_INIT, /* .opt_ensemble_all_states_mutex */ \
        NULL, /* .next */ \
    }

/**
 * Initialize default configuration.
 */
void pddlHPotConfigInit(pddl_hpot_config_t *cfg);

/**
 * Replace inital state with the specified state in all configurations.
 */
void pddlHPotConfigReplaceInitStateWithState(pddl_hpot_config_t *cfg,
                                             const int *fdr_state);

/**
 * Log the given configuration
 */
void pddlHPotConfigLog(const pddl_hpot_config_t *cfg, pddl_err_t *err);

/**
 * Check the configuration.
 * Returns 0 if everything is ok.
 */
int pddlHPotConfigCheck(const pddl_hpot_config_t *cfg, pddl_err_t *err);

/**
 * Returns true if the configuration requires .mg_strips
 */
pddl_bool_t pddlHPotConfigNeedMGStrips(const pddl_hpot_config_t *cfg);

/**
 * Returns true if the configuration requires .mutex
 */
pddl_bool_t pddlHPotConfigNeedMutex(const pddl_hpot_config_t *cfg);

/**
 * Return true if there is no potential function added to the configuration.
 */
pddl_bool_t pddlHPotConfigIsEmpty(const pddl_hpot_config_t *cfg);

/**
 * Returns true if the config produces an ensamble of potential
 * heuristics.
 */
pddl_bool_t pddlHPotConfigIsEnsemble(const pddl_hpot_config_t *cfg);

/**
 * Compute potential functions corresponding to the provided configuration.
 */
int pddlHPot(pddl_pot_solutions_t *sols,
             const pddl_hpot_config_t *cfg,
             pddl_err_t *err);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_HPOT_H__ */
