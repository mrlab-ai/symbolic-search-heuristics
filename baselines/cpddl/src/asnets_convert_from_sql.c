/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "sqlite3.h"
#include "pddl/asnets_convert_from_sql.h"
#include "pddl/asnets.h"
#include "pddl/sha256.h"
#include "pddl/base64.h"
#include "pddl/sort.h"


#define SIG_ACTION_W 0
#define SIG_ACTION_B 1
#define SIG_PROP_W 2
#define SIG_PROP_B 3


struct params {
    int layer;
    int sig;
    char *name;
    int idx;

    int size;
    unsigned char *enc;
};

struct info {
    char cpddl_version[128];
    char domain_name[128];
    char domain_pddl[4096];
    char domain_hash[PDDL_SHA256_HASH_STR_SIZE];

    pddl_asnets_config_t cfg;

    /** Train stats */
    int epoch;
    int num_samples;
    float success_rate;
    float overall_loss;

    struct params *params;
    int params_size;
    int params_alloc;
};

static void infoInit(struct info *info)
{
    ZEROIZE(info);
    info->params_size = 0;
    info->params_alloc = 4;
    info->params = ALLOC_ARR(struct params, info->params_alloc);
}

static void infoFree(struct info *info)
{
    for (int i = 0; i < info->params_size; ++i){
        if (info->params[i].name != NULL)
            FREE(info->params[i].name);
        if (info->params[i].enc != NULL)
            FREE(info->params[i].enc);
    }
    if (info->params != NULL)
        FREE(info->params);
}

static const char sql_query_info[]
    = "SELECT int_value, flt_value, str_value"
      " FROM asnets_info WHERE parameter = ?;";

static const char sql_query_all_weights[]
    = "SELECT layer, sig, name, idx, weights FROM asnets_weights;";

static int _sqlSelectInfo(pddl_sqlite3 *db,
                          pddl_sqlite3_stmt *stmt,
                          const char *param,
                          int *int_val,
                          float *flt_val,
                          char *str_val,
                          pddl_err_t *err)
{
    pddl_sqlite3_reset(stmt);
    int ret = pddl_sqlite3_bind_text(stmt, 1, param, -1, SQLITE_STATIC);
    if (ret != SQLITE_OK){
        ERR_RET(err, -1, "Sqlite Error: %s: %s",
                pddl_sqlite3_errstr(ret), pddl_sqlite3_errmsg(db));
    }

    int found = (ret = pddl_sqlite3_step(stmt)) == SQLITE_ROW;
    if (ret != SQLITE_ROW && ret != SQLITE_DONE){
        ERR_RET(err, -1, "Sqlite Error: %s: %s",
                pddl_sqlite3_errstr(ret), pddl_sqlite3_errmsg(db));
    }
    if (!found)
        ERR_RET(err, -1, "Parameter %s not found.", param);

    if (int_val != NULL)
        *int_val = pddl_sqlite3_column_int(stmt, 0);
    if (flt_val != NULL)
        *flt_val = pddl_sqlite3_column_double(stmt, 1);
    if (str_val != NULL){
        const unsigned char *v = pddl_sqlite3_column_text(stmt, 2);
        strcpy(str_val, (const char *)v);
    }
    return 0;
}

static int _sqlSelectInfoInt(pddl_sqlite3 *db,
                             pddl_sqlite3_stmt *stmt,
                             const char *param,
                             pddl_err_t *err)
{
    int val;
    int ret = _sqlSelectInfo(db, stmt, param, &val, NULL, NULL, err);
    if (ret < 0)
        TRACE_RET(err, INT_MIN);
    return val;

}

static float _sqlSelectInfoFlt(pddl_sqlite3 *db,
                               pddl_sqlite3_stmt *stmt,
                               const char *param,
                               pddl_err_t *err)
{
    float val;
    int ret = _sqlSelectInfo(db, stmt, param, NULL, &val, NULL, err);
    if (ret < 0)
        TRACE_RET(err, -FLT_MAX);
    return val;

}

static int _sqlSelectInfoStr(pddl_sqlite3 *db,
                             pddl_sqlite3_stmt *stmt,
                             const char *param,
                             char *val,
                             pddl_err_t *err)
{
    int ret = _sqlSelectInfo(db, stmt, param, NULL, NULL, val, err);
    if (ret < 0)
        TRACE_RET(err, -1);
    return 0;
}

#define SQL_INFO_CFG_INT(N) \
    do { \
        info->cfg.N = _sqlSelectInfoInt(db, stmt, "cfg_" #N, err); \
        if (info->cfg.N == INT_MIN){ \
            TRACE_RET(err, -1); \
        }else{ \
            LOG(err, "cfg." #N " = %d", info->cfg.N); \
        } \
    } while (0)

#define SQL_INFO_CFG_FLT(N) \
    do { \
        info->cfg.N = _sqlSelectInfoFlt(db, stmt, "cfg_" #N, err); \
        if (info->cfg.N == -FLT_MAX){ \
            TRACE_RET(err, -1); \
        }else{ \
            LOG(err, "cfg." #N " = %f", info->cfg.N); \
        } \
    } while (0)

static int infoLoad(struct info *info, pddl_sqlite3 *db, pddl_err_t *err)
{
    pddl_sqlite3_stmt *stmt;
    int ret = pddl_sqlite3_prepare_v2(db, sql_query_info, -1, &stmt, NULL);
    if (ret != SQLITE_OK){
        ERR_RET(err, -1, "Sqlite Error: %s: %s",
                pddl_sqlite3_errstr(ret), pddl_sqlite3_errmsg(db));
    }

    if (_sqlSelectInfoStr(db, stmt, "cpddl_version", info->cpddl_version, err) != 0)
        TRACE_RET(err, -1);
    LOG(err, "cpddl version = %s", info->cpddl_version);
    if (_sqlSelectInfoStr(db, stmt, "domain_name", info->domain_name, err) != 0)
        TRACE_RET(err, -1);
    LOG(err, "domain name = %s", info->domain_name);
    if (_sqlSelectInfoStr(db, stmt, "domain_pddl", info->domain_pddl, err) != 0)
        TRACE_RET(err, -1);
    LOG(err, "domain pddl = %s", info->domain_pddl);
    if (_sqlSelectInfoStr(db, stmt, "domain_hash", info->domain_hash, err) != 0)
        TRACE_RET(err, -1);
    LOG(err, "domain hash = %s", info->domain_hash);

    info->epoch = _sqlSelectInfoInt(db, stmt, "epoch", err);
    if (info->epoch == INT_MIN)
        TRACE_RET(err, -1);
    LOG(err, "train epoch = %d", info->epoch);
    info->num_samples = _sqlSelectInfoInt(db, stmt, "num_samples", err);
    if (info->num_samples == INT_MIN)
        TRACE_RET(err, -1);
    LOG(err, "num samples = %d", info->num_samples);
    info->success_rate = _sqlSelectInfoFlt(db, stmt, "success_rate", err);
    if (info->success_rate == -FLT_MAX)
        TRACE_RET(err, -1);
    LOG(err, "success rate = %f", info->success_rate);
    info->overall_loss = _sqlSelectInfoFlt(db, stmt, "overall_loss", err);
    if (info->overall_loss == -FLT_MAX)
        TRACE_RET(err, -1);
    LOG(err, "overall loss = %f", info->overall_loss);

    SQL_INFO_CFG_INT(hidden_dimension);
    SQL_INFO_CFG_INT(num_layers);
    SQL_INFO_CFG_FLT(weight_decay);
    SQL_INFO_CFG_FLT(dropout_rate);
    SQL_INFO_CFG_INT(random_seed);
    SQL_INFO_CFG_INT(batch_size);
    SQL_INFO_CFG_INT(double_batch_size_every_epoch);
    SQL_INFO_CFG_INT(max_train_epochs);
    SQL_INFO_CFG_INT(train_steps);
    SQL_INFO_CFG_INT(policy_rollout_limit);
    SQL_INFO_CFG_FLT(teacher_timeout);
    SQL_INFO_CFG_FLT(early_termination_success_rate);
    SQL_INFO_CFG_INT(early_termination_epochs);

    return 0;
}

static int cmpParams(const void *a, const void *b, void *_)
{
    const struct params *p1 = a;
    const struct params *p2 = b;
    int cmp = p1->layer - p2->layer;
    if (cmp == 0){
        int p1_is_action = (p1->sig == SIG_ACTION_W || p1->sig == SIG_ACTION_B);
        int p2_is_action = (p2->sig == SIG_ACTION_W || p2->sig == SIG_ACTION_B);
        if (p1_is_action && !p2_is_action)
            return -1;
        if (!p1_is_action && p2_is_action)
            return 1;
        cmp = p1->idx - p2->idx;
        if (cmp == 0)
            return p1->sig - p2->sig;
    }
    return cmp;
}

int pddlASNetsConvertFromSql(const char *input_model_sql,
                             const char *output_model,
                             pddl_err_t *err)
{
    CTX(err, "ASNets-Convert");
    LOG(err, "Converting from sql model %s to a new model %s",
        input_model_sql, output_model);

    pddl_sqlite3 *db;
    int flags = SQLITE_OPEN_READONLY;
    int ret = pddl_sqlite3_open_v2(input_model_sql, &db, flags, NULL);
    if (ret != SQLITE_OK){
        CTXEND(err);
        ERR_RET(err, -1, "Sqlite Error: %s: %s",
                pddl_sqlite3_errstr(ret), pddl_sqlite3_errmsg(db));
    }

    struct info info;
    infoInit(&info);
    if (infoLoad(&info, db, err) != 0){
        pddl_sqlite3_close_v2(db);
        CTXEND(err);
        TRACE_RET(err, -1);
    }

    pddl_sqlite3_stmt *stmt;
    ret = pddl_sqlite3_prepare_v2(db, sql_query_all_weights, -1, &stmt, NULL);
    if (ret != SQLITE_OK){
        pddl_sqlite3_close_v2(db);
        CTXEND(err);
        ERR_RET(err, -1, "Sqlite Error: %s: %s",
                pddl_sqlite3_errstr(ret), pddl_sqlite3_errmsg(db));
    }

    int sql_st;
    while ((sql_st = pddl_sqlite3_step(stmt)) == SQLITE_ROW){
        if (info.params_size == info.params_alloc){
            info.params_alloc *= 2;
            info.params = REALLOC_ARR(info.params, struct params,
                                      info.params_alloc);
        }

        struct params *p = info.params + info.params_size++;
        ZEROIZE(p);
        p->layer = pddl_sqlite3_column_int(stmt, 0);
        p->sig = pddl_sqlite3_column_int(stmt, 1);
        const unsigned char *name = pddl_sqlite3_column_text(stmt, 2);
        p->name = STRDUP((const char *)name);
        p->idx = pddl_sqlite3_column_int(stmt, 3);

        p->size = pddl_sqlite3_column_bytes(stmt, 4) / sizeof(float);
        const float *w = (const float *)pddl_sqlite3_column_blob(stmt, 4);
        int enc_size;
        p->enc = pddlBase64Encode((const unsigned char *)w,
                                  p->size * sizeof(float), &enc_size, err);
        if (p->enc == NULL){
            infoFree(&info);
            pddl_sqlite3_close_v2(db);
            CTXEND(err);
            ERR_RET(err, -1, "Error while encoding weights, sig: %d,"
                    " layer: %d, id: %d :: ", p->sig, p->layer, p->idx);
        }
    }

    if (sql_st != SQLITE_DONE){
        infoFree(&info);
        pddl_sqlite3_close_v2(db);
        CTXEND(err);
        ERR_RET(err, -1, "Sqlite Error: %s: %s",
                pddl_sqlite3_errstr(sql_st), pddl_sqlite3_errmsg(db));
    }

    if (info.params_size % 2 != 0){
        infoFree(&info);
        pddl_sqlite3_close_v2(db);
        CTXEND(err);
        ERR_RET(err, -1, "Invalid number of weights.");
    }

    pddlSort(info.params, info.params_size, sizeof(struct params),
             cmpParams, NULL);

    pddl_sqlite3_finalize(stmt);
    sql_st = pddl_sqlite3_close_v2(db);
    if (sql_st != SQLITE_OK){
        infoFree(&info);
        CTXEND(err);
        ERR_RET(err, -1, "Sqlite Error: %s: %s",
                pddl_sqlite3_errstr(sql_st), pddl_sqlite3_errmsg(db));
    }

    // Write info to TOML format -- this needs to match the format used in
    // src/asnets.c
    FILE *fout = fopen(output_model, "w");
    if (fout == NULL){
        infoFree(&info);
        CTXEND(err);
        ERR_RET(err, -1, "Could not open file %s", output_model);
    }

    pddlASNetsConfigWrite(&info.cfg, fout);

    fprintf(fout, "\n");
    fprintf(fout, "[asnets.model]\n");
    fprintf(fout, "cpddl_version = \"%s\"\n", info.cpddl_version);
    fprintf(fout, "domain_name = \"%s\"\n", info.domain_name);
    fprintf(fout, "domain_file = \"%s\"\n", info.domain_pddl);
    fprintf(fout, "domain_hash = \"%s\"\n", info.domain_hash);

    fprintf(fout, "\n");
    fprintf(fout, "[asnets.model.train_stats]\n");
    fprintf(fout, "epoch = %d\n", info.epoch);
    fprintf(fout, "num_samples = %d\n", info.num_samples);
    fprintf(fout, "overall_loss = %f\n", info.overall_loss);
    fprintf(fout, "success_rate = %f\n", info.success_rate);

    for (int pi = 0; pi < info.params_size; pi += 2){
        if (info.params[pi].layer != info.params[pi + 1].layer
                || info.params[pi].idx != info.params[pi + 1].idx
                || info.params[pi + 1].sig != info.params[pi].sig + 1
                || (info.params[pi].sig != SIG_ACTION_W
                        && info.params[pi].sig != SIG_PROP_W)){
            infoFree(&info);
            pddl_sqlite3_close_v2(db);
            CTXEND(err);
            ERR_RET(err, -1, "Invalid set of weights.");
        }

        const struct params *p = info.params + pi;
        int bias_size = info.params[pi + 1].size;
        const unsigned char *bias_enc = info.params[pi + 1].enc;

        fprintf(fout, "\n");
        if (p->sig == SIG_ACTION_W){
            fprintf(fout, "[[asnets.model.action_module]]\n");
        }else{
            fprintf(fout, "[[asnets.model.proposition_module]]\n");
        }
        fprintf(fout, "layer = %d\n", p->layer);
        if (p->sig == SIG_ACTION_W){
            fprintf(fout, "action_id = %d\n", p->idx);
        }else{
            fprintf(fout, "pred_id = %d\n", p->idx);
        }
        fprintf(fout, "weights_size = %d\n", p->size);
        fprintf(fout, "weights = \"\"\"\n%s\"\"\"\n", p->enc);
        fprintf(fout, "bias_size = %d\n", bias_size);
        fprintf(fout, "bias = \"\"\"\n%s\"\"\"\n", bias_enc);
    }

    fclose(fout);
    infoFree(&info);

    CTXEND(err);
    return 0;
}
