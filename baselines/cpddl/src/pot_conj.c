/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "toml.h"
#include "_heur.h"
#include "pddl/pot_conj.h"
#include "pddl/critical_path.h"
#include "pddl/time_limit.h"
#include "pddl/rand.h"
#include "pddl/heur.h"

// Time limit for LP computing potential functions.
// This value is used for all pddlPotConjMaxInitHValue*() functions.
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

int pddlPotConjInit(pddl_pot_conj_t *pot,
                    const pddl_set_iset_t *conjs,
                    const pddl_hpot_config_t *cfg,
                    pddl_err_t *err)
{
    if (cfg->fdr == NULL || cfg->mg_strips == NULL)
        ERR_RET(err, -1, "Both FDR and MG-Strips representations are required.");
    if (cfg->mutex == NULL)
        ERR_RET(err, -1, "Mutexes are required.");
    if (pddlSetISetSize(conjs) == 0)
        ERR_RET(err, -1, "At least one conjunction is required.");
    if (!hpotConfigIsSupported(cfg, err))
        TRACE_RET(err, -1);

    ASSERT(cfg->fdr->var.global_id_size == cfg->mg_strips->strips.fact.fact_size);

    ZEROIZE(pot);
    pot->var_size = cfg->fdr->var.var_size;
    pddlPotSolutionsInit(&pot->pot);

    CTX(err, "Pot-Conj");
    CTX_NO_TIME(err, "Cfg");
    LOG(err, "Number of conjunctions: %d", pddlSetISetSize(conjs));
    for (int i = 0; i < pddlSetISetSize(conjs); ++i){
        const pddl_iset_t *c = pddlSetISetGet(conjs, i);
        char str[1024];
        int written = 0;
        int fact;
        PDDL_ISET_FOR_EACH(c, fact){
            if (written < 1024){
                const char *name = cfg->mg_strips->strips.fact.fact[fact]->name;
                int is_goal = pddlISetIn(fact, &cfg->mg_strips->strips.goal);
                written += snprintf(str + written, 1024 - written, " %d:(%s)%s",
                                    fact, name, (is_goal ? ":G" : ""));
            }
        }
        LOG(err, "Conj[%d]:%s", i, str);
    }
    pddlHPotConfigLog(cfg, err);
    CTXEND(err);

    // Construct P^C STRIPS task
    pddl_strips_conj_config_t pc_cfg;
    pddlStripsConjConfigInit(&pc_cfg);
    for (int i = 0; i < pddlSetISetSize(conjs); ++i)
        pddlStripsConjConfigAddConjAndSubsets(&pc_cfg, pddlSetISetGet(conjs, i));

    pddl_strips_conj_t pc;
    pddlStripsConjInit(&pc, &cfg->mg_strips->strips, &pc_cfg, err);
    ASSERT(pc.strips.fact.fact_size
                == cfg->mg_strips->strips.fact.fact_size + pddlSetISetSize(conjs));
#ifdef PDDL_DEBUG
    for (int fid = 0; fid < cfg->mg_strips->strips.fact.fact_size; ++fid){
        ASSERT(strcmp(cfg->mg_strips->strips.fact.fact[fid]->name,
                      pc.strips.fact.fact[fid]->name) == 0);
        ASSERT(strncmp(cfg->fdr->var.global_id_to_val[fid]->name,
                       pc.strips.fact.fact[fid]->name,
                       strlen(cfg->fdr->var.global_id_to_val[fid]->name)) == 0);
    }
#endif

    pddl_mutex_pairs_t pc_mutex;
    pddlStripsConjMutexPairsInitCopy(&pc_mutex, cfg->mutex, &pc);

    for (int i = 0; i < cfg->mg_strips->mg.mgroup_size; ++i){
        for (int j = i + 1; j < cfg->mg_strips->mg.mgroup_size; ++j){
            ASSERT(pddlISetIsDisjoint(&cfg->mg_strips->mg.mgroup[i].mgroup,
                                      &cfg->mg_strips->mg.mgroup[j].mgroup));
        }
    }

    // Construct the corresponding P^C FDR task
    pddl_fdr_config_t fdr_cfg = PDDL_FDR_CONFIG_INIT;
    fdr_cfg.var.alg = PDDL_FDR_VARS_ALG_LARGEST_FIRST;

    pddl_fdr_t fdr;
    pddlFDRInitFromStrips(&fdr, &pc.strips, &cfg->mg_strips->mg, &pc_mutex,
                          &fdr_cfg, err);

    pddl_mutex_pairs_t fdr_mutex;
    pddlFDRMutexPairsInitCopy(&fdr_mutex, &pc_mutex, &fdr);

    pddl_mg_strips_t mg_strips;
    pddlMGStripsInitFDR(&mg_strips, &fdr);

    // Infer mutexes in the P^C FDR task
    pddlMutexPairsAddMGroups(&fdr_mutex, &mg_strips.mg);
    pddlH2(&mg_strips.strips, &fdr_mutex, NULL, NULL, 0., err);

    // Transform cfg_in into the configuration for the current fdr
    // representation.
    // At this point, we don't support arbitrary states in
    // pddl_hpot_config_opt_state_t.fdr_state and in *.add_fdr_state_constr.
    // So, we just need to change the global part of the configuration
    // pertaining to the task and mutexes.
    pddl_hpot_config_t pot_cfg = *cfg;
    pot_cfg.fdr = &fdr;
    pot_cfg.mg_strips = &mg_strips;
    pot_cfg.mutex = &fdr_mutex;

    // Compute potential functions
    if (pddlHPot(&pot->pot, &pot_cfg, err) != 0){
        pddlMGStripsFree(&mg_strips);
        pddlMutexPairsFree(&fdr_mutex);
        pddlFDRFree(&fdr);
        pddlMutexPairsFree(&pc_mutex);
        pddlStripsConjFree(&pc);
        pddlStripsConjConfigFree(&pc_cfg);
        TRACE_RET(err, -1);
    }

    if (pot->pot.sol_size > 0){
        int hvalue = pddlPotSolutionEvalFDRState(pot->pot.sol + 0, &fdr.var, fdr.init);
        PDDL_LOG(err, "Heuristic value: %d", hvalue);
    }

    // Note that the all representations at this point are synchronized
    // as follows:
    //  1. Fact IDs (global IDs) in cfg->fdr are the same as fact IDs
    //     in cfg->mg_strips.
    //  2. Fact IDs in cfg->mg_strips are the same as fact IDs in pc.
    //     However, pc has additional facts corresponding to
    //     conjunctions (with higher IDs).
    //  3. Facts in fdr do NOT have the same ID as the corresponding
    //     facts in pc, but the fdr structure has the mapping
    //     .strips_id_to_val that maps pc's fact IDs to fdr facts.

    // Create a mapping from the original FDR to the P^C FDR task so that
    // we can later evaluate states from the original FDR.
    // That is, we need to be able to evaluate states from cfg->fdr while
    // our potential heuristics are computed for the P^C FDR task fdr.
    pddlFDRVarsInitCopy(&pot->pc_vars, &fdr.var);
    pot->fact_to_pc_fact = ALLOC_ARR(pddl_fdr_fact_t *, cfg->fdr->var.var_size);
    for (int vari = 0; vari < cfg->fdr->var.var_size; ++vari){
        const pddl_fdr_var_t *var = cfg->fdr->var.var + vari;
        pot->fact_to_pc_fact[vari] = ALLOC_ARR(pddl_fdr_fact_t, var->val_size);
        // From 1-3, we have that global IDs in cfg->fdr map through
        // fdr.strips_id_to_val to values in fdr.

        for (int vali = 0; vali < var->val_size; ++vali){
            int glob_id = var->val[vali].global_id;
            const pddl_iset_t *pcval_ids = fdr.var.strips_id_to_val + glob_id;
            PANIC_IF(pddlISetSize(pcval_ids) != 1,
                     "The translation to the P^C FDR task must be set up so"
                     " that every fact is encoded only once. It seems this"
                     " is not the case for the fact (%s). This is"
                     " definitely a bug.",
                     var->val[vali].name);
            int pcval_id = pddlISetGet(pcval_ids, 0);
            const pddl_fdr_val_t *pcval = fdr.var.global_id_to_val[pcval_id];
            pot->fact_to_pc_fact[vari][vali].var = pcval->var_id;
            pot->fact_to_pc_fact[vari][vali].val = pcval->val_id;
        }
    }


    // Create a mapping from conjunctions in the original FDR task to the
    // corresponding facts in the P^C FDR task
    pot->pc_conj_size = pddlSetISetSize(conjs);
    pot->pc_conj = ZALLOC_ARR(pddl_pot_conj_pc_conj_t, pot->pc_conj_size);
    for (int conji = 0; conji < pddlSetISetSize(conjs); ++conji){
        const pddl_iset_t *conj = pddlSetISetGet(conjs, conji);
        int conj_fact_id = pddlSetISetFind(&pc.conj_to_fact, conj);
        PANIC_IF(conj_fact_id < 0, "Conjunction is missing in the P^C task."
                 " This seems like a bug.");

        // From 1. it follows that the construction of the partial state in
        // the original FDR corresponding to the conjunction is
        // straightforward.
        pddlFDRPartStateInit(&pot->pc_conj[conji].fdr);
        int cfact;
        PDDL_ISET_FOR_EACH(conj, cfact){
            const pddl_fdr_val_t *v = cfg->fdr->var.global_id_to_val[cfact];
            pddlFDRPartStateSet(&pot->pc_conj[conji].fdr, v->var_id, v->val_id);
        }

        // Now, from 1. and 2., it follows that conj_fact_id is the fact ID
        // in pc of the fact corresponding to the input conjunction.
        // And from 3. it follows that we can obtain the corresponding
        // value in fdr using the .strips_id_to_val mapping.
        const pddl_iset_t *vals = fdr.var.strips_id_to_val + conj_fact_id;
        PANIC_IF(pddlISetSize(vals) != 1,
                 "Conjunction (%s) is encoded in two different variables."
                 " This shouldn't happen, because the translation should be"
                 " set up in such a way to avoid it. This is definitely a bug!",
                 pc.strips.fact.fact[conj_fact_id]->name);
        int fact_id = pddlISetGet(vals, 0);

        // Obtain the corresponding FDR value
        const pddl_fdr_val_t *v = fdr.var.global_id_to_val[fact_id];
        PANIC_IF(v == NULL, "Could not find fact ID %d in the P^C FDR task.",
                 conj_fact_id);
        ASSERT(strcmp(v->name, pc.strips.fact.fact[conj_fact_id]->name) == 0);
        PANIC_IF(fdr.var.var[v->var_id].val_size != 2,
                 "The conjunction is not encoded as a binary variable."
                 " It is unclear how this could happen."
                 " This seems like a bug.");

        // and set the fact (variable/value) in the P^C FDR task
        pot->pc_conj[conji].pc_var = v->var_id;
        pot->pc_conj[conji].pc_val = v->val_id;
        if (v->val_id == 0){
            pot->pc_conj[conji].pc_neg_val = 1;
        }else{
            pot->pc_conj[conji].pc_neg_val = 0;
        }
    }

    pddlMGStripsFree(&mg_strips);
    pddlMutexPairsFree(&fdr_mutex);
    pddlFDRFree(&fdr);
    pddlMutexPairsFree(&pc_mutex);
    pddlStripsConjFree(&pc);
    pddlStripsConjConfigFree(&pc_cfg);
    CTXEND(err);

    if (pot->pot.sol_size == 0)
        ERR_RET(err, -1, "No potential function found.");
    return 0;
}

void pddlPotConjFree(pddl_pot_conj_t *pot)
{
    pddlPotSolutionsFree(&pot->pot);
    for (int vari = 0; vari < pot->var_size; ++vari){
        if (pot->fact_to_pc_fact[vari] != NULL)
            FREE(pot->fact_to_pc_fact[vari]);
    }
    if (pot->fact_to_pc_fact != NULL)
        FREE(pot->fact_to_pc_fact);
    pddlFDRVarsFree(&pot->pc_vars);

    for (int conji = 0; conji < pot->pc_conj_size; ++conji){
        pddlFDRPartStateFree(&pot->pc_conj[conji].fdr);
    }
}

int pddlPotConjEvalMaxFDRState(const pddl_pot_conj_t *pot,
                               const pddl_fdr_vars_t *vars,
                               const int *fdr_state)
{
    int pc_state[pot->pc_vars.var_size];
    for (int vari = 0; vari < pot->pc_vars.var_size; ++vari)
        pc_state[vari] = pot->pc_vars.var[vari].val_none_of_those;

    for (int vari = 0; vari < vars->var_size; ++vari){
        const pddl_fdr_fact_t *pc_fact
                = &pot->fact_to_pc_fact[vari][fdr_state[vari]];
        pc_state[pc_fact->var] = pc_fact->val;
    }

    for (int conji = 0; conji < pot->pc_conj_size; ++conji){
        const pddl_pot_conj_pc_conj_t *c = pot->pc_conj + conji;
        if (pddlFDRPartStateIsConsistentWithState(&c->fdr, fdr_state)){
            pc_state[c->pc_var] = c->pc_val;
        }else{
            pc_state[c->pc_var] = c->pc_neg_val;
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


void pddlPotConjFindConfigLog(const pddl_pot_conj_find_config_t *cfg,
                              pddl_err_t *err)
{
    LOG_CONFIG_DBL(cfg, time_limit, err);
    LOG_CONFIG_INT(cfg, max_epochs, err);
    LOG_CONFIG_INT(cfg, max_conj_dim, err);
    LOG_CONFIG_DBL(cfg, log_freq, err);
    LOG_CONFIG_BOOL(cfg, random_conjs, err);
    LOG_CONFIG_INT(cfg, random_seed, err);
    LOG_CONFIG_STR(cfg, write_progress_prefix, err);
}

#define SET_MAX_SIZE 10

enum conj_iterator_type {
    IT_PAIRS,
    IT_TRIPLES,
    IT_ALL,
    IT_RND,
};

struct conj_iterator {
    enum conj_iterator_type type;
    const pddl_strips_t *strips;
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
        int max_val = it->strips->fact.fact_size - (it->set_size - idx - 1);
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
                             const pddl_strips_t *strips,
                             const pddl_mutex_pairs_t *mutex)
{
    ZEROIZE(it);
    it->type = type;
    it->strips = strips;
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
        case IT_RND:
            pddlRandInit(&it->rnd, 0);
            it->not_mutex_with = ZALLOC_ARR(pddl_iset_t, strips->fact.fact_size);
            for (int fi = 0; fi < strips->fact.fact_size; ++fi){
                pddlMutexPairsGetNotMutexWith(mutex, fi, it->not_mutex_with + fi);
            }
            break;
    }
}

static void conjIteratorInitRand(conj_iterator_t *it,
                                 int max_size,
                                 int random_seed,
                                 const pddl_strips_t *strips,
                                 const pddl_mutex_pairs_t *mutex)
{
    conjIteratorInit(it, IT_RND, strips, mutex);
    pddlRandInit(&it->rnd, random_seed);
    it->rnd_max_size = max_size;
}

static void conjIteratorInitCopy(conj_iterator_t *it,
                                 const conj_iterator_t *src)
{
    *it = *src;
    pddlISetInit(&it->conj);

    if (src->not_mutex_with != NULL){
        it->not_mutex_with = ZALLOC_ARR(pddl_iset_t, it->strips->fact.fact_size);
        for (int fi = 0; fi < it->strips->fact.fact_size; ++fi){
            pddlISetUnion(it->not_mutex_with + fi, src->not_mutex_with + fi);
        }
    }
}

static void conjIteratorFree(conj_iterator_t *it)
{
    pddlISetFree(&it->conj);
    if (it->not_mutex_with != NULL){
        for (int fi = 0; fi < it->strips->fact.fact_size; ++fi)
            pddlISetFree(it->not_mutex_with + fi);
        FREE(it->not_mutex_with);
    }
}

static const pddl_iset_t *conjIteratorNext(conj_iterator_t *it)
{
    if (it->type == IT_RND){
        PDDL_ISET(available);
        do {
            int size = pddlRand(&it->rnd, 2, it->rnd_max_size + 1);
            pddlISetEmpty(&it->conj);
            pddlISetEmpty(&available);
            for (int i = 0; i < size; ++i){
                if (i != 0 && pddlISetSize(&available) == 0)
                    break;

                int fact;
                if (i == 0){
                    fact = pddlRand(&it->rnd, 0, it->strips->fact.fact_size);
                    pddlISetUnion(&available, it->not_mutex_with + fact);
                }else{
                    int idx = pddlRand(&it->rnd, 0, pddlISetSize(&available));
                    fact = pddlISetGet(&available, idx);
                    pddlISetIntersect(&available, it->not_mutex_with + fact);
                }
                pddlISetAdd(&it->conj, fact);
            }
            ASSERT(pddlISetSize(&it->conj) <= 1
                    || !pddlMutexPairsIsMutexSet(it->mutex, &it->conj));
        } while (pddlISetSize(&it->conj) <= 1);
        pddlISetFree(&available);
        return &it->conj;
    }

    while (!it->set_end){
        pddlISetEmpty(&it->conj);
        for (int i = 0; i < it->set_size; ++i)
            pddlISetAdd(&it->conj, it->set[i]);

        if (!pddlMutexPairsIsMutexSet(it->mutex, &it->conj))
            break;

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


static int pot(const pddl_strips_t *strips,
               const pddl_mutex_pairs_t *mutex,
               const pddl_mgroups_t *mgroup,
               float lp_time_limit,
               const pddl_hpot_config_t *pot_cfg_in,
               double *objval,
               pddl_err_t *err)
{
    pddl_fdr_config_t cfg = PDDL_FDR_CONFIG_INIT;
    cfg.var.alg = PDDL_FDR_VARS_ALG_LARGEST_FIRST;

    pddl_fdr_t fdr;
    pddlFDRInitFromStrips(&fdr, strips, mgroup, mutex, &cfg, err);

    pddl_mutex_pairs_t fdr_mutex;
    pddlFDRMutexPairsInitCopy(&fdr_mutex, mutex, &fdr);

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

static int potConj(const pddl_strips_t *strips,
                   const pddl_mutex_pairs_t *mutex,
                   const pddl_mgroups_t *mgroup,
                   const pddl_set_iset_t *conjs,
                   const pddl_iset_t *conj,
                   float lp_time_limit,
                   const pddl_hpot_config_t *pot_cfg,
                   double *objval,
                   pddl_err_t *err)
{
    if (conj == NULL && (conjs == NULL || pddlSetISetSize(conjs) == 0)){
        pddlErrLogPause(err);
        int ret = pot(strips, mutex, mgroup, lp_time_limit, pot_cfg, objval, err);
        pddlErrLogContinue(err);
        return ret;
    }

    pddl_strips_conj_config_t pc_cfg;
    pddlStripsConjConfigInit(&pc_cfg);
    // Set up the set of conjunctions C
    if (conjs != NULL){
        for (int i = 0; i < pddlSetISetSize(conjs); ++i)
            pddlStripsConjConfigAddConjAndSubsets(&pc_cfg, pddlSetISetGet(conjs, i));
    }
    if (conj != NULL)
        pddlStripsConjConfigAddConjAndSubsets(&pc_cfg, conj);

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
    pddl_strips_conj_t pc;
    pddlStripsConjInit(&pc, strips, &pc_cfg, err);

    // Initialize a set of mutexes
    pddl_mutex_pairs_t pc_mutex;
    pddlStripsConjMutexPairsInitCopy(&pc_mutex, mutex, &pc);

    // Compute h-value for P^C
    int hvalue = pot(&pc.strips, &pc_mutex, mgroup, lp_time_limit, pot_cfg, objval, err);

    pddlErrLogContinue(err);

    // Free allocated memory
    pddlMutexPairsFree(&pc_mutex);
    pddlStripsConjFree(&pc);
    pddlStripsConjConfigFree(&pc_cfg);

    return hvalue;
}

static int writeProgress(int hvalue,
                         const pddl_set_iset_t *conjs,
                         const pddl_strips_t *strips,
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
            fprintf(fout, "\"%s\"", strips->fact.fact[pddlISetGet(c, i)]->name);
        }
        fprintf(fout, "],\n");
    }
    fprintf(fout, "]\n");

    pddlSetISetFree(&out_conjs);

    fclose(fout);
    return 0;
}


int pddlPotConjFind(pddl_set_iset_t *conjs,
                    int *best_hvalue_out,
                    double *best_objval_out,
                    const pddl_strips_t *strips,
                    const pddl_mutex_pairs_t *mutex,
                    const pddl_mgroups_t *mgroup,
                    const pddl_pot_conj_find_config_t *cfg,
                    const pddl_hpot_config_t *pot_cfg,
                    pddl_err_t *err)
{
    if (!hpotConfigIsSupported(pot_cfg, err))
        TRACE_RET(err, -1);

    CTX(err, "Pot-Conj-Find");
    CTX_NO_TIME(err, "Cfg");
    pddlPotConjFindConfigLog(cfg, err);
    CTXEND(err);
    CTX_NO_TIME(err, "Cfg-Pot");
    pddlHPotConfigLog(pot_cfg, err);
    CTXEND(err);

    // Set up time limit
    pddl_time_limit_t time_limit;
    pddlTimeLimitSet(&time_limit, cfg->time_limit);

    // Determine the base heuristic value
    double best_objval;
    int best_hvalue = potConj(strips, mutex, mgroup, conjs, NULL,
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
        if (cfg->random_conjs){
            conjIteratorInitRand(&it, cfg->max_conj_dim, cfg->random_seed,
                                 strips, mutex);
        }else{
            conjIteratorInit(&it, IT_ALL, strips, mutex);
        }

        const pddl_iset_t *conj = conjIteratorNext(&it);
        for (int conji = 0; conji < cfg->max_num_conjs && conj != NULL; ++conji){
            ASSERT(!cfg->random_conjs || pddlISetSize(conj) <= cfg->max_conj_dim);
            if (pddlISetSize(conj) > cfg->max_conj_dim)
                break;

            if (pddlTimeLimitCheck(&time_limit) != 0){
                LOG(err, "Reached time limit. (%.2f seconds)", cfg->time_limit);
                break;
            }

            // Compute h-value for P^C
            double objval;
            int hvalue = potConj(strips, mutex, mgroup, conjs, conj,
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
                    written += snprintf(log + written, 1024 - written, " (%s)%s",
                                        strips->fact.fact[fact]->name,
                                        (pddlISetIn(fact, &strips->goal) ? ":G" : ""));
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
                    if (writeProgress(hvalue, conjs, strips,
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

int pddlPotConjLoadFromFile(pddl_set_iset_t *conjs,
                            int *best_hvalue,
                            const pddl_strips_t *strips,
                            const pddl_fdr_t *fdr,
                            const char *filename,
                            pddl_err_t *err)
{
    if ((strips == NULL && fdr == NULL) || (strips != NULL && fdr != NULL)){
        ERR_RET(err, -1, "Exactly one of strips and fdr parameters must be non-NULL.");
    }

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
            if (strips != NULL){
                for (fact = 0; fact < strips->fact.fact_size; ++fact){
                    if (strcmp(strips->fact.fact[fact]->name, d.u.s) == 0)
                        break;
                }
                if (fact >= strips->fact.fact_size)
                    fact = -1;

            }else if (fdr != NULL){
                for (fact = 0; fact < fdr->var.global_id_size; ++fact){
                    const pddl_fdr_val_t *v = fdr->var.global_id_to_val[fact];
                    if (strcmp(v->name, d.u.s) == 0)
                        break;
                }
                if (fact >= fdr->var.global_id_size)
                    fact = -1;
            }

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

    return 0;
}

static int pddlPotConjMaxInitHValue1(const pddl_strips_t *strips,
                                     const pddl_mutex_pairs_t *mutex,
                                     const pddl_mgroups_t *mgroup,
                                     enum conj_iterator_type it_type,
                                     pddl_err_t *err)
{
    pddl_hpot_config_t pot_cfg = PDDL_HPOT_CONFIG_INIT;
    pot_cfg.type = PDDL_HPOT_OPT_STATE_TYPE;

    int max_hvalue = -1;

    conj_iterator_t it;
    conjIteratorInit(&it, it_type, strips, mutex);
    const pddl_iset_t *conj = conjIteratorNext(&it);
    while (conj != NULL){
        if (it_type == IT_PAIRS){
            CTX(err, "CONJ-1-pair");
            int f1 = pddlISetGet(conj, 0);
            int f2 = pddlISetGet(conj, 1);
            LOG(err, "Set: %d:(%s) %d:(%s)",
                f1, strips->fact.fact[f1]->name,
                f2, strips->fact.fact[f2]->name);

        }else if (it_type == IT_TRIPLES){
            CTX(err, "CONJ-1-triple");
            int f1 = pddlISetGet(conj, 0);
            int f2 = pddlISetGet(conj, 1);
            int f3 = pddlISetGet(conj, 2);
            LOG(err, "Set: %d:(%s) %d:(%s) %d:(%s)",
                f1, strips->fact.fact[f1]->name,
                f2, strips->fact.fact[f2]->name,
                f3, strips->fact.fact[f3]->name);
        }

        pddl_strips_conj_config_t cfg;
        pddlStripsConjConfigInit(&cfg);
        pddlStripsConjConfigAddConj(&cfg, conj);

        if (pddlISetSize(conj) > 2){
            PDDL_ISET(pair);
            for (int i = 0; i < pddlISetSize(conj) - 1; ++i){
                for (int j = i + 1; j < pddlISetSize(conj); ++j){
                    PDDL_ISET_SET(&pair, pddlISetGet(conj, i), pddlISetGet(conj, j));
                    pddlStripsConjConfigAddConj(&cfg, &pair);
                }
            }
            pddlISetFree(&pair);
        }

        pddl_strips_conj_t pc;
        pddlStripsConjInit(&pc, strips, &cfg, err);

        pddl_mutex_pairs_t pc_mutex;
        pddlStripsConjMutexPairsInitCopy(&pc_mutex, mutex, &pc);

        pddlErrLogPause(err);
        int hvalue = pot(&pc.strips, &pc_mutex, mgroup,
                         MAX_INIT_LP_TIME_LIMIT, &pot_cfg, NULL, err);
        pddlErrLogContinue(err);
        if (hvalue < 0)
            TRACE_RET(err, -1);
        if (hvalue > max_hvalue)
            max_hvalue = hvalue;
        LOG(err, "Heuristic value: %d / best: %d", hvalue, max_hvalue);

        pddlMutexPairsFree(&pc_mutex);
        pddlStripsConjFree(&pc);
        pddlStripsConjConfigFree(&cfg);
        CTXEND(err);

        if (hvalue < 0)
            return -1;

        conj = conjIteratorNext(&it);
    }
    conjIteratorFree(&it);

    PDDL_LOG(err, "Maximum heuristic value: %d", max_hvalue);
    return max_hvalue;
}

static int pddlPotConjMaxInitHValue2(const pddl_strips_t *strips,
                                     const pddl_mutex_pairs_t *mutex,
                                     const pddl_mgroups_t *mgroup,
                                     enum conj_iterator_type it_type,
                                     pddl_err_t *err)
{
    pddl_hpot_config_t pot_cfg = PDDL_HPOT_CONFIG_INIT;
    pot_cfg.type = PDDL_HPOT_OPT_STATE_TYPE;

    int max_hvalue = -1;

    conj_iterator_t it;
    conjIteratorInit(&it, it_type, strips, mutex);
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
                    f1, strips->fact.fact[f1]->name,
                    f2, strips->fact.fact[f2]->name);
                f1 = pddlISetGet(conj2, 0);
                f2 = pddlISetGet(conj2, 1);
                LOG(err, "Set: %d:(%s) %d:(%s)",
                    f1, strips->fact.fact[f1]->name,
                    f2, strips->fact.fact[f2]->name);

            }else if (it_type == IT_TRIPLES){
                CTX(err, "CONJ-2-triple");
                int f1 = pddlISetGet(conj, 0);
                int f2 = pddlISetGet(conj, 1);
                int f3 = pddlISetGet(conj, 2);
                LOG(err, "Set: %d:(%s) %d:(%s) %d:(%s)",
                    f1, strips->fact.fact[f1]->name,
                    f2, strips->fact.fact[f2]->name,
                    f3, strips->fact.fact[f3]->name);

                f1 = pddlISetGet(conj2, 0);
                f2 = pddlISetGet(conj2, 1);
                f3 = pddlISetGet(conj2, 2);
                LOG(err, "Set: %d:(%s) %d:(%s) %d:(%s)",
                    f1, strips->fact.fact[f1]->name,
                    f2, strips->fact.fact[f2]->name,
                    f3, strips->fact.fact[f3]->name);
            }

            pddl_strips_conj_config_t cfg;
            pddlStripsConjConfigInit(&cfg);
            pddlStripsConjConfigAddConj(&cfg, conj);
            pddlStripsConjConfigAddConj(&cfg, conj2);

            pddl_strips_conj_t pc;
            pddlStripsConjInit(&pc, strips, &cfg, err);

            pddl_mutex_pairs_t pc_mutex;
            pddlStripsConjMutexPairsInitCopy(&pc_mutex, mutex, &pc);

            pddlErrLogPause(err);
            int hvalue = pot(&pc.strips, &pc_mutex, mgroup,
                             MAX_INIT_LP_TIME_LIMIT, &pot_cfg, NULL, err);
            pddlErrLogContinue(err);
            if (hvalue > max_hvalue)
                max_hvalue = hvalue;
            LOG(err, "Heuristic value: %d / best: %d", hvalue, max_hvalue);

            pddlMutexPairsFree(&pc_mutex);
            pddlStripsConjFree(&pc);
            pddlStripsConjConfigFree(&cfg);
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

int pddlPotConjMaxInitHValueBase(const pddl_strips_t *strips,
                                 const pddl_mutex_pairs_t *mutex,
                                 const pddl_mgroups_t *mgroup,
                                 pddl_err_t *err)
{
    pddl_hpot_config_t pot_cfg = PDDL_HPOT_CONFIG_INIT;
    pot_cfg.type = PDDL_HPOT_OPT_STATE_TYPE;

    CTX(err, "BASE");

    pddlErrLogPause(err);
    int hvalue = pot(strips, mutex, mgroup, MAX_INIT_LP_TIME_LIMIT,
                     &pot_cfg, NULL, err);
    pddlErrLogContinue(err);

    LOG(err, "Heuristic value: %d", hvalue);
    CTXEND(err);
    return hvalue;
}

int pddlPotConjMaxInitHValueOnePair(const pddl_strips_t *strips,
                                    const pddl_mutex_pairs_t *mutex,
                                    const pddl_mgroups_t *mgroup,
                                    pddl_err_t *err)
{
    return pddlPotConjMaxInitHValue1(strips, mutex, mgroup, IT_PAIRS, err);
}

int pddlPotConjMaxInitHValueOneTriple(const pddl_strips_t *strips,
                                      const pddl_mutex_pairs_t *mutex,
                                      const pddl_mgroups_t *mgroup,
                                      pddl_err_t *err)
{
    return pddlPotConjMaxInitHValue1(strips, mutex, mgroup, IT_TRIPLES, err);
}

int pddlPotConjMaxInitHValueTwoPairs(const pddl_strips_t *strips,
                                     const pddl_mutex_pairs_t *mutex,
                                     const pddl_mgroups_t *mgroup,
                                     pddl_err_t *err)
{
    return pddlPotConjMaxInitHValue2(strips, mutex, mgroup, IT_PAIRS, err);
}


struct pddl_heur_pot_conj {
    pddl_heur_t heur;
    pddl_pot_conj_t pot;
    pddl_fdr_vars_t vars;
};
typedef struct pddl_heur_pot_conj pddl_heur_pot_conj_t;

static void heurDel(pddl_heur_t *_h)
{
    CONTAINER_OF(h, _h, pddl_heur_pot_conj_t, heur);
    _pddlHeurFree(&h->heur);
    pddlPotConjFree(&h->pot);
    pddlFDRVarsFree(&h->vars);
    FREE(h);
}

static int heurEstimate(pddl_heur_t *_h,
                        const pddl_fdr_state_space_node_t *node,
                        const pddl_fdr_state_space_t *state_space)
{
    CONTAINER_OF(h, _h, pddl_heur_pot_conj_t, heur);
    int est = pddlPotConjEvalMaxFDRState(&h->pot, &h->vars, node->state);
    return est;
}

pddl_heur_t *pddlHeurPotConj(const pddl_hpot_config_t *cfg,
                             const pddl_set_iset_t *conjs,
                             pddl_err_t *err)
{
    if (cfg->fdr->has_cond_eff)
        ERR_RET(err, NULL, "Potential heuristic does not support conditional effects.");

    pddl_heur_pot_conj_t *h = ZALLOC(pddl_heur_pot_conj_t);
    if (pddlPotConjInit(&h->pot, conjs, cfg, err) != 0){
        FREE(h);
        TRACE_RET(err, NULL);
    }
    pddlFDRVarsInitCopy(&h->vars, &cfg->fdr->var);
    _pddlHeurInit(&h->heur, heurDel, heurEstimate);
    return &h->heur;
}
