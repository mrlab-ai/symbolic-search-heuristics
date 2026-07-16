#include "internal.h"
#include "pddl/libs_info.h"
#include "pddl/asnets_dynet.h"
const char * const pddl_dynet_version = NULL;
#define ERROR PANIC("ASNets require the DyNet library; cpddl must be re-compiled with the DyNet support.")
pddl_asnets_model_t *pddlASNetsModelNew(const pddl_asnets_lifted_task_t *task,
                                        const pddl_asnets_model_config_t *cfg,
                                        pddl_err_t *err)
{ ERROR;return NULL;}
void pddlASNetsModelDel(pddl_asnets_model_t *m)
{ ERROR;}
int pddlASNetsModelSetActionWeights(pddl_asnets_model_t *m,
                                    int layer,
                                    int action_id,
                                    const float *w,
                                    int w_size,
                                    pddl_err_t *err)
{ ERROR;return -1;}
int pddlASNetsModelSetActionBias(pddl_asnets_model_t *m,
                                 int layer,
                                 int action_id,
                                 const float *w,
                                 int w_size,
                                 pddl_err_t *err)
{ ERROR;return -1;}
int pddlASNetsModelSetPropWeights(pddl_asnets_model_t *m,
                                  int layer,
                                  int pred_id,
                                  const float *w,
                                  int w_size,
                                  pddl_err_t *err)
{ ERROR;return -1;}
int pddlASNetsModelSetPropBias(pddl_asnets_model_t *m,
                               int layer,
                               int pred_id,
                               const float *w,
                               int w_size,
                               pddl_err_t *err)
{ ERROR;return -1;}
int pddlASNetsModelGetActionWeights(pddl_asnets_model_t *m,
                                    int layer,
                                    int action_id,
                                    float **w,
                                    int *w_size,
                                    pddl_err_t *err)
{ ERROR;return -1;}
int pddlASNetsModelGetActionBias(pddl_asnets_model_t *m,
                                 int layer,
                                 int action_id,
                                 float **w,
                                 int *w_size,
                                 pddl_err_t *err)
{ ERROR;return -1;}
int pddlASNetsModelGetPropWeights(pddl_asnets_model_t *m,
                                  int layer,
                                  int pred_id,
                                  float **w,
                                  int *w_size,
                                  pddl_err_t *err)
{ ERROR;return -1;}
int pddlASNetsModelGetPropBias(pddl_asnets_model_t *m,
                               int layer,
                               int pred_id,
                               float **w,
                               int *w_size,
                               pddl_err_t *err)
{ ERROR;return -1;}
int pddlASNetsModelTrainStep(pddl_asnets_model_t *m,
                             pddl_asnets_train_data_t *data,
                             int minibatch_size,
                             float dropout_rate,
                             float *loss,
                             pddl_err_t *err)
{ ERROR;return -1;}
float pddlASNetsModelOverallLoss(pddl_asnets_model_t *m,
                                 pddl_asnets_train_data_t *data,
                                 float dropout_rate)
{ ERROR;return -1;}
int pddlASNetsModelEvalFDRState(pddl_asnets_model_t *m,
                                const pddl_asnets_ground_task_t *task,
                                const int *in_state,
                                const pddl_fdr_part_state_t *in_goal,
                                const pddl_set_iset_t *in_ldms,
                                const pddl_iarr_t *in_path,
                                pddl_asnets_policy_distribution_t *distr)
{ ERROR;return -1;}
