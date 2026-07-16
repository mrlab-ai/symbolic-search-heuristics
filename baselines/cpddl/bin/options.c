/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include <pddl/pddl.h>
#include <libgen.h>
#include "print_to_file.h"
#include "options.h"
#include "opts.h"

extern const int is_pddl_fdr;
extern const int is_pddl_symba;
extern const int is_pddl_pddl;
extern const int is_pddl_lplan;

options_t opt = { 0 };

FILE *log_out = NULL;

struct op_mutex_cfg {
    pddl_bool_t ts;
    int op_fact;
    int hm_op;
    pddl_bool_t no_prune;
    int prune_method;
    float prune_time_limit;
    char *out;
};
typedef struct op_mutex_cfg op_mutex_cfg_t;

struct h3_cfg {
    float time;
    int mem;
};
typedef struct h3_cfg h3_cfg_t;

struct endomorph_cfg {
    pddl_endomorphism_config_t cfg;
    pddl_bool_t fdr;
    pddl_bool_t ts;
    pddl_bool_t fdr_ts;
};
typedef struct endomorph_cfg endomorph_cfg_t;

static pddl_endomorphism_config_t endomorph_default_cfg = PDDL_ENDOMORPHISM_CONFIG_INIT;

static int setLPSolver(const char *v)
{
    int solver = -1;
    if (strcmp(v, "cplex") == 0){
        solver = PDDL_LP_CPLEX;

    }else if (strcmp(v, "gurobi") == 0 || strcmp(v, "grb") == 0){
        solver = PDDL_LP_GUROBI;

    }else if (strcmp(v, "highs") == 0){
        solver = PDDL_LP_HIGHS;

    }else if (strcmp(v, "?") == 0 || strcmp(v, "help") == 0){
        opt.list_lp_solvers = pddl_true;
        return 0;

    }else{
        fprintf(stderr, "Option Error: Unknown lp solver '%s'\n", v);
        return -1;
    }

    if (!pddlLPSolverAvailable(solver)){
        fprintf(stderr, "Option Error: %s is not an available LP solver!\n", v);
        return -1;
    }
    pddlLPSetDefault(solver, NULL);
    return 0;
}

static int setCPSolver(const char *v)
{
    int solver = -1;
    if (strcmp(v, "cpoptimizer") == 0
            || strcmp(v, "cp-optimizer") == 0
            || strcmp(v, "cplex") == 0){
        solver = PDDL_CP_SOLVER_CPOPTIMIZER;

    }else if (strcmp(v, "minizinc") == 0 || strcmp(v, "mzn") == 0){
        solver = PDDL_CP_SOLVER_MINIZINC;

    }else if (strcmp(v, "?") == 0 || strcmp(v, "help") == 0){
        opt.list_cp_solvers = pddl_true;
        return 0;

    }else{
        fprintf(stderr, "Option Error: Unknown CP solver '%s'\n", v);
        return -1;
    }

    if (!pddlLPSolverAvailable(solver)){
        fprintf(stderr, "Option Error: %s is not an available CP solver!\n", v);
        return -1;
    }
    pddlCPSetDefaultSolver(solver);
    return 0;
}

static int setMinizinc(const char *v)
{
    if (!pddlIsFile(v)){
        fprintf(stderr, "Option Error: Cannot find %s", v);
        return -1;
    }

    pddlCPSetDefaultMinizincBin(v);
    setCPSolver("minizinc");
    return 0;
}

static void hpotSetDisamb(pddl_bool_t value, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->disambiguation = value;
    if (value)
        cfg->weak_disambiguation = 0;
}

static void hpotSetWeakDisamb(pddl_bool_t value, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->weak_disambiguation = value;
    if (value)
        cfg->disambiguation = 0;
}

static void hpotSetObjInit(pddl_bool_t v, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->type = PDDL_HPOT_OPT_STATE_TYPE;
}

static void hpotSetObjAllStates(pddl_bool_t v, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->type = PDDL_HPOT_OPT_ALL_SYNTACTIC_STATES_TYPE;
}

static void hpotSetObjAllStatesInit(pddl_bool_t v, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->type = PDDL_HPOT_OPT_ALL_SYNTACTIC_STATES_TYPE;
    cfg->opt_all_syntactic_states.add_state_constr.init_state = pddl_true;
}

static void hpotSetObjAllStatesInitNoHMax0(pddl_bool_t v, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->type = PDDL_HPOT_OPT_ALL_SYNTACTIC_STATES_TYPE;
    cfg->opt_all_syntactic_states.add_state_constr.init_state = pddl_true;
    cfg->opt_all_syntactic_states.add_state_constr.ignore_hmax0 = pddl_true;
}

static void hpotSetObjSamplesSum(int v, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->type = PDDL_HPOT_OPT_SAMPLED_STATES_TYPE;
    cfg->opt_sampled_states.num_samples = v;
}

static void hpotSetObjSamplesSumInit(int v, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->type = PDDL_HPOT_OPT_SAMPLED_STATES_TYPE;
    cfg->opt_sampled_states.num_samples = v;
    cfg->opt_sampled_states.add_state_constr.init_state = pddl_true;
}

static void hpotSetObjAllMutex(int v, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->type = PDDL_HPOT_OPT_ALL_STATES_MUTEX_TYPE;
    cfg->opt_all_states_mutex.mutex_size = v;
}

static void hpotSetObjAllMutexInit(int v, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->type = PDDL_HPOT_OPT_ALL_STATES_MUTEX_TYPE;
    cfg->opt_all_states_mutex.mutex_size = v;
    cfg->opt_all_states_mutex.add_state_constr.init_state = pddl_true;
}


static void hpotSetObjSamplesMax(int v, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->type = PDDL_HPOT_OPT_ENSEMBLE_SAMPLED_STATES_TYPE;
    cfg->opt_ensemble_sampled_states.num_samples = v;
}

static void hpotSetObjDiverse(int v, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->type = PDDL_HPOT_OPT_ENSEMBLE_DIVERSIFICATION_TYPE;
    cfg->opt_ensemble_diversification.num_samples = v;
}


static void hpotSetObjAllMutexCond(int v, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->type = PDDL_HPOT_OPT_ENSEMBLE_ALL_STATES_MUTEX_TYPE;
    cfg->opt_ensemble_all_states_mutex.cond_size = 1;
    cfg->opt_ensemble_all_states_mutex.mutex_size = v;
}

static void hpotSetObjAllMutexCondRand(int v, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->type = PDDL_HPOT_OPT_ENSEMBLE_ALL_STATES_MUTEX_TYPE;
    cfg->opt_ensemble_all_states_mutex.cond_size = 1;
    cfg->opt_ensemble_all_states_mutex.mutex_size = 1;
    cfg->opt_ensemble_all_states_mutex.num_rand_samples = v;
}

static void hpotSetObjAllMutexCondRand2(int v, void *_cfg)
{
    pddl_hpot_config_t *cfg = _cfg;
    cfg->type = PDDL_HPOT_OPT_ENSEMBLE_ALL_STATES_MUTEX_TYPE;
    cfg->opt_ensemble_all_states_mutex.cond_size = 1;
    cfg->opt_ensemble_all_states_mutex.mutex_size = 2;
    cfg->opt_ensemble_all_states_mutex.num_rand_samples = v;
}

static void hpotParams(opts_params_t *params,
                       pddl_hpot_config_t *cfg)
{
    optsParamsAddFlagFn(params, "disam", cfg, hpotSetDisamb);
    optsParamsAddFlagFn(params, "disambiguation", cfg, hpotSetDisamb);
    optsParamsAddFlagFn(params, "D", cfg, hpotSetDisamb);

    optsParamsAddFlagFn(params, "weak-disam", cfg, hpotSetWeakDisamb);
    optsParamsAddFlagFn(params, "weak-disambiguation", cfg, hpotSetWeakDisamb);
    optsParamsAddFlagFn(params, "W", cfg, hpotSetWeakDisamb);

    optsParamsAddFlagFn(params, "init", cfg, hpotSetObjInit);
    optsParamsAddFlagFn(params, "I", cfg, hpotSetObjInit);

    optsParamsAddFlagFn(params, "all", cfg, hpotSetObjAllStates);
    optsParamsAddFlagFn(params, "A", cfg, hpotSetObjAllStates);
    optsParamsAddFlagFn(params, "A+I", cfg, hpotSetObjAllStatesInit);
    optsParamsAddFlagFn(params, "A+I-no-hmax0", cfg, hpotSetObjAllStatesInitNoHMax0);

    optsParamsAddIntFn(params, "sample-sum", cfg, hpotSetObjSamplesSum);
    optsParamsAddIntFn(params, "S", cfg, hpotSetObjSamplesSum);
    optsParamsAddIntFn(params, "S+I", cfg, hpotSetObjSamplesSumInit);

    optsParamsAddIntFn(params, "all-mutex", cfg, hpotSetObjAllMutex);
    optsParamsAddIntFn(params, "M", cfg, hpotSetObjAllMutex);
    optsParamsAddIntFn(params, "M+I", cfg, hpotSetObjAllMutexInit);

    optsParamsAddIntFn(params, "sample-max", cfg, hpotSetObjSamplesMax);
    optsParamsAddIntFn(params, "diverse", cfg, hpotSetObjDiverse);
    optsParamsAddIntFn(params, "all-mutex-cond", cfg, hpotSetObjAllMutexCond);
    optsParamsAddIntFn(params, "all-mutex-cond-rand", cfg,
                       hpotSetObjAllMutexCondRand);
    optsParamsAddIntFn(params, "all-mutex-cond-rand2", cfg,
                       hpotSetObjAllMutexCondRand2);

    optsParamsAddFlt(params, "lp-time-limit", &cfg->lp_time_limit);

    optsParamsAddFlag(params, "hmax0", &cfg->hmax0);
}

static int optGroundNoPruning(pddl_bool_t enabled)
{
    if (enabled){
        opt.ground.cfg.prune_op_pre_mutex = 0;
        opt.ground.cfg.prune_op_dead_end = 0;
    }
    return 0;
}


static int optFDRLargestFirst(pddl_bool_t enabled)
{
    opt.fdr.cfg.var.alg = PDDL_FDR_VARS_ALG_LARGEST_FIRST;
    return 0;
}

static int optFDREssentialFirst(pddl_bool_t enabled)
{
    opt.fdr.cfg.var.alg = PDDL_FDR_VARS_ALG_ESSENTIAL_FIRST;
    return 0;
}

static void irrelevance(void)
{
    pddlProcessStripsAddIrrelevance(&opt.strips.process);
}

static void irrelevanceOps(void)
{
    pddlProcessStripsAddIrrelevanceOps(&opt.strips.process);
}

static void removeUselessDelEffs(void)
{
    pddlProcessStripsAddRemoveUselessDelEffs(&opt.strips.process);
}

static void unreachableOps(void)
{
    pddlProcessStripsAddUnreachableOps(&opt.strips.process);
}

static void removeOpsEmptyAddEff(void)
{
    pddlProcessStripsAddRemoveOpsEmptyAddEff(&opt.strips.process);
}

static void famDeadEnd(void)
{
    pddlProcessStripsAddFAMGroupsDeadEndOps(&opt.strips.process);
}

static void deduplicateOps(void)
{
    pddlProcessStripsAddDeduplicateOps(&opt.strips.process);
}

static void sortOps(void)
{
    pddlProcessStripsAddSortOps(&opt.strips.process);
}

static void pruneH2Fw(void)
{
    pddlProcessStripsAddH2Fw(&opt.strips.process, 0.f);
}

static int pruneH2FwLimit(float v)
{
    pddlProcessStripsAddH2Fw(&opt.strips.process, v);
    return 0;
}

static void pruneH2FwBw(void)
{
    pddlProcessStripsAddH2FwBw(&opt.strips.process, 0.f);
}

static int pruneH2FwBwLimit(float v)
{
    pddlProcessStripsAddH2FwBw(&opt.strips.process, v);
    return 0;
}

static void pruneH3Fw(void)
{
    pddlProcessStripsAddH3Fw(&opt.strips.process, 0.f, 0);
}

static void pruneH3FwLimit(void *ud)
{
    h3_cfg_t *cfg = ud;
    size_t mem = cfg->mem;
    mem *= 1024UL * 1024UL;
    pddlProcessStripsAddH3Fw(&opt.strips.process, cfg->time, mem);
    bzero(cfg, sizeof(*cfg));
}

static void h2Alias(void)
{
    unreachableOps();
    irrelevanceOps();
    famDeadEnd();
    pruneH2FwBw();
    irrelevance();
    removeUselessDelEffs();
    deduplicateOps();
}

static int printStripsPddlDomain(const char *fn)
{
    pddlProcessStripsAddPrintPddlDomain(&opt.strips.process, fn);
    return 0;
}

static int printStripsPddlProblem(const char *fn)
{
    pddlProcessStripsAddPrintPddlProblem(&opt.strips.process, fn);
    return 0;
}

static void endomorphism(void *ud)
{
    endomorph_cfg_t *cfg = ud;
    if (cfg->fdr){
        pddlProcessStripsAddEndomorphFDR(&opt.strips.process, &cfg->cfg);
    }else if (cfg->ts){
        pddlProcessStripsAddEndomorphTS(&opt.strips.process, &cfg->cfg);
    }else if (cfg->fdr_ts){
        pddlProcessStripsAddEndomorphFDRTS(&opt.strips.process, &cfg->cfg);
    }
    bzero(cfg, sizeof(*cfg));
    cfg->cfg = endomorph_default_cfg;
}

static void opMutex(void *ud)
{
    op_mutex_cfg_t *cfg = ud;
    if (!cfg->no_prune && cfg->prune_method == 0){
        fprintf(stderr, "Option Error: --P-opm requires prune-method=..."
                " option unless no-prune is set\n");
        exit(-1);
    }
    pddlProcessStripsAddOpMutex(&opt.strips.process,
                                cfg->ts, cfg->op_fact, cfg->hm_op,
                                cfg->no_prune, cfg->prune_method,
                                cfg->prune_time_limit,
                                cfg->out);
    if (cfg->out != NULL)
        PDDL_FREE(cfg->out);
    bzero(cfg, sizeof(*cfg));
}

static void groundHeurOpMutex(void *ud)
{
    op_mutex_cfg_t *cfg = ud;
    opt.ground_planner.heur_op_mutex = 1;
    opt.ground_planner.heur_op_mutex_ts = cfg->ts;
    opt.ground_planner.heur_op_mutex_op_fact = cfg->op_fact;
    opt.ground_planner.heur_op_mutex_hm_op = cfg->hm_op;
    bzero(cfg, sizeof(*cfg));
}

static void setBaseOptions(void)
{
    optsAddFlag("help", 'h', &opt.help, 0, "Print this help.");
    optsAddFlag("version", 0x0, &opt.version, 0, "Print version and exit.");
    optsAddInt("max-mem", 0x0, &opt.max_mem, 0,
               "Maximum memory in MB if >0.");
    optsAddStr("log-out", 0x0, &opt.log_out, "-",
               "Set output file for logs.");
    optsAddStrFn("lp-solver", 0x0, setLPSolver,
                 "Set the default LP solver: cplex/gurobi/highs");
    optsAddStrFn("cp-solver", 0x0, setCPSolver,
                 "Set the default CP solver: cpoptimizer/minizinc");
    optsAddStr("cplex-lib", 0x0, &opt.link_cplex, NULL,
                 "Load CPLEX dynamic library. Also sets LP solver to cplex.");
    optsAddStr("gurobi-lib", 0x0, &opt.link_gurobi, NULL,
                 "Load Gurobi dynamic library. Also sets LP solver to gurobi.");
    optsAddStrFn("minizinc", 0x0, setMinizinc,
                 "Use the specified minizinc binary as a CP solver.");
}

static void setPddlOptions(void)
{
    optsStartGroup("PDDL:");
    optsAddFlag("force-adl", 0x0, &opt.pddl.force_adl, 1,
                "Force :adl requirement if it is not specified in the"
                " domain file.");
    optsAddFlag("pedantic", 0x0, &opt.pddl.pedantic, 0,
                "Turns warnings emitted by the parser into errors.");
    optsAddFlag("remove-empty-types", 0x0, &opt.pddl.remove_empty_types, 1,
                "Remove empty types");
    optsAddFlag("pddl-ce", 0x0, &opt.pddl.compile_away_cond_eff, 0,
                "Compile away conditional effects on the PDDL level.");
    optsAddFlag("pddl-disj-goal", 0x0, &opt.pddl.compile_away_disjunctive_goals, 0,
                "Compile away disjunctive goals by adding auxiliary actions.");
    optsAddFlag("pddl-unit-cost", 0x0, &opt.pddl.enforce_unit_cost, 0,
                "Enforce unit cost on the PDDL level.");
    optsAddIntSwitch("pddl-neg-cond", 0x0,
                     &opt.pddl.compile_away_neg_cond,
                     "Compile away negative conditions during normalization, one of:\n"
                     "  dynamic -- only dynamic predicates (default)\n"
                     "  all -- all conditions including static predicates\n"
                     "  goal -- only dynamic predicates appearing in the goal\n"
                     "  none -- do not compile away negative conditions",
                     4,
                     "dynamic", COMPILE_AWAY_NEG_COND_DYNAMIC,
                     "all", COMPILE_AWAY_NEG_COND_ALL,
                     "goal", COMPILE_AWAY_NEG_COND_GOAL,
                     "none", COMPILE_AWAY_NEG_COND_NONE);
}

static void setLMGOptions(void)
{
    optsStartGroup("Lifted Mutex Groups:");
    optsAddFlag("lmg", 0x0, &opt.lmg.enable, 1,
                "Enabled inference of lifted mutex groups.");
    optsAddInt("lmg-max-candidates", 0x0, &opt.lmg.max_candidates, 10000,
               "Maximum number of lifted mutex group candidates.");
    optsAddInt("lmg-max-mgroups", 0x0, &opt.lmg.max_mgroups, 10000,
               "Maximum number of lifted mutex group.");
    optsAddFlag("lmg-fd", 0x0, &opt.lmg.fd, 0,
                "Find Fast-Downward type of lifted mutex groups.");
    optsAddFlag("lmg-fd-mono", 0x0, &opt.lmg.fd_monotonicity, 0,
                "Find Fast-Downward monotonicit invariants; implies --lmg-fd.");
    optsAddStr("lmg-out", 0x0, &opt.lmg.out, NULL,
                "Output filename for infered lifted mutex groups.");
    optsAddStr("lmg-fd-mono-out", 0x0, &opt.lmg.fd_monotonicity_out, NULL,
                "Output filename for infered monotonicity invariants.");
    optsAddFlag("lmg-stop", 0x0, &opt.lmg.stop, 0,
                "Stop after inferring lifted mutex groups.");
}

static void setLEndoOptions(void)
{
    optsStartGroup("Lifted Endomorphisms:");
    optsAddFlag("lendo", 0x0, &opt.lifted_endomorph.enable, 0,
                "Enable pruning od PDDL using lifted endomorphisms.");
    optsAddFlag("lendo-ignore-costs", 0x0, &opt.lifted_endomorph.ignore_costs, 0,
                "Ignore costs of actions when inferring lifted endomorphisms.");
}

static void setPddlPostprocessOptions(void)
{
    optsStartGroup("PDDL Post-process:");
    optsAddStr("pddl-domain-out", 0x0, &opt.pddl.domain_out, NULL,
               "Write PDDL domain file.");
    optsAddStr("pddl-problem-out", 0x0, &opt.pddl.problem_out, NULL,
               "Write PDDL problem file.");
    optsAddFlag("pddl-compile-in-lmg", 0x0, &opt.pddl.compile_in_lmg, 0,
                "Alias for --pddl-compile-in-lmg-mutex --pddl-compile-in-dead-end");
    optsAddFlag("pddl-compile-in-lmg-mutex", 0x0,
                &opt.pddl.compile_in_lmg_mutex, 0,
                "Compile lifted mutex groups into actions' preconditions"
                " pruning mutexes.");
    optsAddFlag("pddl-compile-in-lmg-dead-end", 0x0,
                &opt.pddl.compile_in_lmg_dead_end, 0,
                "Compile lifted mutex groups into actions' preconditions"
                " pruning dead-ends.");
    optsAddFlag("pddl-stop", 0x0, &opt.pddl.stop, 0,
                "Stop after processing PDDL.");
}

static void setLiftedPlannerOptions(void)
{

    pddl_homomorphism_config_t _homomorph_cfg = PDDL_HOMOMORPHISM_CONFIG_INIT;
    opt.lifted_planner.homomorph_cfg = _homomorph_cfg;
    opt.lifted_planner.homomorph_samples = 1;
    opt.lifted_planner.homomorph_sampling_max_time = -1.;

    opts_params_t *params;
    optsStartGroup("Lifted Planner:");
    optsAddIntSwitch("lplan", 0x0, &opt.lifted_planner.search,
                     "Search algorithm for the lifted planner, one of:\n"
                     "  none - no search (default)\n"
                     "  astar - A*\n"
                     "  gbfs - Greedy Best First Search\n"
                     "  lazy - Greedy Best First Search with lazy evaluation",
                     4,
                     "none", LIFTED_PLAN_NONE,
                     "astar", LIFTED_PLAN_ASTAR,
                     "gbfs", LIFTED_PLAN_GBFS,
                     "lazy", LIFTED_PLAN_LAZY);
    optsAddIntSwitch("lplan-succ-gen", 0x0, &opt.lifted_planner.succ_gen,
                     "Backend of the successor generator, one of:\n"
                     "  dl - datalog (default)\n"
                     "  sql - sqlite\n",
                     2,
                     "dl", LIFTED_PLAN_SUCC_GEN_DL,
                     "sql", LIFTED_PLAN_SUCC_GEN_SQL);
    optsAddIntSwitch("lplan-h", 0x0, &opt.lifted_planner.heur,
                     "Heuristic function for the lifted planner, one of:\n"
                     "  blind - Blind heuristic (default)\n"
                     "  hmax - lifted h^max\n"
                     "  hadd - lifted h^add\n"
                     "  hff-max - lifted h^ff based on h^max\n"
                     "  hff/hff-add - lifted h^ff based on h^add\n"
                     "  homo-lmc - Homomorphism-based LM-Cut heuristic (see --lplan-h-homo)\n"
                     "  homo-ff - Homomorphism-based FF heuristic (see --lplan-h-homo)\n"
                     "  gaif-lb - Plan length lower bound using gaifman graphs\n"
                     "  gaif-max - Max distance using gaifman graphs\n"
                     "  gaif-add - Sum of distances using gaifman graphs",
                     11,
                     "blind", LIFTED_PLAN_HEUR_BLIND,
                     "hmax", LIFTED_PLAN_HEUR_HMAX,
                     "hadd", LIFTED_PLAN_HEUR_HADD,
                     "hff-max", LIFTED_PLAN_HEUR_HFF_MAX,
                     "hff", LIFTED_PLAN_HEUR_HFF_ADD,
                     "hff-add", LIFTED_PLAN_HEUR_HFF_ADD,
                     "homo-lmc", LIFTED_PLAN_HEUR_HOMO_LMC,
                     "homo-ff", LIFTED_PLAN_HEUR_HOMO_FF,
                     "gaif-lb", LIFTED_PLAN_HEUR_GAIF_LB,
                     "gaif-max", LIFTED_PLAN_HEUR_GAIF_MAX,
                     "gaif-add", LIFTED_PLAN_HEUR_GAIF_ADD);
    params = optsAddParams("lplan-h-homo", 0x0,
        "Configuration of the homomorphism for the"
        " homomorphism-based heuristics.\n"
        "Possible options:\n"
        "  type = types|rnd-objs|gaif|rpg\n"
        "  endomorph = <bool> -- enables lifted endomorphism (default: false)\n"
        "  endomorph-ignore-cost = <bool> -- endomorphism ignores costs (default: false)\n"
        "  rm-ratio = <float> -- ratio of removed objects\n"
        "  seed = <int> -- random seed\n"
        "  keep-goal-objs = <bool> -- do not collapse goal objects (default: true)\n"
        "  samples = <int> -- number of samples from which 1 is selected (default: 1)\n"
        "  sampling-max-time = <float> -- maximum time in seconds allocated for sampling (default: off)\n"
        "  rpg-max-depth = <int> -- maximum depth used for the rpg method (default: 2)"
        );
    optsParamsAddIntSwitch(params, "type",
                           &opt.lifted_planner.homomorph_cfg.type,
                           5,
                           "types", PDDL_HOMOMORPHISM_TYPES,
                           "rnd-objs", PDDL_HOMOMORPHISM_RAND_OBJS,
                           "gaifmain", PDDL_HOMOMORPHISM_GAIFMAN,
                           "gaif", PDDL_HOMOMORPHISM_GAIFMAN,
                           "rpg", PDDL_HOMOMORPHISM_RPG);
    optsParamsAddFlag(params, "endomorph",
                      &opt.lifted_planner.homomorph_cfg.use_endomorphism);
    optsParamsAddFlag(params, "endomorph-ignore-costs",
                      &opt.lifted_planner.homomorph_cfg.endomorphism_cfg.ignore_costs);
    optsParamsAddFlt(params, "rm-ratio",
                     &opt.lifted_planner.homomorph_cfg.rm_ratio);
    optsParamsAddInt(params, "seed", &opt.lifted_planner.random_seed);
    optsParamsAddFlag(params, "keep-goal-objs",
                      &opt.lifted_planner.homomorph_cfg.keep_goal_objs);
    optsParamsAddInt(params, "samples",
                     &opt.lifted_planner.homomorph_samples);
    optsParamsAddFlt(params, "sampling-max-time",
                     &opt.lifted_planner.homomorph_sampling_max_time);
    optsParamsAddInt(params, "rpg-max-depth",
                     &opt.lifted_planner.homomorph_cfg.rpg_max_depth);

    optsAddStr("lplan-out", 0x0, &opt.lifted_planner.plan_out, NULL,
               "Output filename for the found plan.");
    optsAddStr("lplan-o", 0x0, &opt.lifted_planner.plan_out, NULL,
               "Alias for --lplan-out");

    if (is_pddl_lplan)
        opt.lifted_planner.search = LIFTED_PLAN_ASTAR;
}

static void setGroundOptions(void)
{
    pddl_ground_config_t _cfg = PDDL_GROUND_CONFIG_INIT;
    opt.ground.cfg = _cfg;
    opt.ground.cfg.method = PDDL_GROUND_DATALOG;
    PDDL_PANIC_IF(sizeof(int) != sizeof(opt.ground.cfg.method),
                  "pddl_ground_method_t enum is not representable as int!");

    optsStartGroup("Grounding:");
    optsAddIntSwitch("ground", 'G', (int *)&opt.ground.cfg.method,
                     "Grounding method, one of:\n"
                     "  dl/datalog - datalog-based grounding method (default)\n"
                     "  gringo - use Gringo grounder\n"
                     "  clingo - use Clingo solver (iterative grounding)\n"
                     "  sql - sqlite-based grounding method\n"
                     "  trie - default grounding method",
                     6,
                     "trie", PDDL_GROUND_TRIE,
                     "sql", PDDL_GROUND_SQL,
                     "dl", PDDL_GROUND_DATALOG,
                     "datalog", PDDL_GROUND_DATALOG,
                     "gringo", PDDL_GROUND_GRINGO,
                     "clingo", PDDL_GROUND_CLINGO);
    optsAddFlag("ground-prune-mutex", 0x0,
                &opt.ground.cfg.prune_op_pre_mutex, 1,
                "Prune during grounding by checking preconditions of operators");
    optsAddFlag("ground-prune-de", 0x0,
                &opt.ground.cfg.prune_op_dead_end, 1,
                "Prune during grounding by checking dead-ends");
    optsAddFlag("ground-prune-dead-end", 0x0,
                &opt.ground.cfg.prune_op_dead_end, 1,
                "Alias for --ground-prune-dead-end");
    optsAddFlagFn("ground-prune-none", 0x0, optGroundNoPruning,
                  "Alias for --no-ground-prune-mutex --no-ground-prune-de");
    optsAddFlag("ground-lmg", 0x0, &opt.ground.mgroup, 1,
                "Ground lifted mutex groups.");
    optsAddFlag("ground-lmg-remove-subsets", 0x0,
                &opt.ground.mgroup_remove_subsets, 1,
                "After grounding lifted mutex groups, remove subsets.");
    optsAddStr("ground-mg-out", 0x0, &opt.ground.mgroup_out, NULL,
                "Output filename for grounded mutex groups.");
    optsAddStr("ground-gringo-lpopt", 0x0, (char **)&opt.ground.cfg.gringo_lpopt, NULL,
               "Path to the lpopt optimizer used for preprocessing datalog"
               " program before it is passed to Gringo.");

    optsStartGroup("STRIPS:");
    optsAddFlag("ce", 0x0, &opt.strips.compile_away_cond_eff, 0,
                "Compile away conditional effects on the STRIPS level"
                " (recommended instead of --pddl-ce).");
    optsAddStr("strips-as-py", 0x0, &opt.strips.py_out, NULL,
               "Output filename for STRIPS in python format.");
    optsAddStr("strips-fam-dump", 0x0, &opt.strips.fam_dump, NULL,
               "Compute fam-groups and dump the corresponding mutex pairs"
               " to the specified file.");
    optsAddStr("strips-h2-dump", 0x0, &opt.strips.h2_dump, NULL,
               "Compute h^2 and dump the mutexes to the specified file.");
    optsAddStr("strips-h3-dump", 0x0, &opt.strips.h3_dump, NULL,
               "Compute h^3 and dump the mutexes to the specified file.");
    optsAddFlag("strips-stop", 0x0, &opt.strips.stop, 0,
                "Stop after grounding to STRIPS.");
}

static void setMutexGroupOptions(void)
{
    optsStartGroup("Mutex Groups:");
    optsAddIntSwitch("mg", 0x0, &opt.mg.method,
                     "Method for inference of mutex groups, one of:\n"
                     "  0/n/none - no mutex groups will be inferred on STRIPS level (default)\n"
                     "  fam - fact-alternating mutex groups\n"
                     "  h2 - mutex groups from h^2 mutexes\n",
                     5,
                     "none", MG_NONE,
                     "n", MG_NONE,
                     "0", MG_NONE,
                     "fam", MG_FAM,
                     "h2", MG_H2);
    optsAddStr("mg-out", 0x0, &opt.mg.out, NULL,
                "Output filename for infered mutex groups.");
    optsAddFlag("mg-remove-subsets", 0x0, &opt.mg.remove_subsets, 1,
                "Remove subsets of the inferred mutex groups.");
    optsAddFlag("fam-lmg", 0x0, &opt.mg.fam_lmg, 1,
                "Use lifted mutex groups as initial set for inference of"
                " fam-groups.");
    optsAddFlag("fam-maximal", 0x0, &opt.mg.fam_maximal, 1,
                "Infer only maximal fam-groups"
                " (see also --no-mg-remove-subsets).");
    optsAddFlt("fam-time-limit", 0x0, &opt.mg.fam_time_limit, -1.,
                "Set time limit in seconds for the inference of fam-groups.");
    optsAddInt("fam-limit", 0x0, &opt.mg.fam_limit, -1,
                "Set limit on the number of inferred fam-groups.");
    optsAddFlag("mg-cover-num", 0x0, &opt.mg.cover_number, 0,
                "Compute cover number of the inferred mutex groups.");
}

static void fixpointOpen(void)
{
    pddlProcessStripsFixpointStart(&opt.strips.process);
}

static void fixpointClose(void)
{
    pddlProcessStripsFixpointFinalize(&opt.strips.process);
}

static void setProcessStripsOptions(void)
{
    opts_params_t *params;

    pddlProcessStripsInit(&opt.strips.process);

    optsStartGroup("Process STRIPS:");
    optsAddFlagFn2("P-irr", 0x0, irrelevance, "Irrelevance analysis.");
    optsAddFlagFn2("P-irr-op", 0x0, irrelevanceOps,
                   "As --P-irr but removes only operators.");
    optsAddFlagFn2("P-rm-useless-del-effs", 0x0, removeUselessDelEffs,
                   "Remove delete effects that can never be used.");
    optsAddFlagFn2("P-unreachable-op", 0x0, unreachableOps,
                   "Remove unreachable operators based on mutexes.");
    optsAddFlagFn2("P-rm-ops-empty-add-eff", 0x0, removeOpsEmptyAddEff,
                   "Remove operators with empty add effects.");
    optsAddFlagFn2("P-fam-dead-end", 0x0, famDeadEnd,
                   "Remove dead-end operators using fam-groups (see --mg fam).");
    optsAddFlagFn2("P-dedup", 0x0, deduplicateOps,
                   "Remove duplicate operators.");
    optsAddFlagFn2("P-sort", 0x0, sortOps, "Sort operators by their names.");
    optsAddFlagFn2("P-h2fw", 0x0, pruneH2Fw,
                   "Prune with h^2 in forward direction without time limit.");
    optsAddFltFn("P-h2fw-time-limit", 0x0, pruneH2FwLimit,
                 "Prune with h^2 in forward direction with the specified time limit.");
    optsAddFlagFn2("P-h2fwbw", 0x0, pruneH2FwBw,
                   "Prune with h^2 in forward/backward direction without time limit.");
    optsAddFltFn("P-h2fwbw-time-limit", 0x0, pruneH2FwBwLimit,
                 "Prune with h^2 in forward/backward direction with the specified time limit.");
    optsAddFlagFn2("P-h3fw", 0x0, pruneH3Fw,
                   "Prune with h^3 in forward direction without time limit.");

    static h3_cfg_t h3_cfg = { 0 };
    params = optsAddParamsAndFn("P-h3fw-limit", 0x0,
                                "Prune with h^3 with the specified limits.\n"
                                "Options:\n"
                                "  time = <float> -- time limit in s\n"
                                "  mem = <int> -- excess memory in MB",
                                &h3_cfg, pruneH3FwLimit);
    optsParamsAddFlt(params, "time", &h3_cfg.time);
    optsParamsAddInt(params, "mem", &h3_cfg.mem);

    static endomorph_cfg_t endomorph_cfg = { 0 };
    endomorph_cfg.cfg = endomorph_default_cfg;
    params = optsAddParamsAndFn("P-endo", 0x0,
                                "Endomorphism.\n"
                                "Options:\n"
                                "  fdr = <bool> -- use FDR\n"
                                "  mg-strips = <bool> -- use MG-STRIPS\n"
                                "  ts = <bool> -- use factored transition system\n"
                                "  fdr-ts = <bool> -- use FDR and then factored TS\n"
                                "  max-time = <float> -- time limit (default: 1 hour)\n"
                                "  max-search-time = <float> -- time limit for the search part (default: 1 hour)\n"
                                "  num-threads = <int> -- number of threads for the solved (default: 1)\n"
                                "  fork = <bool> -- run in subprocess (default: true)\n"
                                "  ignore-costs = <bool> -- ignore operator costs (default: false)",
                                &endomorph_cfg, endomorphism);
    optsParamsAddFlag(params, "fdr", &endomorph_cfg.fdr);
    optsParamsAddFlag(params, "ts", &endomorph_cfg.ts);
    optsParamsAddFlag(params, "fdr-ts", &endomorph_cfg.fdr_ts);
    optsParamsAddFlt(params, "max-time", &endomorph_cfg.cfg.max_time);
    optsParamsAddFlt(params, "max-search-time", &endomorph_cfg.cfg.max_search_time);
    optsParamsAddInt(params, "num-threads", &endomorph_cfg.cfg.num_threads);
    optsParamsAddFlag(params, "fork", &endomorph_cfg.cfg.run_in_subprocess);
    optsParamsAddFlag(params, "ignore-costs", &endomorph_cfg.cfg.ignore_costs);


    static op_mutex_cfg_t opm_cfg = { 0 };
    params = optsAddParamsAndFn("P-opm", 0x0,
                                "Operator mutexes.\n"
                                "Options:\n"
                                "  ts = <bool> -- use transition systems\n"
                                "  op-fact = <int> -- op-fact compilation\n"
                                "  hm-op = <int> -- h^m from each operator\n"
                                "  no-prune = <bool> -- disabled pruning\n"
                                "  p/prune-method = max/greedy -- inference method\n"
                                "  tl/prune-time-limit = <float>\n"
                                "  out = <str> -- path to file where operator mutex are stored",
                                &opm_cfg, opMutex);
    optsParamsAddFlag(params, "ts", &opm_cfg.ts);
    optsParamsAddInt(params, "op-fact", &opm_cfg.op_fact);
    optsParamsAddInt(params, "hm-op", &opm_cfg.hm_op);
    optsParamsAddFlag(params, "no-prune", &opm_cfg.no_prune);
    optsParamsAddIntSwitch(params, "p", &opm_cfg.prune_method, 2,
                           "max", PDDL_OP_MUTEX_REDUNDANT_MAX,
                           "greedy", PDDL_OP_MUTEX_REDUNDANT_GREEDY);
    optsParamsAddIntSwitch(params, "prune-method", &opm_cfg.prune_method, 2,
                           "max", PDDL_OP_MUTEX_REDUNDANT_MAX,
                           "greedy", PDDL_OP_MUTEX_REDUNDANT_GREEDY);
    optsParamsAddFlt(params, "tl", &opm_cfg.prune_time_limit);
    optsParamsAddFlt(params, "prune-time-limit", &opm_cfg.prune_time_limit);
    optsParamsAddStr(params, "out", &opm_cfg.out);

    optsAddFlagFn2("h2", 0x0, h2Alias,
                   "Alias for --P-{unreachable-op,irr-op,fam-dead-end,"
                   "h2fwbw,irr,rm-useless-del-effs,dedup}"
                   " (set by default for pddl-symba)");

    optsAddStrFn("P-pddl-domain", 0x0, printStripsPddlDomain,
                 "Print STRIPS problem in the PDDL format -- domain file.");
    optsAddStrFn("P-pddl-problem", 0x0, printStripsPddlProblem,
                 "Print STRIPS problem in the PDDL format -- problem file.");

    optsAddFlagFn2("P-fixpoint-start", 0x0, fixpointOpen,
                   "Beginning of the fixpoint block.");
    optsAddFlagFn2("P-fp[", 0x0, fixpointOpen,
                   "Alias for --P-fixpoint-start.");
    optsAddFlagFn2("P-fixpoint-end", 0x0, fixpointClose,
                   "End of the fixpoint block.");
    optsAddFlagFn2("P-fp]", 0x0, fixpointClose,
                   "Alias for --P-fixpoint-end.");


    if (is_pddl_symba){
        h2Alias();
        sortOps();
    }
}

static void enablePotConjFind(void *_)
{
    (void)_;
    opt.pot_conj_find.enable = pddl_true;
}

static void setPotConjFindOptions(void)
{
    pddlHPotConfigInit(&opt.pot_conj_find.pot_cfg);
    pddl_pot_conj_find_config_t _cfg = PDDL_POT_CONJ_FIND_CONFIG_INIT;
    opt.pot_conj_find.cfg = _cfg;

    optsStartGroup("Potentials over Conjunctions: Generating Conjunctions");
    opts_params_t *params;
    params = optsAddParamsAndFn("pot-conj-find", 0x0,
                                "Find conjunctions for potentials over conjunctions\n"
                                "Options:\n"
                                "  out = <str> -- prefix for output files\n"
                                "  time-limit/tl <dbl> -- time limit in seconds\n"
                                "  max-epochs <int> -- maximum number of improvements considered\n"
                                "  max-dim <int> -- maximum considered size of conjunctions\n"
                                "  random <bool> -- try random conjunctions\n"
                                "  random-seed <int>\n"
                                "  log-freq <dbl> -- frequency of logging in seconds",
                                NULL, enablePotConjFind);
    optsParamsAddStr(params, "out", (char **)&opt.pot_conj_find.cfg.write_progress_prefix);
    optsParamsAddDbl(params, "time-limit", &opt.pot_conj_find.cfg.time_limit);
    optsParamsAddDbl(params, "tl", &opt.pot_conj_find.cfg.time_limit);
    optsParamsAddInt(params, "max-epochs", &opt.pot_conj_find.cfg.max_epochs);
    optsParamsAddInt(params, "max-dim", &opt.pot_conj_find.cfg.max_conj_dim);
    optsParamsAddFlag(params, "random", &opt.pot_conj_find.cfg.random_conjs);
    optsParamsAddInt(params, "random-seed", &opt.pot_conj_find.cfg.random_seed);
    optsParamsAddDbl(params, "log-freq", &opt.pot_conj_find.cfg.log_freq);

    params = optsAddParams("pot-conj-find-pot", 0x0,
                           "Configuration for the potential heuristic. Default: I");
    hpotParams(params, &opt.pot_conj_find.pot_cfg);
}

static void enablePotConjExactFind(void *_)
{
    (void)_;
    opt.pot_conj_exact_find.enable = pddl_true;
}

static void setPotConjExactFindOptions(void)
{
    pddlHPotConfigInit(&opt.pot_conj_exact_find.pot_cfg);
    pddl_pot_conj_exact_find_config_t _cfg = PDDL_POT_CONJ_EXACT_FIND_CONFIG_INIT;
    opt.pot_conj_exact_find.cfg = _cfg;

    optsStartGroup("Potentials over Conjunctions: Generating Conjunctions");
    opts_params_t *params;
    params = optsAddParamsAndFn("pot-conj-exact-find", 0x0,
                                "Find conjunctions for potentials over conjunctions\n"
                                "Options:\n"
                                "  out = <str> -- prefix for output files\n"
                                "  time-limit/tl <dbl> -- time limit in seconds\n"
                                "  max-epochs <int> -- maximum number of improvements considered\n"
                                "  max-dim <int> -- maximum considered size of conjunctions\n"
                                "  random <bool> -- try random conjunctions\n"
                                "  random-seed <int>\n"
                                "  log-freq <dbl> -- frequency of logging in seconds",
                                NULL, enablePotConjExactFind);
    optsParamsAddStr(params, "out", (char **)&opt.pot_conj_exact_find.cfg.write_progress_prefix);
    optsParamsAddDbl(params, "time-limit", &opt.pot_conj_exact_find.cfg.time_limit);
    optsParamsAddDbl(params, "tl", &opt.pot_conj_exact_find.cfg.time_limit);
    optsParamsAddInt(params, "max-epochs", &opt.pot_conj_exact_find.cfg.max_epochs);
    optsParamsAddInt(params, "max-dim", &opt.pot_conj_exact_find.cfg.max_conj_dim);
    optsParamsAddDbl(params, "log-freq", &opt.pot_conj_exact_find.cfg.log_freq);

    params = optsAddParams("pot-conj-exact-find-pot", 0x0,
                           "Configuration for the potential heuristic. Default: I");
    hpotParams(params, &opt.pot_conj_exact_find.pot_cfg);
}

static void setExtendStripsConjOptions(void)
{
    optsStartGroup("Extending STRIPS with Conjunctions (Replacing P with P^C)");
    optsAddStr("extend-strips-conj-file", 0x0,
               &opt.extend_strips_conj_file, NULL,
               "Replace STIRPS task P with P^C where C is read from the"
               "input .toml file that must contain a key 'conj' assigining"
               " an array of arrays of strings.");
}

static void setRedBlackOptions(void)
{
    pddl_red_black_fdr_config_t _rb_cfg = PDDL_RED_BLACK_FDR_CONFIG_INIT;
    opt.rb_fdr.cfg = _rb_cfg;

    optsStartGroup("Red-Black FDR:");
    optsAddFlag("rb-fdr", 0x0, &opt.rb_fdr.enable, 0,
                "Compute red-black FDR encoding of the task.");
    optsAddInt("rb-fdr-size", 0x0, &opt.rb_fdr.cfg.mgroup.num_solutions, 1,
               "Number of different encodings to compute.");
    optsAddFlag("rb-fdr-relaxed-plan", 0x0,
                &opt.rb_fdr.cfg.mgroup.weight_facts_with_relaxed_plan, 0,
                "Weight facts using relaxed plan.");
    optsAddFlag("rb-fdr-conflicts", 0x0,
                &opt.rb_fdr.cfg.mgroup.weight_facts_with_conflicts, 0,
                "Weight facts with conflicts in relaxed plan.");
    optsAddStr("rb-fdr-out", 0x0, &opt.rb_fdr.out, NULL,
               "Output filename for the red-black FDR task.");
}

static void setFDROptions(void)
{
    pddlFDRConfigInit(&opt.fdr.cfg);

    opts_params_t *params;

    pddlHPotConfigInit(&opt.fdr.pot_cfg);

    if (is_pddl_fdr)
        opt.fdr.out = "-";

    optsStartGroup("Finite Domain Representation:");
    char desc[512];
    sprintf(desc, "Sort FDR variables with largest first%s.",
            (is_pddl_symba ? "" : " (default)"));
    optsAddFlagFn("fdr-largest", 0x0, optFDRLargestFirst, desc);
    sprintf(desc, "Sort FDR variables with essential first%s.",
            (is_pddl_symba ? " (default)" : ""));
    optsAddFlagFn("fdr-essential", 0x0, optFDREssentialFirst, desc);
    optsAddFlagFn("fdr-ess", 0x0, optFDREssentialFirst,
                  "Alias for --fdr-essential.");
    optsAddFlag("fdr-order-vars-cg", 0x0, &opt.fdr.order_vars_cg, 1,
                "Order FDR variables using causal graph.");
    optsAddStr("fdr-out", 'o', &opt.fdr.out, opt.fdr.out,
               "Output filename for FDR encoding of the task.");
    optsAddFlag("fdr-pretty-print-vars", 0x0, &opt.fdr.pretty_print_vars, 0,
                "Log FDR variables.");
    optsAddFlag("fdr-pretty-print-cg", 0x0, &opt.fdr.pretty_print_cg, 0,
                "Log FDR causal graph.");
    optsAddFlag("fdr-pot", 0x0, &opt.fdr.pot, 0,
                "Generate potential heuristics as part of the FDR output.");
    params = optsAddParams("fdr-pot-cfg", 0x0,
               "Configuration for the potential heuristic (if --fdr-pot is used).\n"
               "See --gplan-pot for the description of options.");
    hpotParams(params, &opt.fdr.pot_cfg);
    optsAddFlag("fdr-tnf", 0x0, &opt.fdr.to_tnf, 0,
                "Transform FDR to Transition Normal Form.");
    optsAddFlag("fdr-tnfm", 0x0, &opt.fdr.to_tnf_multiply, 0,
                "Transform FDR operators to TNF by multiplying its"
                " preconditions.");

    if (is_pddl_symba){
        optFDREssentialFirst(1);
    }else{
        optFDRLargestFirst(1);
    }
}

static void setExtendFDRConjOptions(void)
{
    optsStartGroup("Extending FDR with Conjunctions (Replacing P with P^C_exact)");
    optsAddStr("extend-fdr-conj-file", 0x0,
               &opt.extend_fdr_conj_file, NULL,
               "Replace FDR task P with P^C_exact where C is read from the"
               "input .toml file that must contain a key 'conj' assigining"
               " an array of arrays of strings.");
}

pddl_hpot_config_t ground_planner_pot_cfg = PDDL_HPOT_CONFIG_INIT;

static void groundPlannerHPot(void *_)
{
    if (opt.ground_planner.pot_cfg_size >= 5){
        fprintf(stderr, "Error: --gplan-pot: At most 5 configurations can be specified!\n");
        exit(-1);
        return;
    }

    opt.ground_planner.pot_cfg[opt.ground_planner.pot_cfg_size]
            = ground_planner_pot_cfg;
    if (opt.ground_planner.pot_cfg_size > 0){
        opt.ground_planner.pot_cfg[opt.ground_planner.pot_cfg_size - 1].next
            = &opt.ground_planner.pot_cfg[opt.ground_planner.pot_cfg_size];
    }
    opt.ground_planner.pot_cfg_size++;
    pddlHPotConfigInit(&ground_planner_pot_cfg);
}

static void setGroundPlannerOptions(void)
{
    for (int i = 0; i < 5; ++i)
        pddlHPotConfigInit(&opt.ground_planner.pot_cfg[i]);

    opts_params_t *params;
    optsStartGroup("Grounded Planner:");
    optsAddIntSwitch("gplan", 0x0, &opt.ground_planner.search,
                     "Search algorithm for the grounded planner, one of:\n"
                     "  none - no search (default)\n"
                     "  astar - A*\n"
                     "  gbfs - Greedy Best First Search\n"
                     "  lazy - Greedy Best First Search with lazy evaluation",
                     4,
                     "none", GROUND_PLAN_NONE,
                     "astar", GROUND_PLAN_ASTAR,
                     "gbfs", GROUND_PLAN_GBFS,
                     "lazy", GROUND_PLAN_LAZY);
    optsAddIntSwitch("gplan-h", 0x0, &opt.ground_planner.heur,
                     "Heuristic function for the grounded planner, one of:\n"
                     "  blind - Blind heuristic (default)\n"
                     "  lmc - LM-Cut\n"
                     "  max/hmax - h^max\n"
                     "  add/hadd - h^add\n"
                     "  ff/hff - FF heuristic\n"
                     "  flow - Flow heuristic\n"
                     "  pot - Potential heuristic\n"
                     "  pot-conj - Potential heuristic over conjunctions"
                     "  pot-conj-exact - Potential heuristic over conjunctions (P^C_exact compilation)",
                     13,
                     "none", GROUND_PLAN_HEUR_BLIND,
                     "blind", GROUND_PLAN_HEUR_BLIND,
                     "lmc", GROUND_PLAN_HEUR_LMC,
                     "max", GROUND_PLAN_HEUR_MAX,
                     "hmax", GROUND_PLAN_HEUR_MAX,
                     "add", GROUND_PLAN_HEUR_ADD,
                     "hadd", GROUND_PLAN_HEUR_ADD,
                     "ff", GROUND_PLAN_HEUR_FF,
                     "hff", GROUND_PLAN_HEUR_FF,
                     "flow", GROUND_PLAN_HEUR_FLOW,
                     "pot", GROUND_PLAN_HEUR_POT,
                     "pot-conj", GROUND_PLAN_HEUR_POT_CONJ,
                     "pot-conj-exact", GROUND_PLAN_HEUR_POT_CONJ_EXACT);

    params = optsAddParamsAndFn("gplan-pot", 0x0,
        "Configuration for the potential heuristic"
        " (if --gplan-h pot is used)."
        "Options:\n"
        "  D/disamb = <bool> -- turns on disambiguation (default: true)\n"
        "  W/weak-disamb = <bool> -- turns on weak disambiguation (default: false)\n"
        "  I/init = <bool> -- sets objective to initial state\n"
        "  A/all = <bool> -- sets objective to all syntactic states\n"
        "  A+I = <bool> -- A + add constraint on the initial state\n"
        "  A+I-no-hmax0 = <bool> -- as A+I but +I is without hmax0\n"
        "  S/sample-sum = <int> -- optimize for the sum over the specified number of sampled states\n"
        "  S+I = <int> -- S + add constriant on the initial state\n"
        "  M/all-mutex = <int> -- all syntactic states respecting mutexes of the given size\n"
        "  M+I = <int> -- M + add constraint on the initial state\n"
        "  sample-max = <int> -- maximum over the specified number of samples states\n"
        "  diverse = <int> -- diversification over the specified number states\n"
        "  all-mutex-cond = <int> -- conditioned ensemble\n"
        "  all-mutex-cond-rand = <int> -- conditioned on fact sets\n"
        "  all-mutex-cond-rand2 = <int>\n"
        "  hmax0 -- compute max(h^P,0)\n"
        "  hmax0-max -- ensemble of h^P and max(h^P,0)\n"
        "  lp-time-limit = <flt> -- Time limit for each LP",
        NULL,
        groundPlannerHPot
        );
    hpotParams(params, &ground_planner_pot_cfg);

    optsAddStr("gplan-pot-conj-file", 0x0, &opt.ground_planner.pot_conj_file, NULL,
               "Input configuration file for potentials over conjunctions.");
    optsAddStr("gplan-pot-conj-exact-file", 0x0, &opt.ground_planner.pot_conj_exact_file, NULL,
               "Input configuration file for potentials over conjunctions (FDR P^C_exact compilation).");

    static op_mutex_cfg_t opm_cfg = { 0 };
    params = optsAddParamsAndFn("gplan-h-opm", 0x0,
                                "Heuristics + pruning with operator mutexes.\n"
                                "Options:\n"
                                "  ts = <bool> -- use transition systems\n"
                                "  op-fact = <int> -- op-fact compilation\n"
                                "  hm-op = <int> -- h^m from each operator",
                                &opm_cfg, groundHeurOpMutex);
    optsParamsAddFlag(params, "ts", &opm_cfg.ts);
    optsParamsAddInt(params, "op-fact", &opm_cfg.op_fact);
    optsParamsAddInt(params, "hm-op", &opm_cfg.hm_op);

    optsAddStr("gplan-out", 0x0, &opt.ground_planner.plan_out, NULL,
               "Output filename for the found plan.");
    optsAddStr("gplan-o", 0x0, &opt.ground_planner.plan_out, NULL,
               "Alias for --gplan-out");
}

static void setSymbaOptions(void)
{
    opts_params_t *params;

    pddl_symbolic_task_config_t _symba_cfg = PDDL_SYMBOLIC_TASK_CONFIG_INIT;
    opt.symba.cfg = _symba_cfg;

    if (is_pddl_symba)
        opt.symba.search = SYMBA_FWBW;

    optsStartGroup("Symbolic Search:");
    optsAddIntSwitch("symba", 0x0, &opt.symba.search,
                     "Symbolic search, one of:\n"
                     "  none -- symbolic search disabled (default)\n"
                     "  fw -- forward-only search\n"
                     "  bw -- backward-only search\n"
                     "  fwbw/bi -- bi-directional search (default fot pddl-symba)",
                     5,
                     "none", SYMBA_NONE,
                     "fw", SYMBA_FW,
                     "bw", SYMBA_BW,
                     "fwbw", SYMBA_FWBW,
                     "bi", SYMBA_FWBW);
    optsAddInt("symba-fam", 0x0, &opt.symba.cfg.fam_groups, 0,
               "Infer at most the specified number of goal-aware fam-groups.");
    optsAddFlag("symba-fw-pot", 0x0, &opt.symba.cfg.fw.use_pot_heur, 0,
                "Use potential heuristics in the forward search.");
    params = optsAddParams("symba-fw-pot-cfg", 0x0,
                           "Configuration of the potential heuristic for"
                           " the forward search. (See --gplan-pot)");
    hpotParams(params, &opt.symba.cfg.fw.pot_heur_config);
    optsAddFlag("symba-bw-pot", 0x0,
                &opt.symba.cfg.bw.use_pot_heur, 0,
                "Use potential heuristics in the backward search."
                " Note that this will always be treated as inconsistent.");
    params = optsAddParams("symba-bw-pot-cfg", 0x0,
                           "Configuration of the potential heuristic for"
                           " the backward search. (See --gplan-pot)");
    hpotParams(params, &opt.symba.cfg.bw.pot_heur_config);
    optsAddFlt("symba-goal-constr-max-time", 0x0,
               &opt.symba.cfg.goal_constr_max_time, 30.f,
               "Set the time limit for applying mutex constraints on the"
               " set of goal states.");
    optsAddFlag("symba-bw-goal-split", 0x0,
                &opt.symba.cfg.bw.use_goal_splitting, 1,
                "Use goal-splitting for backward search if potential"
                " heuristic is used.");
    optsAddFlt("symba-fw-tr-merge-max-time", 0x0,
               &opt.symba.cfg.fw.trans_merge_max_time, 10.,
               "Time limit for merging transition relations in the forward"
               " direction.");
    optsAddFlt("symba-bw-tr-merge-max-time", 0x0,
               &opt.symba.cfg.bw.trans_merge_max_time, 10.,
               "Time limit for merging transition relations in the backward"
               " direction.");
    optsAddFlag("symba-bw-off", 0x0,
                &opt.symba.bw_off_if_constr_failed, 1,
                "Turn off backward search in case of bi-directional search"
                " when mutex constraints could not be applied within\n"
                "the time limit (see also --symba-goal-constr-max-time).");
    optsAddFlt("symba-bw-step-time-limit", 0x0,
               &opt.symba.cfg.bw.step_time_limit, 180.,
               "Time limit (in seconds) for a single step in the backward"
               " direction in case of bi-directional search.\n"
               "If the time limit is reached the backward search is disabled.");
    optsAddFlag("symba-log-every-step", 0x0,
                &opt.symba.cfg.log_every_step, 0,
                "Log every step of during the search.");
    optsAddStr("symba-out", 0x0, &opt.symba.out, NULL,
               "Output file for the plan.");
    optsAddFlag("symba-compile-away-conj", 0x0,
                &opt.symba.cfg.compile_away_conjunctions, 0,
                "Compile away (meta-)facts corresponding to conjunctions"
                " before search starts.");
}

static void setReversibilityOptions(void)
{
    optsStartGroup("Reversibility:");
    optsAddInt("reversibility-max-depth", 0x0, &opt.reversibility.max_depth, 1,
               "Maximum depth when searching for reversible plans"
               " (also see --report-reversibility*).");
    optsAddFlag("reversibility-use-mutex", 0x0, &opt.reversibility.use_mutex, 0,
                "Use mutexes when search for reversible plans"
                " (also see --report-reversibility*).");
}

static void setASNetsOptions(void)
{
    optsStartGroup("ASNets:");
    optsAddFlag("asnets-task", 0x0, &opt.asnets.enable, 0,
                "Produce task for ASNets.");
    optsAddStr("asnets-task-out", 0x0, &opt.asnets.out_task, NULL,
               "Set output file for the PDDL/Strips task.");
    optsAddStr("asnets-task-fdr-out", 0x0, &opt.asnets.out_fdr, NULL,
               "Set output file for the FDR/SAS FD task.");
}

static void setReportsOptions(void)
{
    optsStartGroup("Reports:");
    optsAddFlag("report-lmg", 0x0, &opt.report.lmg, 0,
                "Create report of lifted mutex groups.");
    optsAddFlag("report-reversibility-simple", 0x0,
                &opt.report.reversibility_simple, 0,
                "Compute reversibility with the \"simple\" method.");
    optsAddFlag("report-reversibility-iterative", 0x0,
                &opt.report.reversibility_iterative, 0,
                "Compute reversibility with the \"iterative\" method.");
    optsAddFlag("report-mgroups", 0x0, &opt.report.mgroups, 0,
                "Report on mutex groups.");

    optsAddStr("report-pot-conj-max-init-h-value", 0x0,
               &opt.report.pot_conj_max_init_h_value, NULL,
               "Exhaustively compute the maximum possible heuristic value"
               " for the initial state of the potential heuristic computed"
               " over conjunctions of facts.\n"
               "Possible values:\n"
               "  one-pair -- One pair of facts is added.\n"
               "  two-pair -- Two pairs of facts.\n"
               "  one-triple -- One triple of facts is added.");

    optsAddStr("report-pot-conj-exact-max-init-h-value", 0x0,
               &opt.report.pot_conj_exact_max_init_h_value, NULL,
               "Exhaustively compute the maximum possible heuristic value"
               " for the initial state of the potential heuristic computed"
               " over conjunctions of facts (P^C_exact compilation).\n"
               "Possible values:\n"
               "  one-pair -- One pair of facts is added.\n"
               "  two-pair -- Two pairs of facts.\n"
               "  one-triple -- One triple of facts is added.");

    optsAddFlag("report-pot-strips", 0x0, &opt.report.pot_strips, 0,
                "Run comparison of STRIPS and FDR-based potential heuristics.");
}

static void help(const char *argv0, FILE *fout)
{
    fprintf(fout, "Usage: %s [OPTIONS] [domain.pddl] problem.pddl\n", argv0);
    fprintf(fout, "version: %s\n", pddl_version);
    fprintf(fout, "source code: https://gitlab.com/danfis/cpddl\n");
    if (pddl_bliss_version != NULL
            || pddl_cudd_version != NULL
            || pddl_sqlite_version != NULL
            || pddl_cplex_version != NULL
            || pddl_cplex_api_version != NULL
            || pddl_cp_optimizer_version != NULL
            || pddl_gurobi_version != NULL
            || pddl_gurobi_api_version != NULL
            || pddl_highs_version != NULL
            || pddl_dynet_version != NULL){
        fprintf(fout, "Used libraries:\n");

        if (pddl_bliss_version != NULL){
            fprintf(fout, "  Bliss v%s"
                    " | License LPGL | https://users.aalto.fi/~tjunttil/bliss"
                    " (modified version from cpddl https://gitlab.com/danfis/cpddl)\n",
                    pddl_bliss_version);
        }

        if (pddl_cudd_version != NULL){
            fprintf(fout, "  CUDD v%s"
                    " | License BSD | https://davidkebo.com/cudd\n",
                    pddl_cudd_version);
        }

        if (pddl_sqlite_version != NULL){
            fprintf(fout, "  SQLite v%s"
                    " | public domain | https://www.sqlite.org\n",
                    pddl_sqlite_version);
        }

        if (pddl_cplex_version != NULL){
            fprintf(fout, "  CPLEX v%s"
                    " | Commercial | https://www.ibm.com/analytics/cplex-optimizer\n",
                    pddl_cplex_version);
        }

        if (pddl_cplex_api_version != NULL){
            fprintf(fout, "  CPLEX API v%s"
                    " | Commercial | https://www.ibm.com/analytics/cplex-optimizer\n",
                    pddl_cplex_api_version);
        }

        if (pddl_cp_optimizer_version != NULL){
            fprintf(fout, "  CPLEX CP Optimizer v%s"
                    " | Commercial | https://www.ibm.com/analytics/cplex-cp-optimizer\n",
                    pddl_cp_optimizer_version);
        }

        if (pddl_gurobi_version != NULL){
            fprintf(fout, "  Gurobi v%s"
                    " | Commercial | https://www.gurobi.com\n",
                    pddl_gurobi_version);
        }

        if (pddl_gurobi_api_version != NULL){
            fprintf(fout, "  Gurobi API v%s"
                    " | Commercial | https://www.gurobi.com\n",
                    pddl_gurobi_api_version);
        }

        if (pddl_highs_version != NULL){
            fprintf(fout, "  HiGHS v%s"
                    " | License MIT | https://highs.dev\n",
                    pddl_highs_version);
        }

        if (pddl_dynet_version != NULL){
            fprintf(fout, "  DyNet (version is not exported)"
                    " | License Apache | https://github.com/clab/dynet\n");
        }
#ifdef PDDL_MINIZINC
        fprintf(fout, "  Minizinc external binary %s v%s"
                " | License Mozilla | https://www.minizinc.org\n",
                PDDL_MINIZINC_BIN, PDDL_MINIZINC_VERSION);
#endif /* PDDL_MINIZIN */
    }
    fprintf(fout, "\n");
    fprintf(fout, "OPTIONS:\n");
    optsPrint(fout);
}

int setOptions(int argc, char *argv[], pddl_err_t *err)
{
    setBaseOptions();
    setPddlOptions();
    setLMGOptions();
    setLEndoOptions();
    setPddlPostprocessOptions();
    if (!is_pddl_pddl){
        if (!is_pddl_fdr && !is_pddl_symba)
            setLiftedPlannerOptions();
        if (!is_pddl_lplan){
            setGroundOptions();
            setMutexGroupOptions();
            setProcessStripsOptions();
            setPotConjFindOptions();
            setExtendStripsConjOptions();
            if (!is_pddl_fdr && !is_pddl_symba)
                setRedBlackOptions();
            setFDROptions();
            setExtendFDRConjOptions();
            setPotConjExactFindOptions();
            if (!is_pddl_fdr && !is_pddl_symba)
                setGroundPlannerOptions();
            if (!is_pddl_fdr)
                setSymbaOptions();
            if (!is_pddl_fdr && !is_pddl_symba)
                setReversibilityOptions();
            if (!is_pddl_fdr && !is_pddl_symba)
                setASNetsOptions();
            if (!is_pddl_fdr && !is_pddl_symba)
                setReportsOptions();
        }
    }

    if (is_pddl_pddl)
        opt.pddl.stop = 1;

    if (opts(&argc, argv) != 0)
        return -1;

    if (opt.help){
        help(argv[0], stderr);
        return -1;
    }

    if (opt.version){
        fprintf(stdout, "%s\n", pddl_version);
        return 1;
    }

    if (opt.list_lp_solvers){
        printf("Available (directly linked) LP solvers:\n");
        if (pddlLPSolverAvailable(PDDL_LP_CPLEX))
            printf("   cplex (v%s)\n", pddl_cplex_version);
        if (pddlLPSolverAvailable(PDDL_LP_GUROBI))
            printf("   gurobi (v%s)\n", pddl_gurobi_version);
        if (pddlLPSolverAvailable(PDDL_LP_HIGHS))
            printf("   highs (v%s)\n", pddl_highs_version);
        return 1;
    }

    if (opt.list_cp_solvers){
        printf("Available (directly linked) CP solvers:\n");
        if (pddlCPIsSolverAvailable(PDDL_CP_SOLVER_CPOPTIMIZER))
            printf("   cpoptimier (v%s)\n", pddl_cp_optimizer_version);
        if (pddlCPIsSolverAvailable(PDDL_CP_SOLVER_MINIZINC))
            printf("   minizinc (%s)\n", pddlCPDefaultMinizincBin());
        return 1;
    }

    if (opt.lmg.fd_monotonicity)
        opt.lmg.fd = 1;

    if (argc != 3 && argc != 2){
        for (int i = 1; i < argc; ++i){
            fprintf(stderr, "Error: Unrecognized argument: %s\n", argv[i]);
        }
        help(argv[0], stderr);
        return -1;
    }

    if (opt.log_out != NULL){
        log_out = openFile(opt.log_out);
        pddlErrLogEnable(err, log_out);
    }

    if (argc == 2){
        if (pddlFiles1(&opt.files, argv[1], err) != 0)
            PDDL_TRACE_RET(err, -1);
    }else{ // argc == 3
        if (pddlFiles(&opt.files, argv[1], argv[2], err) != 0)
            PDDL_TRACE_RET(err, -1);
    }

    if (opt.max_mem > 0){
        struct rlimit mem_limit;
        mem_limit.rlim_cur
            = mem_limit.rlim_max = opt.max_mem * 1024UL * 1024UL;
        setrlimit(RLIMIT_AS, &mem_limit);
    }

    if (opt.lifted_planner.random_seed > 0){
        opt.lifted_planner.homomorph_cfg.random_seed
                = opt.lifted_planner.random_seed;
    }

    if (opt.asnets.enable){
        if (opt.asnets.out_task == NULL)
            PDDL_ERR_RET(err, -1, "--asnets-task-out must be set!");
        if (opt.asnets.out_fdr == NULL)
            PDDL_ERR_RET(err, -1, "--asnets-fdr-out must be set!");
    }

    PDDL_LOG(err, "Version: %s", pddl_version);
    if (pddl_bliss_version != NULL)
        PDDL_LOG(err, "Linked Bliss v%s", pddl_bliss_version);

    if (pddl_cudd_version != NULL)
        PDDL_LOG(err, "Linked CUDD v%s", pddl_cudd_version);

    if (pddl_cplex_version != NULL)
        PDDL_LOG(err, "Linked CPLEX v%s", pddl_cplex_version);
    if (pddl_cplex_api_version != NULL)
        PDDL_LOG(err, "Have CPLEX API v%s", pddl_cplex_api_version);

    if (pddl_cp_optimizer_version != NULL)
        PDDL_LOG(err, "Linked CPLEX CP Optimizer v%s", pddl_cp_optimizer_version);

    if (pddl_gurobi_version != NULL)
        PDDL_LOG(err, "Linked Gurobi v%s", pddl_gurobi_version);
    if (pddl_gurobi_api_version != NULL)
        PDDL_LOG(err, "Have Gurobi API v%s", pddl_gurobi_api_version);

    if (pddl_highs_version != NULL)
        PDDL_LOG(err, "Linked HiGHS v%s", pddl_highs_version);

    if (pddl_dynet_version != NULL)
        PDDL_LOG(err, "Linked DyNet");
#ifdef PDDL_MINIZINC_BIN
    PDDL_LOG(err, "Have minizinc external binary %s v%s",
                PDDL_MINIZINC_BIN, PDDL_MINIZINC_VERSION);
#endif /* PDDL_MINIZINC_BIN */

    if (opt.link_cplex != NULL){
        if (pddlLPLoadCPLEX(opt.link_cplex, err) != 0)
            return -1;
        pddlLPSetDefault(PDDL_LP_CPLEX, err);
    }

    if (opt.link_gurobi != NULL){
        if (pddlLPLoadGurobi(opt.link_gurobi, err) != 0)
            return -1;
        pddlLPSetDefault(PDDL_LP_GUROBI, err);
    }

    return 0;
}
