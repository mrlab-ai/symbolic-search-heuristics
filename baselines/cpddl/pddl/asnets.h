/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_ASNETS_H__
#define __PDDL_ASNETS_H__

#include <pddl/iarr.h>
#include <pddl/asnets_task.h>
#include <pddl/asnets_policy_distribution.h>
#include <pddl/fdr_state_space.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

typedef struct pddl_asnets pddl_asnets_t;

enum pddl_asnets_teacher {
    /** Internal A* with LM-Cut heuristic */
    PDDL_ASNETS_TEACHER_ASTAR_LMCUT = 0,
    /** Internal A* with potential heuristic optimized for the initial state */
    PDDL_ASNETS_TEACHER_ASTAR_POT_I,
    /** Internal lazy GBFS with FF heuristic */
    PDDL_ASNETS_TEACHER_LAZY_FF,
    /** External planner accepting encoding in Fast Downward's format */
    PDDL_ASNETS_TEACHER_EXTERNAL_FAST_DOWNWARD,
};
typedef enum pddl_asnets_teacher pddl_asnets_teacher_t;

struct pddl_asnets_config {
    /** Domain PDDL file. Set using *SetDomain() */
    char *domain_pddl;
    /** Number of input training problem PDDL files
     *  (i.e., size of .train_problem_pddl[]) */
    int train_problem_pddl_size;
    /** Training problem PDDL files. Set using *AddTrainProblem() */
    char **train_problem_pddl;

    /** Output size of the hidden layers. Default: 16 */
    int hidden_dimension;
    /** Number of the layers. Default: 2 */
    int num_layers;

    /* Training parameters: */
    /** Fixed random seed. Default: 6961 */
    int random_seed;
    /** Weigth decay rate for regularization. Default: 2E-4 */
    float weight_decay;
    /** Dropout rate if set to >0. Default: 0.1 */
    float dropout_rate;
    /** Number of samples in a minibatch. Default: 64 */
    int batch_size;
    /** Double .batch_size every specified number of epochs. Default: 0 */
    int double_batch_size_every_epoch;
    /** Maximum number of epochs used for training. Default: 300 */
    int max_train_epochs;
    /** Number of train cycles within each epoch. Default: 700 */
    int train_steps;
    /** Limit on the number of steps for the policy rollout. Default: 1000 */
    int policy_rollout_limit;
    /** Minimum success rate in .early_termination_epochs to terminate
     *  early. Default: 0.999 */
    float early_termination_success_rate;
    /** Number of epochs in which the success rate must be at higher than
     *  .early_termination_success_rate. Default: 20 */
    int early_termination_epochs;
    /** How many random walks are used to generate training data in
     *  addition to policy rollouts. Default: 0 */
    int train_num_random_walks;
    /** Maximum number of steps taken by the random walks used for
     *  generating addtional training data. The actual number of steps will
     *  be sampled from a binomial distribution between 0 and this number.
     *  Default: 5 */
    int train_random_walk_max_steps;

    /** Use LM-Cut landmarks as part of the input. Default: false */
    pddl_bool_t lmc;

    /** Use operator history as part of the input. Default: false */
    pddl_bool_t op_history;

    /** Time limit in seconds for the teacher to solve the given task.
     *  Default: 10.f */
    float teacher_timeout;
    /** Which teacher will be used. One of PDDL_ASNETS_TEACHER_* */
    pddl_asnets_teacher_t teacher;

    /** External command used as a teacher. This must be specified when
     *  .teacher is set to PDDL_ASNETS_TEACHER_EXTERNAL_FAST_DOWNWARD.
     *
     *  The external command ought to read the problem encoded in the Fast
     *  Downward format from stdin, and write the plan to stdout. The plan
     *  must be in "lisp" format, i.e., (action-name ...), each action on a
     *  separate line, and reading of the output stops on a first line that
     *  does not follow this format. Output containing zero actions is
     *  interpreted as the external planner wasn't able to solve the task.
     *  If the command writes anything to stderr or exits non-zero, the
     *  training terminates with error.
     *
     *  It must be specified the same way as the "argv" parameter of
     *  execv(3) and the first argument must point to the file being
     *  executed. (Don't forget that the last argument must be NULL.).
     *
     *  Default: NULL */
    char **teacher_external_cmd;

    /** If set to non-NULL, pddlASNetsTrain() saves a model to the path
     *  with this prefix every time it finds a model with improved success
     *  rate */
    const char *save_model_prefix;

    /** If true, all tasks are considered to be OSP tasks where all goal
     *  facts are soft goals. When this option is used, it is expected that
     *  each input PDDL problem file is accompanied by an additional file
     *  of the same time with suffix .toml. This file must state the size
     *  of maximal solvable goal set via key 'msgs_size'.
     *
     *  This also affects the encoding of the task in case of using external
     *  teacher,
     *
     *  The success rate is computed as an average ratio of the number of
     *  reached goal facts over the size of the maximal solvable goal set.
     *
     *  Default: False */
    pddl_bool_t osp_all_soft_goals;
};
typedef struct pddl_asnets_config pddl_asnets_config_t;

void pddlASNetsConfigLog(const pddl_asnets_config_t *cfg, pddl_err_t *err);
void pddlASNetsConfigInit(pddl_asnets_config_t *cfg);
void pddlASNetsConfigInitCopy(pddl_asnets_config_t *dst,
                              const pddl_asnets_config_t *src);
int pddlASNetsConfigInitFromFile(pddl_asnets_config_t *cfg,
                                 const char *filename,
                                 pddl_err_t *err);
void pddlASNetsConfigRemoveProblems(pddl_asnets_config_t *cfg);
void pddlASNetsConfigFree(pddl_asnets_config_t *cfg);

void pddlASNetsConfigSetDomain(pddl_asnets_config_t *cfg, const char *fn);
void pddlASNetsConfigAddTrainProblem(pddl_asnets_config_t *cfg,
                                     const char *problem_fn);
void pddlASNetsConfigSetTeacherExternalCmd(pddl_asnets_config_t *cfg,
                                           char * const * argv);
void pddlASNetsConfigWrite(const pddl_asnets_config_t *cfg, FILE *fout);

/**
 * Creates a new instance of ASNets according to the configuration.
 */
pddl_asnets_t *pddlASNetsNew(const pddl_asnets_config_t *cfg, pddl_err_t *err);

/**
 * Free allocated memory.
 */
void pddlASNetsDel(pddl_asnets_t *a);

/**
 * Save ASNets model into the given file.
 */
int pddlASNetsSave(const pddl_asnets_t *a, const char *fn, pddl_err_t *err);

/**
 * Loads an instance (weights) of ASNets.
 * It requires a file containing a model together with configuration (this
 * is normally generated by pddlASNetsSave()).
 * The model must have the same network parameters as the ASNets object {a},
 * otherwise loading ends with an error.
 * Returns 0 on success, -1 otherwise.
 */
int pddlASNetsLoad(pddl_asnets_t *a,
                   const char *model_fn,
                   pddl_err_t *err);

/**
 * Returns config structure used by the ASNets instance.
 */
const pddl_asnets_config_t *pddlASNetsGetConfig(const pddl_asnets_t *a);

/**
 * Load model information from the given file and print it out.
 */
int pddlASNetsPrintModelInfo(const char *fn, pddl_err_t *err);

/**
 * Returns ASNets lifted task.
 */
const pddl_asnets_lifted_task_t *pddlASNetsGetLiftedTask(const pddl_asnets_t *a);

/**
 * Returns number of ground tasks stored in the given object.
 */
int pddlASNetsNumGroundTasks(const pddl_asnets_t *a);

/**
 * Returns ASNets task with the given ID
 */
const pddl_asnets_ground_task_t *
pddlASNetsGetGroundTask(const pddl_asnets_t *a, int id);

/**
 * Run policy on the given state from the given task.
 * If {out_state} is non-NULL, it is filled with the resulting state.
 * If the 'op_history' configuration option is set to false, {path} is
 * ignored, otherwise it is required.
 * Returns ID of the selected operator, or -1 if no operator is applicable.
 */
int pddlASNetsRunPolicy(pddl_asnets_t *a,
                        pddl_asnets_ground_task_t *task,
                        const int *in_state,
                        const pddl_iarr_t *path,
                        int *out_state);

/**
 * Run policy on the given state from the given task and returns a
 * distribution over applicable actions. The function can be repeatedly
 * called on the same pddl_asnets_policy_distribution_t struct -- it will
 * be rewritten every time.
 * If the 'op_history' configuration option is set to false, {path} is
 * ignored, otherwise it is required.
 * Returns 0 on success, -1 otherwise.
 */
int pddlASNetsPolicyDistribution(pddl_asnets_t *a,
                                 pddl_asnets_ground_task_t *task,
                                 const int *in_state,
                                 const pddl_iarr_t *path,
                                 pddl_asnets_policy_distribution_t *dist);

/**
 * Train ASNets according to the configuration it was created with.
 */
int pddlASNetsTrain(pddl_asnets_t *a, pddl_err_t *err);


struct pddl_asnets_policy_rollout {
    /** Intermediate states of the rollout */
    pddl_fdr_state_pool_t states;
    /** Trace of operators */
    pddl_iarr_t ops;
    /** Set to a plan, if found */
    pddl_iarr_t plan;
    /** Number of goal facts satisfied by the rollout.
     *  Applies only to osp policies. */
    int osp_reached_goal_size;
    /** True if plan was found */
    pddl_bool_t found_plan;
};
typedef struct pddl_asnets_policy_rollout pddl_asnets_policy_rollout_t;

void pddlASNetsPolicyRolloutInit(pddl_asnets_policy_rollout_t *r,
                                 const pddl_asnets_ground_task_t *task);
void pddlASNetsPolicyRolloutFree(pddl_asnets_policy_rollout_t *r);

/**
 * Runs policy rollout from the initial state.
 * If {max_number_of_steps} <= 0, then a->cfg.policy_rollout_limit is used.
 */
pddl_bool_t pddlASNetsPolicyRollout(pddl_asnets_t *a,
                                    pddl_asnets_policy_rollout_t *rollout,
                                    pddl_asnets_ground_task_t *task,
                                    int max_number_of_steps,
                                    pddl_err_t *err);

/**
 * Same as pddlASNetsPolicyRollout() except more logs are printed out.
 */
pddl_bool_t pddlASNetsPolicyRolloutVerbose(pddl_asnets_t *a,
                                           pddl_asnets_policy_rollout_t *rollout,
                                           pddl_asnets_ground_task_t *task,
                                           int max_number_of_steps,
                                           pddl_err_t *err);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_ASNETS_H__ */
