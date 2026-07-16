/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef OPTIONS_H
#define OPTIONS_H

#include <pddl/pddl.h>
#include "process_strips.h"

enum {
    LIFTED_PLAN_NONE = 0,
    LIFTED_PLAN_ASTAR,
    LIFTED_PLAN_GBFS,
    LIFTED_PLAN_LAZY
};

enum {
    LIFTED_PLAN_SUCC_GEN_DL = 0,
    LIFTED_PLAN_SUCC_GEN_SQL,
};

enum {
    LIFTED_PLAN_HEUR_BLIND = 0,
    LIFTED_PLAN_HEUR_HMAX,
    LIFTED_PLAN_HEUR_HADD,
    LIFTED_PLAN_HEUR_HFF_MAX,
    LIFTED_PLAN_HEUR_HFF_ADD,
    LIFTED_PLAN_HEUR_HOMO_LMC,
    LIFTED_PLAN_HEUR_HOMO_FF,
    LIFTED_PLAN_HEUR_GAIF_LB,
    LIFTED_PLAN_HEUR_GAIF_MAX,
    LIFTED_PLAN_HEUR_GAIF_ADD,
};

enum {
    MG_NONE = 0,
    MG_FAM,
    MG_H2
};

enum {
    GROUND_PLAN_NONE = 0,
    GROUND_PLAN_ASTAR,
    GROUND_PLAN_GBFS,
    GROUND_PLAN_LAZY
};

enum {
    GROUND_PLAN_HEUR_BLIND = 0,
    GROUND_PLAN_HEUR_LMC,
    GROUND_PLAN_HEUR_MAX,
    GROUND_PLAN_HEUR_ADD,
    GROUND_PLAN_HEUR_FF,
    GROUND_PLAN_HEUR_FLOW,
    GROUND_PLAN_HEUR_POT,
    GROUND_PLAN_HEUR_POT_CONJ,
    GROUND_PLAN_HEUR_POT_CONJ_EXACT,
};

enum {
    SYMBA_NONE = 0,
    SYMBA_FW,
    SYMBA_BW,
    SYMBA_FWBW,
};

enum {
    COMPILE_AWAY_NEG_COND_DYNAMIC = 0,
    COMPILE_AWAY_NEG_COND_ALL,
    COMPILE_AWAY_NEG_COND_GOAL,
    COMPILE_AWAY_NEG_COND_NONE,
};

struct options {
    pddl_bool_t help;
    pddl_bool_t version;
    int max_mem;
    char *log_out;
    char *prop_out;
    pddl_files_t files;
    char *link_cplex;
    char *link_gurobi;
    pddl_bool_t list_lp_solvers;
    pddl_bool_t list_cp_solvers;

    struct {
        pddl_bool_t force_adl;
        pddl_bool_t pedantic;
        pddl_bool_t remove_empty_types;
        pddl_bool_t compile_away_cond_eff;
        pddl_bool_t compile_away_disjunctive_goals;
        int compile_away_neg_cond;
        pddl_bool_t compile_in_lmg;
        pddl_bool_t compile_in_lmg_mutex;
        pddl_bool_t compile_in_lmg_dead_end;
        pddl_bool_t enforce_unit_cost;
        char *domain_out;
        char *problem_out;
        pddl_bool_t stop;
    } pddl;

    struct {
        int max_candidates;
        int max_mgroups;
        pddl_bool_t fd;
        pddl_bool_t fd_monotonicity;
        pddl_bool_t enable;
        char *out;
        char *fd_monotonicity_out;
        pddl_bool_t stop;
    } lmg;

    struct {
        pddl_bool_t enable;
        pddl_bool_t ignore_costs;
    } lifted_endomorph;

    struct {
        int search;
        int succ_gen;
        int heur;
        pddl_homomorphism_config_t homomorph_cfg;
        int random_seed;
        int homomorph_samples;
        float homomorph_sampling_max_time;
        char *plan_out;
    } lifted_planner;

    struct {
        pddl_ground_config_t cfg;

        pddl_bool_t mgroup;
        pddl_bool_t mgroup_remove_subsets;
        char *mgroup_out;
    } ground;

    struct {
        pddl_bool_t compile_away_cond_eff;
        pddl_process_strips_t process;
        char *py_out;
        char *fam_dump;
        char *h2_dump;
        char *h3_dump;
        pddl_bool_t stop;
    } strips;

    struct {
        int method;
        pddl_bool_t fam_lmg;
        pddl_bool_t fam_maximal;
        float fam_time_limit;
        int fam_limit;
        pddl_bool_t remove_subsets;
        pddl_bool_t cover_number;
        char *out;
    } mg;

    struct {
        pddl_bool_t enable;
        pddl_pot_conj_find_config_t cfg;
        pddl_hpot_config_t pot_cfg;
    } pot_conj_find;

    struct {
        pddl_bool_t enable;
        pddl_pot_conj_exact_find_config_t cfg;
        pddl_hpot_config_t pot_cfg;
    } pot_conj_exact_find;

    char *extend_strips_conj_file;

    struct {
        pddl_bool_t enable;
        pddl_red_black_fdr_config_t cfg;
        char *out;
    } rb_fdr;

    struct {
        pddl_fdr_config_t cfg;
        pddl_bool_t order_vars_cg;
        char *out;
        pddl_bool_t pretty_print_vars;
        pddl_bool_t pretty_print_cg;
        pddl_bool_t pot;
        pddl_hpot_config_t pot_cfg;
        pddl_bool_t to_tnf;
        pddl_bool_t to_tnf_multiply;
    } fdr;

    char *extend_fdr_conj_file;

    struct {
        int search;
        int heur;
        int heur_op_mutex;
        int heur_op_mutex_ts;
        int heur_op_mutex_op_fact;
        int heur_op_mutex_hm_op;
        char *plan_out;
        pddl_hpot_config_t pot_cfg[5];
        int pot_cfg_size;
        char *pot_conj_file;
        char *pot_conj_exact_file;
    } ground_planner;

    struct {
        int search;
        pddl_symbolic_task_config_t cfg;
        pddl_bool_t bw_off_if_constr_failed;
        char *out;
    } symba;

    struct {
        pddl_bool_t lmg;
        pddl_bool_t reversibility_simple;
        pddl_bool_t reversibility_iterative;
        pddl_bool_t mgroups;
        char *pot_conj_max_init_h_value;
        char *pot_conj_exact_max_init_h_value;
        pddl_bool_t pot_strips;
    } report;

    struct {
        int max_depth;
        pddl_bool_t use_mutex;
    } reversibility;

    struct {
        pddl_bool_t enable;
        char *out_task;
        char *out_fdr;
    } asnets;
};
typedef struct options options_t;
extern options_t opt;

int setOptions(int argc, char *argv[], pddl_err_t *err);

extern FILE *log_out;
extern FILE *prop_out;

#endif /* OPTIONS_H */
