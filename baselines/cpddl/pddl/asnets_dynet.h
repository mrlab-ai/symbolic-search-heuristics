/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_ASNETS_DYNET_H__
#define __PDDL_ASNETS_DYNET_H__

#include <pddl/iarr.h>
#include <pddl/asnets_task.h>
#include <pddl/asnets_policy_distribution.h>
#include <pddl/asnets_train_data.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

typedef struct pddl_asnets_model pddl_asnets_model_t;

struct pddl_asnets_model_config {
    int hidden_dimension;
    int num_layers;
    int random_seed;
    float weight_decay;
    pddl_bool_t lmc;
    pddl_bool_t op_history;
};
typedef struct pddl_asnets_model_config pddl_asnets_model_config_t;

/**
 * Create a model for the given task according to the configuration.
 */
pddl_asnets_model_t *pddlASNetsModelNew(const pddl_asnets_lifted_task_t *task,
                                        const pddl_asnets_model_config_t *cfg,
                                        pddl_err_t *err);

/**
 * Free allocated resources.
 */
void pddlASNetsModelDel(pddl_asnets_model_t *m);

/**
 * Checks whether the model has the same parameters (relevant to the
 * structure of the network) as the provided configuration.
 * Returns 0 if the parameters are in-sync, -1 otherwise (in which case an
 * error message is set).
 */
int pddlASNetsModelCheckCompatibleCfg(const pddl_asnets_model_t *model,
                                      const pddl_asnets_config_t *cfg,
                                      pddl_err_t *err);

/**
 * Set weights and biases.
 */
int pddlASNetsModelSetActionWeights(pddl_asnets_model_t *m,
                                    int layer,
                                    int action_id,
                                    const float *w,
                                    int w_size,
                                    pddl_err_t *err);
int pddlASNetsModelSetActionBias(pddl_asnets_model_t *m,
                                 int layer,
                                 int action_id,
                                 const float *w,
                                 int w_size,
                                 pddl_err_t *err);
int pddlASNetsModelSetPropWeights(pddl_asnets_model_t *m,
                                  int layer,
                                  int pred_id,
                                  const float *w,
                                  int w_size,
                                  pddl_err_t *err);
int pddlASNetsModelSetPropBias(pddl_asnets_model_t *m,
                               int layer,
                               int pred_id,
                               const float *w,
                               int w_size,
                               pddl_err_t *err);

/**
 * Get weights and biases.
 * If *w is NULL it will be allocated using PDDL_ALLOC_ARR.
 * If *w is non-NULL then *w_size must be set to the size of the array, and
 * *w will be re-allocated using PDDL_REALLOC_ARR as needed.
 * In any case, *w_size will equal to the number of elements in weights/biases.
 */
int pddlASNetsModelGetActionWeights(pddl_asnets_model_t *m,
                                    int layer,
                                    int action_id,
                                    float **w,
                                    int *w_size,
                                    pddl_err_t *err);
int pddlASNetsModelGetActionBias(pddl_asnets_model_t *m,
                                 int layer,
                                 int action_id,
                                 float **w,
                                 int *w_size,
                                 pddl_err_t *err);
int pddlASNetsModelGetPropWeights(pddl_asnets_model_t *m,
                                  int layer,
                                  int pred_id,
                                  float **w,
                                  int *w_size,
                                  pddl_err_t *err);
int pddlASNetsModelGetPropBias(pddl_asnets_model_t *m,
                               int layer,
                               int pred_id,
                               float **w,
                               int *w_size,
                               pddl_err_t *err);

/**
 * Perform one step of training.
 * Note that this function shuffles training data.
 */
int pddlASNetsModelTrainStep(pddl_asnets_model_t *m,
                             pddl_asnets_train_data_t *data,
                             int minibatch_size,
                             float dropout_rate,
                             float *loss,
                             pddl_err_t *err);

/**
 * Computes loss on over all data.
 */
float pddlASNetsModelOverallLoss(pddl_asnets_model_t *m,
                                 pddl_asnets_train_data_t *data,
                                 float dropout_rate);

/**
 * Evaluate the model on the given task/state/goal.
 * Returns the selected operator ID and fill policy distribution if {dist} is
 * non-NULL.
 */
int pddlASNetsModelEvalFDRState(pddl_asnets_model_t *m,
                                const pddl_asnets_ground_task_t *task,
                                const int *in_state,
                                const pddl_fdr_part_state_t *in_goal,
                                const pddl_set_iset_t *in_ldms,
                                const pddl_iarr_t *in_path,
                                pddl_asnets_policy_distribution_t *distr);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_ASNETS_DYNET_H__ */
