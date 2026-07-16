/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_HOMOMORPHISM_H__
#define __PDDL_HOMOMORPHISM_H__

#include <pddl/rand.h>
#include <pddl/pddl_struct.h>
#include <pddl/endomorphism.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

#define PDDL_HOMOMORPHISM_TYPES          1
#define PDDL_HOMOMORPHISM_RAND_OBJS      2
#define PDDL_HOMOMORPHISM_RAND_TYPE_OBJS 3
#define PDDL_HOMOMORPHISM_GAIFMAN        4
#define PDDL_HOMOMORPHISM_RPG            5
struct pddl_homomorphism_config {
    int type;
    pddl_bool_t use_endomorphism; /*!< If true, interleave collapsing with
                                       lifted endomorphisms */
    pddl_endomorphism_config_t endomorphism_cfg;
    pddl_iset_t collapse_types; /*!< Set of types to collapse each to a
                                    single object */
    float rm_ratio; /*!< Ratio of objects that should be removed
                         -- for *_RAND_* types */
    uint32_t random_seed;
    pddl_bool_t keep_goal_objs;
    int rpg_max_depth;
};
typedef struct pddl_homomorphism_config pddl_homomorphism_config_t;

#define PDDL_HOMOMORPHISM_CONFIG_INIT { \
        PDDL_HOMOMORPHISM_RAND_OBJS, /* .type */ \
        pddl_false, /* .use_endomorphism */ \
        PDDL_ENDOMORPHISM_CONFIG_INIT, /* .endomorphism_cfg */ \
        PDDL_ISET_INIT, /*. collapse_types */ \
        0.5, /* .rm_ratio */ \
        6899, /* .random_seed */ \
        pddl_true, /* .keep_goal_objs */ \
        2, /* .rpg_max_depth */ \
    }

void pddlHomomorphismConfigLog(const pddl_homomorphism_config_t *cfg,
                               pddl_err_t *err);


/**
 * Computes a homomorphism image of src according to the given config.
 */
int pddlHomomorphism(pddl_t *homo_image,
                     const pddl_t *src,
                     const pddl_homomorphism_config_t *cfg,
                     int *obj_map,
                     pddl_err_t *err);

struct pddl_homomorphic_task {
    pddl_t task; /*!< Homomorphic image of the input task */
    int input_obj_size; /*!< Number of objects in the input task */
    int *obj_map; /*!< Mapping from object IDs of the input task to
                                 object IDs of .task */
    pddl_rand_t rnd; /*!< Random number generator */
};
typedef struct pddl_homomorphic_task pddl_homomorphic_task_t;

/**
 * Creates an identity of in
 */
void pddlHomomorphicTaskInit(pddl_homomorphic_task_t *h, const pddl_t *in);

/**
 * Free allocated memory.
 */
void pddlHomomorphicTaskFree(pddl_homomorphic_task_t *h);

/**
 * (Re-)seed the internal random number generator.
 */
void pddlHomomorphicTaskSeed(pddl_homomorphic_task_t *h, uint32_t seed);


/**
 * Collapse all objects from the given type into a single object.
 */
int pddlHomomorphicTaskCollapseType(pddl_homomorphic_task_t *h,
                                    int type,
                                    pddl_err_t *err);

/**
 * Collapse random pair of objects from the same minimal type.
 * If preserve_goals is set to true, all objects appearing in the goal are
 * mapped to identity.
 */
int pddlHomomorphicTaskCollapseRandomPair(pddl_homomorphic_task_t *h,
                                          int preserve_goals,
                                          pddl_err_t *err);

/**
 * Collapse a pair of objects that are closest to each other in the
 * Gaifman graph of static atoms.
 */
int pddlHomomorphicTaskCollapseGaifman(pddl_homomorphic_task_t *h,
                                       int preserve_goals,
                                       pddl_err_t *err);

/**
 * Collapse pair of objects so that the image of init is within {max_depth}
 * layers of relaxed planning graph.
 */
int pddlHomomorphicTaskCollapseRPG(pddl_homomorphic_task_t *h,
                                   int preserve_goals,
                                   int max_depth,
                                   pddl_err_t *err);

/**
 * Apply relaxed endomorphism on the task.
 */
int pddlHomomorphicTaskApplyRelaxedEndomorphism(
            pddl_homomorphic_task_t *h,
            const pddl_endomorphism_config_t *cfg,
            pddl_err_t *err);


struct pddl_homomorphic_task_method {
    int method;
    int arg_type;
    int arg_preserve_goals;
    int arg_max_depth;
    pddl_endomorphism_config_t arg_endomorphism_cfg;
    pddl_list_t conn;
};
typedef struct pddl_homomorphic_task_method pddl_homomorphic_task_method_t;

struct pddl_homomorphic_task_reduce {
    int target_obj_size;
    pddl_list_t method;
};
typedef struct pddl_homomorphic_task_reduce pddl_homomorphic_task_reduce_t;

void pddlHomomorphicTaskReduceInit(pddl_homomorphic_task_reduce_t *r,
                                   int target_obj_size);
void pddlHomomorphicTaskReduceFree(pddl_homomorphic_task_reduce_t *r);
void pddlHomomorphicTaskReduceAddType(pddl_homomorphic_task_reduce_t *r,
                                      int type);
void pddlHomomorphicTaskReduceAddRandomPair(pddl_homomorphic_task_reduce_t *r,
                                            int preserve_goals);
void pddlHomomorphicTaskReduceAddGaifman(pddl_homomorphic_task_reduce_t *r,
                                         int preserve_goals);
void pddlHomomorphicTaskReduceAddRPG(pddl_homomorphic_task_reduce_t *r,
                                     int preserve_goals,
                                     int max_depth);
void pddlHomomorphicTaskReduceAddRelaxedEndomorphism(
            pddl_homomorphic_task_reduce_t *r,
            const pddl_endomorphism_config_t *cfg);
int pddlHomomorphicTaskReduce(pddl_homomorphic_task_reduce_t *r,
                              pddl_homomorphic_task_t *h,
                              pddl_err_t *err);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_HOMOMORPHISM_H__ */
