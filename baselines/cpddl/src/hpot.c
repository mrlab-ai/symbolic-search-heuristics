/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "_heur.h"
#include "pddl/fdr_state_sampler.h"
#include "pddl/set.h"
#include "pddl/hpot.h"

#define INIT_STATE_RHS_DECREASE_STEP 0.125
#define INIT_STATE_RHS_DECREASE_MAX_STEPS 8

static const uint32_t rand_diverse_seed = 131071;
static const uint32_t rand_seed = 131071;

enum status {
    ST_SOLVED = 0,
    ST_NOT_SOLVED = 1,
    ST_ERR = -1,
    ST_TIMEOUT = -2,
};
typedef enum status status_t;

struct hpot {
    /** Input configuration */
    const pddl_hpot_config_t *cfg;
    /** Output set of potential functions */
    pddl_pot_solutions_t *sols;

    /** Underlying structure for inference of potential functions */
    pddl_pot_t pot;
    pddl_pot_solve_config_t pot_cfg;

    /** Prepared data for adding additional state constraint */
    struct {
        pddl_iset_t lp_vars;
        double rhs;
        pddl_pot_solution_t sol;
        pddl_bool_t is_init;
        pddl_bool_t enabled;
    } add_state_constr;

    /** State samplers */
    pddl_fdr_state_sampler_t state_sampler_random_walk;
    int state_sampler_random_walk_set;
    pddl_fdr_state_sampler_t state_sampler_syntactic;
    int state_sampler_syntactic_set;
    pddl_fdr_state_sampler_t state_sampler_mutex;
    int state_sampler_mutex_set;
};
typedef struct hpot hpot_t;

static int hpotInit(hpot_t *hpot,
                    const pddl_hpot_config_t *cfg,
                    pddl_pot_solutions_t *sols,
                    pddl_err_t *err)
{
    ZEROIZE(hpot);
    hpot->cfg = cfg;
    hpot->sols = sols;

    if (cfg->fdr == NULL)
        ERR_RET(err, -1, "Config Error: .fdr needs to be set.");

    pddl_pot_solve_config_t _cfg = PDDL_POT_SOLVE_CONFIG_INIT;
    hpot->pot_cfg = _cfg;

    if (cfg->weak_disambiguation){
        if (cfg->mg_strips == NULL){
            ERR_RET(err, -1, "Config Error: .mg_strips needs to be set if"
                     " the weak disambiguation is used");
        }
        if (cfg->mutex == NULL){
            ERR_RET(err, -1, "Config Error: .mutex needs to be set if"
                     " the weak disambiguation is used");
        }

        if (pddlPotInitSingleFactDisamb(&hpot->pot, cfg->mg_strips, cfg->mutex) == 0){
            LOG(err, "Initialized with weak-disambiguation."
                " vars: %d, ops: %d,"
                " goal-constr: %d, maxpots: %d",
                hpot->pot.var_size,
                hpot->pot.op_size,
                hpot->pot.c_goal.c_size,
                hpot->pot.maxpot.maxpot_size);
        }else{
            LOG(err, "Disambiguation proved the task unsolvable.");
            sols->unsolvable = 1;
            return 1;
        }

    }else if (cfg->disambiguation){
        if (cfg->mg_strips == NULL){
            ERR_RET(err, -1, "Config Error: .mg_strips needs to be set if"
                     " the weak disambiguation is used");
        }
        if (cfg->mutex == NULL){
            ERR_RET(err, -1, "Config Error: .mutex needs to be set if"
                     " the weak disambiguation is used");
        }

        if (pddlPotInit(&hpot->pot, cfg->mg_strips, cfg->mutex) == 0){
            LOG(err, "Initialized with disambiguation."
                " vars: %d, ops: %d,"
                " goal-constr: %d, maxpots: %d",
                hpot->pot.var_size,
                hpot->pot.op_size,
                hpot->pot.c_goal.c_size,
                hpot->pot.maxpot.maxpot_size);
        }else{
            LOG(err, "Disambiguation proved the task unsolvable.");
            sols->unsolvable = 1;
            return 1;
        }

    }else{
        pddlPotInitFDR(&hpot->pot, cfg->fdr);
        LOG(err, "Initialized without disambiguation."
            " vars: %d, ops: %d,"
            " goal-constr: %d, maxpots: %d",
            hpot->pot.var_size,
            hpot->pot.op_size,
            hpot->pot.c_goal.c_size,
            hpot->pot.maxpot.maxpot_size);
    }

    pddlPotSolutionInit(&hpot->add_state_constr.sol);

    if (cfg->op_pot)
        hpot->pot_cfg.op_pot = pddl_true;
    if (cfg->op_pot_real)
        hpot->pot_cfg.op_pot_real = pddl_true;
    if (cfg->lp_time_limit > 0.)
        hpot->pot_cfg.lp_time_limit = cfg->lp_time_limit;

    return 0;
}

static void hpotFree(hpot_t *hpot)
{
    pddlISetFree(&hpot->add_state_constr.lp_vars);
    pddlPotSolutionFree(&hpot->add_state_constr.sol);
    if (hpot->state_sampler_random_walk_set)
        pddlFDRStateSamplerFree(&hpot->state_sampler_random_walk);
    if (hpot->state_sampler_syntactic_set)
        pddlFDRStateSamplerFree(&hpot->state_sampler_syntactic);
    if (hpot->state_sampler_mutex_set)
        pddlFDRStateSamplerFree(&hpot->state_sampler_mutex);
    pddlPotFree(&hpot->pot);
}

static status_t hpotSolve(hpot_t *hpot,
                          pddl_pot_solution_t *sol,
                          pddl_bool_t ignore_hmax0,
                          pddl_err_t *err)
{
    status_t ret = ST_SOLVED;

    if (hpot->cfg->hmax0 && !ignore_hmax0)
        pddlPotSetMinOpConsistencyConstrAll(&hpot->pot);
    int st = pddlPotSolve(&hpot->pot, &hpot->pot_cfg, sol, err);
    if (hpot->cfg->hmax0 && !ignore_hmax0)
        pddlPotDisableMinOpConsistencyConstrAll(&hpot->pot);

    if (st == 0){
        LOG(err, "Have a solution. objval: %.4f, suboptimal: %s",
            sol->objval, F_BOOL(sol->suboptimal));
        ret = ST_SOLVED;

    }else if (sol->timed_out){
        LOG(err, "Solution not found. timed-out: %s", F_BOOL(sol->timed_out));
        ret = ST_TIMEOUT;

    }else if (sol->error){
        LOG(err, "Error occurred while searching for a solution.");
        TRACE(err);
        ret = ST_ERR;

    }else{
        LOG(err, "Solution not found.");
        ret = ST_NOT_SOLVED;
    }
    return ret;
}

static status_t hpotInitAddStateConstr(hpot_t *hpot,
                                       const pddl_hpot_config_add_state_constr_t *cfg,
                                       pddl_err_t *err)
{
    CTX(err, "+I");
    PANIC_IF(cfg->coef < 0. || (cfg->init_state && cfg->fdr_state != NULL),
             "Invalid .add_state_constr configuration");
    PANIC_IF(hpot->add_state_constr.enabled,
             "Second initialization of .add_state_constr constraint.");
    if (!cfg->init_state && cfg->fdr_state == NULL){
        CTXEND(err);
        return ST_SOLVED;
    }

    // Determine state for which to compute maximal h-value
    const int *add_state = NULL;
    if (cfg->init_state){
        add_state = hpot->cfg->fdr->init;
    }else{
        add_state = cfg->fdr_state;
    }
    hpot->add_state_constr.is_init = (add_state == hpot->cfg->fdr->init);

    pddlPotSetObjFDRState(&hpot->pot, &hpot->cfg->fdr->var, add_state);
    status_t st = hpotSolve(hpot, &hpot->add_state_constr.sol,
                            cfg->ignore_hmax0, err);
    if (st != ST_SOLVED){
        CTXEND(err);
        if (st == ST_ERR)
            TRACE_RET(err, st);
        return st;
    }

    double h = pddlPotSolutionEvalFDRStateFlt(&hpot->add_state_constr.sol,
                                              &hpot->cfg->fdr->var, add_state);
    LOG(err, "Solved for the %sstate: sum: %.4f,"
              " objval: %.4f, suboptimal: %s",
              (add_state == hpot->cfg->fdr->init ? "initial " : ""),
              h, hpot->add_state_constr.sol.objval,
              F_BOOL(hpot->add_state_constr.sol.suboptimal));
    h = hpot->add_state_constr.sol.objval;
    if (h < 0.)
        h = 0.;

    double add_state_coef = cfg->coef;
    if (cfg->coef <= 0.)
        add_state_coef = 1.;
    hpot->add_state_constr.rhs = h * add_state_coef;

    for (int var = 0; var < hpot->cfg->fdr->var.var_size; ++var){
        int v = hpot->cfg->fdr->var.var[var].val[add_state[var]].global_id;
        pddlISetAdd(&hpot->add_state_constr.lp_vars, v);
    }
    LOG(err, "Found %sstate lower bound: %.4f",
        (cfg->init_state ? "initial " : ""), hpot->add_state_constr.rhs);
    hpot->add_state_constr.enabled = pddl_true;
    CTXEND(err);
    return ST_SOLVED;
}

static status_t hpotInitStateMaxHValue(hpot_t *hpot, int *h, pddl_err_t *err)
{
    CTX(err, "I-max-hvalue");
    if (hpot->add_state_constr.enabled && hpot->add_state_constr.is_init){
        *h = pddlPotSolutionEvalFDRState(&hpot->add_state_constr.sol,
                                         &hpot->cfg->fdr->var,
                                         hpot->cfg->fdr->init);
        LOG(err, "Taking precomputed solution from +I: h-value: %d,"
            " objval: %.4f, suboptimal: %s",
            *h, hpot->add_state_constr.sol.objval,
            F_BOOL(hpot->add_state_constr.sol.suboptimal));
        CTXEND(err);
        return ST_SOLVED;
    }
    pddlPotSetObjFDRState(&hpot->pot, &hpot->cfg->fdr->var,
                          hpot->cfg->fdr->init);
    pddl_pot_solution_t sol;
    pddlPotSolutionInit(&sol);
    status_t st = hpotSolve(hpot, &sol, pddl_false, err);
    if (st != ST_SOLVED){
        CTXEND(err);
        if (st == ST_ERR)
            TRACE_RET(err, st);
        return st;
    }

    *h = pddlPotSolutionEvalFDRState(&sol, &hpot->cfg->fdr->var,
                                     hpot->cfg->fdr->init);
    LOG(err, "Solved for the initial state: h-value: %d,"
              " objval: %.4f, suboptimal: %s",
              *h, sol.objval, F_BOOL(sol.suboptimal));
    pddlPotSolutionFree(&sol);
    CTXEND(err);
    return ST_SOLVED;
}


static pddl_fdr_state_sampler_t *hpotGetStateSampler(hpot_t *hpot,
                                                     pddl_bool_t use_random_walk,
                                                     pddl_bool_t use_syntactic_samples,
                                                     pddl_bool_t use_mutex_samples,
                                                     pddl_err_t *err)
{
    if (use_random_walk){
        if (hpot->state_sampler_random_walk_set)
            return &hpot->state_sampler_random_walk;
        int hinit;
        status_t st = hpotInitStateMaxHValue(hpot, &hinit, err);
        if (st == ST_ERR){
            TRACE_RET(err, NULL);
        }else if (st != ST_SOLVED){
            ERR_RET(err, NULL, "Could not create a sampler because of"
                    " a missing heuristic estimate for the initial state.");
        }

        int max_steps = pddlFDRStateSamplerComputeMaxStepsFromHeurInit(hpot->cfg->fdr, hinit);
        pddlFDRStateSamplerInitRandomWalk(&hpot->state_sampler_random_walk,
                                          hpot->cfg->fdr, max_steps, err);
        hpot->state_sampler_random_walk_set = 1;
        return &hpot->state_sampler_random_walk;

    }else if (use_syntactic_samples){
        if (hpot->state_sampler_syntactic_set)
            return &hpot->state_sampler_syntactic;
        pddlFDRStateSamplerInitSyntactic(&hpot->state_sampler_syntactic,
                                         hpot->cfg->fdr, err);
        return &hpot->state_sampler_syntactic;

    }else if (use_mutex_samples){
        if (hpot->state_sampler_mutex_set)
            return &hpot->state_sampler_mutex;
        pddlFDRStateSamplerInitSyntacticMutex(&hpot->state_sampler_mutex,
                                              hpot->cfg->fdr, hpot->cfg->mutex, err);
        return &hpot->state_sampler_mutex;
    }

    PANIC("No state sampler specified!");
    return NULL;
}

static status_t hpotSolveAndAdd(hpot_t *hpot, pddl_err_t *err)
{
    pddl_pot_solution_t sol;
    pddlPotSolutionInit(&sol);
    status_t ret = hpotSolve(hpot, &sol, pddl_false, err);
    if (ret == ST_SOLVED)
        pddlPotSolutionsAdd(hpot->sols, &sol);
    pddlPotSolutionFree(&sol);

    return ret;
}

static status_t hpotSolveAndAddWithStateConstr(hpot_t *hpot, pddl_err_t *err)
{
    if (!hpot->add_state_constr.enabled)
        return hpotSolveAndAdd(hpot, err);

    if (hpot->cfg->hmax0){
        LOG(err, "Setting start solution from the previous +I optimization.");
        pddlPotSetStartSolution(&hpot->pot, &hpot->add_state_constr.sol);
    }

    double rhs = hpot->add_state_constr.rhs;
    pddlPotSetLowerBoundConstr(&hpot->pot, &hpot->add_state_constr.lp_vars, rhs);
    status_t st = ST_NOT_SOLVED;
    for (int i = 0; i < INIT_STATE_RHS_DECREASE_MAX_STEPS && st != ST_SOLVED; ++i){
        pddlPotDecreaseLowerBoundConstrRHS(&hpot->pot, INIT_STATE_RHS_DECREASE_STEP);
        double rhs = pddlPotGetLowerBoundConstrRHS(&hpot->pot);
        LOG(err, "Setting lower bound state constraint with rhs: %.4f", rhs);

        st = hpotSolveAndAdd(hpot, err);
        if (st == ST_TIMEOUT){
            if (hpot->cfg->hmax0)
                pddlPotResetStartSolution(&hpot->pot);
            pddlPotResetLowerBoundConstr(&hpot->pot);
            return st;

        }else if (st == ST_ERR){
            if (hpot->cfg->hmax0)
                pddlPotResetStartSolution(&hpot->pot);
            pddlPotResetLowerBoundConstr(&hpot->pot);
            TRACE_RET(err, st);

        }else if (st != ST_SOLVED){
            LOG(err, "Solution not found for state constraint with rhs %.4f", rhs);
        }
    }

    if (hpot->cfg->hmax0)
        pddlPotResetStartSolution(&hpot->pot);
    pddlPotResetLowerBoundConstr(&hpot->pot);
    return st;
}

void pddlHPotConfigInit(pddl_hpot_config_t *cfg)
{
    pddl_hpot_config_t init = PDDL_HPOT_CONFIG_INIT;
    *cfg = init;
}

static void hpotConfigReplaceInitConstrWithState(pddl_hpot_config_t *c,
                                                 const int *fdr_state)
{
    switch (c->type){
        case PDDL_HPOT_OPT_STATE_TYPE:
            {
                if (c->opt_state.fdr_state == NULL)
                    c->opt_state.fdr_state = fdr_state;
            }
            break;
        case PDDL_HPOT_OPT_ALL_SYNTACTIC_STATES_TYPE:
            {
                if (c->opt_all_syntactic_states.add_state_constr.init_state){
                    c->opt_all_syntactic_states.add_state_constr.init_state = 0;
                    c->opt_all_syntactic_states.add_state_constr.fdr_state = fdr_state;
                }
            }
            break;
        case PDDL_HPOT_OPT_ALL_STATES_MUTEX_TYPE:
            {
                if (c->opt_all_states_mutex.add_state_constr.init_state){
                    c->opt_all_states_mutex.add_state_constr.init_state = 0;
                    c->opt_all_states_mutex.add_state_constr.fdr_state = fdr_state;
                }
            }
            break;
        case PDDL_HPOT_OPT_SAMPLED_STATES_TYPE:
            {
                if (c->opt_sampled_states.add_state_constr.init_state){
                    c->opt_sampled_states.add_state_constr.init_state = 0;
                    c->opt_sampled_states.add_state_constr.fdr_state = fdr_state;
                }
            }
            break;
        case PDDL_HPOT_OPT_ENSEMBLE_SAMPLED_STATES_TYPE:
        case PDDL_HPOT_OPT_ENSEMBLE_DIVERSIFICATION_TYPE:
        case PDDL_HPOT_OPT_ENSEMBLE_ALL_STATES_MUTEX_TYPE:
        case _PDDL_HPOT_TYPE_SIZE:
            break;
    }
}

void pddlHPotConfigReplaceInitConstrWithState(pddl_hpot_config_t *c,
                                              const int *fdr_state)
{
    hpotConfigReplaceInitConstrWithState(c, fdr_state);
    pddl_hpot_config_t *next = c->next;
    while (next != NULL){
        hpotConfigReplaceInitConstrWithState(next, fdr_state);
        next = next->next;
    }
}

static void hpotConfigLogOptState(const pddl_hpot_config_opt_state_t *c,
                                  pddl_err_t *err)
{
    LOG(err, "type: %s", "state");
    if (c->fdr_state == NULL){
        LOG(err, "optimize for the initial state");
    }
}

static void hpotConfigLogAddStateConstr(
                const pddl_hpot_config_add_state_constr_t *c,
                const char *prefix,
                pddl_err_t *err)
{
    LOG(err, "%s.init_state = %s", prefix, F_BOOL(c->init_state));
    if (c->fdr_state != NULL){
        LOG(err, "%s.state_constr = used", prefix);
    }else{
        LOG(err, "%s.state_constr = not-used", prefix);
    }
    LOG(err, "%s.coef = %.2f", prefix, c->coef);
}

static void hpotConfigLogOptAllSyntacticStates(
                const pddl_hpot_config_opt_all_syntactic_states_t *c,
                pddl_err_t *err)
{
    LOG(err, "type: %s", "all-syntactic-states");
    hpotConfigLogAddStateConstr(&c->add_state_constr, "add_state_constr", err);
}

static void hpotConfigLogOptAllStatesMutex(
                const pddl_hpot_config_opt_all_states_mutex_t *c,
                pddl_err_t *err)
{
    LOG(err, "type: %s", "all-states-mutex");
    LOG_CONFIG_INT(c, mutex_size, err);
    hpotConfigLogAddStateConstr(&c->add_state_constr, "add_state_constr", err);
}

static void hpotConfigLogOptSampledStates(
                const pddl_hpot_config_opt_sampled_states_t *c,
                pddl_err_t *err)
{
    LOG(err, "type: %s", "sampled-states");
    LOG_CONFIG_INT(c, num_samples, err);
    LOG_CONFIG_BOOL(c, use_random_walk, err);
    LOG_CONFIG_BOOL(c, use_syntactic_samples, err);
    LOG_CONFIG_BOOL(c, use_mutex_samples, err);
    hpotConfigLogAddStateConstr(&c->add_state_constr, "add_state_constr", err);
}

static void hpotConfigLogOptEnsembleSampledStates(
                const pddl_hpot_config_opt_ensemble_sampled_states_t *c,
                pddl_err_t *err)
{
    LOG(err, "type: %s", "ensemble-sampled-states");
    LOG_CONFIG_INT(c, num_samples, err);
    LOG_CONFIG_BOOL(c, use_random_walk, err);
    LOG_CONFIG_BOOL(c, use_syntactic_samples, err);
    LOG_CONFIG_BOOL(c, use_mutex_samples, err);
}

static void hpotConfigLogOptEnsembleDiversification(
                const pddl_hpot_config_opt_ensemble_diversification_t *c,
                pddl_err_t *err)
{
    LOG(err, "type: %s", "ensemble-diversification");
    LOG_CONFIG_INT(c, num_samples, err);
    LOG_CONFIG_BOOL(c, use_random_walk, err);
    LOG_CONFIG_BOOL(c, use_syntactic_samples, err);
    LOG_CONFIG_BOOL(c, use_mutex_samples, err);
}

static void hpotConfigLogOptEnsembleAllStatesMutex(
                const pddl_hpot_config_opt_ensemble_all_states_mutex_t *c,
                pddl_err_t *err)
{
    LOG(err, "type: %s", "all-states-mutex");
    LOG_CONFIG_INT(c, cond_size, err);
    LOG_CONFIG_INT(c, mutex_size, err);
    LOG_CONFIG_INT(c, num_rand_samples, err);
}

static const char *hpotTypeName(pddl_hpot_type_t type)
{
    switch(type){
        case PDDL_HPOT_OPT_STATE_TYPE:
            return "state";
        case PDDL_HPOT_OPT_ALL_SYNTACTIC_STATES_TYPE:
            return "all-syntactic-states";
        case PDDL_HPOT_OPT_ALL_STATES_MUTEX_TYPE:
            return "all-states-mutex";
        case PDDL_HPOT_OPT_SAMPLED_STATES_TYPE:
            return "sampled-states";
        case PDDL_HPOT_OPT_ENSEMBLE_SAMPLED_STATES_TYPE:
            return "ensemble-sampled-states";
        case PDDL_HPOT_OPT_ENSEMBLE_DIVERSIFICATION_TYPE:
            return "ensemble-diversification";
        case PDDL_HPOT_OPT_ENSEMBLE_ALL_STATES_MUTEX_TYPE:
            return "ensemble-all-states-mutex";
        case _PDDL_HPOT_TYPE_SIZE:
            return "(unknown)";
    }
    return "(unknown)";
}

void pddlHPotConfigLog(const pddl_hpot_config_t *cfg, pddl_err_t *err)
{
    LOG(err, "type = %s", hpotTypeName(cfg->type));
    LOG_CONFIG_BOOL(cfg, disambiguation, err);
    LOG_CONFIG_BOOL(cfg, weak_disambiguation, err);
    LOG_CONFIG_BOOL(cfg, op_pot, err);
    LOG_CONFIG_BOOL(cfg, op_pot_real, err);
    LOG_CONFIG_BOOL(cfg, hmax0, err);
    LOG_CONFIG_DBL(cfg, lp_time_limit, err);

    CTX_NO_TIME(err, "Opt");
    switch(cfg->type){
        case PDDL_HPOT_OPT_STATE_TYPE:
            hpotConfigLogOptState(&cfg->opt_state, err);
            break;
        case PDDL_HPOT_OPT_ALL_SYNTACTIC_STATES_TYPE:
            hpotConfigLogOptAllSyntacticStates(&cfg->opt_all_syntactic_states, err);
            break;
        case PDDL_HPOT_OPT_ALL_STATES_MUTEX_TYPE:
            hpotConfigLogOptAllStatesMutex(&cfg->opt_all_states_mutex, err);
            break;
        case PDDL_HPOT_OPT_SAMPLED_STATES_TYPE:
            hpotConfigLogOptSampledStates(&cfg->opt_sampled_states, err);
            break;
        case PDDL_HPOT_OPT_ENSEMBLE_SAMPLED_STATES_TYPE:
            hpotConfigLogOptEnsembleSampledStates(&cfg->opt_ensemble_sampled_states, err);
            break;
        case PDDL_HPOT_OPT_ENSEMBLE_DIVERSIFICATION_TYPE:
            hpotConfigLogOptEnsembleDiversification(&cfg->opt_ensemble_diversification, err);
            break;
        case PDDL_HPOT_OPT_ENSEMBLE_ALL_STATES_MUTEX_TYPE:
            hpotConfigLogOptEnsembleAllStatesMutex(&cfg->opt_ensemble_all_states_mutex, err);
            break;
        case _PDDL_HPOT_TYPE_SIZE:
            break;
    }
    CTXEND(err);

    const pddl_hpot_config_t *cnext = cfg->next;
    for (int idx = 1; cnext != NULL; ++idx){
        pddl_hpot_config_t c = *cnext;
        c.fdr = cfg->fdr;
        c.mg_strips = cfg->mg_strips;
        c.mutex = cfg->mutex;
        c.next = NULL;
        CTX_NO_TIME(err, "conf-%d", idx);
        pddlHPotConfigLog(&c, err);
        CTXEND(err);
        cnext = cnext->next;
    }
}

int pddlHPotConfigCheck(const pddl_hpot_config_t *cfg, pddl_err_t *err)
{
    if (pddlHPotConfigIsEmpty(cfg))
        ERR_RET(err, -1, "Missing configuration of potential heuristics");

    if (cfg->fdr == NULL){
        ERR_RET(err, -1, "Config Error: .fdr is not set");
    }
    if (cfg->disambiguation && cfg->weak_disambiguation){
        ERR_RET(err, -1, "Config Error: Only one of .disambiguation and"
                 " .weak_disambiguation can be set");
    }
    if (cfg->disambiguation || cfg->weak_disambiguation){
        if (cfg->mg_strips == NULL || cfg->mutex == NULL){
            ERR_RET(err, -1, "Config Error: Disambiguation requires"
                     " .mg_strips and .mutex");
        }
    }

    if (cfg->type == PDDL_HPOT_OPT_SAMPLED_STATES_TYPE){
        if (cfg->opt_sampled_states.use_mutex_samples && cfg->mutex == NULL){
            ERR_RET(err, -1, "Config Error: .op_sampled_states.use_mutex_samples"
                    " requires .mutex to be set");
        }

    }else if (cfg->type == PDDL_HPOT_OPT_ENSEMBLE_SAMPLED_STATES_TYPE){
        if (cfg->opt_ensemble_sampled_states.use_mutex_samples && cfg->mutex == NULL){
            ERR_RET(err, -1, "Config Error: .opt_ensemble_sampled_states.use_mutex_samples"
                    " requires .mutex to be set");
        }
        if (cfg->opt_ensemble_sampled_states.num_samples <= 0)
            ERR_RET(err, -1, "Config Error: .opt_ensemble_sampled_states.num_samples must be > 0.");

    }else if (cfg->type == PDDL_HPOT_OPT_ENSEMBLE_DIVERSIFICATION_TYPE){
        if (cfg->opt_ensemble_diversification.use_mutex_samples && cfg->mutex == NULL){
            ERR_RET(err, -1, "Config Error: .opt_ensemble_diversification.use_mutex_samples"
                    " requires .mutex to be set");
        }
        if (cfg->opt_ensemble_diversification.num_samples <= 0)
            ERR_RET(err, -1, "Config Error: .opt_ensemble_diversification.num_samples must be > 0.");

    }else if (cfg->type == PDDL_HPOT_OPT_ALL_STATES_MUTEX_TYPE){
        if (cfg->mutex == NULL){
            ERR_RET(err, -1, "Config Error: all-states-mutex requires .mutex to be set");
        }
        if (cfg->opt_all_states_mutex.mutex_size < 1
                || cfg->opt_all_states_mutex.mutex_size > 2){
            ERR_RET(err, -1, "Config Error: .opt_all_states_mutex.mutex_size must be 1 or 2.");
        }

    }else if (cfg->type == PDDL_HPOT_OPT_ENSEMBLE_ALL_STATES_MUTEX_TYPE){
        if (cfg->mutex == NULL){
            ERR_RET(err, -1, "Config Error: ensemble-all-states-mutex"
                    " requires .mutex to be set");
        }
        if (cfg->opt_ensemble_all_states_mutex.mutex_size < 1
                || cfg->opt_ensemble_all_states_mutex.mutex_size > 2){
            ERR_RET(err, -1, "Config Error: .opt_ensemble_all_states_mutex.mutex_size must be 1 or 2.");
        }
    }
    return 0;
}

pddl_bool_t pddlHPotConfigNeedMGStrips(const pddl_hpot_config_t *cfg)
{
    if (cfg->disambiguation || cfg->weak_disambiguation)
        return pddl_true;
    return pddl_false;
}

pddl_bool_t pddlHPotConfigNeedMutex(const pddl_hpot_config_t *cfg)
{
    if (cfg->disambiguation || cfg->weak_disambiguation)
        return pddl_true;

    if (cfg->type == PDDL_HPOT_OPT_SAMPLED_STATES_TYPE){
        if (cfg->opt_sampled_states.use_mutex_samples)
            return pddl_true;

    }else if (cfg->type == PDDL_HPOT_OPT_ENSEMBLE_SAMPLED_STATES_TYPE){
        if (cfg->opt_ensemble_sampled_states.use_mutex_samples)
            return pddl_true;

    }else if (cfg->type == PDDL_HPOT_OPT_ENSEMBLE_DIVERSIFICATION_TYPE){
        if (cfg->opt_ensemble_diversification.use_mutex_samples)
            return pddl_true;

    }else if (cfg->type == PDDL_HPOT_OPT_ALL_STATES_MUTEX_TYPE){
        return pddl_true;

    }else if (cfg->type == PDDL_HPOT_OPT_ENSEMBLE_ALL_STATES_MUTEX_TYPE){
        return pddl_true;
    }
    return pddl_false;
}

pddl_bool_t pddlHPotConfigIsEmpty(const pddl_hpot_config_t *cfg)
{
    return cfg->type < 0 || cfg->type >= _PDDL_HPOT_TYPE_SIZE;
}

pddl_bool_t pddlHPotConfigIsEnsemble(const pddl_hpot_config_t *cfg)
{
    switch (cfg->type){
        case PDDL_HPOT_OPT_ENSEMBLE_SAMPLED_STATES_TYPE:
        case PDDL_HPOT_OPT_ENSEMBLE_DIVERSIFICATION_TYPE:
        case PDDL_HPOT_OPT_ENSEMBLE_ALL_STATES_MUTEX_TYPE:
            return pddl_true;
        default:
            return pddl_false;
    }
    return pddl_false;
}

static status_t _hpotOptState(hpot_t *hpot,
                              const int *fdr_state,
                              pddl_err_t *err)
{
    pddlPotSetObjFDRState(&hpot->pot, &hpot->cfg->fdr->var, fdr_state);
    return hpotSolveAndAdd(hpot, err);
}

static status_t hpotOptState(hpot_t *hpot,
                             const pddl_hpot_config_opt_state_t *cfg_opt,
                             pddl_err_t *err)
{
    CTX(err, "state");
    const int *state = cfg_opt->fdr_state;
    if (state == NULL)
        state = hpot->cfg->fdr->init;
    status_t st = _hpotOptState(hpot, state, err);
    CTXEND(err);
    return st;
}

static status_t hpotOptAllSyntacticStates(hpot_t *hpot,
                                          const pddl_hpot_config_opt_all_syntactic_states_t *cfg_opt,
                                          pddl_err_t *err)
{
    CTX(err, "A");
    status_t st = hpotInitAddStateConstr(hpot, &cfg_opt->add_state_constr, err);
    if (st == ST_SOLVED){
        pddlPotSetObjFDRAllSyntacticStates(&hpot->pot, &hpot->cfg->fdr->var);
        st = hpotSolveAndAddWithStateConstr(hpot, err);
    }
    CTXEND(err);
    return st;
}

static double countStatesMutex(const pddl_mgroups_t *mgs,
                               const pddl_mutex_pairs_t *mutex,
                               const pddl_iset_t *fixed)
{
    if (pddlMutexPairsIsMutexSet(mutex, fixed))
        return 0.;

    if (fixed == NULL || pddlISetSize(fixed) == 0){
        double num = pddlISetSize(&mgs->mgroup[0].mgroup);
        for (int i = 1; i < mgs->mgroup_size; ++i)
            num *= pddlISetSize(&mgs->mgroup[i].mgroup);
        return num;
    }

    double num = 1.;
    for (int mgi = 0; mgi < mgs->mgroup_size; ++mgi){
        int mg_size = 0;
        int fact;
        PDDL_ISET_FOR_EACH(&mgs->mgroup[mgi].mgroup, fact){
            if (!pddlMutexPairsIsMutexFactSet(mutex, fact, fixed))
                mg_size += 1;
        }
        num *= (double)mg_size;
    }
    return num;
}

static void setObjAllStatesMutex1(hpot_t *hpot, const pddl_mgroups_t *mgs)
{
    double *coef = ZALLOC_ARR(double, hpot->pot.var_size);
    PDDL_ISET(fixed);

    for (int mgi = 0; mgi < mgs->mgroup_size; ++mgi){
        const pddl_mgroup_t *mg = mgs->mgroup + mgi;
        double sum = 0.;
        int fixed_fact;
        PDDL_ISET_FOR_EACH(&mg->mgroup, fixed_fact){
            pddlISetEmpty(&fixed);
            pddlISetAdd(&fixed, fixed_fact);
            coef[fixed_fact] = countStatesMutex(mgs, hpot->cfg->mutex, &fixed);
            sum += coef[fixed_fact];
        }
        PDDL_ISET_FOR_EACH(&mg->mgroup, fixed_fact){
            coef[fixed_fact] /= sum;
            if (coef[fixed_fact] < 1E-6)
                coef[fixed_fact] = 0.;
        }
    }

    pddlPotSetObj(&hpot->pot, coef);

    pddlISetFree(&fixed);
    if (coef != NULL)
        FREE(coef);
}

static void setObjAllStatesMutex2(hpot_t *hpot, const pddl_mgroups_t *mgs)
{
    double *coef = ZALLOC_ARR(double, hpot->pot.var_size);
    PDDL_ISET(fixed);

    for (int mgi = 0; mgi < mgs->mgroup_size; ++mgi){
        const pddl_mgroup_t *mg = mgs->mgroup + mgi;
        double sum = 0.;
        int fixed_fact;
        PDDL_ISET_FOR_EACH(&mg->mgroup, fixed_fact){
            coef[fixed_fact] = 0.;
            for (int f = 0; f < hpot->cfg->mg_strips->strips.fact.fact_size; ++f){
                if (f == fixed_fact)
                    continue;

                pddlISetEmpty(&fixed);
                pddlISetAdd(&fixed, fixed_fact);
                pddlISetAdd(&fixed, f);
                ASSERT(pddlISetSize(&fixed) == 2);
                coef[fixed_fact] += countStatesMutex(mgs, hpot->cfg->mutex, &fixed);
            }
            sum += coef[fixed_fact];
        }
        PDDL_ISET_FOR_EACH(&mg->mgroup, fixed_fact){
            coef[fixed_fact] /= sum;
            if (coef[fixed_fact] < 1E-6)
                coef[fixed_fact] = 0.;
        }
    }

    pddlPotSetObj(&hpot->pot, coef);

    pddlISetFree(&fixed);
    if (coef != NULL)
        FREE(coef);
}

static status_t hpotOptAllStatesMutex(hpot_t *hpot,
                                      const pddl_hpot_config_opt_all_states_mutex_t *cfg_opt,
                                      pddl_err_t *err)
{
    CTX(err, "M=%d", cfg_opt->mutex_size);
    status_t st = hpotInitAddStateConstr(hpot, &cfg_opt->add_state_constr, err);
    if (st == ST_SOLVED){
        if (cfg_opt->mutex_size == 1){
            setObjAllStatesMutex1(hpot, &hpot->cfg->mg_strips->mg);

        }else if (cfg_opt->mutex_size == 2){
            setObjAllStatesMutex2(hpot, &hpot->cfg->mg_strips->mg);

        }else{
            PANIC("All states mutex optimization not supported for"
                  " mutex_size=%d", cfg_opt->mutex_size);
        }

        st = hpotSolveAndAddWithStateConstr(hpot, err);
    }
    CTXEND(err);
    return st;
}

static status_t hpotOptSampledStates(hpot_t *hpot,
                                     const pddl_hpot_config_opt_sampled_states_t *cfg_opt,
                                     pddl_err_t *err)
{
    CTX(err, "S");
    status_t st = hpotInitAddStateConstr(hpot, &cfg_opt->add_state_constr, err);
    if (st == ST_SOLVED){
        pddl_fdr_state_sampler_t *sampler;
        sampler = hpotGetStateSampler(hpot, cfg_opt->use_random_walk,
                                      cfg_opt->use_syntactic_samples,
                                      cfg_opt->use_mutex_samples, err);
        if (sampler == NULL){
            CTXEND(err);
            TRACE_RET(err, ST_ERR);
        }

        int state[hpot->cfg->fdr->var.var_size];
        int num_states = 0;
        double *coef = ZALLOC_ARR(double, hpot->pot.var_size);
        for (int si = 0; si < cfg_opt->num_samples; ++si){
            pddlFDRStateSamplerNext(sampler, state);
            for (int var = 0; var < hpot->cfg->fdr->var.var_size; ++var)
                coef[hpot->cfg->fdr->var.var[var].val[state[var]].global_id] += 1.;
            ++num_states;
        }

        pddlPotSetObj(&hpot->pot, coef);
        if (coef != NULL)
            FREE(coef);

        st = hpotSolveAndAddWithStateConstr(hpot, err);
        if (st == ST_SOLVED)
            LOG(err, "Solved for average over %d states", num_states);
    }
    CTXEND(err);
    return st;
}

static status_t hpotOptEnsembleSampledStates(hpot_t *hpot,
                                             const pddl_hpot_config_opt_ensemble_sampled_states_t *cfg_opt,
                                             pddl_err_t *err)
{
    CTX(err, "eS");
    // TODO: Add option to always add initial state

    pddl_fdr_state_sampler_t *sampler;
    sampler = hpotGetStateSampler(hpot, cfg_opt->use_random_walk,
                                  cfg_opt->use_syntactic_samples,
                                  cfg_opt->use_mutex_samples, err);
    if (sampler == NULL){
        CTXEND(err);
        TRACE_RET(err, ST_ERR);
    }

    // TODO: remove dead-ends

    int state[hpot->cfg->fdr->var.var_size];
    int num_states = 0;
    for (int si = 0; si < cfg_opt->num_samples; ++si){
        pddlFDRStateSamplerNext(sampler, state);
        status_t st = _hpotOptState(hpot, state, err);
        if (st == ST_ERR)
            TRACE_RET(err, st);
        if (st == ST_SOLVED)
            ++num_states;
        if ((si + 1) % 100 == 0){
            LOG(err, "Solved for %d/%d states",
                      num_states, cfg_opt->num_samples);
        }
    }
    LOG(err, "Solved for %d/%d states", num_states, cfg_opt->num_samples);
    CTXEND(err);
    if (num_states > 0)
        return ST_SOLVED;
    return ST_NOT_SOLVED;
}

struct diverse_pot {
    hpot_t *hpot;
    double *coef;
    pddl_pot_solutions_t func;
    pddl_pot_solution_t avg_func;
    int *state_est;
    pddl_set_iset_t states;
    int active_states;
    pddl_rand_t rnd;
};
typedef struct diverse_pot diverse_pot_t;

static void stripsStateToFDRState(const pddl_iset_t *state,
                                  int *fdr_state,
                                  const pddl_fdr_t *fdr)
{
    int fact_id;
    PDDL_ISET_FOR_EACH(state, fact_id){
        const pddl_fdr_val_t *v = fdr->var.global_id_to_val[fact_id];
        fdr_state[v->var_id] = v->val_id;
    }
}

static void diverseInit(diverse_pot_t *div, hpot_t *hpot, int num_samples)
{
    div->hpot = hpot;
    div->coef = ALLOC_ARR(double, hpot->pot.var_size);
    pddlPotSolutionsInit(&div->func);
    pddlPotSolutionInit(&div->avg_func);
    div->state_est = ZALLOC_ARR(int, num_samples);
    pddlSetISetInit(&div->states);
    div->active_states = 0;
    pddlRandInit(&div->rnd, rand_diverse_seed);
}

static void diverseFree(diverse_pot_t *div)
{
    FREE(div->coef);
    pddlPotSolutionsFree(&div->func);
    pddlPotSolutionFree(&div->avg_func);
    FREE(div->state_est);
    pddlSetISetFree(&div->states);
}

static int diverseGenStates(diverse_pot_t *div,
                            pddl_fdr_state_sampler_t *sampler,
                            int num_samples,
                            pddl_err_t *err)
{
    LOG(err, "generating %d samples and computing potentials...",
              num_samples);

    // Samples states, filter out dead-ends and compute estimate for each
    // state
    int num_states = 0;
    int num_dead_ends = 0;
    int num_duplicates = 0;
    int num_timeouts = 0;
    int fdr_state[div->hpot->cfg->fdr->var.var_size];
    PDDL_ISET(state);
    for (int si = 0; si < num_samples; ++si){
        pddlFDRStateSamplerNext(sampler, fdr_state);

        pddlISetEmpty(&state);
        ZEROIZE_ARR(div->coef, div->hpot->pot.var_size);
        for (int var = 0; var < div->hpot->cfg->fdr->var.var_size; ++var){
            int id = div->hpot->cfg->fdr->var.var[var].val[fdr_state[var]].global_id;
            div->coef[id] = 1.;
            pddlISetAdd(&state, id);
        }

        if (pddlSetISetFind(&div->states, &state) >= 0){
            // Ignore duplicates
            ++num_duplicates;
            continue;
        }

        // Compute heuristic estimate
        pddlPotSetObj(&div->hpot->pot, div->coef);
        pddl_pot_solution_t sol;
        pddlPotSolutionInit(&sol);
        status_t st = hpotSolve(div->hpot, &sol, pddl_false, err);
        if (st == ST_SOLVED){
            ASSERT(sol.found);
            int h = pddlPotSolutionEvalFDRState(&sol, &div->hpot->cfg->fdr->var, fdr_state);
            if (h != PDDL_COST_DEAD_END){
                // Add state to the set of states and store heuristic estimate
                int state_id = pddlSetISetAdd(&div->states, &state);
                ASSERT(state_id == num_states);
                div->state_est[state_id] = h;
                PANIC_IF(div->state_est[state_id] < 0, "Invalid heuristic value");
                pddlPotSolutionsAdd(&div->func, &sol);
                ++num_states;

                if ((si + 1) % 100 == 0){
                    LOG(err, "Diverse: %d/%d (dead-ends: %d)",
                              num_states, num_samples, num_dead_ends);
                }

            }else{
                if (sol.timed_out){
                    ++num_timeouts;
                }else{
                    ++num_dead_ends;
                }
            }
        }else if (st == ST_ERR){
            TRACE_RET(err, -1);
        }
        pddlPotSolutionFree(&sol);
    }
    LOG(err, "Detected dead-ends: %d", num_dead_ends);
    LOG(err, "Detected duplicates: %d", num_duplicates);
    LOG(err, "Timeouts: %d", num_timeouts);
    ASSERT(num_states == pddlSetISetSize(&div->states));
    div->active_states = pddlSetISetSize(&div->states);
    pddlISetFree(&state);
    return 0;
}



static status_t diverseAvg(diverse_pot_t *div, pddl_err_t *err)
{
    ZEROIZE_ARR(div->coef, div->hpot->pot.var_size);
    const pddl_iset_t *state;
    PDDL_SET_ISET_FOR_EACH_ID_SET(&div->states, i, state){
        if (div->state_est[i] < 0)
            continue;
        int fact_id;
        PDDL_ISET_FOR_EACH(state, fact_id)
            div->coef[fact_id] += 1.;
    }
    pddlPotSetObj(&div->hpot->pot, div->coef);

    return hpotSolve(div->hpot, &div->avg_func, pddl_false, err);
}

static const pddl_pot_solution_t *diverseSelectFunc(diverse_pot_t *div,
                                                    pddl_err_t *err)
{
    status_t st = diverseAvg(div, err);
    if (st != ST_SOLVED){
        if (st == ST_ERR)
            TRACE_RET(err, NULL);
        return NULL;
    }

    int *fdr_state = ALLOC_ARR(int, div->hpot->cfg->fdr->var.var_size);
    const pddl_iset_t *state;
    PDDL_SET_ISET_FOR_EACH_ID_SET(&div->states, si, state){
        if (div->state_est[si] < 0)
            continue;
        stripsStateToFDRState(state, fdr_state, div->hpot->cfg->fdr);

        int hest;
        hest = pddlPotSolutionEvalFDRState(&div->avg_func,
                                           &div->hpot->cfg->fdr->var, fdr_state);
        if (hest == div->state_est[si]){
            FREE(fdr_state);
            return &div->avg_func;
        }
    }

    int sid = pddlRand(&div->rnd, 0, div->active_states);
    PDDL_SET_ISET_FOR_EACH_ID(&div->states, si){
        if (div->state_est[si] < 0)
            continue;
        if (sid-- == 0){
            FREE(fdr_state);
            return div->func.sol + si;
        }
    }
    PANIC("The number of active states is invalid!");
    return NULL;
}

static void diverseFilterOutStates(diverse_pot_t *div,
                                   const pddl_fdr_t *fdr,
                                   const pddl_pot_solution_t *func,
                                   pddl_err_t *err)
{
    int *fdr_state = ALLOC_ARR(int, fdr->var.var_size);
    const pddl_iset_t *state;
    PDDL_SET_ISET_FOR_EACH_ID_SET(&div->states, si, state){
        if (div->state_est[si] < 0)
            continue;
        stripsStateToFDRState(state, fdr_state, fdr);
        int hest = pddlPotSolutionEvalFDRState(func, &fdr->var, fdr_state);
        if (hest >= div->state_est[si]){
            div->state_est[si] = -1;
            --div->active_states;
        }
    }
    FREE(fdr_state);
}

static status_t hpotOptEnsembleDiversification(
        hpot_t *hpot,
        const pddl_hpot_config_opt_ensemble_diversification_t *cfg_opt,
        pddl_err_t *err)
{
    CTX(err, "D");
    LOG(err, "Diverse potentials with %d samples", cfg_opt->num_samples);

    pddl_fdr_state_sampler_t *sampler;
    sampler = hpotGetStateSampler(hpot, cfg_opt->use_random_walk,
                                  cfg_opt->use_syntactic_samples,
                                  cfg_opt->use_mutex_samples, err);
    if (sampler == NULL){
        CTXEND(err);
        TRACE_RET(err, ST_ERR);
    }

    diverse_pot_t div;
    diverseInit(&div, hpot, cfg_opt->num_samples);
    if (diverseGenStates(&div, sampler, cfg_opt->num_samples, err) != 0){
        CTXEND(err);
        TRACE_RET(err, ST_ERR);
    }

    while (div.active_states > 0){
        const pddl_pot_solution_t *func = diverseSelectFunc(&div, err);
        if (func == NULL){
            CTXEND(err);
            if (pddlErrIsSet(err))
                TRACE_RET(err, ST_ERR);
            return ST_NOT_SOLVED;
        }
        pddlPotSolutionsAdd(hpot->sols, func);
        diverseFilterOutStates(&div, hpot->cfg->fdr, func, err);
    }
    diverseFree(&div);
    LOG(err, "Computed diverse potentials with %d functions",
              hpot->sols->sol_size);
    CTXEND(err);
    if (hpot->sols->sol_size > 0)
        return ST_SOLVED;
    return ST_NOT_SOLVED;
}

static void setObjAllStatesMutexConditioned(hpot_t *hpot,
                                            const pddl_iset_t *cond,
                                            int mutex_size)
{
    pddl_mgroups_t mgs;
    pddlMGroupsInitEmpty(&mgs);
    PDDL_ISET(mg);
    for (int mgi = 0; mgi < hpot->cfg->mg_strips->mg.mgroup_size; ++mgi){
        int fact_id;
        pddlISetEmpty(&mg);
        PDDL_ISET_FOR_EACH(&hpot->cfg->mg_strips->mg.mgroup[mgi].mgroup, fact_id){
            if (!pddlMutexPairsIsMutexFactSet(hpot->cfg->mutex, fact_id, cond))
                pddlISetAdd(&mg, fact_id);
        }

        if (pddlISetSize(&mg) == 0){
            pddlISetFree(&mg);
            pddlMGroupsFree(&mgs);
            return;
        }

        pddlMGroupsAdd(&mgs, &mg);
    }
    pddlISetFree(&mg);

    if (mutex_size == 1){
        setObjAllStatesMutex1(hpot, &mgs);
    }else if (mutex_size == 2){
        setObjAllStatesMutex2(hpot, &mgs);
    }else{
        PANIC("mutex-size >= 3 is not supported!");
    }
    pddlMGroupsFree(&mgs);
}

static status_t allStatesMutexCond(hpot_t *hpot,
                                   int mutex_size,
                                   const pddl_iset_t *facts,
                                   pddl_err_t *err)
{
    PDDL_ISET(cond);
    int fact_id;
    int count = 0;
    PDDL_ISET_FOR_EACH(facts, fact_id){
        pddlISetEmpty(&cond);
        pddlISetAdd(&cond, fact_id);
        setObjAllStatesMutexConditioned(hpot, &cond, mutex_size);
        status_t st = hpotSolveAndAdd(hpot, err);
        if (st == ST_SOLVED){
            ++count;

        }else if (st == ST_ERR){
            pddlISetFree(&cond);
            TRACE_RET(err, st);
        }

        if (count % 10 == 0){
            LOG(err, "Computed conditioned func %d/%d and generated %d"
                      " potential functions",
                      count, pddlISetSize(facts), hpot->sols->sol_size);
        }
    }
    LOG(err, "Computed conditioned func %d/%d and generated %d"
              " potential functions",
              count, pddlISetSize(facts), hpot->sols->sol_size);
    pddlISetFree(&cond);

    if (hpot->sols->sol_size > 0)
        return ST_SOLVED;
    return ST_NOT_SOLVED;
}

static status_t allStatesMutexCond2(hpot_t *hpot,
                                    int mutex_size,
                                    int num_samples,
                                    pddl_err_t *err)
{
    pddl_rand_t rnd;
    pddlRandInit(&rnd, rand_seed);
    PDDL_ISET(cond);
    int count = 0;
    int fact_size = hpot->cfg->mg_strips->strips.fact.fact_size;
    for (int i = 0; i < num_samples; ++i){
        int f1 = pddlRand(&rnd, 0, fact_size);
        int f2 = pddlRand(&rnd, 0, fact_size);
        if (pddlMutexPairsIsMutex(hpot->cfg->mutex, f1, f2))
            continue;
        pddlISetEmpty(&cond);
        pddlISetAdd(&cond, f1);
        pddlISetAdd(&cond, f2);

        setObjAllStatesMutexConditioned(hpot, &cond, mutex_size);
        status_t st = hpotSolveAndAdd(hpot, err);
        if (st == ST_SOLVED){
            ++count;

        }else if (st == ST_ERR){
            pddlISetFree(&cond);
            TRACE_RET(err, st);
        }

        if (count % 10 == 0){
            LOG(err, "Computed conditioned func^2 %d and generated %d"
                      " potential functions",
                      count, hpot->sols->sol_size);
        }
    }
    LOG(err, "Computed conditioned func^2 %d and generated %d"
              " potential functions",
              count, hpot->sols->sol_size);
    pddlISetFree(&cond);

    if (hpot->sols->sol_size > 0)
        return ST_SOLVED;
    return ST_NOT_SOLVED;
}

static status_t hpotOptEnsembleAllStatesMutex(
        hpot_t *hpot,
        const pddl_hpot_config_opt_ensemble_all_states_mutex_t *cfg_opt,
        pddl_err_t *err)
{
    CTX(err, "eM");
    status_t st = ST_SOLVED;
    if (cfg_opt->num_rand_samples == 0){
        PDDL_ISET(facts);
        for (int f = 0; f < hpot->cfg->mg_strips->strips.fact.fact_size; ++f)
            pddlISetAdd(&facts, f);
        st = allStatesMutexCond(hpot, cfg_opt->mutex_size, &facts, err);
        pddlISetFree(&facts);

    }else if (cfg_opt->cond_size == 1){
        pddl_rand_t rnd;
        pddlRandInit(&rnd, rand_seed);
        PDDL_ISET(facts);
        int fact_size = hpot->cfg->mg_strips->strips.fact.fact_size;
        for (int i = 0; i < cfg_opt->num_rand_samples; ++i)
            pddlISetAdd(&facts, pddlRand(&rnd, 0, fact_size));

        st = allStatesMutexCond(hpot, cfg_opt->mutex_size, &facts, err);
        pddlISetFree(&facts);

    }else if (cfg_opt->cond_size == 2){
        st = allStatesMutexCond2(hpot, cfg_opt->mutex_size,
                                 cfg_opt->num_rand_samples, err);
    }
    CTXEND(err);
    return st;
}

static status_t findSolutions(hpot_t *hpot, pddl_err_t *err)
{
    status_t st = ST_SOLVED;
    switch (hpot->cfg->type){
        case PDDL_HPOT_OPT_STATE_TYPE:
            st = hpotOptState(hpot, &hpot->cfg->opt_state, err);
            break;

        case PDDL_HPOT_OPT_ALL_SYNTACTIC_STATES_TYPE:
            st = hpotOptAllSyntacticStates(hpot, &hpot->cfg->opt_all_syntactic_states, err);
            break;

        case PDDL_HPOT_OPT_ALL_STATES_MUTEX_TYPE:
            st = hpotOptAllStatesMutex(hpot, &hpot->cfg->opt_all_states_mutex, err);
            break;

        case PDDL_HPOT_OPT_SAMPLED_STATES_TYPE:
            st = hpotOptSampledStates(hpot, &hpot->cfg->opt_sampled_states, err);
            break;

        case PDDL_HPOT_OPT_ENSEMBLE_SAMPLED_STATES_TYPE:
            st = hpotOptEnsembleSampledStates(hpot, &hpot->cfg->opt_ensemble_sampled_states, err);
            break;

        case PDDL_HPOT_OPT_ENSEMBLE_DIVERSIFICATION_TYPE:
            st = hpotOptEnsembleDiversification(hpot, &hpot->cfg->opt_ensemble_diversification, err);
            break;

        case PDDL_HPOT_OPT_ENSEMBLE_ALL_STATES_MUTEX_TYPE:
            st = hpotOptEnsembleAllStatesMutex(hpot, &hpot->cfg->opt_ensemble_all_states_mutex, err);
            break;
        case _PDDL_HPOT_TYPE_SIZE:
            break;
    }
    return st;
}
static int hpot(pddl_pot_solutions_t *sols,
                const pddl_hpot_config_t *cfg,
                pddl_err_t *err)
{
    if (pddlHPotConfigCheck(cfg, err) != 0)
        TRACE_RET(err, -1);

    CTX(err, "HPot");
    CTX_NO_TIME(err, "Cfg");
    pddlHPotConfigLog(cfg, err);
    CTXEND(err);

    hpot_t hpot;

    int init_ret = 0;
    if ((init_ret = hpotInit(&hpot, cfg, sols, err)) != 0){
        CTXEND(err);
        if (init_ret > 0)
            return 0;
        if (init_ret < 0)
            TRACE_RET(err, -1);
    }

    status_t st = findSolutions(&hpot, err);

    hpotFree(&hpot);

    int ret = 0;
    switch (st){
        case ST_SOLVED:
            ret = 0;
            break;
        case ST_NOT_SOLVED:
            LOG(err, "Potential heuristics not found!");
            ret = 0;
            break;
        case ST_TIMEOUT:
            LOG(err, "Potential heuristics not found!");
            LOG(err, "Inference of potential heuristics timed out.");
            ret = 0;
            break;
        case ST_ERR:
            TRACE(err);
            ret = -1;
            break;
    }

    CTXEND(err);
    return ret;
}

int pddlHPot(pddl_pot_solutions_t *sols,
             const pddl_hpot_config_t *cfg,
             pddl_err_t *err)
{
    int ret = hpot(sols, cfg, err);
    if (ret < 0)
        TRACE_RET(err, ret);

    const pddl_hpot_config_t *cnext = cfg->next;
    for (int idx = 1; cnext != NULL; ++idx){
        pddl_hpot_config_t c = *cnext;
        c.fdr = cfg->fdr;
        c.mg_strips = cfg->mg_strips;
        c.mutex = cfg->mutex;
        c.next = NULL;

        CTX(err, "HPot-%d", idx);
        int ret = hpot(sols, &c, err);
        CTXEND(err);
        if (ret < 0)
            TRACE_RET(err, ret);

        cnext = cnext->next;
    }

    LOG(err, "Number of potential functions: %d", sols->sol_size);
    return ret;
}

struct pddl_heur_pot {
    pddl_heur_t heur;
    pddl_pot_solutions_t sols;
    pddl_fdr_vars_t vars;
};
typedef struct pddl_heur_pot pddl_heur_pot_t;

static void heurDel(pddl_heur_t *_h)
{
    pddl_heur_pot_t *h = pddl_container_of(_h, pddl_heur_pot_t, heur);
    _pddlHeurFree(&h->heur);
    pddlPotSolutionsFree(&h->sols);
    pddlFDRVarsFree(&h->vars);
    FREE(h);
}

static int heurEstimate(pddl_heur_t *_h,
                        const pddl_fdr_state_space_node_t *node,
                        const pddl_fdr_state_space_t *state_space)
{
    pddl_heur_pot_t *h = pddl_container_of(_h, pddl_heur_pot_t, heur);
    int est = pddlPotSolutionsEvalMaxFDRState(&h->sols, &h->vars, node->state);
    return est;
}

pddl_heur_t *pddlHeurPot(const pddl_hpot_config_t *cfg, pddl_err_t *err)
{
    if (cfg->fdr->has_cond_eff)
        ERR_RET(err, NULL, "Potential heuristic does not support conditional effects.");

    pddl_heur_pot_t *h = ALLOC(pddl_heur_pot_t);
    pddlPotSolutionsInit(&h->sols);
    int ret = pddlHPot(&h->sols, cfg, err);
    if (ret != 0){
        pddlPotSolutionsFree(&h->sols);
        FREE(h);
        TRACE_RET(err, NULL);

    }else if (h->sols.sol_size == 0){
        pddlPotSolutionsFree(&h->sols);
        FREE(h);
        ERR_RET(err, NULL, "Could not find a potential function.");
    }
    pddlFDRVarsInitCopy(&h->vars, &cfg->fdr->var);
    _pddlHeurInit(&h->heur, heurDel, heurEstimate);
    return &h->heur;
}
