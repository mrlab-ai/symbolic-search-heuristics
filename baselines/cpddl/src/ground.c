/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/ground.h"
#include "pddl/strips_ground_datalog.h"
#include "pddl/strips_ground_sql.h"
#include "pddl/strips_ground_trie.h"
#include "pddl/strips_ground_clingo.h"

void pddlGroundConfigLog(const pddl_ground_config_t *cfg, pddl_err_t *err)
{
    switch (cfg->method){
        case PDDL_GROUND_DATALOG:
            LOG(err, "method = datalog");
            break;

        case PDDL_GROUND_SQL:
            LOG(err, "method = sql");
            break;

        case PDDL_GROUND_TRIE:
            LOG(err, "method = trie");
            break;

        case PDDL_GROUND_GRINGO:
            LOG(err, "method = gringo");
            break;

        case PDDL_GROUND_CLINGO:
            LOG(err, "method = clingo");
            break;

        default:
            LOG(err, "method = unknown");
    }

    if (cfg->lifted_mgroups == NULL){
        LOG(err, "lifted_mgroups->mgroup_size = 0");
    }else{
        LOG_CONFIG_INT(cfg, lifted_mgroups->mgroup_size, err);
    }
    LOG_CONFIG_BOOL(cfg, prune_op_pre_mutex, err);
    LOG_CONFIG_BOOL(cfg, prune_op_dead_end, err);
    LOG_CONFIG_BOOL(cfg, remove_static_facts, err);
    LOG_CONFIG_BOOL(cfg, keep_action_args, err);
    LOG_CONFIG_BOOL(cfg, keep_all_static_facts, err);
    LOG_CONFIG_BOOL(cfg, ground_only_facts, err);
    LOG_CONFIG_STR(cfg, gringo_lpopt, err);
}

int pddlGround(pddl_strips_t *strips,
               const pddl_t *pddl,
               const pddl_ground_config_t *cfg,
               pddl_err_t *err)
{
    CTX(err, "GR");
    CTX_NO_TIME(err, "Cfg");
    pddlGroundConfigLog(cfg, err);
    CTXEND(err);

    int ret = -1;
    switch (cfg->method){
        case PDDL_GROUND_DATALOG:
            ret = pddlStripsGroundDatalog(strips, pddl, cfg, err);
            break;

        case PDDL_GROUND_SQL:
            ret = pddlStripsGroundSql(strips, pddl, cfg, err);
            break;

        case PDDL_GROUND_TRIE:
            ret = pddlStripsGroundTrie(strips, pddl, cfg, err);
            break;

        case PDDL_GROUND_GRINGO:
            ret = pddlStripsGroundGringo(strips, pddl, cfg, err);
            break;

        case PDDL_GROUND_CLINGO:
            ret = pddlStripsGroundClingo(strips, pddl, cfg, err);
            break;

        default:
            ERR_RET(err, -1, "Unkown grounding method %d", cfg->method);
    }
    CTXEND(err);
    return ret;
}
