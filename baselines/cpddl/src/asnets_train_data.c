/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/asnets_train_data.h"
#include "pddl/hfunc.h"

struct pddl_asnets_train_data_sample {
    pddl_htable_key_t hash;
    pddl_list_t htable;

    int ground_task_id;
    int fdr_state_size;
    int *fdr_state;
    int selected_op_id;
    pddl_set_iset_t ldms;
    pddl_iarr_t path;
};

static pddl_htable_key_t htableHash(const pddl_list_t *key, void *_)
{
    const pddl_asnets_train_data_sample_t *sample;
    sample = PDDL_LIST_ENTRY(key, pddl_asnets_train_data_sample_t, htable);
    return sample->hash;
}

static int htableEq(const pddl_list_t *key1, const pddl_list_t *key2, void *_)
{
    const pddl_asnets_train_data_sample_t *sample1, *sample2;
    sample1 = PDDL_LIST_ENTRY(key1, pddl_asnets_train_data_sample_t, htable);
    sample2 = PDDL_LIST_ENTRY(key2, pddl_asnets_train_data_sample_t, htable);
    int cmp = sample1->ground_task_id - sample2->ground_task_id;
    if (cmp == 0){
        ASSERT(sample1->fdr_state_size == sample2->fdr_state_size);
        cmp = memcmp(sample1->fdr_state, sample2->fdr_state,
                     sizeof(int) * sample1->fdr_state_size);
    }
    if (cmp == 0)
        return pddlIArrEq(&sample1->path, &sample2->path);
    return 0;
}

static pddl_htable_key_t sampleHash(const pddl_asnets_train_data_sample_t *s)
{
    uint64_t key = s->ground_task_id;
    key <<= 32;
    uint64_t fkey =  pddlFastHash_64(s->fdr_state,
                                     sizeof(int) * s->fdr_state_size,
                                     3929);
    key |= fkey;

    if (pddlIArrSize(&s->path) > 0){
        uint64_t fkey =  pddlFastHash_64(s->path.arr,
                                         sizeof(int) * pddlIArrSize(&s->path),
                                         3929);
        key |= fkey;
    }

    return key;
}

static pddl_asnets_train_data_sample_t *sampleNew(int ground_task_id,
                                                  const int *state,
                                                  int state_size,
                                                  int selected_op_id)
{
    pddl_asnets_train_data_sample_t *sample = ZALLOC(pddl_asnets_train_data_sample_t);
    sample->ground_task_id = ground_task_id;
    sample->fdr_state_size = state_size;
    sample->fdr_state = ZALLOC_ARR(int, sample->fdr_state_size);
    memcpy(sample->fdr_state, state, sizeof(int) * state_size);
    sample->selected_op_id = selected_op_id;
    pddlSetISetInit(&sample->ldms);
    pddlIArrInit(&sample->path);
    sample->hash = sampleHash(sample);
    return sample;
}

static void sampleDel(pddl_asnets_train_data_sample_t *sample)
{
    if (sample->fdr_state != NULL)
        FREE(sample->fdr_state);
    pddlSetISetFree(&sample->ldms);
    pddlIArrFree(&sample->path);
    FREE(sample);
}

void pddlASNetsTrainDataInit(pddl_asnets_train_data_t *td,
                             const pddl_asnets_ground_task_t *task,
                             int task_size,
                             int random_seed)
{
    ZEROIZE(td);
    td->htable = pddlHTableNew(htableHash, htableEq, NULL);
    td->fail_cache = pddlHTableNew(htableHash, htableEq, NULL);

    td->task_size = task_size;
    td->task = ALLOC_ARR(const pddl_asnets_ground_task_t *, td->task_size);
    for (int ti = 0; ti < td->task_size; ++ti)
        td->task[ti] = task + ti;

    pddlRandInit(&td->rnd, random_seed);
}

void pddlASNetsTrainDataFree(pddl_asnets_train_data_t *td)
{
    pddlHTableDel(td->htable);

    pddl_list_t list;
    pddlListInit(&list);
    pddlHTableGather(td->fail_cache, &list);
    while (!pddlListEmpty(&list)){
        pddl_list_t *item = pddlListNext(&list);
        pddlListDel(item);
        pddl_asnets_train_data_sample_t *s;
        s = PDDL_LIST_ENTRY(item, pddl_asnets_train_data_sample_t, htable);
        sampleDel(s);
    }
    pddlHTableDel(td->fail_cache);

    for (int i = 0; i < td->sample_size; ++i)
        sampleDel(td->sample[i]);
    if (td->sample != NULL)
        FREE(td->sample);

    if (td->task != NULL)
        FREE(td->task);

    pddlRandFree(&td->rnd);
}

int pddlASNetsTrainDataGetSample(const pddl_asnets_train_data_t *td,
                                 int sample_id,
                                 int *ground_task_id,
                                 int *selected_op_id,
                                 pddl_iset_t *strips_state,
                                 pddl_iset_t *applicable_ops,
                                 pddl_iset_t *strips_goal,
                                 const pddl_set_iset_t **ldms,
                                 const pddl_iarr_t **path)
{
    const pddl_asnets_train_data_sample_t *sample = td->sample[sample_id];
    if (ground_task_id != NULL)
        *ground_task_id = sample->ground_task_id;
    if (selected_op_id != NULL)
        *selected_op_id = sample->selected_op_id;
    if (strips_state != NULL){
        pddlISetEmpty(strips_state);
        pddlASNetsGroundTaskFDRStateToStrips(td->task[sample->ground_task_id],
                                             sample->fdr_state, strips_state);
    }
    if (applicable_ops != NULL){
        pddlISetEmpty(applicable_ops);
        pddlASNetsGroundTaskFDRApplicableOps(td->task[sample->ground_task_id],
                                             sample->fdr_state, applicable_ops);
    }
    if (strips_goal != NULL){
        pddlISetEmpty(strips_goal);
        // TODO: We might want to allow different goals for the given sample
        pddlASNetsGroundTaskFDRPartStateToStrips(td->task[sample->ground_task_id],
                                                 &td->task[sample->ground_task_id]->fdr.goal,
                                                 strips_goal);
    }

    if (ldms != NULL)
        *ldms = &sample->ldms;

    if (path != NULL)
        *path = &sample->path;

    return 0;
}

void pddlASNetsTrainDataAdd(pddl_asnets_train_data_t *td,
                            int ground_task_id,
                            const int *state,
                            int state_size,
                            int selected_op_id,
                            const pddl_set_iset_t *lmc_landmarks,
                            const pddl_iarr_t *path)
{
    pddl_asnets_train_data_sample_t *sample;
    sample = sampleNew(ground_task_id, state, state_size, selected_op_id);

    if (pddlHTableInsertUnique(td->htable, &sample->htable) == NULL){
        if (lmc_landmarks != NULL)
            pddlSetISetUnion(&sample->ldms, lmc_landmarks);
        if (path != NULL)
            pddlIArrAppendArr(&sample->path, path);

        ARR_MAKE_SPACE(td->sample, pddl_asnets_train_data_sample_t *,
                       td->sample_size, td->sample_alloc, 2);
        td->sample[td->sample_size++] = sample;
    }else{
        sampleDel(sample);
    }
}

void pddlASNetsTrainDataAddFail(pddl_asnets_train_data_t *td,
                                int ground_task_id,
                                const int *state,
                                int state_size)
{
    pddl_asnets_train_data_sample_t *sample;
    sample = sampleNew(ground_task_id, state, state_size, -1);

    if (pddlHTableInsertUnique(td->fail_cache, &sample->htable) != NULL)
        sampleDel(sample);
}

pddl_bool_t pddlASNetsTrainDataExists(const pddl_asnets_train_data_t *td,
                                      int ground_task_id,
                                      const int *state,
                                      const pddl_iarr_t *path,
                                      int state_size)
{
    pddl_asnets_train_data_sample_t *sample;
    sample = alloca(sizeof(pddl_asnets_train_data_sample_t));
    ZEROIZE(sample);
    sample->fdr_state_size = state_size;
    sample->ground_task_id = ground_task_id;
    sample->fdr_state = alloca(sizeof(int) * state_size);
    memcpy(sample->fdr_state, state, sizeof(int) * state_size);
    if (path != NULL)
        sample->path = *path;
    sample->hash = sampleHash(sample);

    if (pddlHTableFind(td->htable, &sample->htable) == NULL){
        return pddl_false;
    }else{
        return pddl_true;
    }
}

pddl_bool_t pddlASNetsTrainDataExistsFail(const pddl_asnets_train_data_t *td,
                                          int ground_task_id,
                                          const int *state,
                                          int state_size)
{
    pddl_asnets_train_data_sample_t *sample;
    sample = alloca(sizeof(pddl_asnets_train_data_sample_t));
    ZEROIZE(sample);
    sample->fdr_state_size = state_size;
    sample->ground_task_id = ground_task_id;
    sample->fdr_state = alloca(sizeof(int) * state_size);
    memcpy(sample->fdr_state, state, sizeof(int) * state_size);
    sample->hash = sampleHash(sample);

    if (pddlHTableFind(td->fail_cache, &sample->htable) == NULL){
        return 0;
    }else{
        return 1;
    }
}

void pddlASNetsTrainDataShuffle(pddl_asnets_train_data_t *td)
{
    for (int dst = td->sample_size - 1; dst > 0; --dst){
        int src = pddlRand(&td->rnd, 0, dst + 1);
        ASSERT(src <= dst && src >= 0);
        if (src != dst){
            pddl_asnets_train_data_sample_t *tmp;
            PDDL_SWAP(td->sample[src], td->sample[dst], tmp);
        }
    }
}


