/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "toml.h"
#include "_heur.h"
#include "pddl/pot_conj_exact.h"
#include "pddl/critical_path.h"
#include "pddl/time_limit.h"
#include "pddl/rand.h"
#include "pddl/heur.h"

// Time limit for LP computing potential functions.
// This value is used for all pddlPotConjExactMaxInitHValue*() functions.
#define MAX_INIT_LP_TIME_LIMIT 30.

#define EPS 1E-6

static int hpotConfigIsSupported(const pddl_hpot_config_t *c,
                                 pddl_err_t *err)
{
    switch (c->type){
        case PDDL_HPOT_OPT_STATE_TYPE:
            {
                if (c->opt_state.fdr_state != NULL){
                    ERR_RET(err, 0, "Optimization for an arbitrary state"
                            " is not supported yet.");
                }
            }
            break;
        case PDDL_HPOT_OPT_ALL_SYNTACTIC_STATES_TYPE:
            {
                if (c->opt_all_syntactic_states.add_state_constr.fdr_state != NULL){
                    ERR_RET(err, 0, "Additional constraint for an"
                            " arbitrary state is not supported yet.");
                }
            }
            break;
        case PDDL_HPOT_OPT_ALL_STATES_MUTEX_TYPE:
            {
                if (c->opt_all_states_mutex.add_state_constr.fdr_state != NULL){
                    ERR_RET(err, 0, "Additional constraint for an"
                            " arbitrary state is not supported yet.");
                }
            }
            break;
        case PDDL_HPOT_OPT_SAMPLED_STATES_TYPE:
            {
                if (c->opt_sampled_states.add_state_constr.fdr_state != NULL){
                    ERR_RET(err, 0, "Additional constraint for an"
                            " arbitrary state is not supported yet.");
                }
            }
            break;
        case PDDL_HPOT_OPT_ENSEMBLE_SAMPLED_STATES_TYPE:
        case PDDL_HPOT_OPT_ENSEMBLE_DIVERSIFICATION_TYPE:
        case PDDL_HPOT_OPT_ENSEMBLE_ALL_STATES_MUTEX_TYPE:
        case _PDDL_HPOT_TYPE_SIZE:
            break;
    }

    return 1;
}

static void h2(pddl_fdr_t *fdr,
               pddl_mutex_pairs_t *mutex,
               pddl_err_t *err)
{
    pddl_mg_strips_t mg_strips;
    pddlMGStripsInitFDR(&mg_strips, fdr);

    pddlMutexPairsAddMGroups(mutex, &mg_strips.mg);

    PDDL_ISET(rm_facts);
    PDDL_ISET(rm_ops);
    pddlH2(&mg_strips.strips, mutex, &rm_facts, &rm_ops, -1., err);

    // Prune redundant operators if found any
    if (pddlISetSize(&rm_ops) > 0)
        pddlFDRReduce(fdr, NULL, NULL, &rm_ops);

    pddlISetFree(&rm_facts);
    pddlISetFree(&rm_ops);
    pddlMGStripsFree(&mg_strips);
}

int pddlPotConjExactInit(pddl_pot_conj_exact_t *pot,
                         const pddl_set_iset_t *conjs,
                         const pddl_hpot_config_t *cfg,
                         pddl_err_t *err)
{
    if (cfg->fdr == NULL)
        ERR_RET(err, -1, "FDR representations is required.");
    if (cfg->mutex == NULL)
        ERR_RET(err, -1, "Mutexes are required.");
    if (pddlSetISetSize(conjs) == 0)
        ERR_RET(err, -1, "At least one conjunction is required.");
    if (!hpotConfigIsSupported(cfg, err))
        TRACE_RET(err, -1);

    CTX(err, "Pot-Conj-Exact");
    ZEROIZE(pot);
    pot->var_size = cfg->fdr->var.var_size;
    pddlPotSolutionsInit(&pot->pot);

    pddl_mutex_pairs_t mutex;
    pddlMutexPairsInitCopy(&mutex, cfg->mutex);
    pddlMutexPairsAddFDRVars(&mutex, &cfg->fdr->var);

    CTX_NO_TIME(err, "Cfg");
    LOG(err, "Number of conjunctions: %d", pddlSetISetSize(conjs));
    for (int i = 0; i < pddlSetISetSize(conjs); ++i){
        const pddl_iset_t *c = pddlSetISetGet(conjs, i);
        char str[1024];
        int written = 0;
        int fact;
        PDDL_ISET_FOR_EACH(c, fact){
            if (written < 1024){
                const char *name = cfg->fdr->var.global_id_to_val[fact]->name;
                written += snprintf(str + written, 1024 - written, " %d:(%s)",
                                    fact, name);
            }
        }
        LOG(err, "Conj[%d]:%s%s", i, str,
            (pddlMutexPairsIsMutexSet(&mutex, pddlSetISetGet(conjs, i))
                ? " :: is-mutex, skipping" : ""));
    }
    pddlHPotConfigLog(cfg, err);
    CTXEND(err);

    // Construct P^C_exact FDR task
    pddl_fdr_conj_exact_config_t pc_cfg;
    pddlFDRConjExactConfigInit(&pc_cfg);
    for (int i = 0; i < pddlSetISetSize(conjs); ++i){
        if (!pddlMutexPairsIsMutexSet(&mutex, pddlSetISetGet(conjs, i)))
            pddlFDRConjExactConfigAddConjAndSubsets(&pc_cfg, pddlSetISetGet(conjs, i));
    }
    pc_cfg.mutex = &mutex;

    pddl_fdr_conj_exact_t pc;
    pddlFDRConjExactInit(&pc, cfg->fdr, &pc_cfg, err);

    // Fix mutexes
    pddl_mutex_pairs_t fdr_mutex;
    pddlFDRConjExactMutexPairsInitCopy(&fdr_mutex, &mutex, &pc);

    // Create a copy of the P^C_exact FDR task
    pddl_fdr_t fdr;
    pddlFDRInitCopy(&fdr, &pc.fdr);

    // Infer mutexes in the P^C FDR task and prune FDR
    h2(&fdr, &fdr_mutex, err);

    // Transform cfg_in into the configuration for the current fdr
    // representation.
    // At this point, we don't support arbitrary states in
    // pddl_hpot_config_opt_state_t.fdr_state and in *.add_fdr_state_constr.
    // So, we just need to change the global part of the configuration
    // pertaining to the task and mutexes.
    pddl_mg_strips_t mg_strips;
    pddlMGStripsInitFDR(&mg_strips, &fdr);

    pddl_hpot_config_t pot_cfg = *cfg;
    pot_cfg.fdr = &fdr;
    pot_cfg.mg_strips = &mg_strips;
    pot_cfg.mutex = &fdr_mutex;

    // Compute potential functions
    if (pddlHPot(&pot->pot, &pot_cfg, err) != 0){
        pddlMutexPairsFree(&mutex);
        pddlMGStripsFree(&mg_strips);
        pddlMutexPairsFree(&fdr_mutex);
        pddlFDRFree(&fdr);
        pddlFDRConjExactFree(&pc);
        pddlFDRConjExactConfigFree(&pc_cfg);
        TRACE_RET(err, -1);
    }

    if (pot->pot.sol_size > 0){
        int hvalue = pddlPotSolutionEvalFDRState(pot->pot.sol + 0, &fdr.var, fdr.init);
        PDDL_LOG(err, "Heuristic value: %d", hvalue);
    }

#ifdef PDDL_DEBUG
    for (int vi = 0; vi < cfg->fdr->var.var_size; ++vi){
        ASSERT(vi < fdr.var.var_size);
        ASSERT(cfg->fdr->var.var[vi].val_size == fdr.var.var[vi].val_size);
        for (int vali = 0; vali < cfg->fdr->var.var[vi].val_size; ++vali){
            ASSERT(strcmp(cfg->fdr->var.var[vi].val[vali].name,
                          fdr.var.var[vi].val[vali].name) == 0);
        }
    }
#endif /* PDDL_DEBUG */


    // Create a mapping from input FDR to P^C_exact FDR
    pddlFDRVarsInitCopy(&pot->pc_vars, &fdr.var);
    pot->pc_conj_size = pc.conj_size;
    pot->pc_conj = ZALLOC_ARR(pddl_pot_conj_exact_pc_conj_t, pot->pc_conj_size);
    for (int conji = 0; conji < pc.conj_size; ++conji){
        pddlFDRPartStateInitCopy(&pot->pc_conj[conji].fdr,
                                 &pc.conj[conji].part_state);
        pot->pc_conj[conji].pc_var = pc.conj[conji].var_id;
    }

    pddlMutexPairsFree(&mutex);
    pddlMGStripsFree(&mg_strips);
    pddlMutexPairsFree(&fdr_mutex);
    pddlFDRFree(&fdr);
    pddlFDRConjExactFree(&pc);
    pddlFDRConjExactConfigFree(&pc_cfg);
    CTXEND(err);

    if (pot->pot.sol_size == 0)
        ERR_RET(err, -1, "No potential function found.");
    return 0;
}

void pddlPotConjExactFree(pddl_pot_conj_exact_t *pot)
{
    pddlPotSolutionsFree(&pot->pot);
    pddlFDRVarsFree(&pot->pc_vars);
    for (int conji = 0; conji < pot->pc_conj_size; ++conji)
        pddlFDRPartStateFree(&pot->pc_conj[conji].fdr);
}

int pddlPotConjExactEvalMaxFDRState(const pddl_pot_conj_exact_t *pot,
                               const pddl_fdr_vars_t *vars,
                               const int *fdr_state)
{
    ASSERT(pot->pc_vars.var_size > vars->var_size);
    int pc_state[pot->pc_vars.var_size];
    memcpy(pc_state, fdr_state, sizeof(int) * vars->var_size);

    for (int conji = 0; conji < pot->pc_conj_size; ++conji){
        const pddl_pot_conj_exact_pc_conj_t *c = pot->pc_conj + conji;
        if (pddlFDRPartStateIsConsistentWithState(&c->fdr, fdr_state)){
            pc_state[c->pc_var] = 1;
        }else{
            pc_state[c->pc_var] = 0;
        }
    }

#ifdef PDDL_DEBUG
    for (int vari = 0; vari < pot->pc_vars.var_size; ++vari){
        ASSERT(pc_state[vari] >= 0
                    && pc_state[vari] < pot->pc_vars.var[vari].val_size);
    }
#endif /* PDDL_DEBUG */

    return pddlPotSolutionsEvalMaxFDRState(&pot->pot, &pot->pc_vars, pc_state);
}


void pddlPotConjExactFindConfigLog(const pddl_pot_conj_exact_find_config_t *cfg,
                              pddl_err_t *err)
{
    LOG_CONFIG_DBL(cfg, time_limit, err);
    LOG_CONFIG_INT(cfg, max_epochs, err);
    LOG_CONFIG_INT(cfg, max_conj_dim, err);
    LOG_CONFIG_INT(cfg, max_num_conjs, err);
    LOG_CONFIG_DBL(cfg, log_freq, err);
    LOG_CONFIG_DBL(cfg, lp_time_limit, err);
    LOG_CONFIG_STR(cfg, write_progress_prefix, err);
}

#define SET_MAX_SIZE 10

enum conj_iterator_type {
    IT_PAIRS,
    IT_TRIPLES,
    IT_ALL,
};

struct conj_iterator {
    enum conj_iterator_type type;
    const pddl_fdr_t *fdr;
    const pddl_mutex_pairs_t *mutex;
    pddl_iset_t conj;
    int set[SET_MAX_SIZE];
    int set_size;
    pddl_bool_t set_end;
    pddl_rand_t rnd;
    int rnd_max_size;
    pddl_iset_t *not_mutex_with;
};
typedef struct conj_iterator conj_iterator_t;

static void _conjIteratorSetInit(conj_iterator_t *it, int size)
{
    PANIC_IF(size >= SET_MAX_SIZE, "The maximum set size is %d", SET_MAX_SIZE);
    it->set_size = size;
    for (int i = 0; i < SET_MAX_SIZE; ++i)
        it->set[i] = i;
    it->set_end = pddl_false;
}

static void _conjIteratorSetNext(conj_iterator_t *it)
{
    for (int idx = it->set_size - 1; idx >= 0; --idx){
        int max_val = it->fdr->var.global_id_size - (it->set_size - idx - 1);
        it->set[idx]++;
        if (it->set[idx] < max_val){
            for (int i = idx + 1; i < it->set_size; ++i)
                it->set[i] = it->set[i - 1] + 1;
            return;
        }
    }

    it->set_end = pddl_true;
}

static void conjIteratorInit(conj_iterator_t *it,
                             enum conj_iterator_type type,
                             const pddl_fdr_t *fdr,
                             const pddl_mutex_pairs_t *mutex)
{
    ZEROIZE(it);
    it->type = type;
    it->fdr = fdr;
    it->mutex = mutex;
    pddlISetInit(&it->conj);

    switch (type){
        case IT_PAIRS:
        case IT_ALL:
            _conjIteratorSetInit(it, 2);
            break;
        case IT_TRIPLES:
            _conjIteratorSetInit(it, 3);
            break;
    }
}

static void conjIteratorInitCopy(conj_iterator_t *it,
                                 const conj_iterator_t *src)
{
    *it = *src;
    pddlISetInit(&it->conj);

    if (src->not_mutex_with != NULL){
        it->not_mutex_with = ZALLOC_ARR(pddl_iset_t, it->fdr->var.global_id_size);
        for (int fi = 0; fi < it->fdr->var.global_id_size; ++fi){
            pddlISetUnion(it->not_mutex_with + fi, src->not_mutex_with + fi);
        }
    }
}

static void conjIteratorFree(conj_iterator_t *it)
{
    pddlISetFree(&it->conj);
    if (it->not_mutex_with != NULL){
        for (int fi = 0; fi < it->fdr->var.global_id_size; ++fi)
            pddlISetFree(it->not_mutex_with + fi);
        FREE(it->not_mutex_with);
    }
}

static pddl_bool_t hasNoneOfThose(const conj_iterator_t *it,
                                  const pddl_iset_t *conj)
{
    int fact;
    PDDL_ISET_FOR_EACH(conj, fact){
        PANIC_IF(it->fdr->var.global_id_to_val[fact]->name == NULL,
                 "The input FDR task has a fact without name."
                 " This is not supported as the output conjunctions are sets"
                 " of fact names.");
        if (strcmp(it->fdr->var.global_id_to_val[fact]->name, "none-of-those") == 0)
            return pddl_true;
    }
    return pddl_false;
}

static const pddl_iset_t *conjIteratorNext(conj_iterator_t *it)
{
    while (!it->set_end){
        pddlISetEmpty(&it->conj);
        for (int i = 0; i < it->set_size; ++i)
            pddlISetAdd(&it->conj, it->set[i]);

        if (!hasNoneOfThose(it, &it->conj)
                && !pddlMutexPairsIsMutexSet(it->mutex, &it->conj)){
            break;
        }

        _conjIteratorSetNext(it);
    }

    if (it->set_end){
        if (it->type == IT_ALL && it->set_size + 1 < SET_MAX_SIZE){
            _conjIteratorSetInit(it, it->set_size + 1);
            return conjIteratorNext(it);
        }
        return NULL;
    }

    _conjIteratorSetNext(it);
    return &it->conj;
}


static int pot(const pddl_fdr_t *fdr_in,
               const pddl_mutex_pairs_t *mutex,
               float lp_time_limit,
               const pddl_hpot_config_t *pot_cfg_in,
               double *objval,
               pddl_err_t *err)
{
    pddl_fdr_t fdr;
    pddlFDRInitCopy(&fdr, fdr_in);

    pddl_mutex_pairs_t fdr_mutex;
    pddlMutexPairsInitCopy(&fdr_mutex, mutex);

    pddl_mg_strips_t mg_strips;
    pddlMGStripsInitFDR(&mg_strips, &fdr);

    pddlMutexPairsAddMGroups(&fdr_mutex, &mg_strips.mg);
    PDDL_ISET(rm_ops);
    pddlH2(&mg_strips.strips, &fdr_mutex, NULL, &rm_ops, 0., err);
    //pddlH2FwBw(&mg_strips.strips, &mg_strips.mg, &fdr_mutex, NULL, NULL, 0., err);
    if (pddlISetSize(&rm_ops) > 0){
        pddlFDRReduce(&fdr, NULL, NULL, &rm_ops);
        pddlMGStripsReduce(&mg_strips, NULL, &rm_ops);
        LOG(err, "Removed %d redundant operators", pddlISetSize(&rm_ops));
    }
    pddlISetFree(&rm_ops);

    pddl_hpot_config_t pot_cfg = *pot_cfg_in;
    pot_cfg.fdr = &fdr;
    pot_cfg.mg_strips = &mg_strips;
    pot_cfg.mutex = &fdr_mutex;
    if (lp_time_limit > 0.)
        pot_cfg.lp_time_limit = lp_time_limit;

    pddl_pot_solutions_t sol;
    pddlPotSolutionsInit(&sol);
    if (pddlHPot(&sol, &pot_cfg, err) != 0)
        TRACE_RET(err, -1);


    int hvalue = -1;
    if (sol.sol_size > 0){
        hvalue = pddlPotSolutionEvalFDRState(sol.sol + 0, &fdr.var, fdr.init);
        PDDL_LOG(err, "Heuristic value: %d", hvalue);
        if (objval != NULL){
            PDDL_LOG(err, "Objective value: %.4f", sol.sol[0].objval);
            *objval = sol.sol[0].objval;
        }

    }else if (sol.sol_size == 0){
        PDDL_LOG(err, "Could not find a potential function.");
        hvalue = 0;

    }else if (sol.unsolvable){
        PDDL_LOG(err, "Task is unsolvable.");
        hvalue = 0;
    }
    pddlPotSolutionsFree(&sol);

    pddlMGStripsFree(&mg_strips);
    pddlMutexPairsFree(&fdr_mutex);
    pddlFDRFree(&fdr);
    return hvalue;
}

static int potConj(const pddl_fdr_t *fdr,
                   const pddl_mutex_pairs_t *mutex,
                   const pddl_set_iset_t *conjs,
                   const pddl_iset_t *conj,
                   float lp_time_limit,
                   const pddl_hpot_config_t *pot_cfg,
                   double *objval,
                   pddl_err_t *err)
{
    if (conj == NULL && (conjs == NULL || pddlSetISetSize(conjs) == 0)){
        pddlErrLogPause(err);
        int ret = pot(fdr, mutex, lp_time_limit, pot_cfg, objval, err);
        pddlErrLogContinue(err);
        return ret;
    }

    pddl_fdr_conj_exact_config_t pc_cfg;
    pddlFDRConjExactConfigInit(&pc_cfg);
    // Set up the set of conjunctions C
    if (conjs != NULL){
        for (int i = 0; i < pddlSetISetSize(conjs); ++i)
            pddlFDRConjExactConfigAddConjAndSubsets(&pc_cfg, pddlSetISetGet(conjs, i));
    }
    if (conj != NULL)
        pddlFDRConjExactConfigAddConjAndSubsets(&pc_cfg, conj);
    pc_cfg.mutex = mutex;

    /*
    int fact;
    PDDL_ISET_FOR_EACH(conj, fact)
        printf(" (%s)%s", strips->fact.fact[fact]->name,
               (pddlISetIn(fact, &strips->goal) ? ":G" : ""));
    printf(" :: %d\n", pddlSetISetSize(&pc_cfg.conj));
    fflush(stdout);
    */

    pddlErrLogPause(err);

    // Construct P^C
    pddl_fdr_conj_exact_t pc;
    pddlFDRConjExactInit(&pc, fdr, &pc_cfg, err);

    // Initialize a set of mutexes
    pddl_mutex_pairs_t pc_mutex;
    pddlFDRConjExactMutexPairsInitCopy(&pc_mutex, mutex, &pc);

    // Compute h-value for P^C
    int hvalue = pot(&pc.fdr, &pc_mutex, lp_time_limit, pot_cfg, objval, err);

    pddlErrLogContinue(err);

    // Free allocated memory
    pddlMutexPairsFree(&pc_mutex);
    pddlFDRConjExactFree(&pc);
    pddlFDRConjExactConfigFree(&pc_cfg);

    return hvalue;
}

static int writeProgress(int hvalue,
                         const pddl_set_iset_t *conjs,
                         const pddl_fdr_t *fdr,
                         const char *prefix,
                         int epoch_idx,
                         pddl_err_t *err)
{
    char fn[1024];
    snprintf(fn, 1024, "%s.%04d", prefix, epoch_idx);
    FILE *fout = fopen(fn, "w");
    if (fout == NULL)
        ERR_RET(err, -1, "Could not open %s", fn);

    pddl_set_iset_t out_conjs;
    pddlSetISetInitCopy(&out_conjs, conjs);
    pddlSetISetGenAllSubsets(&out_conjs, 2);

    fprintf(fout, "hvalue = %d\n", hvalue);
    fprintf(fout, "conj = [\n");
    for (int cid = 0; cid < pddlSetISetSize(&out_conjs); ++cid){
        fprintf(fout, "  [");
        const pddl_iset_t *c = pddlSetISetGet(&out_conjs, cid);
        for (int i = 0; i < pddlISetSize(c); ++i){
            if (i > 0)
                fprintf(fout, ", ");
            fprintf(fout, "\"%s\"", fdr->var.global_id_to_val[pddlISetGet(c, i)]->name);
        }
        fprintf(fout, "],\n");
    }
    fprintf(fout, "]\n");

    pddlSetISetFree(&out_conjs);

    fclose(fout);
    return 0;
}


int pddlPotConjExactFind(pddl_set_iset_t *conjs,
                         int *best_hvalue_out,
                         double *best_objval_out,
                         const pddl_fdr_t *fdr,
                         const pddl_mutex_pairs_t *mutex,
                         const pddl_pot_conj_exact_find_config_t *cfg,
                         const pddl_hpot_config_t *pot_cfg,
                         pddl_err_t *err)
{
    if (!hpotConfigIsSupported(pot_cfg, err))
        TRACE_RET(err, -1);

    CTX(err, "Pot-Conj-Exact-Find");
    CTX_NO_TIME(err, "Cfg");
    pddlPotConjExactFindConfigLog(cfg, err);
    CTXEND(err);
    CTX_NO_TIME(err, "Cfg-Pot");
    pddlHPotConfigLog(pot_cfg, err);
    CTXEND(err);

    // Set up time limit
    pddl_time_limit_t time_limit;
    pddlTimeLimitSet(&time_limit, cfg->time_limit);

    // Determine the base heuristic value
    double best_objval;
    int best_hvalue = potConj(fdr, mutex, conjs, NULL,
                              cfg->lp_time_limit, pot_cfg, &best_objval, err);
    if (best_hvalue_out != NULL)
        *best_hvalue_out = best_hvalue;
    if (best_objval_out != NULL)
        *best_objval_out = best_objval;
    LOG(err, "Base h-value: %d", best_hvalue);

    for (int epoch = 0; epoch < cfg->max_epochs; ++epoch){
        if (pddlTimeLimitCheck(&time_limit) != 0){
            LOG(err, "Reached time limit. (%.2f seconds)", cfg->time_limit);
            break;
        }

        CTX(err, "Epoch %d", epoch);

        // Set to true if an improvement was found
        pddl_bool_t improved = pddl_false;

        // Frequency of logging
        pddl_time_limit_t log_timer;
        pddlTimeLimitSet(&log_timer, cfg->log_freq);

        conj_iterator_t it;
        conjIteratorInit(&it, IT_ALL, fdr, mutex);

        const pddl_iset_t *conj = conjIteratorNext(&it);
        for (int conji = 0; conji < cfg->max_num_conjs && conj != NULL; ++conji){
            ASSERT(pddlISetSize(conj) <= cfg->max_conj_dim);
            if (pddlISetSize(conj) > cfg->max_conj_dim)
                break;

            if (pddlTimeLimitCheck(&time_limit) != 0){
                LOG(err, "Reached time limit. (%.2f seconds)", cfg->time_limit);
                break;
            }

            // Compute h-value for P^C
            double objval;
            int hvalue = potConj(fdr, mutex, conjs, conj,
                                 cfg->lp_time_limit, pot_cfg, &objval, err);

            if (objval - best_objval > EPS){
                // Found improving conjunction
                LOG(err, "Tested %d conjunctions, cur size: %d",
                    conji + 1, pddlISetSize(conj));

                char log[1024];
                int written = 0;
                int fact;
                PDDL_ISET_FOR_EACH(conj, fact){
                    if (written >= 1024 - 1)
                        break;
                    written += snprintf(log + written, 1024 - written, " (%s)",
                                        fdr->var.global_id_to_val[fact]->name);
                }
                log[written] = '\x0';
                LOG(err, "Improving conjunction:%s", log);
                LOG(err, "Best h-value so far: %d", hvalue);
                LOG(err, "Best objective value so far: %.4f", objval);
                best_hvalue = hvalue;
                best_objval = objval;
                if (best_hvalue_out != NULL)
                    *best_hvalue_out = best_hvalue;
                if (best_objval_out != NULL)
                    *best_objval_out = best_objval;
                pddlSetISetAdd(conjs, conj);
                improved = pddl_true;

                if (cfg->write_progress_prefix != NULL){
                    if (writeProgress(hvalue, conjs, fdr,
                                cfg->write_progress_prefix, epoch, err) != 0){
                        conjIteratorFree(&it);
                        CTXEND(err);
                        CTXEND(err);
                        TRACE_RET(err, -1);
                    }
                }

            }else if (pddlTimeLimitCheck(&log_timer) != 0){
                // Log progress so that we know that something is happenning
                LOG(err, "Tested %d conjunctions, cur size: %d",
                    conji + 1, pddlISetSize(conj));
                pddlTimeLimitSet(&log_timer, cfg->log_freq);
            }

            // Handle error state
            if (hvalue < 0){
                conjIteratorFree(&it);
                CTXEND(err);
                CTXEND(err);
                TRACE_RET(err, -1);
            }

            if (improved)
                break;

            conj = conjIteratorNext(&it);
        }
        conjIteratorFree(&it);
        CTXEND(err);

        // No improvement -- there is no point in continuing
        if (!improved)
            break;
    }

    pddlSetISetGenAllSubsets(conjs, 2);

    CTXEND(err);
    return 0;
}

int pddlPotConjExactLoadFromFile(pddl_set_iset_t *conjs,
                                 int *best_hvalue,
                                 const pddl_fdr_t *fdr,
                                 const char *filename,
                                 pddl_err_t *err)
{
    FILE *fin = fopen(filename, "r");
    if (fin == NULL)
        ERR_RET(err, -1, "Cannot open file %s", filename);

    pddl_toml_table_t *table = pddl_toml_parse_file(fin, err);
    fclose(fin);
    if (table == NULL)
        TRACE_RET(err, -1);

    if (best_hvalue != NULL){
        pddl_toml_datum_t d = pddl_toml_int_in(table, "hvalue");
        if (!d.ok){
            pddl_toml_free(table);
            ERR_RET(err, -1, "Cannot find integer key 'hvalue' in the file %s",
                    filename);
        }
        *best_hvalue = d.u.i;
    }

    const pddl_toml_array_t *arr = pddl_toml_array_in(table, "conj");
    if (arr == NULL){
        pddl_toml_free(table);
        ERR_RET(err, -1, "Cannot find array 'conj' in the file %s", filename);
    }
    int conj_size = pddl_toml_array_nelem(arr);
    for (int conji = 0; conji < conj_size; ++conji){
        const pddl_toml_array_t *conj_arr = pddl_toml_array_at(arr, conji);
        if (conj_arr == NULL){
            pddl_toml_free(table);
            ERR_RET(err, -1, "Input file %s is maloformed: 'conj' has to be"
                    " array of arrays of strings", filename);
        }
        PDDL_ISET(conj);
        int size = pddl_toml_array_nelem(conj_arr);
        for (int i = 0; i < size; ++i){
            pddl_toml_datum_t d = pddl_toml_string_at(conj_arr, i);
            if (!d.ok){
                pddl_toml_free(table);
                pddlISetFree(&conj);
                ERR_RET(err, -1, "Input file %s is maloformed: 'conj' has to be"
                        " array of arrays of strings", filename);
            }

            int fact = -1;
            for (fact = 0; fact < fdr->var.global_id_size; ++fact){
                const pddl_fdr_val_t *v = fdr->var.global_id_to_val[fact];
                if (strcmp(v->name, d.u.s) == 0)
                    break;
            }
            if (fact >= fdr->var.global_id_size)
                fact = -1;

            if (fact < 0){
                pddl_toml_free(table);
                pddlISetFree(&conj);
                ERR_RET(err, -1, "Could not find fact (%s). The input file %s"
                        " probably does not match the planning task.",
                        d.u.s, filename);
            }
            pddlISetAdd(&conj, fact);
        }
        pddlSetISetAdd(conjs, &conj);
        pddlISetFree(&conj);
    }

    pddl_toml_free(table);

    return 0;
}

static int pddlPotConjExactMaxInitHValue1(const pddl_fdr_t *fdr,
                                          const pddl_mutex_pairs_t *mutex,
                                          enum conj_iterator_type it_type,
                                          pddl_err_t *err)
{
    pddl_hpot_config_t pot_cfg = PDDL_HPOT_CONFIG_INIT;
    pot_cfg.type = PDDL_HPOT_OPT_STATE_TYPE;

    int max_hvalue = -1;

    conj_iterator_t it;
    conjIteratorInit(&it, it_type, fdr, mutex);
    const pddl_iset_t *conj = conjIteratorNext(&it);
    while (conj != NULL){
        if (it_type == IT_PAIRS){
            CTX(err, "CONJ-1-pair");
            int f1 = pddlISetGet(conj, 0);
            int f2 = pddlISetGet(conj, 1);
            LOG(err, "Set: %d:(%s) %d:(%s)",
                f1, fdr->var.global_id_to_val[f1]->name,
                f2, fdr->var.global_id_to_val[f2]->name);

        }else if (it_type == IT_TRIPLES){
            CTX(err, "CONJ-1-triple");
            int f1 = pddlISetGet(conj, 0);
            int f2 = pddlISetGet(conj, 1);
            int f3 = pddlISetGet(conj, 2);
            LOG(err, "Set: %d:(%s) %d:(%s) %d:(%s)",
                f1, fdr->var.global_id_to_val[f1]->name,
                f2, fdr->var.global_id_to_val[f2]->name,
                f3, fdr->var.global_id_to_val[f3]->name);
        }

        pddl_fdr_conj_exact_config_t cfg;
        pddlFDRConjExactConfigInit(&cfg);
        pddlFDRConjExactConfigAddConj(&cfg, conj);

        if (pddlISetSize(conj) > 2){
            PDDL_ISET(pair);
            for (int i = 0; i < pddlISetSize(conj) - 1; ++i){
                for (int j = i + 1; j < pddlISetSize(conj); ++j){
                    PDDL_ISET_SET(&pair, pddlISetGet(conj, i), pddlISetGet(conj, j));
                    pddlFDRConjExactConfigAddConj(&cfg, &pair);
                }
            }
            pddlISetFree(&pair);
        }
        cfg.mutex = mutex;

        pddl_fdr_conj_exact_t pc;
        pddlFDRConjExactInit(&pc, fdr, &cfg, err);

        pddl_mutex_pairs_t pc_mutex;
        pddlFDRConjExactMutexPairsInitCopy(&pc_mutex, mutex, &pc);

        pddlErrLogPause(err);
        int hvalue = pot(&pc.fdr, &pc_mutex, MAX_INIT_LP_TIME_LIMIT, &pot_cfg, NULL, err);
        pddlErrLogContinue(err);
        if (hvalue < 0)
            TRACE_RET(err, -1);
        if (hvalue > max_hvalue)
            max_hvalue = hvalue;
        LOG(err, "Heuristic value: %d / best: %d", hvalue, max_hvalue);

        pddlMutexPairsFree(&pc_mutex);
        pddlFDRConjExactFree(&pc);
        pddlFDRConjExactConfigFree(&cfg);
        CTXEND(err);

        if (hvalue < 0)
            return -1;

        conj = conjIteratorNext(&it);
    }
    conjIteratorFree(&it);

    PDDL_LOG(err, "Maximum heuristic value: %d", max_hvalue);
    return max_hvalue;
}

static int pddlPotConjExactMaxInitHValue2(const pddl_fdr_t *fdr,
                                          const pddl_mutex_pairs_t *mutex,
                                          enum conj_iterator_type it_type,
                                          pddl_err_t *err)
{
    pddl_hpot_config_t pot_cfg = PDDL_HPOT_CONFIG_INIT;
    pot_cfg.type = PDDL_HPOT_OPT_STATE_TYPE;

    int max_hvalue = -1;

    conj_iterator_t it;
    conjIteratorInit(&it, it_type, fdr, mutex);
    const pddl_iset_t *conj = conjIteratorNext(&it);
    while (conj != NULL){
        conj_iterator_t it2;
        conjIteratorInitCopy(&it2, &it);
        const pddl_iset_t *conj2 = conjIteratorNext(&it2);
        while (conj2 != NULL){
            if (it_type == IT_PAIRS){
                CTX(err, "CONJ-2-pair");
                int f1 = pddlISetGet(conj, 0);
                int f2 = pddlISetGet(conj, 1);
                LOG(err, "Set: %d:(%s) %d:(%s)",
                    f1, fdr->var.global_id_to_val[f1]->name,
                    f2, fdr->var.global_id_to_val[f2]->name);
                f1 = pddlISetGet(conj2, 0);
                f2 = pddlISetGet(conj2, 1);
                LOG(err, "Set: %d:(%s) %d:(%s)",
                    f1, fdr->var.global_id_to_val[f1]->name,
                    f2, fdr->var.global_id_to_val[f2]->name);

            }else if (it_type == IT_TRIPLES){
                CTX(err, "CONJ-2-triple");
                int f1 = pddlISetGet(conj, 0);
                int f2 = pddlISetGet(conj, 1);
                int f3 = pddlISetGet(conj, 2);
                LOG(err, "Set: %d:(%s) %d:(%s) %d:(%s)",
                    f1, fdr->var.global_id_to_val[f1]->name,
                    f2, fdr->var.global_id_to_val[f2]->name,
                    f3, fdr->var.global_id_to_val[f3]->name);

                f1 = pddlISetGet(conj2, 0);
                f2 = pddlISetGet(conj2, 1);
                f3 = pddlISetGet(conj2, 2);
                LOG(err, "Set: %d:(%s) %d:(%s) %d:(%s)",
                    f1, fdr->var.global_id_to_val[f1]->name,
                    f2, fdr->var.global_id_to_val[f2]->name,
                    f3, fdr->var.global_id_to_val[f3]->name);
            }

            pddl_fdr_conj_exact_config_t cfg;
            pddlFDRConjExactConfigInit(&cfg);
            pddlFDRConjExactConfigAddConj(&cfg, conj);
            pddlFDRConjExactConfigAddConj(&cfg, conj2);

            pddl_fdr_conj_exact_t pc;
            pddlFDRConjExactInit(&pc, fdr, &cfg, err);

            pddl_mutex_pairs_t pc_mutex;
            pddlFDRConjExactMutexPairsInitCopy(&pc_mutex, mutex, &pc);

            pddlErrLogPause(err);
            int hvalue = pot(&pc.fdr, &pc_mutex, MAX_INIT_LP_TIME_LIMIT, &pot_cfg, NULL, err);
            pddlErrLogContinue(err);
            if (hvalue > max_hvalue)
                max_hvalue = hvalue;
            LOG(err, "Heuristic value: %d / best: %d", hvalue, max_hvalue);

            pddlMutexPairsFree(&pc_mutex);
            pddlFDRConjExactFree(&pc);
            pddlFDRConjExactConfigFree(&cfg);
            CTXEND(err);

            if (hvalue < 0)
                return -1;

            conj2 = conjIteratorNext(&it2);
        }
        conjIteratorFree(&it2);

        conj = conjIteratorNext(&it);
    }
    conjIteratorFree(&it);

    PDDL_LOG(err, "Maximum heuristic value: %d", max_hvalue);
    return max_hvalue;
}

int pddlPotConjExactMaxInitHValueBase(const pddl_fdr_t *fdr,
                                      const pddl_mutex_pairs_t *mutex,
                                      pddl_err_t *err)
{
    pddl_hpot_config_t pot_cfg = PDDL_HPOT_CONFIG_INIT;
    pot_cfg.type = PDDL_HPOT_OPT_STATE_TYPE;

    CTX(err, "BASE");

    pddlErrLogPause(err);
    int hvalue = pot(fdr, mutex, MAX_INIT_LP_TIME_LIMIT, &pot_cfg, NULL, err);
    pddlErrLogContinue(err);

    LOG(err, "Heuristic value: %d", hvalue);
    CTXEND(err);
    return hvalue;
}

int pddlPotConjExactMaxInitHValueOnePair(const pddl_fdr_t *fdr,
                                         const pddl_mutex_pairs_t *mutex,
                                         pddl_err_t *err)
{
    return pddlPotConjExactMaxInitHValue1(fdr, mutex, IT_PAIRS, err);
}

int pddlPotConjExactMaxInitHValueOneTriple(const pddl_fdr_t *fdr,
                                           const pddl_mutex_pairs_t *mutex,
                                           pddl_err_t *err)
{
    return pddlPotConjExactMaxInitHValue1(fdr, mutex, IT_TRIPLES, err);
}

int pddlPotConjExactMaxInitHValueTwoPairs(const pddl_fdr_t *fdr,
                                          const pddl_mutex_pairs_t *mutex,
                                          pddl_err_t *err)
{
    return pddlPotConjExactMaxInitHValue2(fdr, mutex, IT_PAIRS, err);
}


struct pddl_heur_pot_conj_exact {
    pddl_heur_t heur;
    pddl_pot_conj_exact_t pot;
    pddl_fdr_vars_t vars;
};
typedef struct pddl_heur_pot_conj_exact pddl_heur_pot_conj_exact_t;

static void heurDel(pddl_heur_t *_h)
{
    CONTAINER_OF(h, _h, pddl_heur_pot_conj_exact_t, heur);
    _pddlHeurFree(&h->heur);
    pddlPotConjExactFree(&h->pot);
    pddlFDRVarsFree(&h->vars);
    FREE(h);
}

static int heurEstimate(pddl_heur_t *_h,
                        const pddl_fdr_state_space_node_t *node,
                        const pddl_fdr_state_space_t *state_space)
{
    CONTAINER_OF(h, _h, pddl_heur_pot_conj_exact_t, heur);
    int est = pddlPotConjExactEvalMaxFDRState(&h->pot, &h->vars, node->state);
    return est;
}

pddl_heur_t *pddlHeurPotConjExact(const pddl_hpot_config_t *cfg,
                                  const pddl_set_iset_t *conjs,
                                  pddl_err_t *err)
{
    PANIC_IF(cfg->mutex == NULL, "pddlHeurPotConjExact() requires mutexes");
    if (cfg->fdr->has_cond_eff)
        ERR_RET(err, NULL, "Potential heuristic does not support conditional effects.");

    pddl_heur_pot_conj_exact_t *h = ZALLOC(pddl_heur_pot_conj_exact_t);
    if (pddlPotConjExactInit(&h->pot, conjs, cfg, err) != 0){
        FREE(h);
        TRACE_RET(err, NULL);
    }
    pddlFDRVarsInitCopy(&h->vars, &cfg->fdr->var);
    _pddlHeurInit(&h->heur, heurDel, heurEstimate);
    return &h->heur;
}

