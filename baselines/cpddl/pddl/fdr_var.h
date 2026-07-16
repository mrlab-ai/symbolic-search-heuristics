/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_FDR_VAR_H__
#define __PDDL_FDR_VAR_H__

#include <pddl/strips.h>
#include <pddl/mgroup.h>
#include <pddl/mutex_pair.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * Algorithms that can be used for the construction of variables
 */
enum pddl_fdr_vars_alg {
    /** Prioritize mutex groups having higher number of facts not covered
     *  by any other mutex group. */
    PDDL_FDR_VARS_ALG_ESSENTIAL_FIRST = 0,
    /** Prioritize larger mutex groups. */
    PDDL_FDR_VARS_ALG_LARGEST_FIRST,
    /** Prioritize larger mutex groups, and encode each fact multiple times
     *  if it appears in multiple mutex groups, i.e., every input mutex
     *  group is exactly represented by one variable. */
    PDDL_FDR_VARS_ALG_LARGEST_FIRST_MULTI,
};

struct pddl_fdr_vars_config {
    /** Which algorithm should be used for constructing variables */
    enum pddl_fdr_vars_alg alg;
    /** The information about which fact is a negation of which fact is
     *  ignored (i.e., .neg_of property of facts is ignored) */
    pddl_bool_t ignore_negated_facts;
};
typedef struct pddl_fdr_vars_config pddl_fdr_vars_config_t;

#define PDDL_FDR_VARS_CONFIG_INIT \
    { \
        PDDL_FDR_VARS_ALG_LARGEST_FIRST, /* .alg */ \
        pddl_false, /* .ignore_negated_facts */ \
    }

void pddlFDRVarsConfigLog(const pddl_fdr_vars_config_t *cfg, pddl_err_t *err);

struct pddl_fdr_val {
    char *name;
    /** ID of the variable this value belongs to */
    int var_id;
    /** Value ID within the variable */
    int val_id;
    /** Global unique ID of this value */
    int global_id;
    /** ID of the STRIPS fact this value was created from */
    int strips_id;
    /** True if this value corresponds to a conjunction in P^C compilation. */
    pddl_bool_t is_conjunction;
};
typedef struct pddl_fdr_val pddl_fdr_val_t;

void pddlFDRValInit(pddl_fdr_val_t *val);
void pddlFDRValFree(pddl_fdr_val_t *val);


struct pddl_fdr_var {
    int var_id; /*!< ID of the variable */
    pddl_fdr_val_t *val; /*!< List of values */
    int val_size; /*!< Number of values, i.e., range of the variable */
    int val_none_of_those; /*!< ID of the "none of those" value or -1 --
                                this value is created during translation from
                                STRIPS */
    pddl_bool_t is_black; /*!< True if the variable is painted black in a
                               red-black problem */
};
typedef struct pddl_fdr_var pddl_fdr_var_t;

void pddlFDRVarInit(pddl_fdr_var_t *var);
void pddlFDRVarFree(pddl_fdr_var_t *var);

struct pddl_fdr_vars {
    pddl_fdr_vars_config_t cfg;
    /** List of variables */
    pddl_fdr_var_t *var;
    /** Number of variables */
    int var_size;

    /** Number of global IDs */
    int global_id_size;
    /** Mapping from global ID to FDR value */
    pddl_fdr_val_t **global_id_to_val;
    int strips_id_size;
    /** If the variables were created from STRIPS, this maps STRIPS IDs to
     *  global IDs of variable values */
    pddl_iset_t *strips_id_to_val;
};
typedef struct pddl_fdr_vars pddl_fdr_vars_t;

/**
 * Initialize the set of variables from the strips representation given a
 * set of mutex groups and mutex pairs.
 */
int pddlFDRVarsInitFromStrips(pddl_fdr_vars_t *vars,
                              const pddl_strips_t *strips,
                              const pddl_mgroups_t *mg,
                              const pddl_mutex_pairs_t *mutex,
                              const pddl_fdr_vars_config_t *cfg);

/**
 * Initialize dst as a deep copy of src.
 */
void pddlFDRVarsInitCopy(pddl_fdr_vars_t *dst, const pddl_fdr_vars_t *src);

struct pddl_fdr_vars_remap {
    int var_size;
    /** Mapping from old variable/value pair to new value, i.e., for every
     *  old variable-value pair (V, v), remap[V][v] points to the
     *  corresponding pddl_fdr_val_t in the current fdr task. */
    const pddl_fdr_val_t ***remap;
    /** Mapping from old global IDs to new IDs */
    int *remap_global_id;
};
typedef struct pddl_fdr_vars_remap pddl_fdr_vars_remap_t;

void pddlFDRVarsRemapFree(pddl_fdr_vars_remap_t *remap);

/**
 * Remove specified facts and create the remapping structure.
 */
void pddlFDRVarsDelFacts(pddl_fdr_vars_t *vars,
                         const pddl_iset_t *del_facts,
                         pddl_fdr_vars_remap_t *remap);

/**
 * Free allocated memory.
 */
void pddlFDRVarsFree(pddl_fdr_vars_t *vars);

/**
 * Adds a new value with the given name to the specified variable.
 */
pddl_fdr_val_t *pddlFDRVarsAddVal(pddl_fdr_vars_t *vars,
                                  int var,
                                  const char *name);

/**
 * TODO
 */
void pddlFDRVarsRemap(pddl_fdr_vars_t *vars, const int *remap);

/**
 * Adds a new variable with the given size of the domain.
 */
pddl_fdr_var_t *pddlFDRVarsAdd(pddl_fdr_vars_t *vars, int val_size);

void pddlFDRVarsPrintDebug(const pddl_fdr_vars_t *vars, FILE *fout);
void pddlFDRVarsPrintTable(const pddl_fdr_vars_t *vars,
                           int linesize,
                           FILE *fout,
                           pddl_err_t *err);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_FDR_VAR_H__ */
