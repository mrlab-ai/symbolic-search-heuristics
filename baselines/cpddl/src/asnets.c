/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "toml.h"
#include "pddl/asnets.h"
#include "pddl/asnets_dynet.h"
#include "pddl/asnets_task.h"
#include "pddl/asnets_train_data.h"
#include "pddl/sha256.h"
#include "pddl/pddl_file.h"
#include "pddl/base64.h"
#include "pddl/search.h"
#include "pddl/subprocess.h"
#include "pddl/strstream.h"
#include "pddl/lm_cut.h"


static const char *teacherName(pddl_asnets_teacher_t teacher)
{
    switch (teacher){
        case PDDL_ASNETS_TEACHER_ASTAR_LMCUT:
            return "astar-lmcut";
        case PDDL_ASNETS_TEACHER_ASTAR_POT_I:
            return "astar-pot-I";
        case PDDL_ASNETS_TEACHER_LAZY_FF:
            return "lazy-ff";
        case PDDL_ASNETS_TEACHER_EXTERNAL_FAST_DOWNWARD:
            return "external-fd";
    }
    return "(unknown)";
}

static int teacherNameToID(const char *name, pddl_asnets_teacher_t *teacher)
{
    if (strcmp(name, "astar-lmcut") == 0){
        *teacher = PDDL_ASNETS_TEACHER_ASTAR_LMCUT;
        return 0;

    }else if (strcmp(name, "astar-pot-I") == 0){
        *teacher = PDDL_ASNETS_TEACHER_ASTAR_POT_I;
        return 0;

    }else if (strcmp(name, "lazy-ff") == 0){
      *teacher = PDDL_ASNETS_TEACHER_LAZY_FF;
      return 0;

    }else if (strcmp(name, "external-fd") == 0){
        *teacher = PDDL_ASNETS_TEACHER_EXTERNAL_FAST_DOWNWARD;
        return 0;
    }
    return -1;
}

void pddlASNetsConfigLog(const pddl_asnets_config_t *cfg, pddl_err_t *err)
{
    LOG(err, "domain_pddl = %s", cfg->domain_pddl);
    LOG_CONFIG_INT(cfg, train_problem_pddl_size, err);
    for (int i = 0; i < cfg->train_problem_pddl_size; ++i)
        LOG(err, "train_problem_pddl[%d] = %s", i, cfg->train_problem_pddl[i]);
    LOG_CONFIG_INT(cfg, hidden_dimension, err);
    LOG_CONFIG_INT(cfg, num_layers, err);
    LOG_CONFIG_INT(cfg, random_seed, err);
    LOG_CONFIG_DBL(cfg, weight_decay, err);
    LOG_CONFIG_DBL(cfg, dropout_rate, err);
    LOG_CONFIG_INT(cfg, batch_size, err);
    LOG_CONFIG_INT(cfg, double_batch_size_every_epoch, err);
    LOG_CONFIG_INT(cfg, max_train_epochs, err);
    LOG_CONFIG_INT(cfg, train_steps, err);
    LOG_CONFIG_INT(cfg, policy_rollout_limit, err);
    LOG_CONFIG_DBL(cfg, early_termination_success_rate, err);
    LOG_CONFIG_INT(cfg, early_termination_epochs, err);
    LOG_CONFIG_INT(cfg, train_num_random_walks, err);
    LOG_CONFIG_INT(cfg, train_random_walk_max_steps, err);
    LOG_CONFIG_BOOL(cfg, lmc, err);
    LOG_CONFIG_BOOL(cfg, op_history, err);
    LOG_CONFIG_DBL(cfg, teacher_timeout, err);
    LOG(err, "teacher = %s", teacherName(cfg->teacher));
    LOG_CONFIG_STR(cfg, save_model_prefix, err);
    LOG_CONFIG_BOOL(cfg, osp_all_soft_goals, err);
}

void pddlASNetsConfigInit(pddl_asnets_config_t *cfg)
{
    ZEROIZE(cfg);
    cfg->hidden_dimension = 16;
    cfg->num_layers = 2;
    cfg->random_seed = 6961;
    cfg->weight_decay = 2e-4f;
    cfg->dropout_rate = 0.1f;
    cfg->batch_size = 64;
    cfg->double_batch_size_every_epoch = 0;
    cfg->max_train_epochs = 300;
    cfg->train_steps = 700;
    cfg->policy_rollout_limit = 1000;
    cfg->early_termination_success_rate = 0.999f;
    cfg->early_termination_epochs = 20;
    cfg->train_num_random_walks = 0;
    cfg->train_random_walk_max_steps = 5;
    cfg->lmc = pddl_false;
    cfg->op_history = pddl_false;
    cfg->teacher_timeout = 10.f;
    cfg->teacher = PDDL_ASNETS_TEACHER_ASTAR_LMCUT;
    cfg->save_model_prefix = NULL;
    cfg->osp_all_soft_goals = pddl_false;
}

void pddlASNetsConfigInitCopy(pddl_asnets_config_t *dst,
                              const pddl_asnets_config_t *src)
{
    *dst = *src;
    if (src->domain_pddl != NULL)
        dst->domain_pddl = STRDUP(src->domain_pddl);

    if (dst->train_problem_pddl_size > 0){
        dst->train_problem_pddl = ALLOC_ARR(char *, dst->train_problem_pddl_size);
        for (int i = 0; i < dst->train_problem_pddl_size; ++i)
            dst->train_problem_pddl[i] = STRDUP(src->train_problem_pddl[i]);
    }

    if (src->teacher_external_cmd != NULL){
        int size = 0;
        while (src->teacher_external_cmd[size] != NULL)
            ++size;
        dst->teacher_external_cmd = ALLOC_ARR(char *, size + 1);
        for (int i = 0; i < size; ++i)
            dst->teacher_external_cmd[i] = STRDUP(src->teacher_external_cmd[i]);
        dst->teacher_external_cmd[size] = NULL;
    }
}

static int cfgLoadProb(pddl_asnets_config_t *cfg,
                       void (*add_fn)(pddl_asnets_config_t *cfg, const char *fn),
                       const char *fn,
                       pddl_err_t *err)
{
    if (pddlIsFile(fn)){
        add_fn(cfg, fn);

    }else{
        int len;
        char **files = pddlListDirPDDLFiles(fn, &len, err);
        if (files == NULL)
            TRACE_RET(err, -1);

        for (int i = 0; i < len; ++i){
            if (strstr(files[i], "domain") != NULL){
                FREE(files[i]);
                continue;
            }
            if (pddlIsFile(files[i]))
                add_fn(cfg, files[i]);
            FREE(files[i]);
        }
        FREE(files);
    }

    return 0;
}

static int cfgLoadProbsArr(pddl_asnets_config_t *cfg,
                           void (*add_fn)(pddl_asnets_config_t *cfg, const char *fn),
                           pddl_toml_t *t,
                           const char *key,
                           const char *root,
                           pddl_err_t *err)
{
    char **problems = NULL;
    int problems_size = 0;
    pddlTomlArrStr(t, key, &problems, &problems_size, pddl_false);
    if (problems_size == 0)
        return 0;

    int ret = 0;
    for (int i = 0; ret == 0 && i < problems_size; ++i){
        char *fn = problems[i];
        if (root != NULL){
            fn = ALLOC_ARR(char, strlen(root) + strlen(problems[i]) + 2);
            sprintf(fn, "%s/%s", root, problems[i]);
        }

        ret = cfgLoadProb(cfg, add_fn, fn, err);

        if (fn != problems[i])
            FREE(fn);
    }

    for (int i = 0; i < problems_size; ++i)
        FREE(problems[i]);
    if (problems != NULL)
        FREE(problems);
    return 0;
}

#define TOML_INT(K) pddlTomlInt(&t, #K, &cfg->K, pddl_false)
#define TOML_FLT(K) pddlTomlFlt(&t, #K, &cfg->K, pddl_false)
#define TOML_BOOL(K) pddlTomlBool(&t, #K, &cfg->K, pddl_false)

int pddlASNetsConfigInitFromFile(pddl_asnets_config_t *cfg,
                                 const char *filename,
                                 pddl_err_t *err)
{
    pddlASNetsConfigInit(cfg);

    pddl_toml_t t;
    if (pddlTomlInitFile(&t, filename, err) != 0)
        TRACE_RET(err, -1);

    pddlTomlPush(&t, "asnets");

    char *root = NULL;
    pddlTomlStr(&t, "root", &root, pddl_false);
    if (root != NULL && strcmp(root, "__PWD__") == 0){
        FREE(root);
        root = pddlDirname(filename);
    }

    char *domain = NULL;
    pddlTomlStr(&t, "domain", &domain, pddl_false);

    if (domain != NULL){
        if (root != NULL){
            char *fn = ALLOC_ARR(char, strlen(root) + strlen(domain) + 2);
            sprintf(fn, "%s/%s", root, domain);
            pddlASNetsConfigSetDomain(cfg, fn);
            FREE(fn);
        }else{
            pddlASNetsConfigSetDomain(cfg, domain);
        }
        FREE(domain);
    }

    if (cfgLoadProbsArr(cfg, pddlASNetsConfigAddTrainProblem, &t,
                        "problems", root, err) != 0
            || cfgLoadProbsArr(cfg, pddlASNetsConfigAddTrainProblem, &t,
                               "train_problems", root, err) != 0){
        if (root != NULL)
            FREE(root);
        TRACE_RET(err, -1);
    }

    if (root != NULL)
        FREE(root);

    TOML_INT(hidden_dimension);
    TOML_INT(num_layers);
    TOML_INT(random_seed);
    TOML_FLT(weight_decay);
    TOML_FLT(dropout_rate);
    TOML_INT(batch_size);
    TOML_INT(double_batch_size_every_epoch);
    TOML_INT(max_train_epochs);
    TOML_INT(train_steps);
    TOML_INT(policy_rollout_limit);
    TOML_FLT(teacher_timeout);
    TOML_FLT(early_termination_success_rate);
    TOML_INT(early_termination_epochs);
    TOML_INT(train_num_random_walks);
    TOML_INT(train_random_walk_max_steps);
    TOML_BOOL(lmc);
    TOML_BOOL(op_history);
    TOML_BOOL(osp_all_soft_goals);

    char *teacher = NULL;
    pddlTomlStr(&t, "teacher", &teacher, pddl_false);
    if (teacher != NULL){
        if (teacherNameToID(teacher, &cfg->teacher) != 0){
            pddlTomlFree(&t);
            ERR_RET(err, -1, "Unkown teacher type \"%s\"", teacher);
        }
        FREE(teacher);
    }

    char **external_cmd = NULL;
    int external_cmd_size = 0;
    if (pddlTomlArrStr(&t, "teacher_external_cmd", &external_cmd,
                       &external_cmd_size, pddl_false) == 0){
        if (external_cmd_size == 0){
            pddlTomlFree(&t);
            ERR_RET(err, -1, "teacher_external_cmd must be non-empty");
        }
        external_cmd = REALLOC_ARR(external_cmd, char *, external_cmd_size + 1);
        external_cmd[external_cmd_size] = NULL;
        pddlASNetsConfigSetTeacherExternalCmd(cfg, external_cmd);
    }
    for (int i = 0; i < external_cmd_size; ++i)
        FREE(external_cmd[i]);
    if (external_cmd != NULL)
        FREE(external_cmd);


    if (cfg->teacher == PDDL_ASNETS_TEACHER_EXTERNAL_FAST_DOWNWARD
            && cfg->teacher_external_cmd == NULL){
        pddlTomlFree(&t);
        ERR_RET(err, -1, "teacher_external_cmd must be defined if the teacher"
                " \"%s\" is used",
                teacherName(PDDL_ASNETS_TEACHER_EXTERNAL_FAST_DOWNWARD));
    }

    if (pddlTomlErr(&t, err)){
        pddlTomlFree(&t);
        TRACE_RET(err, -1);
    }
    pddlTomlFree(&t);
    return 0;
}

void pddlASNetsConfigRemoveProblems(pddl_asnets_config_t *cfg)
{
    for (int i = 0; i < cfg->train_problem_pddl_size; ++i)
        FREE(cfg->train_problem_pddl[i]);
    if (cfg->train_problem_pddl != NULL)
        FREE(cfg->train_problem_pddl);
    cfg->train_problem_pddl_size = 0;
    cfg->train_problem_pddl = NULL;
}

void pddlASNetsConfigFree(pddl_asnets_config_t *cfg)
{
    if (cfg->domain_pddl != NULL)
        FREE(cfg->domain_pddl);
    pddlASNetsConfigRemoveProblems(cfg);

    if (cfg->teacher_external_cmd != NULL){
        for (int i = 0; cfg->teacher_external_cmd[i] != NULL; ++i)
            FREE(cfg->teacher_external_cmd[i]);
        FREE(cfg->teacher_external_cmd);
    }
}

void pddlASNetsConfigSetDomain(pddl_asnets_config_t *cfg, const char *fn)
{
    if (cfg->domain_pddl != NULL)
        FREE(cfg->domain_pddl);
    cfg->domain_pddl = STRDUP(fn);
}

void pddlASNetsConfigAddTrainProblem(pddl_asnets_config_t *cfg, const char *fn)
{
    cfg->train_problem_pddl = REALLOC_ARR(cfg->train_problem_pddl, char *,
                                          cfg->train_problem_pddl_size + 1);
    cfg->train_problem_pddl[cfg->train_problem_pddl_size++] = STRDUP(fn);
}

void pddlASNetsConfigSetTeacherExternalCmd(pddl_asnets_config_t *cfg,
                                           char * const * argv)
{
    int size = 0;
    while (argv[size] != NULL)
        ++size;

    if (cfg->teacher_external_cmd != NULL){
        for (int i = 0; cfg->teacher_external_cmd[i] != NULL; ++i)
            FREE(cfg->teacher_external_cmd[i]);
        FREE(cfg->teacher_external_cmd);
    }
    cfg->teacher_external_cmd = ALLOC_ARR(char *, size + 1);
    for (int i = 0; i < size; ++i)
        cfg->teacher_external_cmd[i] = STRDUP(argv[i]);
    cfg->teacher_external_cmd[size] = NULL;
}

void pddlASNetsConfigWrite(const pddl_asnets_config_t *cfg, FILE *fout)
{
    fprintf(fout, "[asnets]\n");
    if (cfg->domain_pddl == NULL){
        fprintf(fout, "#\n");
        fprintf(fout, "# The following defines the input planning tasks:\n");
        fprintf(fout, "#\n");
        fprintf(fout, "# root = \"__PWD__\"\n");
        fprintf(fout, "# domain = \"domain.pddl\"\n");
        fprintf(fout, "# train_problems = [\"prob1.pddl\", \"prob2.pddl\"]\n");
    }else{
        fprintf(fout, "domain = \"%s\"\n", cfg->domain_pddl);
        fprintf(fout, "train_problems = [\n");
        for (int i = 0; i < cfg->train_problem_pddl_size; ++i)
            fprintf(fout, "    \"%s\",\n", cfg->train_problem_pddl[i]);
        fprintf(fout, "]\n");
    }
    fprintf(fout, "hidden_dimension = %d\n", cfg->hidden_dimension);
    fprintf(fout, "num_layers = %d\n", cfg->num_layers);
    fprintf(fout, "random_seed = %d\n", cfg->random_seed);
    fprintf(fout, "weight_decay = %f\n", cfg->weight_decay);
    fprintf(fout, "dropout_rate = %f\n", cfg->dropout_rate);
    fprintf(fout, "batch_size = %d\n", cfg->batch_size);
    fprintf(fout, "double_batch_size_every_epoch = %d\n",
            cfg->double_batch_size_every_epoch);
    fprintf(fout, "max_train_epochs = %d\n", cfg->max_train_epochs);
    fprintf(fout, "train_steps = %d\n", cfg->train_steps);
    fprintf(fout, "policy_rollout_limit = %d\n", cfg->policy_rollout_limit);
    fprintf(fout, "teacher_timeout = %f\n", cfg->teacher_timeout);
    fprintf(fout, "early_termination_success_rate = %f\n",
            cfg->early_termination_success_rate);
    fprintf(fout, "early_termination_epochs = %d\n",
            cfg->early_termination_epochs);
    fprintf(fout, "train_num_random_walks = %d\n", cfg->train_num_random_walks);
    fprintf(fout, "train_random_walk_max_steps = %d\n",
            cfg->train_random_walk_max_steps);
    fprintf(fout, "lmc = %s\n", F_BOOL(cfg->lmc));
    fprintf(fout, "op_history = %s\n", F_BOOL(cfg->op_history));

    fprintf(fout, "teacher = \"%s\"", teacherName(cfg->teacher));
    fprintf(fout, " # one of \"%s\", \"%s\", \"%s\", \"%s\"\n",
            teacherName(PDDL_ASNETS_TEACHER_ASTAR_LMCUT),
            teacherName(PDDL_ASNETS_TEACHER_ASTAR_POT_I),
            teacherName(PDDL_ASNETS_TEACHER_LAZY_FF),
            teacherName(PDDL_ASNETS_TEACHER_EXTERNAL_FAST_DOWNWARD));

    if (cfg->teacher_external_cmd != NULL){
        fprintf(fout, "teacher_external_cmd = [");
        for (int i = 0; cfg->teacher_external_cmd[i] != NULL; ++i){
            if (i != 0)
                fprintf(fout, ", ");
            fprintf(fout, "\"%s\"", cfg->teacher_external_cmd[i]);
        }
        fprintf(fout, "]\n");
    }else{
        fprintf(fout, "# teacher_external_cmd = [\"/bin/bash\", \"/path/to/script.sh\"]\n");
    }

    fprintf(fout, "osp_all_soft_goals = %s\n", F_BOOL(cfg->osp_all_soft_goals));
}

static int runPolicy(pddl_asnets_model_t *model,
                     const pddl_asnets_ground_task_t *task,
                     const int *in_state,
                     const pddl_fdr_part_state_t *in_goal,
                     const pddl_set_iset_t *in_ldms,
                     const pddl_iarr_t *in_path,
                     int *out_state,
                     pddl_asnets_policy_distribution_t *distr)
{
    int op_id = pddlASNetsModelEvalFDRState(model, task, in_state, in_goal,
                                            in_ldms, in_path, distr);
    if (op_id < 0)
        return -1;

    if (out_state != NULL && op_id >= 0)
        pddlASNetsGroundTaskFDRApplyOp(task, in_state, op_id, out_state);

    return op_id;
}

struct pddl_asnets_train_stats {
    int max_epochs;
    int epoch;
    int max_train_steps;
    int train_step;
    float overall_loss;
    float success_rate;
    int num_samples;
    int consecutive_successful_epochs;
};
typedef struct pddl_asnets_train_stats pddl_asnets_train_stats_t;

struct pddl_asnets {
    pddl_asnets_config_t cfg;
    pddl_asnets_lifted_task_t lifted_task;
    pddl_asnets_ground_task_t *ground_task;
    int ground_task_size;
    pddl_asnets_model_t *model;

    pddl_asnets_train_stats_t train_stats;
};


void pddlASNetsPolicyRolloutInit(pddl_asnets_policy_rollout_t *r,
                                 const pddl_asnets_ground_task_t *task)
{
    ZEROIZE(r);
    pddlFDRStatePoolInit(&r->states, &task->fdr.var, NULL);
    pddlIArrInit(&r->ops);
    pddlIArrInit(&r->plan);
    r->osp_reached_goal_size = 0;
}

void pddlASNetsPolicyRolloutFree(pddl_asnets_policy_rollout_t *r)
{
    pddlFDRStatePoolFree(&r->states);
    pddlIArrFree(&r->ops);
    pddlIArrFree(&r->plan);
}

static pddl_bool_t policyRollout(pddl_asnets_t *a,
                                 pddl_asnets_policy_rollout_t *rollout,
                                 pddl_asnets_ground_task_t *task,
                                 int max_number_of_steps,
                                 pddl_bool_t verbose,
                                 pddl_err_t *err)
{
    if (max_number_of_steps <= 0)
        max_number_of_steps = a->cfg.policy_rollout_limit;

    pddl_bool_t found = pddl_false;
    int *state = ALLOC_ARR(int, task->fdr.var.var_size);
    int *state2 = ALLOC_ARR(int, task->fdr.var.var_size);

    // In case of OSP task, count when was reached the highest number of goals
    int best_reached_goal_size = 0;
    int best_reached_goal_step = -1;

    // Start in the initial state
    pddl_state_id_t state_id = pddlFDRStatePoolInsert(&rollout->states, task->fdr.init);
    for (int step = 0; step < max_number_of_steps; ++step){
        // get the last reached state
        pddlFDRStatePoolGet(&rollout->states, state_id, state);

        if (pddlFDRPartStateIsConsistentWithState(&task->fdr.goal, state)){
            found = pddl_true;
            best_reached_goal_size = task->fdr.goal.fact_size;
            best_reached_goal_step = step;
            break;
        }

        if (a->cfg.osp_all_soft_goals){
            int goal_size = pddlFDRPartStateStateIntersectionSize(&task->fdr.goal, state);
            if (goal_size > best_reached_goal_size){
                best_reached_goal_size = goal_size;
                best_reached_goal_step = step;
            }
        }

        pddl_set_iset_t ldms;
        if (a->cfg.lmc){
            PANIC_IF(!task->use_lmc, "Task with intialized LM-Cut but it is required.");
            pddlSetISetInit(&ldms);
            pddlLMCut(&task->lmc, state, &task->fdr.var, NULL, &ldms);
            //LOG(err, "Found %d landmarks", pddlSetISetSize(&ldms));
        }

        pddl_timer_t policy_eval_timer;
        if (verbose)
            pddlTimerStart(&policy_eval_timer);

        // Apply policy. If we get -1, it means the state is dead-end,
        // because there are no applicable operators
        int op_id = runPolicy(a->model, task, state, &task->fdr.goal,
                              (a->cfg.lmc ? &ldms : NULL),
                              (a->cfg.op_history ? &rollout->ops : NULL),
                              state2, NULL);
        if (verbose){
            pddlTimerStop(&policy_eval_timer);
            LOG(err, "Step %d: policy eval time: %.8fs",
                step, pddlTimerElapsedInSF(&policy_eval_timer));
        }

        if (a->cfg.lmc)
            pddlSetISetFree(&ldms);
        if (op_id < 0)
            break;
        pddlIArrAdd(&rollout->ops, op_id);

        // Insert current state
        pddl_state_id_t prev_state_id = state_id;
        state_id = pddlFDRStatePoolInsert(&rollout->states, state2);
        // If the new state was already in the pool, then we got a cycle
        if (state_id <= prev_state_id)
            break;
    }

    if (a->cfg.osp_all_soft_goals){
        if (best_reached_goal_step >= 0){
            for (int i = 0; i < best_reached_goal_step; ++i)
                pddlIArrAdd(&rollout->plan, pddlIArrGet(&rollout->ops, i));
            rollout->osp_reached_goal_size = best_reached_goal_size;
        }

    }else{
        if (found)
            pddlIArrAppendArr(&rollout->plan, &rollout->ops);
    }
    rollout->found_plan = found;

    FREE(state);
    FREE(state2);
    return found;
}

pddl_bool_t pddlASNetsPolicyRollout(pddl_asnets_t *a,
                                    pddl_asnets_policy_rollout_t *rollout,
                                    pddl_asnets_ground_task_t *task,
                                    int max_number_of_steps,
                                    pddl_err_t *err)
{
    return policyRollout(a, rollout, task, max_number_of_steps, pddl_false, err);
}

pddl_bool_t pddlASNetsPolicyRolloutVerbose(pddl_asnets_t *a,
                                           pddl_asnets_policy_rollout_t *rollout,
                                           pddl_asnets_ground_task_t *task,
                                           int max_number_of_steps,
                                           pddl_err_t *err)
{
    return policyRollout(a, rollout, task, max_number_of_steps, pddl_true, err);
}


static int setNewModel(pddl_asnets_t *a, pddl_err_t *err)
{
    if (a->model != NULL){
        pddlASNetsModelDel(a->model);
        a->model = NULL;
    }

    pddl_asnets_model_config_t model_cfg;
    model_cfg.hidden_dimension = a->cfg.hidden_dimension;
    model_cfg.num_layers = a->cfg.num_layers;
    model_cfg.random_seed = a->cfg.random_seed;
    model_cfg.weight_decay = a->cfg.weight_decay;
    model_cfg.lmc = a->cfg.lmc;
    model_cfg.op_history = a->cfg.op_history;
    a->model = pddlASNetsModelNew(&a->lifted_task, &model_cfg, err);
    if (a->model == NULL)
        TRACE_RET(err, -1);

    ZEROIZE(&a->train_stats);
    a->train_stats.max_epochs = a->cfg.max_train_epochs;
    a->train_stats.max_train_steps = a->cfg.train_steps;
    a->train_stats.success_rate = -1.f;
    a->train_stats.overall_loss = -1.f;

    return 0;
}

pddl_asnets_t *pddlASNetsNew(const pddl_asnets_config_t *cfg, pddl_err_t *err)
{
    CTX(err, "ASNets");
    pddl_asnets_t *a = ZALLOC(pddl_asnets_t);
    pddlASNetsConfigInitCopy(&a->cfg, cfg);
    CTX_NO_TIME(err, "Cfg");
    pddlASNetsConfigLog(&a->cfg, err);
    CTXEND(err);

    int st;
    st = pddlASNetsLiftedTaskInit(&a->lifted_task, cfg->domain_pddl, err);
    if (st < 0){
        CTXEND(err);
        TRACE_RET(err, NULL);
    }

    a->ground_task_size = cfg->train_problem_pddl_size;
    a->ground_task = NULL;
    if (a->ground_task_size > 0){
        a->ground_task = ALLOC_ARR(pddl_asnets_ground_task_t, a->ground_task_size);
        for (int probi = 0; probi < cfg->train_problem_pddl_size; ++probi){
            st = pddlASNetsGroundTaskInit(&a->ground_task[probi],
                                          &a->lifted_task,
                                          cfg->domain_pddl,
                                          cfg->train_problem_pddl[probi],
                                          cfg,
                                          err);
            if (st < 0){
                pddlASNetsLiftedTaskFree(&a->lifted_task);
                for (int i = 0; i < probi; ++i)
                    pddlASNetsGroundTaskFree(&a->ground_task[i]);
                FREE(a->ground_task);
                CTXEND(err);
                TRACE_RET(err, NULL);
            }
        }
    }

    if (setNewModel(a, err) != 0){
        pddlASNetsDel(a);
        CTXEND(err);
        TRACE_RET(err, NULL);
    }

    CTXEND(err);
    return a;
}

void pddlASNetsDel(pddl_asnets_t *a)
{
    pddlASNetsLiftedTaskFree(&a->lifted_task);
    for (int i = 0; i < a->ground_task_size; ++i)
        pddlASNetsGroundTaskFree(&a->ground_task[i]);
    if (a->ground_task != NULL)
        FREE(a->ground_task);

    if (a->model != NULL)
        pddlASNetsModelDel(a->model);
    pddlASNetsConfigFree(&a->cfg);
    FREE(a);
}


static int saveFloatArr(FILE *fout, const char *key,
                        const float *w, int w_size, pddl_err_t *err)
{
    int enc_size;
    unsigned char *enc = pddlBase64Encode((const unsigned char *)w,
                                          w_size * sizeof(float), &enc_size, err);
    if (enc == NULL)
        TRACE_RET(err, -1);

    fprintf(fout, "%s_size = %d\n", key, w_size);
    fprintf(fout, "%s = \"\"\"\n%s\"\"\"\n", key, enc);
    FREE(enc);
    return 0;
}

static int saveActionModule(const pddl_asnets_t *a,
                            FILE *fout,
                            int layer,
                            int action_id,
                            float **w,
                            int *w_alloc,
                            pddl_err_t *err)
{
    fprintf(fout, "\n");
    fprintf(fout, "[[asnets.model.action_module]]\n");
    fprintf(fout, "layer = %d\n", layer);
    fprintf(fout, "action_id = %d\n", action_id);

    int w_size = *w_alloc;
    int st = pddlASNetsModelGetActionWeights(a->model, layer, action_id,
                                             w, &w_size, err);
    if (st != 0)
        TRACE_RET(err, -1);
    *w_alloc = PDDL_MAX(*w_alloc, w_size);

    if (saveFloatArr(fout, "weights", *w, w_size, err) != 0)
        TRACE_RET(err, -1);
    LOG(err, "Saved %d weights for action module, layer: %d, action_id: %d",
        w_size, layer, action_id);

    w_size = *w_alloc;
    st = pddlASNetsModelGetActionBias(a->model, layer, action_id,
                                      w, &w_size, err);
    if (st != 0)
        TRACE_RET(err, -1);
    *w_alloc = PDDL_MAX(*w_alloc, w_size);

    if (saveFloatArr(fout, "bias", *w, w_size, err) != 0)
        TRACE_RET(err, -1);
    LOG(err, "Saved %d bias weights for action module, layer: %d, action_id: %d",
        w_size, layer, action_id);

    return 0;
}

static int savePropModule(const pddl_asnets_t *a,
                          FILE *fout,
                          int layer,
                          int pred_id,
                          float **w,
                          int *w_alloc,
                          pddl_err_t *err)
{
    fprintf(fout, "\n");
    fprintf(fout, "[[asnets.model.proposition_module]]\n");
    fprintf(fout, "layer = %d\n", layer);
    fprintf(fout, "pred_id = %d\n", pred_id);

    int w_size = *w_alloc;
    int st = pddlASNetsModelGetPropWeights(a->model, layer, pred_id,
                                           w, &w_size, err);
    if (st != 0)
        TRACE_RET(err, -1);
    *w_alloc = PDDL_MAX(*w_alloc, w_size);

    if (saveFloatArr(fout, "weights", *w, w_size, err) != 0)
        TRACE_RET(err, -1);
    LOG(err, "Saved %d weights for proposition module, layer: %d, pred_id: %d",
        w_size, layer, pred_id);

    w_size = *w_alloc;
    st = pddlASNetsModelGetPropBias(a->model, layer, pred_id, w, &w_size, err);
    if (st != 0)
        TRACE_RET(err, -1);
    *w_alloc = PDDL_MAX(*w_alloc, w_size);

    if (saveFloatArr(fout, "bias", *w, w_size, err) != 0)
        TRACE_RET(err, -1);
    LOG(err, "Saved %d bias weights for proposition module, layer: %d, pred_id: %d",
        w_size, layer, pred_id);

    return 0;
}

int pddlASNetsSave(const pddl_asnets_t *a, const char *fn, pddl_err_t *err)
{
    CTX(err, "ASNets-Save");
    LOG(err, "Saving model to %s", fn);

    FILE *fout = fopen(fn, "w");
    if (fout == NULL){
        CTXEND(err);
        ERR_RET(err, -1, "Could not open file %s", fn);
    }

    pddlASNetsConfigWrite(&a->cfg, fout);

    fprintf(fout, "\n");
    fprintf(fout, "[asnets.model]\n");
    fprintf(fout, "cpddl_version = \"%s\"\n", pddl_version);
    fprintf(fout, "domain_name = \"%s\"\n", a->lifted_task.pddl.domain_name);
    fprintf(fout, "domain_file = \"%s\"\n", a->lifted_task.pddl.domain_file);

    char domain_hash[PDDL_SHA256_HASH_STR_SIZE];
    pddlASNetsLiftedTaskToSHA256(&a->lifted_task, domain_hash);
    fprintf(fout, "domain_hash = \"%s\"\n", domain_hash);

    fprintf(fout, "\n");
    fprintf(fout, "[asnets.model.train_stats]\n");
    fprintf(fout, "epoch = %d\n", a->train_stats.epoch);
    fprintf(fout, "num_samples = %d\n", a->train_stats.num_samples);
    fprintf(fout, "overall_loss = %f\n", a->train_stats.overall_loss);
    fprintf(fout, "success_rate = %f\n", a->train_stats.success_rate);

    float *w = NULL;
    int w_alloc = 0;
    for (int layer = 0; layer < a->cfg.num_layers; ++layer){
        for (int action_id = 0; action_id < a->lifted_task.action_size; ++action_id){
            int st = saveActionModule(a, fout, layer, action_id, &w, &w_alloc, err);
            if (st != 0){
                fclose(fout);
                CTXEND(err);
                TRACE_RET(err, -1);
            }
        }

        for (int pred_id = 0; pred_id < a->lifted_task.pred_size; ++pred_id){
            int st = savePropModule(a, fout, layer, pred_id, &w, &w_alloc, err);
            if (st != 0){
                fclose(fout);
                CTXEND(err);
                TRACE_RET(err, -1);
            }
        }
    }

    for (int action_id = 0; action_id < a->lifted_task.action_size; ++action_id){
        int st = saveActionModule(a, fout, a->cfg.num_layers, action_id, &w, &w_alloc, err);
        if (st != 0){
            fclose(fout);
            CTXEND(err);
            TRACE_RET(err, -1);
        }
    }

    if (w != NULL)
        FREE(w);

    FILE *fin = fopen(a->lifted_task.pddl.domain_file, "r");
    if (fin != NULL){
        fprintf(fout, "\n");
        fprintf(fout, "[asnets.train_data]\n");
        fprintf(fout, "file = \"%s\"\n", a->lifted_task.pddl.domain_file);
        fprintf(fout, "domain = \"\"\"\n");
        int c;
        while ((c = fgetc(fin)) != EOF){
            if (c == '"')
                fprintf(fout, "\\");
            fprintf(fout, "%c", c);
        }
        fprintf(fout, "\"\"\"\n");
        fclose(fin);

        for (int gi = 0; gi < a->ground_task_size; ++gi){
            fprintf(fout, "\n");
            fprintf(fout, "[[asnets.train_data.problems]]\n");
            fprintf(fout, "file = \"%s\"\n",
                    a->ground_task[gi].pddl.problem_file);
            FILE *fin = fopen(a->ground_task[gi].pddl.problem_file, "r");
            if (fin != NULL){
                fprintf(fout, "problem = \"\"\"\n");
                int c;
                while ((c = fgetc(fin)) != EOF){
                    if (c == '"' || c == '\\')
                        fprintf(fout, "\\");
                    fprintf(fout, "%c", c);
                }
                fprintf(fout, "\"\"\"\n");
                fclose(fin);

            }else{
                fprintf(fout, "problem = \"Could not open file %s\"\n",
                        a->ground_task[gi].pddl.problem_file);
            }
        }
    }

    fclose(fout);
    CTXEND(err);
    return 0;
    return 0;
}

static int loadModule(pddl_asnets_t *a,
                      pddl_toml_t *t,
                      const char *id_name,
                      const char *module_name,
                      int (*set_w)(pddl_asnets_model_t *m,
                                    int layer,
                                    int id,
                                    const float *w,
                                    int w_size,
                                    pddl_err_t *err),
                      int (*set_b)(pddl_asnets_model_t *m,
                                    int layer,
                                    int id,
                                    const float *w,
                                    int w_size,
                                    pddl_err_t *err),
                      pddl_err_t *err)
{
    int layer;
    int id;
    int w_size;
    char *weights_base64 = NULL;
    int b_size;
    char *bias_base64 = NULL;

    pddlTomlInt(t, "layer", &layer, pddl_true);
    pddlTomlInt(t, id_name, &id, pddl_true);
    pddlTomlInt(t, "weights_size", &w_size, pddl_true);
    pddlTomlStr(t, "weights", &weights_base64, pddl_true);
    pddlTomlInt(t, "bias_size", &b_size, pddl_true);
    pddlTomlStr(t, "bias", &bias_base64, pddl_true);

    if (pddlTomlErr(t, err)){
        if (weights_base64 != NULL)
            FREE(weights_base64);
        if (bias_base64 != NULL)
            FREE(bias_base64);
        TRACE_RET(err, -1);
    }

    if (w_size > 0){
        int w_data_size;
        unsigned char *w_data;
        w_data = pddlBase64Decode((const unsigned char *)weights_base64,
                                  strlen(weights_base64), &w_data_size, err);
        FREE(weights_base64);
        if (w_data == NULL){
            if (bias_base64 != NULL)
                FREE(bias_base64);
            ERR_RET(err, -1, "Could not decode weights for the %s module:"
                    " layer: %d, %s: %d", module_name, layer, id_name, id);
        }

        if (w_data_size != sizeof(float) * w_size){
            FREE(w_data);
            if (bias_base64 != NULL)
                FREE(bias_base64);
            ERR_RET(err, -1, "Could not decode weights for the %s module:"
                    " layer: %d, %s: %d. Invalid size of the data block.",
                    module_name, layer, id_name, id);
        }
        const float *w = (const float *)w_data;
        if (set_w(a->model, layer, id, w, w_size, err) != 0){
            FREE(w_data);
            TRACE_PREPEND_RET(err, -1, "Failed to set weights of %s module,"
                              " layer: %d, %s: %d :: ", module_name, layer,
                              id_name, id);
        }
        FREE(w_data);

    }else if (weights_base64 != NULL){
        FREE(weights_base64);
    }

    if (b_size > 0){
        int b_data_size;
        unsigned char *b_data;
        b_data = pddlBase64Decode((const unsigned char *)bias_base64,
                                  strlen(bias_base64), &b_data_size, err);
        FREE(bias_base64);
        if (b_data == NULL){
            ERR_RET(err, -1, "Could not decode bias for the %s module:"
                    " layer: %d, %s: %d", module_name, layer, id_name, id);
        }

        if (b_data_size != sizeof(float) * b_size){
            FREE(b_data);
            ERR_RET(err, -1, "Could not decode bias for the %s module:"
                    " layer: %d, %s: %d. Invalid size of the data block.",
                    module_name, layer, id_name, id);
        }

        const float *b = (const float *)b_data;
        if (set_b(a->model, layer, id, b, b_size, err) != 0){
            FREE(b_data);
            TRACE_PREPEND_RET(err, -1, "Failed to set bias of %s module,"
                              " layer: %d, %s: %d :: ", module_name, layer,
                              id_name, id);
        }

        FREE(b_data);

    }else if (bias_base64 != NULL){
        FREE(bias_base64);
    }

    LOG(err, "Loaded weights and bias for %s module:"
        " layer: %d, %s: %d, weights: %d, bias: %d",
        module_name, layer, id_name, id, w_size, b_size);
    return 0;
}

static int loadActionModule(pddl_asnets_t *a, pddl_toml_t *t, pddl_err_t *err)
{
    return loadModule(a, t, "action_id", "action",
                      pddlASNetsModelSetActionWeights,
                      pddlASNetsModelSetActionBias,
                      err);
}

static int loadPropModule(pddl_asnets_t *a, pddl_toml_t *t, pddl_err_t *err)
{
    return loadModule(a, t, "pred_id", "proposition",
                      pddlASNetsModelSetPropWeights,
                      pddlASNetsModelSetPropBias,
                      err);
}

int pddlASNetsLoad(pddl_asnets_t *a,
                   const char *model_fn,
                   pddl_err_t *err)
{
    CTX(err, "ASNets-Load");
    LOG(err, "Loading model from %s", model_fn);

    pddl_asnets_config_t cfg;
    if (pddlASNetsConfigInitFromFile(&cfg, model_fn, err) != 0){
        CTXEND(err);
        TRACE_RET(err, -1);
    }
    CTX_NO_TIME(err, "Cfg");
    pddlASNetsConfigLog(&cfg, err);
    CTXEND(err);

    if (pddlASNetsModelCheckCompatibleCfg(a->model, &cfg, err) != 0){
        pddlASNetsConfigFree(&cfg);
        TRACE_RET(err, -1);
    }
    pddlASNetsConfigFree(&cfg);

    pddl_toml_t t;
    if (pddlTomlInitFile(&t, model_fn, err) != 0)
        TRACE_RET(err, -1);

    if (pddlTomlPush(&t, "asnets") != 0){
        pddlTomlFree(&t);
        pddlASNetsDel(a);
        CTXEND(err);
        ERR_RET(err, -1, "Invalid input file: Missing section [asnets]");
    }

    if (pddlTomlPush(&t, "model") != 0){
        pddlTomlFree(&t);
        pddlASNetsDel(a);
        CTXEND(err);
        ERR_RET(err, -1, "Invalid input file: Missing section [asnets.model]");
    }

    // Print version of cpddl
    char *cpddl_version;
    if (pddlTomlStr(&t, "cpddl_version", &cpddl_version, pddl_true) == 0){
        LOG(err, "cpddl_version: %s", cpddl_version);
        FREE(cpddl_version);
    }

    // Check hash of the domain file
    char *domain_hash;
    if (pddlTomlStr(&t, "domain_hash", &domain_hash, pddl_true) == 0){
        LOG(err, "domain_hash: %s", domain_hash);
        char cur_domain_hash[PDDL_SHA256_HASH_STR_SIZE];
        pddlASNetsLiftedTaskToSHA256(&a->lifted_task, cur_domain_hash);
        if (strcmp(domain_hash, cur_domain_hash) != 0){
            pddlTomlFree(&t);
            pddlASNetsDel(a);
            CTXEND(err);
            ERR_RET(err, -1, "Domain hash differ: Domain file: %s, ASNets Model: %s."
                    " Aborting because the ASNets model is likely not"
                    " compatible with the given PDDL domain file.",
                    cur_domain_hash, domain_hash);
        }
        FREE(domain_hash);
    }

    if (pddlTomlErr(&t, err)){
        pddlTomlFree(&t);
        pddlASNetsDel(a);
        CTXEND(err);
        TRACE_RET(err, -1);
    }

    if (setNewModel(a, err) != 0){
        pddlTomlFree(&t);
        pddlASNetsDel(a);
        CTXEND(err);
        TRACE_RET(err, -1);
    }

    int num_action_modules = pddlTomlArrSize(&t, "action_module");
    int need_action_modules = a->lifted_task.action_size * (a->cfg.num_layers + 1);
    if (num_action_modules >= 0 && num_action_modules != need_action_modules){
        pddlTomlFree(&t);
        pddlASNetsDel(a);
        CTXEND(err);
        ERR_RET(err, -1, "Invalid number of action modules. Need %d, found %d.",
                need_action_modules, num_action_modules);
    }

    for (int i = 0; i < num_action_modules; ++i){
        if (pddlTomlPushFromArr(&t, "action_module", i) == 0){
            if (loadActionModule(a, &t, err) != 0){
                pddlTomlFree(&t);
                pddlASNetsDel(a);
                CTXEND(err);
                TRACE_RET(err, -1);
            }
            pddlTomlPop(&t);
        }
    }

    int num_prop_modules = pddlTomlArrSize(&t, "proposition_module");
    int need_prop_modules = a->lifted_task.pred_size * a->cfg.num_layers;
    if (num_prop_modules >= 0 && num_prop_modules != need_prop_modules){
        pddlTomlFree(&t);
        pddlASNetsDel(a);
        CTXEND(err);
        ERR_RET(err, -1, "Invalid number of proposition modules. Need %d, found %d.",
                need_prop_modules, num_prop_modules);
    }

    for (int i = 0; i < num_prop_modules; ++i){
        if (pddlTomlPushFromArr(&t, "proposition_module", i) == 0){
            if (loadPropModule(a, &t, err) != 0){
                pddlTomlFree(&t);
                pddlASNetsDel(a);
                CTXEND(err);
                TRACE_RET(err, -1);
            }
            pddlTomlPop(&t);
        }
    }

    if (pddlTomlErr(&t, err)){
        pddlTomlFree(&t);
        pddlASNetsDel(a);
        CTXEND(err);
        TRACE_RET(err, -1);
    }

    pddlTomlFree(&t);

    CTXEND(err);
    return 0;
}

const pddl_asnets_config_t *pddlASNetsGetConfig(const pddl_asnets_t *a)
{
    return &a->cfg;
}

const pddl_asnets_lifted_task_t *pddlASNetsGetLiftedTask(const pddl_asnets_t *a)
{
    return &a->lifted_task;
}

int pddlASNetsNumGroundTasks(const pddl_asnets_t *a)
{
    return a->ground_task_size;
}

const pddl_asnets_ground_task_t *
pddlASNetsGetGroundTask(const pddl_asnets_t *a, int id)
{
    if (id < 0 || id >= a->ground_task_size)
        return NULL;
    return a->ground_task + id;
}

int pddlASNetsRunPolicy(pddl_asnets_t *a,
                        pddl_asnets_ground_task_t *task,
                        const int *in_state,
                        const pddl_iarr_t *path,
                        int *out_state)
{
    pddl_set_iset_t ldms;
    if (a->cfg.lmc){
        PANIC_IF(!task->use_lmc, "Task without intialized LM-Cut but it is required.");
        pddlSetISetInit(&ldms);
        pddlLMCut(&task->lmc, in_state, &task->fdr.var, NULL, &ldms);
    }
    int ret = runPolicy(a->model, task, in_state, &task->fdr.goal,
                        (a->cfg.lmc ? &ldms : NULL),
                        (a->cfg.op_history ? path : NULL),
                        out_state, NULL);
    if (a->cfg.lmc)
        pddlSetISetFree(&ldms);
    return ret;
}

int pddlASNetsPolicyDistribution(pddl_asnets_t *a,
                                 pddl_asnets_ground_task_t *task,
                                 const int *in_state,
                                 const pddl_iarr_t *path,
                                 pddl_asnets_policy_distribution_t *distr)
{
    pddl_set_iset_t ldms;
    if (a->cfg.lmc){
        PANIC_IF(!task->use_lmc, "Task without intialized LM-Cut but it is required.");
        pddlSetISetInit(&ldms);
        pddlLMCut(&task->lmc, in_state, &task->fdr.var, NULL, &ldms);
    }

    runPolicy(a->model, task, in_state, &task->fdr.goal,
              (a->cfg.lmc ? &ldms : NULL), (a->cfg.op_history ? path : NULL),
              NULL, distr);

    if (a->cfg.lmc)
        pddlSetISetFree(&ldms);
    return 0;
}



static int trainStep(pddl_asnets_t *a,
                     int epoch,
                     int train_step,
                     pddl_asnets_train_data_t *data,
                     pddl_err_t *err)
{
    float loss;

    a->train_stats.train_step = train_step + 1;

    int ret = pddlASNetsModelTrainStep(a->model, data, a->cfg.batch_size,
                                       a->cfg.dropout_rate, &loss, err);
    if (ret < 0)
        TRACE_RET(err, -1);

    LOG(err, "epoch %d/%d, step: %d/%d, loss: %.3f, succ: %.2f, samples: %d,"
        " succ epochs: %d"
        " | minibatch loss: %f, size: %d",
        a->train_stats.epoch, a->train_stats.max_epochs,
        a->train_stats.train_step, a->train_stats.max_train_steps,
        a->train_stats.overall_loss, a->train_stats.success_rate,
        a->train_stats.num_samples,
        a->train_stats.consecutive_successful_epochs,
        loss, a->cfg.batch_size);

    return 0;
}

static void dataAddPlan(pddl_asnets_train_data_t *td,
                        int ground_task_id,
                        pddl_asnets_ground_task_t *gt,
                        const pddl_asnets_config_t *cfg,
                        const pddl_fdr_t *fdr,
                        const int *init_state,
                        const pddl_iarr_t *plan)
{
    int state_size = fdr->var.var_size;
    int state[state_size];
    memcpy(state, init_state, sizeof(int) * state_size);

    PDDL_IARR(path);
    int op_id;
    PDDL_IARR_FOR_EACH(plan, op_id){
        pddl_set_iset_t ldms;
        if (cfg->lmc){
            pddlSetISetInit(&ldms);
            pddlLMCut(&gt->lmc, state, &fdr->var, NULL, &ldms);
        }

        pddlASNetsTrainDataAdd(td, ground_task_id, state, state_size, op_id,
                               (cfg->lmc ? &ldms : NULL),
                               (cfg->op_history ? &path : NULL));
        const pddl_fdr_op_t *op = fdr->op.op[op_id];
        pddlFDROpApplyOnStateInPlace(op, state_size, state);
        if (cfg->lmc)
            pddlSetISetFree(&ldms);

        if (cfg->op_history)
            pddlIArrAdd(&path, op_id);
    }
    pddlIArrFree(&path);
}

static int rolloutSearch(pddl_asnets_train_data_t *td,
                         int ground_task_id,
                         pddl_asnets_ground_task_t *gt,
                         const pddl_asnets_config_t *cfg,
                         const int *state,
                         const pddl_fdr_t *_fdr,
                         const pddl_heur_config_t *heur_cfg,
                         pddl_search_alg_t search_algo,
                         float max_time,
                         pddl_err_t *err)
{
    pddl_timer_t timer;
    pddlTimerStart(&timer);

    pddl_fdr_t fdr;
    pddlFDRInitShallowCopyWithDifferentInitState(&fdr, _fdr, state);

    pddl_heur_t *heur = pddlHeur(heur_cfg, err);
    if (heur == NULL){
        pddlFDRFree(&fdr);
        TRACE_RET(err, -1);
    }

    pddl_search_config_t search_cfg = PDDL_SEARCH_CONFIG_INIT;
    search_cfg.fdr = &fdr;
    search_cfg.alg = search_algo;
    search_cfg.heur = heur;
    pddl_search_t *search = pddlSearchNew(&search_cfg, err);
    if (search == NULL){
        pddlFDRFree(&fdr);
        pddlHeurDel(heur);
        TRACE_RET(err, -1);
    }

    int st = pddlSearchInitStep(search);
    while (st == PDDL_SEARCH_CONT){
        pddlTimerStop(&timer);
        if (pddlTimerElapsedInSF(&timer) > max_time){
            st = PDDL_SEARCH_ABORT;
            break;
        }

        st = pddlSearchStep(search);
    }

    if (st == PDDL_SEARCH_FOUND){
        LOG(err, "Plan found");
        pddl_plan_t plan;
        pddlPlanInit(&plan);
        if (pddlSearchExtractPlan(search, &plan) == 0)
            dataAddPlan(td, ground_task_id, gt, cfg, &fdr, state, &plan.op);
        pddlPlanFree(&plan);

    }else{
        pddlASNetsTrainDataAddFail(td, ground_task_id, state, fdr.var.var_size);
        if (st == PDDL_SEARCH_ABORT)
            LOG(err, "Search reached time-out");
        LOG(err, "Plan not found");
    }

    pddlSearchDel(search);
    pddlHeurDel(heur);
    pddlFDRFree(&fdr);
    return 0;
}

static void stringToPlan(const char *str,
                         const pddl_fdr_t *fdr,
                         pddl_iarr_t *plan)
{
    const char *cur = str;

    while (strncmp(cur, "(id-", 4) == 0){
        if (cur[4] < '0' || cur[4] > '9')
            return;
        int op_id = atoi(cur + 4);
        pddlIArrAdd(plan, op_id);

        for (; *cur != '\x0' && *cur != '\n'; ++cur);
        if (*cur == '\n')
            ++cur;
    }
}

static int rolloutExternalFD(pddl_asnets_train_data_t *td,
                             int ground_task_id,
                             pddl_asnets_ground_task_t *gt,
                             const pddl_asnets_config_t *cfg,
                             const int *state,
                             const pddl_fdr_t *_fdr,
                             char * const *cmd,
                             pddl_bool_t osp_all_soft_goals,
                             pddl_err_t *err)
{
    PANIC_IF(cmd == NULL, "External command is not specified.");
    pddl_fdr_t fdr;
    pddlFDRInitShallowCopyWithDifferentInitState(&fdr, _fdr, state);

    // Write FDR task in FD format into fdrout buffer
    size_t fdrout_size = 0;
    char *fdrout_buf = NULL;
    FILE *fdrout = pddl_strstream(&fdrout_buf, &fdrout_size);
    if (fdrout == NULL){
        ERR_RET(err, -1, "Could not create a buffer for FDR task");
    }

    pddl_fdr_write_config_t wcfg = PDDL_FDR_WRITE_CONFIG_INIT;
    wcfg.fout = fdrout;
    wcfg.fd = pddl_true;
    wcfg.encode_op_ids = pddl_true;
    wcfg.osp_all_soft_goals = osp_all_soft_goals;
    pddlFDRWrite(&fdr, &wcfg);
    fclose(fdrout);

    // Run external planner. Write FDR task to stdin.
    int out_size;
    char *out;
    int oerr_size;
    char *oerr;
    pddl_exec_status_t status;
    int ret = pddlExecvpLimits(cmd, &status, fdrout_buf, fdrout_size, &out,
                               &out_size, &oerr, &oerr_size, -1, -1, err);

    // Free the input buffer
    if (fdrout_buf != NULL)
        FREE(fdrout_buf);

    // Check if running the subprocess failed -- this shouldn't fail
    if (ret != 0){
        if (oerr != NULL)
            FREE(oerr);
        if (out != NULL)
            FREE(out);
        pddlFDRFree(&fdr);
        TRACE_RET(err, -1);
    }

    // If we got something from stderr, then terminate -- this is a bug in
    // the external planner
    if (oerr_size > 0){
        char *outline = oerr;
        while (*outline != '\x0'){
            char *end = outline;
            for (; *end != '\x0' && *end != '\n'; ++end);
            if (*end == '\n'){
                *end = '\x0';
                ++end;
            }
            LOG(err, "Error output: %s", outline);
            outline = end;
        }
    }
    if (oerr != NULL)
        FREE(oerr);


    if (status.exit_status != 0 || status.signaled || oerr_size > 0){
        // Something went wrong with the external planner -- terminate with
        // an error
        if (out != NULL)
            FREE(out);
        pddlFDRFree(&fdr);
        ERR_RET(err, -1, "Calling external teacher failed.");

    }else{
        // Extract plan from from stdout of the external planner
        PDDL_IARR(plan);
        if (out_size > 0)
            stringToPlan(out, &fdr, &plan);

        if (pddlIArrSize(&plan) == 0){
            pddlASNetsTrainDataAddFail(td, ground_task_id, state, fdr.var.var_size);
            LOG(err, "Plan not found");

        }else{
            dataAddPlan(td, ground_task_id, gt, cfg, &fdr, state, &plan);
        }
        pddlIArrFree(&plan);
    }

    if (out != NULL)
        FREE(out);
    pddlFDRFree(&fdr);
    return 0;
}

static int teacherRollout(pddl_asnets_t *a,
                          pddl_asnets_train_data_t *td,
                          int ground_task_id,
                          const int *state,
                          const pddl_fdr_t *fdr,
                          const pddl_asnets_config_t *cfg,
                          pddl_err_t *err)
{
    CTX(err, "Teacher Rollout");
    LOG(err, "start num samples: %d", td->sample_size);
    if (pddlASNetsTrainDataExists(td, ground_task_id, state, NULL, fdr->var.var_size)){
        LOG(err, "State already in the data pool -- skipping.");
        CTXEND(err);
        return 1;

    }else if (pddlASNetsTrainDataExistsFail(td, ground_task_id, state, fdr->var.var_size)){
        LOG(err, "State already seen and could not be solved -- skipping.");
        CTXEND(err);
        return 1;
    }

    int ret = 0;

    if (cfg->teacher == PDDL_ASNETS_TEACHER_EXTERNAL_FAST_DOWNWARD){
        ret = rolloutExternalFD(td, ground_task_id,
                                a->ground_task + ground_task_id,
                                &a->cfg, state, fdr,
                                cfg->teacher_external_cmd,
                                cfg->osp_all_soft_goals, err);

    }else{
        pddl_heur_config_t heur_cfg = PDDL_HEUR_CONFIG_INIT;
        pddl_search_alg_t search_alg = PDDL_SEARCH_ASTAR;

        switch (cfg->teacher){
            case PDDL_ASNETS_TEACHER_ASTAR_LMCUT:
                heur_cfg.fdr = fdr;
                heur_cfg.heur = PDDL_HEUR_LM_CUT;
                search_alg = PDDL_SEARCH_ASTAR;
                break;

            case PDDL_ASNETS_TEACHER_ASTAR_POT_I:
                heur_cfg.fdr = fdr;
                heur_cfg.heur = PDDL_HEUR_POT;
                pddlHPotConfigInit(&heur_cfg.pot);
                heur_cfg.pot.disambiguation = pddl_false;
                heur_cfg.pot.type = PDDL_HPOT_OPT_STATE_TYPE;

                search_alg = PDDL_SEARCH_ASTAR;
                break;

            case PDDL_ASNETS_TEACHER_LAZY_FF:
                heur_cfg.fdr = fdr;
                heur_cfg.heur = PDDL_HEUR_HFF;
                search_alg = PDDL_SEARCH_LAZY;
                break;

            case PDDL_ASNETS_TEACHER_EXTERNAL_FAST_DOWNWARD:
                // Ignore this one -- it is handled above
                PANIC("Unexpected call to external teacher. This is a bug!");
                break;
        }

        ret = rolloutSearch(td, ground_task_id,
                            a->ground_task + ground_task_id,
                            &a->cfg, state, fdr, &heur_cfg, search_alg,
                            cfg->teacher_timeout, err);
    }


    LOG(err, "num samples: %d", td->sample_size);
    CTXEND(err);
    return ret;
}

static int trainExploration(pddl_asnets_t *a,
                            int epoch,
                            int ground_task_id,
                            pddl_asnets_train_data_t *data,
                            pddl_err_t *err)
{
    pddl_asnets_ground_task_t *task = a->ground_task + ground_task_id;
    CTX(err, "Exploration Phase");

    LOG(err, "Task: %s", task->pddl.problem_file);
    int *state = ALLOC_ARR(int, task->fdr.var.var_size);

    pddl_asnets_policy_rollout_t rollout;
    pddlASNetsPolicyRolloutInit(&rollout, task);
    pddl_bool_t found_plan = pddlASNetsPolicyRollout(a, &rollout, task, -1, err);
    LOG(err, "Policy rollout: %d states, found_plan: %s",
        rollout.states.num_states, F_BOOL(found_plan));

    // Extend training data with teacher rollouts
    for (pddl_state_id_t state_id = 0; state_id < rollout.states.num_states; ++state_id){
        pddlFDRStatePoolGet(&rollout.states, state_id, state);
        int ret = teacherRollout(a, data, ground_task_id, state, &task->fdr,
                                 &a->cfg, err);
        if (ret < 0){
            FREE(state);
            pddlASNetsPolicyRolloutFree(&rollout);
            CTXEND(err);
            TRACE_RET(err, -1);
        }
    }
    pddlASNetsPolicyRolloutFree(&rollout);

    // Add sample states from random walks
    LOG(err, "Using random walks to generate %d more starting states"
        " for teacher rollouts.", a->cfg.train_num_random_walks);
    for (int i = 0; i < a->cfg.train_num_random_walks; ++i){
        CTX(err, "Random walk %d", i);
        int steps = pddlRandomWalkSampleState(&task->random_walk, task->fdr.init,
                                              a->cfg.train_random_walk_max_steps,
                                              state);
        LOG(err, "Steps: %d", steps);
        if (steps > 0){
            int ret = teacherRollout(a, data, ground_task_id, state,
                                     &task->fdr, &a->cfg, err);
            if (ret < 0){
                FREE(state);
                CTXEND(err);
                CTXEND(err);
                TRACE_RET(err, -1);
            }
        }
        CTXEND(err);
    }

    FREE(state);
    CTXEND(err);
    return 0;
}


static float successRate(pddl_asnets_t *a, pddl_asnets_train_data_t *td, pddl_err_t *err)
{
    int num_solved = 0;
    float osp_sum_score = 0.;
    for (int task_id = 0; task_id < a->ground_task_size; ++task_id){
        pddl_asnets_ground_task_t *task = a->ground_task + task_id;

        pddl_asnets_policy_rollout_t rollout;
        pddlASNetsPolicyRolloutInit(&rollout, task);
        if (pddlASNetsPolicyRollout(a, &rollout, task, -1, err))
            num_solved += 1;

        if (a->cfg.osp_all_soft_goals){
            PANIC_IF(task->osp_msgs_size_for_init == 0,
                     "MSGS size is zero, therefore the task %s is unsolvable"
                     " and useless for us.", task->pddl.problem_file);
            osp_sum_score += rollout.osp_reached_goal_size
                                / (float)task->osp_msgs_size_for_init;
        }

        pddlASNetsPolicyRolloutFree(&rollout);
    }

    if (a->cfg.osp_all_soft_goals)
        return osp_sum_score / (float)a->ground_task_size;
    return num_solved / (float)a->ground_task_size;
}

static int trainEpoch(pddl_asnets_t *a,
                      int epoch,
                      pddl_asnets_train_data_t *data,
                      pddl_err_t *err)
{
    LOG(err, "epoch: %d/%d", epoch, a->cfg.max_train_epochs);
    a->train_stats.epoch = epoch + 1;

    // Exploration phase
    for (int ground_task = 0; ground_task < a->ground_task_size; ++ground_task){
        int ret;
        if ((ret = trainExploration(a, epoch, ground_task, data, err)) != 0){
            if (ret < 0)
                TRACE_RET(err, ret);
            return ret;
        }
    }
    a->train_stats.num_samples = data->sample_size;

    // Training phase
    int num_steps = a->cfg.train_steps;
    //num_steps = PDDL_MIN(num_steps, data->sample_size / a->cfg.batch_size);
    //num_steps = PDDL_MAX(num_steps, 1);
    LOG(err, "num training steps: %d", num_steps);
    for (int train_step = 0; train_step < num_steps; ++train_step){
        int ret;
        if ((ret = trainStep(a, epoch, train_step, data, err)) != 0){
            if (ret < 0)
                TRACE_RET(err, ret);
            return ret;
        }
    }

    CTX(err, "Success Rate");
    a->train_stats.success_rate = successRate(a, data, err);
    LOG(err, "Success rate: %f", a->train_stats.success_rate);
    CTXEND(err);
    CTX(err, "Overall Loss");
    a->train_stats.overall_loss
            = pddlASNetsModelOverallLoss(a->model, data, a->cfg.dropout_rate);
    LOG(err, "Overall loss: %f", a->train_stats.overall_loss);
    CTXEND(err);
    LOG(err, "Train samples: %d", a->train_stats.num_samples);
    LOG(err, "epoch %d/%d, step: %d/%d, loss: %.3f, succ: %.2f, samples: %d,"
        " succ epochs: %d",
        a->train_stats.epoch, a->train_stats.max_epochs,
        a->train_stats.train_step, a->train_stats.max_train_steps,
        a->train_stats.overall_loss, a->train_stats.success_rate,
        a->train_stats.num_samples,
        a->train_stats.consecutive_successful_epochs);
    return 0;
}

int pddlASNetsTrain(pddl_asnets_t *a, pddl_err_t *err)
{
    CTX(err, "ASNets-Train");
    if (a->ground_task_size <= 0){
        ERR(err, "At least one training problem file is required.");
        CTXEND(err);
        return -1;
    }

    pddl_asnets_train_data_t data;
    pddlASNetsTrainDataInit(&data, a->ground_task, a->ground_task_size,
                            a->cfg.random_seed);

    a->train_stats.success_rate = successRate(a, &data, err);

    for (int epoch = 0; epoch < a->cfg.max_train_epochs; ++epoch){
        if (a->cfg.double_batch_size_every_epoch > 0
                && epoch > 0
                && epoch % a->cfg.double_batch_size_every_epoch == 0){
            a->cfg.batch_size *= 2;
        }

        int ret;
        if ((ret = trainEpoch(a, epoch, &data, err)) != 0){
            pddlASNetsTrainDataFree(&data);
            CTXEND(err);
            if (ret < 0)
                TRACE_RET(err, ret);
            return ret;
        }

        if (a->cfg.save_model_prefix != NULL){
            char fn[4096];
            sprintf(fn, "%s-%05d-%.2f-%.03f.policy",
                    a->cfg.save_model_prefix,
                    epoch,
                    a->train_stats.success_rate,
                    a->train_stats.overall_loss);
            LOG(err, "Saving model to %s (epoch: %d, success rate: %.2f, loss: %.3f)",
                fn, epoch, a->train_stats.success_rate, a->train_stats.overall_loss);
            if (pddlASNetsSave(a, fn, err) != 0){
                CTXEND(err);
                TRACE_RET(err, -1);
            }
        }
        if (a->train_stats.success_rate >= a->cfg.early_termination_success_rate){
            a->train_stats.consecutive_successful_epochs += 1;
        }else{
            a->train_stats.consecutive_successful_epochs = 0;
        }

        LOG(err, "Consecutive successful epochs: %d",
            a->train_stats.consecutive_successful_epochs);
        if (a->train_stats.consecutive_successful_epochs
                >= a->cfg.early_termination_epochs){
            LOG(err, "Reached %d/%d consecutive successful epochs.",
                a->train_stats.consecutive_successful_epochs,
                a->cfg.early_termination_epochs);
            LOG(err, "Terminating training.");
            break;
        }
    }
    LOG(err, "epoch %d/%d, step: %d/%d, loss: %.3f, succ: %.2f, samples: %d,"
        " succ epochs: %d",
        a->train_stats.epoch, a->train_stats.max_epochs,
        a->train_stats.train_step, a->train_stats.max_train_steps,
        a->train_stats.overall_loss, a->train_stats.success_rate,
        a->train_stats.num_samples,
        a->train_stats.consecutive_successful_epochs);
    pddlASNetsTrainDataFree(&data);
    CTXEND(err);
    return 0;
}
