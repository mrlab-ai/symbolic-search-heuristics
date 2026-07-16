/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/pot_conj.h"
#include "pddl/pot_conj_exact.h"
#include "internal.h"
#include "_heur.h"

pddl_heur_t *pot(const pddl_heur_config_t *cfg, pddl_err_t *err)
{
    pddl_hpot_config_t hcfg = cfg->pot;
    hcfg.fdr = cfg->fdr;
    hcfg.mg_strips = cfg->mg_strips;
    hcfg.mutex = cfg->mutex;
    pddl_heur_t *heur = pddlHeurPot(&hcfg, err);
    if (heur == NULL)
        TRACE_RET(err, NULL);
    return heur;
}

pddl_heur_t *potConj(const pddl_heur_config_t *cfg, pddl_err_t *err)
{
    if (cfg->pot_conj_file == NULL){
        ERR_RET(err, NULL, "Missing configuration file defining which"
                " conjunctions to use (pddl_heur_config_t.pot_conj_file)");
    }
    if (cfg->mg_strips == NULL){
        ERR_RET(err, NULL, "Potentials over conjunctions require .mg_strips"
                " to be set.");
    }

    pddl_set_iset_t conjs;
    pddlSetISetInit(&conjs);
    if (pddlPotConjLoadFromFile(&conjs, NULL, NULL, cfg->fdr,
                                cfg->pot_conj_file, err) != 0){
        TRACE_RET(err, NULL);
    }
    pddlSetISetGenAllSubsets(&conjs, 2);

    pddl_hpot_config_t hcfg = cfg->pot;
    hcfg.fdr = cfg->fdr;
    hcfg.mg_strips = cfg->mg_strips;
    hcfg.mutex = cfg->mutex;
    pddl_heur_t *heur = pddlHeurPotConj(&hcfg, &conjs, err);
    pddlSetISetFree(&conjs);
    if (heur == NULL)
        TRACE_RET(err, NULL);
    return heur;
}

pddl_heur_t *potConjExact(const pddl_heur_config_t *cfg, pddl_err_t *err)
{
    if (cfg->pot_conj_exact_file == NULL){
        ERR_RET(err, NULL, "Missing configuration file defining which"
                " conjunctions to use (pddl_heur_config_t.pot_conj_exact_file)");
    }

    pddl_set_iset_t conjs;
    pddlSetISetInit(&conjs);
    if (pddlPotConjExactLoadFromFile(&conjs, NULL, cfg->fdr,
                                     cfg->pot_conj_exact_file, err) != 0){
        TRACE_RET(err, NULL);
    }
    pddlSetISetGenAllSubsets(&conjs, 2);

    pddl_hpot_config_t hcfg = cfg->pot;
    hcfg.fdr = cfg->fdr;
    hcfg.mutex = cfg->mutex;
    pddl_heur_t *heur = pddlHeurPotConjExact(&hcfg, &conjs, err);
    pddlSetISetFree(&conjs);
    if (heur == NULL)
        TRACE_RET(err, NULL);
    return heur;
}

pddl_heur_t *pddlHeur(const pddl_heur_config_t *cfg, pddl_err_t *err)
{
    if (cfg->fdr == NULL)
        ERR_RET(err, NULL, "Config Error: Missing input task!");

    switch (cfg->heur){
        case PDDL_HEUR_BLIND:
            return pddlHeurBlind();
        case PDDL_HEUR_DEAD_END:
            return pddlHeurDeadEnd();
        case PDDL_HEUR_POT:
            return pot(cfg, err);
        case PDDL_HEUR_POT_CONJ:
            return potConj(cfg, err);
        case PDDL_HEUR_POT_CONJ_EXACT:
            return potConjExact(cfg, err);
        case PDDL_HEUR_FLOW:
            return pddlHeurFlow(cfg->fdr, err);
        case PDDL_HEUR_LM_CUT:
            return pddlHeurLMCut(cfg->fdr, err);
        case PDDL_HEUR_HMAX:
            return pddlHeurHMax(cfg->fdr, err);
        case PDDL_HEUR_HADD:
            return pddlHeurHAdd(cfg->fdr, err);
        case PDDL_HEUR_HFF:
            return pddlHeurHFF(cfg->fdr, err);
        case PDDL_HEUR_OP_MUTEX:
            if (cfg->mutex == NULL)
                ERR_RET(err, NULL, "Config Error: Missing input mutex set!");
            return pddlHeurOpMutex(cfg->fdr, cfg->mutex, &cfg->op_mutex, err);
    }
    return NULL;
}

void pddlHeurDel(pddl_heur_t *h)
{
    h->del_fn(h);
}

int pddlHeurEstimate(pddl_heur_t *h,
                     const pddl_fdr_state_space_node_t *node,
                     const pddl_fdr_state_space_t *state_space)
{
    return h->estimate_fn(h, node, state_space);
}
