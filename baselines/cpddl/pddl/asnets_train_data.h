/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_ASNETS_TRAIN_DATA_H__
#define __PDDL_ASNETS_TRAIN_DATA_H__

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

#include <pddl/htable.h>
#include <pddl/set.h>
#include <pddl/asnets.h>
#include <pddl/rand.h>

typedef struct pddl_asnets_train_data_sample pddl_asnets_train_data_sample_t;

struct pddl_asnets_train_data {
    pddl_asnets_train_data_sample_t **sample;
    int sample_size;
    int sample_alloc;

    const pddl_asnets_ground_task_t **task;
    int task_size;

    pddl_htable_t *htable;
    pddl_htable_t *fail_cache;

    pddl_rand_t rnd;
};
typedef struct pddl_asnets_train_data pddl_asnets_train_data_t;

void pddlASNetsTrainDataInit(pddl_asnets_train_data_t *td,
                             const pddl_asnets_ground_task_t *task,
                             int task_size,
                             int random_seed);
void pddlASNetsTrainDataFree(pddl_asnets_train_data_t *td);

int pddlASNetsTrainDataGetSample(const pddl_asnets_train_data_t *td,
                                 int sample_id,
                                 int *ground_task_id,
                                 int *selected_op_id,
                                 pddl_iset_t *strips_state,
                                 pddl_iset_t *applicable_ops,
                                 pddl_iset_t *strips_goal,
                                 const pddl_set_iset_t **ldms,
                                 const pddl_iarr_t **path);

void pddlASNetsTrainDataAdd(pddl_asnets_train_data_t *td,
                            int ground_task_id,
                            const int *state,
                            int state_size,
                            int selected_op_id,
                            const pddl_set_iset_t *lmc_landmarks,
                            const pddl_iarr_t *path);

void pddlASNetsTrainDataAddFail(pddl_asnets_train_data_t *td,
                                int ground_task_id,
                                const int *state,
                                int state_size);

pddl_bool_t pddlASNetsTrainDataExists(const pddl_asnets_train_data_t *td,
                                      int ground_task_id,
                                      const int *state,
                                      const pddl_iarr_t *path,
                                      int state_size);

pddl_bool_t pddlASNetsTrainDataExistsFail(const pddl_asnets_train_data_t *td,
                                          int ground_task_id,
                                          const int *state,
                                          int state_size);

void pddlASNetsTrainDataShuffle(pddl_asnets_train_data_t *td);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_ASNETS_TRAIN_DATA_H__ */
