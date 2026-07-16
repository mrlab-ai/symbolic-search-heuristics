/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_STRUCT_H__
#define __PDDL_STRUCT_H__

#include <pddl/config.h>
#include <pddl/require_flags.h>
#include <pddl/type.h>
#include <pddl/obj.h>
#include <pddl/pred.h>
#include <pddl/fact.h>
#include <pddl/action.h>
#include <pddl/lifted_mgroup.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_config {
    /** If true, the parser of PDDL files will be strict and emit errors
     *  instead of warnings. */
    pddl_bool_t pedantic;
    /** Force ADL to requirements before parsing starts */
    pddl_bool_t force_adl;
    /** Normalize the task right after parsing */
    pddl_bool_t normalize;
    /** When normalizing, compile away negative conditions of dynamic
     *  (non-static) preconditions in actions' preconditions and goal.
     *  This takes effect only if .normalize is true. */
    pddl_bool_t normalize_compile_away_dynamic_neg_cond;
    /** When normalizing, compile away only the negative conditions
     *  appearing in the goal condition. */
    pddl_bool_t normalize_compile_away_only_goal_neg_cond;
    /** As .normalize_compile_away_dynamic_neg_cond, but removes all
     *  negative conditions including of static predicates. */
    pddl_bool_t normalize_compile_away_all_neg_cond;
    /** When compiling away negative conditions, the initial state is
     *  extended with NOT-* facts. If this is set to true, then only the
     *  facts that are relevant to preconditions or the goal are added.
     *  Otherwise, all possible facts are generated.
     *  This takes effect only if .normalize and one of
     *  normalize_compile_away_*_neg_cond are true. */
    pddl_bool_t normalize_compile_away_neg_cond_only_relevant_facts;
    /** Remove types without any objects */
    pddl_bool_t remove_empty_types;
    /** Compile away conditional effects */
    pddl_bool_t compile_away_cond_eff;
    /** Compile away disjunctive goals by introducing auxiliary actions */
    pddl_bool_t compile_away_disjunctive_goals;
    /** Enforce the task to have unit-cost actions */
    pddl_bool_t enforce_unit_cost;
    /** If set to true, all actions should be kept in the task even after
     *  normalization */
    pddl_bool_t keep_all_actions;
};
typedef struct pddl_config pddl_config_t;

#define PDDL_CONFIG_INIT \
    { \
        pddl_false, /* .pedantic */ \
        pddl_true, /* .force_adl */ \
        pddl_true, /* .normalize */ \
        pddl_true, /* .normalize_compile_away_dynamic_neg_cond */ \
        pddl_false, /* .normalize_compile_away_only_goal_neg_cond */ \
        pddl_false, /* .normalize_compile_away_all_neg_cond */ \
        pddl_true, /* .normalize_compile_away_neg_cond_only_relevant_facts */ \
        pddl_true, /* .remove_empty_types */ \
        pddl_false, /* .compile_away_cond_eff */ \
        pddl_false, /* .compile_disjunctive_goals */ \
        pddl_false, /* .enforce_unit_cost */ \
        pddl_false, /* .keep_all_actions */ \
    }

void pddlConfigLog(const pddl_config_t *cfg, pddl_err_t *err);

struct pddl {
    /** Configuration */
    pddl_config_t cfg;
    /** True if the pddl struct was built only from the domain file */
    pddl_bool_t only_domain;
    /** Path to the PDDL domain file */
    char *domain_file;
    /** Path to the PDDL problem file */
    char *problem_file;
    /** Domain name from the domain file */
    char *domain_name;
    /** Problem name from the problem file */
    char *problem_name;
    /** :requirements flags */
    pddl_require_flags_t require;
    /** List of types */
    pddl_types_t type;
    /** List of objects -- both :constants and :objects together */
    pddl_objs_t obj;
    /** List of predicates */
    pddl_preds_t pred;
    /** List of functions */
    pddl_preds_t func;
    /** The initial state */
    pddl_fm_and_t *init;
    /** The goal condition */
    pddl_fm_t *goal;
    /** List of actions */
    pddl_actions_t action;
    /** True if metric is defined in the problem file (i.e., (minimize ...)) */
    pddl_bool_t metric;
    /** In case .metric is true: numeric expression that should be minimized */
    pddl_fm_num_exp_t *minimize;
    /** True if the task was normalized */
    pddl_bool_t normalized;
};

/**
 * Initialize pddl structure from the domain/problem PDDL files.
 */
int pddlInit(pddl_t *pddl, const char *domain_fn, const char *problem_fn,
             const pddl_config_t *cfg, pddl_err_t *err);

/**
 * Creates a copy of the pddl structure.
 */
void pddlInitCopy(pddl_t *dst, const pddl_t *src);

/**
 * Frees allocated memory.
 */
void pddlFree(pddl_t *pddl);

pddl_t *pddlNew(const char *domain_fn, const char *problem_fn,
                const pddl_config_t *cfg, pddl_err_t *err);
void pddlDel(pddl_t *pddl);

/**
 * Returns true if the task has an action with a conditional effect.
 */
pddl_bool_t pddlHasCondEff(const pddl_t *pddl);

/**
 * Normalize pddl, i.e., make preconditions and effects CNF
 */
void pddlNormalize(pddl_t *pddl, pddl_err_t *err);

/**
 * Generate pddl without conditional effects.
 */
void pddlCompileAwayCondEff(pddl_t *pddl);

/**
 * Generate pddl without conditional effects unless the conditional effects
 * that have only static predicates in its preconditions.
 * This is enough for grounding.
 */
void pddlCompileAwayNonStaticCondEff(pddl_t *pddl);

/**
 * Compiles away negative preconditions and goals.
 * If only_dynamic is true, the static negative conditions are kept intact.
 * If only_relevant_facts_in_init is true, then the initial state is
 * extended only with facts that are relevant for actions or goal, i.e.,
 * not all possible instances of facts are generated.
 */
int pddlCompileAwayNegativeConditions(pddl_t *pddl,
                                      pddl_bool_t only_dynamic,
                                      pddl_bool_t only_goal,
                                      pddl_bool_t only_relevant_facts_in_init,
                                      pddl_err_t *err);

/**
 * Compiles away equality predicate.
 * Returns 0 if nothing was changed, 1 if equality predicate was actually
 * removed.
 */
int pddlCompileAwayEqPred(pddl_t *pddl);

/**
 * Compile away disjunctive goals of the form (or (xxx) (yyy)) by adding
 * new actions (xxx) -> (GOAL) and (yyy) -> (GOAL) and changin goal to the
 * single fact (GOAL). Plus it makes sure that once a goal is achieved by
 * one of the auxiliary action, no other action is applicable.
 */
int pddlCompileAwayDisjunctiveGoalsWithAuxActions(pddl_t *pddl, pddl_err_t *err);

/**
 * Returns true if the pddl has and uses equality predicate.
 */
pddl_bool_t pddlHasEqPred(const pddl_t *pddl);

/**
 * Returns maximal number of parameters of all predicates and functions.
 */
// TODO: rename to *MaxArity
int pddlPredFuncMaxParamSize(const pddl_t *pddl);

/**
 * Adds one new type per object if necessary.
 */
void pddlAddObjectTypes(pddl_t *pddl);

/**
 * Remove specified objects from the planning task.
 */
void pddlRemoveObjs(pddl_t *pddl, const pddl_iset_t *rm_objs, pddl_err_t *err);

/**
 * Same as pddlRemoveObjs() except a remap array must be provided.
 */
void pddlRemoveObjsGetRemap(pddl_t *pddl,
                            const pddl_iset_t *rm_obj,
                            int *remap,
                            pddl_err_t *err);

/**
 * Remap object IDs.
 */
void pddlRemapObjs(pddl_t *pddl, const int *remap);

/**
 * Remove empty types and all related predicates and actions from the task
 */
void pddlRemoveEmptyTypes(pddl_t *pddl, pddl_err_t *err);

/**
 * Remove specified predicates and functions.
 */
void pddlRemovePredsFuncs(pddl_t *pddl,
                          const pddl_iset_t *rm_pred,
                          const pddl_iset_t *rm_func,
                          pddl_err_t *err);

/**
 * Remove assign and increase atoms to enforce the task to be unit cost
 */
void pddlEnforceUnitCost(pddl_t *pddl, pddl_err_t *err);

/**
 * Resets .read, .write, .in_init and .in_goal flags of all predicates and
 * functionss
 * This needs to be called after any action, init, or goal are modified.
 */
void pddlResetPredFuncFlags(pddl_t *pddl);

/**
 * If necessary, it renames actions so that there are no two actions with
 * the same name.
 */
void pddlEnforceUniquelyNamedActions(pddl_t *pddl);

/**
 * Set requirement flags to be minimal set of requirements to cover
 * everything appearing in the given PDDL task.
 */
void pddlSetMinimalRequirements(pddl_t *pddl);

/**
 * Prints PDDL domain file.
 */
void pddlPrintPDDLDomain(const pddl_t *pddl, FILE *fout);

/**
 * Prints PDDL problem file.
 */
void pddlPrintPDDLProblem(const pddl_t *pddl, FILE *fout);

void pddlPrintDebug(const pddl_t *pddl, FILE *fout);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_STRUCT_H__ */
