/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/pddl.h"
#include "opts.h"
#include "options.h"
#include "process_strips.h"
#include "report.h"
#include "lifted_planner.h"
#include "print_to_file.h"
#include <signal.h>

#ifndef BIN_PDDL_FDR
# define BIN_PDDL_FDR 0
#endif
#ifndef BIN_PDDL_SYMBA
# define BIN_PDDL_SYMBA 0
#endif
#ifndef BIN_PDDL_PDDL
# define BIN_PDDL_PDDL 0
#endif
#ifndef BIN_PDDL_LPLAN
# define BIN_PDDL_LPLAN 0
#endif

const int is_pddl_fdr = BIN_PDDL_FDR;
const int is_pddl_symba = BIN_PDDL_SYMBA;
const int is_pddl_pddl = BIN_PDDL_PDDL;
const int is_pddl_lplan = BIN_PDDL_LPLAN;


pddl_err_t err = PDDL_ERR_INIT;
pddl_t pddl;
int pddl_set = 0;
pddl_lifted_mgroups_t lifted_mgroups;
int lifted_mgroups_set = 0;
pddl_lifted_mgroups_t monotonicity_invariants;
int monotonicity_invariants_set = 0;
pddl_strips_t strips;
int strips_set = 0;
pddl_fdr_t fdr;
int fdr_set = 0;
pddl_mgroups_t mgroup;
pddl_mutex_pairs_t mutex;
int search_started = 0;
int search_terminate = 0;

static void makeStripsUnsolvable(void)
{
    if (strips.goal_is_unreachable)
        PDDL_LOG(&err, "Goal is unreachable.");
    PDDL_LOG(&err, "Making task artificially unsolvable.");
    pddlStripsMakeUnsolvable(&strips);
    pddlMGroupsFree(&mgroup);
    pddlMGroupsInitEmpty(&mgroup);
    pddlMutexPairsFree(&mutex);
    pddlMutexPairsInitStrips(&mutex, &strips);
}


static int stepPDDL(void)
{
    pddl_config_t pddl_cfg = PDDL_CONFIG_INIT;
    pddl_cfg.force_adl = opt.pddl.force_adl;
    pddl_cfg.pedantic = opt.pddl.pedantic;
    pddl_cfg.normalize = 1;
    pddl_cfg.remove_empty_types = opt.pddl.remove_empty_types;
    pddl_cfg.compile_away_cond_eff = opt.pddl.compile_away_cond_eff;
    pddl_cfg.compile_away_disjunctive_goals = opt.pddl.compile_away_disjunctive_goals;
    pddl_cfg.enforce_unit_cost = opt.pddl.enforce_unit_cost;

    switch (opt.pddl.compile_away_neg_cond){
        case COMPILE_AWAY_NEG_COND_DYNAMIC:
            pddl_cfg.normalize_compile_away_dynamic_neg_cond = pddl_true;
            pddl_cfg.normalize_compile_away_only_goal_neg_cond = pddl_false;
            pddl_cfg.normalize_compile_away_all_neg_cond = pddl_false;
            break;

        case COMPILE_AWAY_NEG_COND_ALL:
            pddl_cfg.normalize_compile_away_dynamic_neg_cond = pddl_false;
            pddl_cfg.normalize_compile_away_only_goal_neg_cond = pddl_false;
            pddl_cfg.normalize_compile_away_all_neg_cond = pddl_true;
            break;

        case COMPILE_AWAY_NEG_COND_GOAL:
            pddl_cfg.normalize_compile_away_dynamic_neg_cond = pddl_true;
            pddl_cfg.normalize_compile_away_only_goal_neg_cond = pddl_true;
            pddl_cfg.normalize_compile_away_all_neg_cond = pddl_false;
            break;

        case COMPILE_AWAY_NEG_COND_NONE:
            pddl_cfg.normalize_compile_away_dynamic_neg_cond = pddl_false;
            pddl_cfg.normalize_compile_away_only_goal_neg_cond = pddl_false;
            pddl_cfg.normalize_compile_away_all_neg_cond = pddl_false;
            break;

        default:
            PDDL_ERR_RET(&err, -1, "Unkown option for compiling away"
                         " negative conditions");
    }

    if (pddlInit(&pddl, opt.files.domain_pddl, opt.files.problem_pddl,
                 &pddl_cfg, &err) != 0){
        PDDL_TRACE_RET(&err, -1);
    }
    pddl_set = 1;

    return 0;
}

static int stepReportLiftedMGroups(void)
{
    if (!opt.report.lmg)
        return 0;
    reportLiftedMGroups(&pddl, &err);
    return 1;
}

static int stepLiftedMGroups(void)
{
    if (lifted_mgroups_set)
        pddlLiftedMGroupsFree(&lifted_mgroups);
    if (monotonicity_invariants_set)
        pddlLiftedMGroupsFree(&monotonicity_invariants);
    pddlLiftedMGroupsInit(&lifted_mgroups);
    lifted_mgroups_set = 1;
    pddlLiftedMGroupsInit(&monotonicity_invariants);
    monotonicity_invariants_set = 1;

    if (!opt.lmg.enable){
        PDDL_LOG(&err, "Inference of lifted mutex groups disabled");
        return 0;
    }

    pddl_lifted_mgroups_infer_config_t cfg
            = PDDL_LIFTED_MGROUPS_INFER_CONFIG_INIT;
    cfg.max_candidates = opt.lmg.max_candidates;
    cfg.max_mgroups = opt.lmg.max_mgroups;
    cfg.fd = opt.lmg.fd;
    if (opt.lmg.fd_monotonicity)
        cfg.fd_monotonicity = &monotonicity_invariants;

    if (pddlLiftedMGroupsInfer(&pddl, &cfg, &lifted_mgroups, &err) != 0)
        return -1;

    PRINT_TO_FILE(&err, opt.lmg.out, "lifted mutex groups",
                  pddlLiftedMGroupsPrint(&pddl, &lifted_mgroups, fout));
    PRINT_TO_FILE(&err, opt.lmg.fd_monotonicity_out, "monotonicity invariants",
                  pddlLiftedMGroupsPrint(&pddl, &monotonicity_invariants, fout));

    return opt.lmg.stop;
}

static int stepLiftedEndomorph(void)
{
    if (!opt.lifted_endomorph.enable){
        PDDL_LOG(&err, "Lifted endomorphisms disabled");
        return 0;
    }

    PDDL_CTX(&err, "LENDO");
    int ret = 0;
    pddl_endomorphism_config_t cfg = PDDL_ENDOMORPHISM_CONFIG_INIT;
    cfg.ignore_costs = opt.lifted_endomorph.ignore_costs;
    PDDL_ISET(redundant_objs);
    pddlEndomorphismLifted(&pddl, &lifted_mgroups, &cfg,
            &redundant_objs, NULL, &err);
    if (pddlISetSize(&redundant_objs) > 0){
        pddlRemoveObjs(&pddl, &redundant_objs, &err);
        if (opt.lmg.enable)
            ret = stepLiftedMGroups();
    }
    pddlISetFree(&redundant_objs);

    PDDL_CTXEND(&err);
    return ret;
}

static int stepPddlOutput(void)
{
    if (opt.pddl.compile_in_lmg
            || opt.pddl.compile_in_lmg_mutex
            || opt.pddl.compile_in_lmg_dead_end){
        pddl_compile_in_lmg_config_t cfg = PDDL_COMPILE_IN_LMG_CONFIG_INIT;
        cfg.prune_mutex = opt.pddl.compile_in_lmg
                            || opt.pddl.compile_in_lmg_mutex;
        cfg.prune_dead_end = opt.pddl.compile_in_lmg
                                || opt.pddl.compile_in_lmg_dead_end;
        int ret = pddlCompileInLiftedMGroups(&pddl, &lifted_mgroups, &cfg, &err);
        if (ret < 0)
            return -1;
        stepLiftedMGroups();
    }

    PRINT_TO_FILE(&err, opt.pddl.domain_out, "PDDL domain file",
                  pddlPrintPDDLDomain(&pddl, fout));
    PRINT_TO_FILE(&err, opt.pddl.problem_out, "PDDL problem file",
                  pddlPrintPDDLProblem(&pddl, fout));

    if (opt.pddl.stop)
        return 1;
    return 0;
}

static int stepLiftedPlanner(void)
{
    if (opt.lifted_planner.search == LIFTED_PLAN_NONE)
        return 0;
    return liftedPlanner(&pddl, &err);
}

static void stripsCompileAwayCondEff(void)
{
    if (!opt.strips.compile_away_cond_eff)
        return;


    PDDL_CTX(&err, "STRIPS CE");
    if (!strips.has_cond_eff){
        PDDL_LOG(&err, "The task has no conditional effects.");
        PDDL_CTXEND(&err);
        return;
    }

    PDDL_LOG(&err, "Compiling away conditional effects ...");
    pddlStripsCompileAwayCondEff(&strips);
    PDDL_LOG(&err, "Conditional effects compiled away.");
    pddlStripsLogInfo(&strips, &err);
    PDDL_CTXEND(&err);
}

static int stepGround(void)
{
    if (lifted_mgroups_set
            && (opt.ground.cfg.prune_op_dead_end
                    || opt.ground.cfg.prune_op_pre_mutex)){
        opt.ground.cfg.lifted_mgroups = &lifted_mgroups;
    }

    if (pddlGround(&strips, &pddl, &opt.ground.cfg, &err) != 0){
        PDDL_LOG(&err, "Grounding failed.");
        PDDL_TRACE_RET(&err, -1);
    }

    stripsCompileAwayCondEff();

    pddlMGroupsInitEmpty(&mgroup);
    pddlMutexPairsInitStrips(&mutex, &strips);
    strips_set = 1;

    PRINT_TO_FILE(&err, opt.strips.py_out, "STRIPS as python",
                  pddlStripsPrintPython(&strips, fout));

    if (opt.strips.fam_dump != NULL){
        pddl_mgroups_t mgs;
        pddlMGroupsInitEmpty(&mgs);
        pddlFAMGroupsInferMaximal(&mgs, &strips, &err);
        pddl_mutex_pairs_t mutex;
        pddlMutexPairsInitStrips(&mutex, &strips);
        pddlMutexPairsAddMGroups(&mutex, &mgs);
        PRINT_TO_FILE(&err, opt.strips.fam_dump, "Dump fam mutexes",
            PDDL_MUTEX_PAIRS_FOR_EACH(&mutex, f1, f2)
                fprintf(fout, "%d:(%s) %d:(%s)\n",
                        f1, strips.fact.fact[f1]->name,
                        f2, strips.fact.fact[f2]->name));
        pddlMutexPairsFree(&mutex);
        pddlMGroupsFree(&mgs);
    }
    if (opt.strips.h2_dump != NULL){
        pddl_mutex_pairs_t mutex;
        pddlMutexPairsInitStrips(&mutex, &strips);
        pddlH2(&strips, &mutex, NULL, NULL, 0., &err);
        PRINT_TO_FILE(&err, opt.strips.h2_dump, "Dump h^2 mutexes",
            PDDL_MUTEX_PAIRS_FOR_EACH(&mutex, f1, f2)
                fprintf(fout, "%d:(%s) %d:(%s)\n",
                        f1, strips.fact.fact[f1]->name,
                        f2, strips.fact.fact[f2]->name));
        pddlMutexPairsFree(&mutex);
    }

    if (opt.strips.h3_dump != NULL){
        pddl_mutex_pairs_t mutex;
        pddlMutexPairsInitStrips(&mutex, &strips);
        pddlH3(&strips, &mutex, NULL, NULL, 0., 0, &err);
        PRINT_TO_FILE(&err, opt.strips.h3_dump, "Dump h^3 mutexes",
            PDDL_MUTEX_PAIRS_FOR_EACH(&mutex, f1, f2)
                fprintf(fout, "%d:(%s) %d:(%s)\n",
                        f1, strips.fact.fact[f1]->name,
                        f2, strips.fact.fact[f2]->name));
        pddlMutexPairsFree(&mutex);
    }

    return opt.strips.stop;
}

static int stepReportPotConjMaxInitHValue(void)
{
    if (opt.report.pot_conj_max_init_h_value == NULL)
        return 0;

    PDDL_CTX(&err, "Report Pot-Conj");
    int base = pddlPotConjMaxInitHValueBase(&strips, &mutex, &mgroup, &err);
    PDDL_LOG(&err, "Heuristic value for init without conjunctions: %d", base);

    int ret = 0;
    if (strcmp(opt.report.pot_conj_max_init_h_value, "one-pair") == 0){
        ret = pddlPotConjMaxInitHValueOnePair(&strips, &mutex, &mgroup, &err);

    }else if (strcmp(opt.report.pot_conj_max_init_h_value, "two-pair") == 0){
        ret = pddlPotConjMaxInitHValueTwoPairs(&strips, &mutex, &mgroup, &err);

    }else if (strcmp(opt.report.pot_conj_max_init_h_value, "one-triple") == 0){
        ret = pddlPotConjMaxInitHValueOneTriple(&strips, &mutex, &mgroup, &err);

    }else{
        PDDL_CTXEND(&err);
        PDDL_ERR_RET(&err, -1, "Unkown value '%s' for the option"
                     " --report-pot-conj-max-init-h-value",
                     opt.report.pot_conj_max_init_h_value);
    }

    if (ret >= 0){
        PDDL_LOG(&err, "Maximum heuristic value for init with conjunctions:"
                 " %d / base: %d", ret, base);
    }

    PDDL_CTXEND(&err);
    return 1;
}

static int stepReportPotConjExactMaxInitHValue(void)
{
    if (opt.report.pot_conj_exact_max_init_h_value == NULL)
        return 0;

    PDDL_CTX(&err, "Report Pot-Conj");

    pddl_mg_strips_t mg_strips;
    pddl_mutex_pairs_t fdr_mutex;
    pddlMGStripsInitFDR(&mg_strips, &fdr);
    pddlMutexPairsInitStrips(&fdr_mutex, &mg_strips.strips);
    pddlMutexPairsAddMGroups(&fdr_mutex, &mg_strips.mg);
    pddlH2(&mg_strips.strips, &fdr_mutex, NULL, NULL, 0., &err);

    int base = pddlPotConjExactMaxInitHValueBase(&fdr, &fdr_mutex, &err);
    PDDL_LOG(&err, "Heuristic value for init without conjunctions: %d", base);

    int ret = 0;
    if (strcmp(opt.report.pot_conj_exact_max_init_h_value, "one-pair") == 0){
        ret = pddlPotConjExactMaxInitHValueOnePair(&fdr, &fdr_mutex, &err);

    }else if (strcmp(opt.report.pot_conj_exact_max_init_h_value, "two-pair") == 0){
        ret = pddlPotConjExactMaxInitHValueTwoPairs(&fdr, &fdr_mutex, &err);

    }else if (strcmp(opt.report.pot_conj_exact_max_init_h_value, "one-triple") == 0){
        ret = pddlPotConjExactMaxInitHValueOneTriple(&fdr, &fdr_mutex, &err);

    }else{
        PDDL_CTXEND(&err);
        PDDL_ERR_RET(&err, -1, "Unkown value '%s' for the option"
                     " --report-pot-conj-exact-max-init-h-value",
                     opt.report.pot_conj_exact_max_init_h_value);
    }

    if (ret >= 0){
        PDDL_LOG(&err, "Maximum heuristic value for init with conjunctions:"
                 " %d / base: %d", ret, base);
    }

    pddlMutexPairsFree(&fdr_mutex);
    pddlMGStripsFree(&mg_strips);

    PDDL_CTXEND(&err);
    return 1;
}

static int stepReportMGroups(void)
{
    if (opt.report.mgroups){
        PDDL_CTX(&err, "Report MGroups");
        reportMGroups(&pddl, &strips, &err);
        PDDL_CTXEND(&err);
        return 1;
    }
    return 0;
}

static int stepGroundMGroups(void)
{
    if (!opt.ground.mgroup){
        PDDL_LOG(&err, "Grounding of lifted mutex groups disabled.");
        return 0;
    }

    PDDL_CTX(&err, "Ground LMG");
    PDDL_LOG(&err, "Grounding of lifted mutex groups ...");
    pddlMGroupsGround(&mgroup, &pddl, &lifted_mgroups, &strips);
    if (opt.ground.mgroup_remove_subsets)
        pddlMGroupsRemoveSubsets(&mgroup);
    pddlMGroupsSetExactlyOne(&mgroup, &strips);
    pddlMGroupsSetGoal(&mgroup, &strips);
    PDDL_LOG(&err, "Found %d mutex groups", mgroup.mgroup_size);
    pddlMutexPairsAddMGroups(&mutex, &mgroup);
    PDDL_LOG(&err, "Found %lu mutex pairs", mutex.num_mutex_pairs);
    PDDL_CTXEND(&err);


    PRINT_TO_FILE(&err, opt.ground.mgroup_out, "grounded mutex groups",
                  pddlMGroupsPrint(&pddl, &strips, &mgroup, fout));

    return 0;
}

static int stepInferMGroups(void)
{
    if (opt.mg.method == MG_NONE){
        PDDL_LOG(&err, "Inference of mutex groups disabled.");
        return 0;
    }

    PDDL_CTX(&err, "MG");
    if (opt.mg.method == MG_FAM){
        pddl_famgroup_config_t cfg = PDDL_FAMGROUP_CONFIG_INIT;
        cfg.maximal = opt.mg.fam_maximal;
        cfg.limit = opt.mg.fam_limit;
        cfg.time_limit = opt.mg.fam_time_limit;
        if (!opt.mg.fam_lmg){
            pddlMGroupsFree(&mgroup);
            pddlMGroupsInitEmpty(&mgroup);
        }
        PDDL_LOG(&err, "Inference of fam-groups starting with %d fam-groups",
                 mgroup.mgroup_size);
        if (pddlFAMGroupsInfer(&mgroup, &strips, &cfg, &err) != 0){
            PDDL_TRACE_RET(&err, -1);
        }
        if (opt.mg.remove_subsets)
            pddlMGroupsRemoveSubsets(&mgroup);

    }else if (opt.mg.method == MG_H2){
        pddl_mutex_pairs_t mutex;
        pddlMutexPairsInitStrips(&mutex, &strips);
        if (pddlH2(&strips, &mutex, NULL, NULL, 0., &err) != 0){
            PDDL_LOG(&err, "h^2 fw failed.");
            PDDL_TRACE_RET(&err, -1);
        }

        pddlMGroupsFree(&mgroup);
        pddlMGroupsInitEmpty(&mgroup);
        pddlMutexPairsInferMutexGroups(&mutex, &mgroup, &err);
        pddlMutexPairsFree(&mutex);
    }

    PDDL_LOG(&err, "Found %d mutex groups", mgroup.mgroup_size);

    pddlMGroupsSetExactlyOne(&mgroup, &strips);
    pddlMGroupsSetGoal(&mgroup, &strips);

    pddlMutexPairsAddMGroups(&mutex, &mgroup);
    PDDL_LOG(&err, "%lu mutex pairs so far", mutex.num_mutex_pairs);
    PDDL_CTXEND(&err);

    PRINT_TO_FILE(&err, opt.mg.out, "mutex groups",
                  pddlMGroupsPrint(&pddl, &strips, &mgroup, fout));

    if (opt.mg.cover_number){
        PDDL_LOG(&err, "Computing mutex group cover number");
        int num = pddlMGroupsCoverNumber(&mgroup, strips.fact.fact_size);
        PDDL_LOG(&err, "Mutex group cover number: %d", num);
    }

    return 0;
}

static int stepProcessStrips(void)
{
    int ret =  pddlProcessStripsExecute(&opt.strips.process, &strips,
                                        &mgroup, &mutex, &err);
    pddlProcessStripsFree(&opt.strips.process);
    if (ret != 0)
        PDDL_TRACE_RET(&err, -1);
    return ret;
}

static int stepPotConjFind(void)
{
    if (!opt.pot_conj_find.enable)
        return 0;

    pddl_set_iset_t conjs;
    pddlSetISetInit(&conjs);
    int st = pddlPotConjFind(&conjs, NULL, NULL, &strips, &mutex, &mgroup,
                             &opt.pot_conj_find.cfg,
                             &opt.pot_conj_find.pot_cfg, &err);
    pddlSetISetFree(&conjs);

    if (st != 0)
        PDDL_TRACE_RET(&err, -1);
    return 1;
}

static int stepPotConjExactFind(void)
{
    if (!opt.pot_conj_exact_find.enable)
        return 0;

    pddl_mg_strips_t mg_strips;
    pddl_mutex_pairs_t fdr_mutex;
    pddlMGStripsInitFDR(&mg_strips, &fdr);
    pddlMutexPairsInitStrips(&fdr_mutex, &mg_strips.strips);
    pddlMutexPairsAddMGroups(&fdr_mutex, &mg_strips.mg);
    pddlH2(&mg_strips.strips, &fdr_mutex, NULL, NULL, 0., &err);

    pddl_set_iset_t conjs;
    pddlSetISetInit(&conjs);
    int st = pddlPotConjExactFind(&conjs, NULL, NULL, &fdr, &fdr_mutex,
                                  &opt.pot_conj_exact_find.cfg,
                                  &opt.pot_conj_exact_find.pot_cfg, &err);
    pddlSetISetFree(&conjs);
    pddlMutexPairsFree(&fdr_mutex);
    pddlMGStripsFree(&mg_strips);

    if (st != 0)
        PDDL_TRACE_RET(&err, -1);
    return 1;
}

static int stepExtendStripsWithConjunctions(void)
{
    if (opt.extend_strips_conj_file == NULL)
        return 0;

    PDDL_CTX(&err, "Extend-Strips-Conj");
    pddl_set_iset_t conjs;
    pddlSetISetInit(&conjs);
    if (pddlSetISetLoadFromFile(&conjs, &strips, NULL,
                                opt.extend_strips_conj_file, &err) != 0){
        pddlSetISetFree(&conjs);
        PDDL_CTXEND(&err);
        PDDL_TRACE_RET(&err, -1);
    }
    pddlSetISetGenAllSubsets(&conjs, 2);

    // Set up the input conjunctions
    pddl_strips_conj_config_t cfg_conj;
    pddlStripsConjConfigInit(&cfg_conj);
    cfg_conj.mutex = &mutex;
    pddlStripsConjConfigAddConjs(&cfg_conj, &conjs);

    // Construct P^C
    pddl_strips_conj_t strips_conj;
    pddlStripsConjInit(&strips_conj, &strips, &cfg_conj, &err);

    // Replace global strips with the P^C task.
    // Note that this preserves the fact IDs from the original strips.
    pddlStripsFree(&strips);
    pddlStripsInitCopy(&strips, &strips_conj.strips);

    // Replace mutexes (mgroups can stay the same)
    pddl_mutex_pairs_t conj_mutex;
    pddlStripsConjMutexPairsInitCopy(&conj_mutex, &mutex, &strips_conj);
    pddlMutexPairsFree(&mutex);
    mutex = conj_mutex;

    // Extend mutexes with h^2
    PDDL_ISET(rm_facts);
    PDDL_ISET(rm_ops);
    pddl_mg_strips_t mg_strips;
    pddlMGStripsInit(&mg_strips, &strips, &mgroup);
    if (pddlH2FwBw(&mg_strips.strips, &mg_strips.mg, &mutex, &rm_facts,
                   &rm_ops, -1., &err) != 0){
        pddlMGStripsFree(&mg_strips);
        pddlISetFree(&rm_facts);
        pddlISetFree(&rm_ops);
        pddlStripsConjFree(&strips_conj);
        pddlStripsConjConfigFree(&cfg_conj);
        pddlSetISetFree(&conjs);
        PDDL_CTXEND(&err);
        PDDL_TRACE_RET(&err, -1);
    }

    // Prune redundant facts and operators if found any
    if (pddlISetSize(&rm_facts) > 0 || pddlISetSize(&rm_ops) > 0)
        pddlStripsReduce(&strips, &rm_facts, &rm_ops);
    if (pddlISetSize(&rm_facts) > 0){
        pddlMutexPairsReduce(&mutex, &rm_facts);
        pddlMGroupsReduce(&mgroup, &rm_facts);
    }

    pddlMGStripsFree(&mg_strips);
    pddlISetFree(&rm_facts);
    pddlISetFree(&rm_ops);

    pddlStripsConjFree(&strips_conj);
    pddlStripsConjConfigFree(&cfg_conj);
    pddlSetISetFree(&conjs);

    pddlStripsLogInfo(&strips, &err);
    PDDL_CTXEND(&err);
    return 0;
}

static void reversibilityIterativeDepth(int *skip, int max_depth, FILE *fout)
{
    for (int op_id = 0; op_id < strips.op.op_size; ++op_id){
        if (skip[op_id])
            continue;

        const pddl_strips_op_t *op = strips.op.op[op_id];

        pddl_reversibility_uniform_t rev;
        pddlReversibilityUniformInit(&rev);
        const pddl_mutex_pairs_t *m = NULL;
        if (opt.reversibility.use_mutex)
            m = &mutex;
        pddlReversibilityUniformInfer(&rev, &strips.op, op, max_depth, m);
        pddlReversibilityUniformSort(&rev);
        for (int i = 0; i < rev.plan_size; ++i){
            if (rev.plan[i].reversible_op_id == op->id
                    && pddlISetSize(&rev.plan[i].formula.pos) == 0
                    && pddlISetSize(&rev.plan[i].formula.neg) == 0){
                skip[op_id] = 1;
            }
            if (pddlIArrSize(&rev.plan[i].plan) == max_depth){
                pddlReversePlanUniformPrint(rev.plan + i, &strips.op, fout);
            }
        }
        pddlReversibilityUniformFree(&rev);
    }
}

static int stepReportReversibility(void)
{
    if (!opt.report.reversibility_simple && !opt.report.reversibility_iterative)
        return 0;

    if (opt.report.reversibility_simple){
        int max_depth = opt.reversibility.max_depth;
        PDDL_LOG(&err, "Computing reverse plans. max-depth: %d", max_depth);
        for (int op_id = 0; op_id < strips.op.op_size; ++op_id){
            const pddl_strips_op_t *op = strips.op.op[op_id];

            pddl_reversibility_uniform_t rev;
            pddlReversibilityUniformInit(&rev);
            const pddl_mutex_pairs_t *m = NULL;
            if (opt.reversibility.use_mutex)
                m = &mutex;
            pddlReversibilityUniformInfer(&rev, &strips.op, op, max_depth, m);
            pddlReversibilityUniformSort(&rev);
            pddlReversibilityUniformPrint(&rev, &strips.op, stdout);
            pddlReversibilityUniformFree(&rev);
        }
        PDDL_LOG(&err, "Reverse plans computed.");

    }else{
        int max_depth = opt.reversibility.max_depth;
        PDDL_LOG(&err, "Computing reverse plans iteratively. max-depth: %d",
                  max_depth);
        int *skip = PDDL_ZALLOC_ARR(int, strips.op.op_size);
        for (int depth = 1; depth <= max_depth; ++depth){
            PDDL_LOG(&err, "Computing for max-depth: %d", depth);
            reversibilityIterativeDepth(skip, depth, stdout);
        }
        PDDL_FREE(skip);
        PDDL_LOG(&err, "Reverse plans computed.");
    }

    return 1;
}

static int stepReportPotStrips_Strips(void)
{
    /* TODO
    PDDL_CTX(&err, "STRIPS");
    pddl_pot_t pot;
    if (pddlPotInitStrips(&pot, &strips, &mgroup) != 0){
        PDDL_CTXEND(&err);
        PDDL_ERR_RET(&err, -1, "Failed to initialize potential heuristic");
    }
    pddlPotSetObjStripsState(&pot, &strips.init);

    pddl_pot_solution_t sol;
    pddlPotSolutionInit(&sol);
    if (pddlPotSolve(&pot, &sol, &err) != 0){
        pddlPotSolutionFree(&sol);
        pddlPotFree(&pot);
        PDDL_CTXEND(&err);
        PDDL_TRACE_RET(&err, -1);
    }

    int hinit = pddlPotSolutionEvalStripsState(&sol, &strips.init);
    PDDL_LOG(&err, "h-value for init: %d", hinit);
    pddlPotSolutionFree(&sol);
    pddlPotFree(&pot);
    PDDL_CTXEND(&err);
    */
    return 0;
}

static int stepReportPotStrips_FDR(void)
{
    PDDL_CTX(&err, "FDR");

    pddl_mutex_pairs_t mutex;
    pddlMutexPairsInitStrips(&mutex, &strips);
    pddlMutexPairsAddMGroups(&mutex, &mgroup);
    pddl_fdr_config_t fdrcfg = PDDL_FDR_CONFIG_INIT;
    pddl_fdr_t fdr;
    if (pddlFDRInitFromStrips(&fdr, &strips, &mgroup, &mutex, &fdrcfg, &err) != 0){
        pddlMutexPairsFree(&mutex);
        PDDL_CTXEND(&err);
        PDDL_TRACE_RET(&err, -1);
    }

    pddl_pot_t pot;
    pddlPotInitFDR(&pot, &fdr);
    pddlPotSetObjFDRState(&pot, &fdr.var, fdr.init);

    pddl_pot_solve_config_t cfg = PDDL_POT_SOLVE_CONFIG_INIT;
    pddl_pot_solution_t sol;
    pddlPotSolutionInit(&sol);
    if (pddlPotSolve(&pot, &cfg, &sol, &err) != 0){
        pddlPotSolutionFree(&sol);
        pddlPotFree(&pot);
        pddlFDRFree(&fdr);
        pddlMutexPairsFree(&mutex);
        PDDL_CTXEND(&err);
        PDDL_TRACE_RET(&err, -1);
    }

    int hinit = pddlPotSolutionEvalFDRState(&sol, &fdr.var, fdr.init);
    PDDL_LOG(&err, "h-value for init: %d", hinit);
    pddlPotSolutionFree(&sol);
    pddlPotFree(&pot);
    pddlFDRFree(&fdr);
    pddlMutexPairsFree(&mutex);
    PDDL_CTXEND(&err);
    return 0;
}

static int stepReportPotStrips_MGStrips(void)
{
    PDDL_CTX(&err, "MG-STRIPS");
    pddl_mutex_pairs_t mutex;
    pddlMutexPairsInitStrips(&mutex, &strips);
    pddlMutexPairsAddMGroups(&mutex, &mgroup);

    pddl_mg_strips_t mg_strips;
    pddlMGStripsInit(&mg_strips, &strips, &mgroup);

    pddl_pot_t pot;
    pddlPotInit(&pot, &mg_strips, &mutex);
    pddlPotSetObjStripsState(&pot, &mg_strips.strips.init);

    pddl_pot_solve_config_t cfg = PDDL_POT_SOLVE_CONFIG_INIT;
    pddl_pot_solution_t sol;
    pddlPotSolutionInit(&sol);
    if (pddlPotSolve(&pot, &cfg, &sol, &err) != 0){
        pddlPotSolutionFree(&sol);
        pddlPotFree(&pot);
        pddlMGStripsFree(&mg_strips);
        pddlMutexPairsFree(&mutex);
        PDDL_CTXEND(&err);
        PDDL_TRACE_RET(&err, -1);
    }

    int hinit = pddlPotSolutionEvalStripsState(&sol, &mg_strips.strips.init);
    PDDL_LOG(&err, "h-value for init: %d", hinit);
    pddlPotSolutionFree(&sol);
    pddlPotFree(&pot);
    pddlMGStripsFree(&mg_strips);
    pddlMutexPairsFree(&mutex);
    PDDL_CTXEND(&err);
    return 0;
}

static int stepReportPotStrips(void)
{
    if (!opt.report.pot_strips)
        return 0;

    int ret = 1;
    PDDL_CTX(&err, "REP-POT-STRIPS");
    if (stepReportPotStrips_Strips() != 0
            || stepReportPotStrips_FDR() != 0
            || stepReportPotStrips_MGStrips() != 0){
        ret = -1;
    }
    PDDL_CTXEND(&err);
    return ret;
}

static int stepRedBlackFDR(void)
{
    if (!opt.rb_fdr.enable)
        return 0;

    if (strips.goal_is_unreachable)
        makeStripsUnsolvable();

    pddl_fdr_t fdr[opt.rb_fdr.cfg.mgroup.num_solutions];
    int num = pddlRedBlackFDRInitFromStrips(fdr, &strips, &mgroup, &mutex,
                                            &opt.rb_fdr.cfg, &err);
    for (int i = 0; i < num; ++i){
        if (opt.fdr.order_vars_cg){
            pddlFDRReorderVarsCG(fdr + i);
            PDDL_LOG(&err, "FDR[%d]: variables reordered using causal graph.", i);
        }
    }

    for (int i = 0; i < num && opt.rb_fdr.out != NULL; ++i){
        if (i > 0){
            char fn[1024];
            sprintf(fn, "%s.%d", opt.rb_fdr.out, i);
            PRINT_TO_FILE(&err, fn, "FDR", pddlFDRPrintFD(fdr + i, &mgroup, 1, fout));
        }else{
            PRINT_TO_FILE(&err, opt.rb_fdr.out, "FDR",
                          pddlFDRPrintFD(fdr, &mgroup, 1, fout));
        }
    }

    for (int i = 0; i < num; ++i)
        pddlFDRFree(fdr + i);
    return 1;
}

static void printPotentials(const pddl_fdr_t *fdr,
                            const pddl_pot_solutions_t *pot,
                            FILE *fout)
{
    fprintf(fout, "%d\n", pot->sol_size);
    for (int pi = 0; pi < pot->sol_size; ++pi){
        const double *w = pot->sol[pi].pot;
        fprintf(fout, "begin_potentials\n");
        for (int fi = 0; fi < fdr->var.global_id_size; ++fi){
            const pddl_fdr_val_t *fval = fdr->var.global_id_to_val[fi];
            fprintf(fout, "%d %d %.20f\n",
                    fval->var_id, fval->val_id, w[fi]);
        }
        fprintf(fout, "end_potentials\n");
    }
}

static int stepExtendFDRWithConjunctions(void)
{
    if (opt.extend_fdr_conj_file == NULL)
        return 0;

    PDDL_CTX(&err, "Extend-FDR-Conj");
    pddl_set_iset_t conjs;
    pddlSetISetInit(&conjs);
    if (pddlSetISetLoadFromFile(&conjs, NULL, &fdr,
                                opt.extend_fdr_conj_file, &err) != 0){
        pddlSetISetFree(&conjs);
        PDDL_CTXEND(&err);
        PDDL_TRACE_RET(&err, -1);
    }
    pddlSetISetGenAllSubsets(&conjs, 2);

    // Infer mutexes
    pddl_mg_strips_t mg_strips;
    pddl_mutex_pairs_t fdr_mutex;
    pddlMGStripsInitFDR(&mg_strips, &fdr);
    pddlMutexPairsInitStrips(&fdr_mutex, &mg_strips.strips);
    pddlMutexPairsAddMGroups(&fdr_mutex, &mg_strips.mg);
    pddlH2(&mg_strips.strips, &fdr_mutex, NULL, NULL, 0., &err);
    pddlMGStripsFree(&mg_strips);

    // Set up the input conjunctions
    pddl_fdr_conj_exact_config_t cfg_conj;
    pddlFDRConjExactConfigInit(&cfg_conj);
    cfg_conj.mutex = &fdr_mutex;
    pddlFDRConjExactConfigAddConjs(&cfg_conj, &conjs);

    // Construct P^C_exact
    pddl_fdr_conj_exact_t fdr_conj;
    pddlFDRConjExactInit(&fdr_conj, &fdr, &cfg_conj, &err);

    // Replace global fdr with the P^C_exact task.
    // Note that this preserves the fact IDs from the original strips.
    pddlFDRFree(&fdr);
    pddlFDRInitCopy(&fdr, &fdr_conj.fdr);

    // Replace mutexes (mgroups can stay the same)
    pddl_mutex_pairs_t conj_mutex;
    pddlFDRConjExactMutexPairsInitCopy(&conj_mutex, &fdr_mutex, &fdr_conj);
    pddlMutexPairsFree(&fdr_mutex);
    fdr_mutex = conj_mutex;

    // Extend mutexes with h^2
    PDDL_ISET(rm_facts);
    PDDL_ISET(rm_ops);
    pddlMGStripsInitFDR(&mg_strips, &fdr);
    if (pddlH2FwBw(&mg_strips.strips, &mg_strips.mg, &fdr_mutex, &rm_facts,
                   &rm_ops, -1., &err) != 0){
        pddlMGStripsFree(&mg_strips);
        pddlISetFree(&rm_facts);
        pddlISetFree(&rm_ops);
        pddlMutexPairsFree(&fdr_mutex);
        pddlFDRConjExactFree(&fdr_conj);
        pddlFDRConjExactConfigFree(&cfg_conj);
        pddlSetISetFree(&conjs);
        PDDL_CTXEND(&err);
        PDDL_TRACE_RET(&err, -1);
    }

    // Prune redundant facts and operators if found any
    if (pddlISetSize(&rm_facts) > 0 || pddlISetSize(&rm_ops) > 0)
        pddlFDRReduce(&fdr, NULL, &rm_facts, &rm_ops);
    if (pddlISetSize(&rm_facts) > 0){
        pddlMutexPairsReduce(&fdr_mutex, &rm_facts);
        pddlMGroupsReduce(&mgroup, &rm_facts);
    }

    pddlMGStripsFree(&mg_strips);
    pddlISetFree(&rm_facts);
    pddlISetFree(&rm_ops);

    pddlMutexPairsFree(&fdr_mutex);
    pddlFDRConjExactFree(&fdr_conj);
    pddlFDRConjExactConfigFree(&cfg_conj);
    pddlSetISetFree(&conjs);

    pddlStripsLogInfo(&strips, &err);
    PDDL_CTXEND(&err);

    return 0;
}

static int stepFDR(void)
{
    if (strips.goal_is_unreachable)
        makeStripsUnsolvable();

    pddlFDRInitFromStrips(&fdr, &strips, &mgroup, &mutex, &opt.fdr.cfg, &err);
    fdr_set = 1;

    if (opt.fdr.order_vars_cg){
        pddlFDRReorderVarsCG(&fdr);
        PDDL_LOG(&err, "FDR variables reordered using causal graph.");
    }

    if (stepExtendFDRWithConjunctions() != 0)
        PDDL_TRACE_RET(&err, -1);


    if (opt.fdr.to_tnf || opt.fdr.to_tnf_multiply){
        PDDL_CTX(&err, "FDR-to-TNF");
        if (opt.fdr.to_tnf){
            PDDL_LOG(&err, "Constructing TNF (ops: %d)", fdr.op.op_size);
        }else if (opt.fdr.to_tnf_multiply){
            PDDL_LOG(&err, "Constructing TNF-multiply (ops: %d)", fdr.op.op_size);
        }

        pddl_mg_strips_t mg_strips;
        pddl_mutex_pairs_t fdr_mutex;
        pddlMGStripsInitFDR(&mg_strips, &fdr);
        pddlMutexPairsInitStrips(&fdr_mutex, &mg_strips.strips);
        pddlMutexPairsAddMGroups(&fdr_mutex, &mg_strips.mg);
        pddlH2(&mg_strips.strips, &fdr_mutex, NULL, NULL, 0., &err);

        pddl_fdr_t fdr_old = fdr;
        unsigned flags = 0;
        if (opt.fdr.to_tnf_multiply)
            flags = PDDL_FDR_TNF_MULTIPLY_OPS;
        if (pddlFDRInitTransitionNormalForm(&fdr, &fdr_old, &fdr_mutex,
                                            flags, &err) != 0){
            pddlMutexPairsFree(&fdr_mutex);
            pddlMGStripsFree(&mg_strips);
            PDDL_CTXEND(&err);
            PDDL_TRACE_RET(&err, -1);
        }
        if (opt.fdr.to_tnf){
            PDDL_LOG(&err, "Constructed TNF, ops: %d", fdr.op.op_size);
        }else if (opt.fdr.to_tnf_multiply){
            PDDL_LOG(&err, "Constructed TNF-multiply, ops: %d", fdr.op.op_size);
        }

        pddlMutexPairsFree(&fdr_mutex);
        pddlMGStripsFree(&mg_strips);
        pddlFDRFree(&fdr_old);
        PDDL_CTXEND(&err);
    }

    PRINT_TO_FILE(&err, opt.fdr.out, "FDR", pddlFDRPrintFD(&fdr, &mgroup, 1, fout));

    if (opt.fdr.pot){
        pddl_mg_strips_t mg_strips;
        pddl_mutex_pairs_t mutex;
        opt.fdr.pot_cfg.fdr = &fdr;
        if (pddlHPotConfigNeedMGStrips(&opt.fdr.pot_cfg)
                || pddlHPotConfigNeedMutex(&opt.fdr.pot_cfg)){
            pddlMGStripsInitFDR(&mg_strips, &fdr);
            opt.fdr.pot_cfg.mg_strips = &mg_strips;
        }

        if (pddlHPotConfigNeedMutex(&opt.fdr.pot_cfg)){
            pddlMutexPairsInitStrips(&mutex, &mg_strips.strips);
            pddlH2(&mg_strips.strips, &mutex, NULL, NULL, -1, &err);
            opt.fdr.pot_cfg.mutex = &mutex;
        }

        pddl_pot_solutions_t pot;
        pddlPotSolutionsInit(&pot);

        if (pddlHPot(&pot, &opt.fdr.pot_cfg, &err) != 0){
            PDDL_ERR_RET(&err, -1, "Cannot find potential heuristic");
        }else if (pot.sol_size == 0){
            PDDL_ERR_RET(&err, -1, "Could not find a single potential function");
        }
        APPEND_TO_FILE(&err, opt.fdr.out, "FDR Pot",
                       printPotentials(&fdr, &pot, fout));
        pddlPotSolutionsFree(&pot);

        if (opt.fdr.pot_cfg.mg_strips != NULL)
            pddlMGStripsFree(&mg_strips);
        if (opt.fdr.pot_cfg.mutex != NULL)
            pddlMutexPairsFree(&mutex);
    }

    if (opt.fdr.pretty_print_vars)
        pddlFDRVarsPrintTable(&fdr.var, 150, NULL, &err);
    if (opt.fdr.pretty_print_cg){
        pddl_cg_t cg;
        pddlCGInit(&cg, &fdr.var, &fdr.op, 0);
        pddlCGPrintAsciiGraph(&cg, NULL, &err);
        pddlCGFree(&cg);
    }
    return 0;
}

static int stepGroundPlanner(void)
{
    if (opt.ground_planner.search == GROUND_PLAN_NONE)
        return 0;

    PDDL_CTX(&err, "GPLAN");
    pddl_heur_config_t heur_cfg = PDDL_HEUR_CONFIG_INIT;
    heur_cfg.fdr = &fdr;
    switch (opt.ground_planner.heur){
        case GROUND_PLAN_HEUR_LMC:
            heur_cfg.heur = PDDL_HEUR_LM_CUT;
            PDDL_LOG(&err, "Heuristic: lmc");
            break;
        case GROUND_PLAN_HEUR_MAX:
            heur_cfg.heur = PDDL_HEUR_HMAX;
            PDDL_LOG(&err, "Heuristic: hmax");
            break;
        case GROUND_PLAN_HEUR_ADD:
            heur_cfg.heur = PDDL_HEUR_HADD;
            PDDL_LOG(&err, "Heuristic: hadd");
            break;
        case GROUND_PLAN_HEUR_FF:
            heur_cfg.heur = PDDL_HEUR_HFF;
            PDDL_LOG(&err, "Heuristic: hff");
            break;
        case GROUND_PLAN_HEUR_FLOW:
            heur_cfg.heur = PDDL_HEUR_FLOW;
            PDDL_LOG(&err, "Heuristic: flow");
            break;
        case GROUND_PLAN_HEUR_POT:
            heur_cfg.heur = PDDL_HEUR_POT;
            PDDL_LOG(&err, "Heuristic: pot");
            break;
        case GROUND_PLAN_HEUR_POT_CONJ:
            heur_cfg.heur = PDDL_HEUR_POT_CONJ;
            heur_cfg.pot_conj_file = opt.ground_planner.pot_conj_file;
            PDDL_LOG(&err, "Heuristic: pot-conj");
            break;
        case GROUND_PLAN_HEUR_POT_CONJ_EXACT:
            heur_cfg.heur = PDDL_HEUR_POT_CONJ_EXACT;
            heur_cfg.pot_conj_exact_file = opt.ground_planner.pot_conj_exact_file;
            PDDL_LOG(&err, "Heuristic: pot-conj-exact");
            break;
        case GROUND_PLAN_HEUR_BLIND:
        default:
            heur_cfg.heur = PDDL_HEUR_BLIND;
            PDDL_LOG(&err, "Heuristic: blind");
    }

    pddl_bool_t is_pot = opt.ground_planner.heur == GROUND_PLAN_HEUR_POT
                            || opt.ground_planner.heur == GROUND_PLAN_HEUR_POT_CONJ
                            || opt.ground_planner.heur == GROUND_PLAN_HEUR_POT_CONJ_EXACT;

    if (is_pot)
        heur_cfg.pot = opt.ground_planner.pot_cfg[0];

    pddl_mg_strips_t mg_strips;
    pddl_mutex_pairs_t mutex;

    int need_mutex = 0;
    int need_mg_strips = 0;

    if (opt.ground_planner.heur == GROUND_PLAN_HEUR_POT_CONJ_EXACT)
        need_mutex = 1;

    if (opt.ground_planner.heur_op_mutex)
        need_mutex = need_mg_strips = 1;

    if (is_pot && pddlHPotConfigNeedMutex(&heur_cfg.pot))
        need_mutex = 1;

    if (need_mutex || (is_pot && pddlHPotConfigNeedMGStrips(&heur_cfg.pot)))
        need_mg_strips = 1;

    if (need_mg_strips){
        pddlMGStripsInitFDR(&mg_strips, &fdr);
        heur_cfg.mg_strips = &mg_strips;
    }

    if (need_mutex){
        pddlMutexPairsInitStrips(&mutex, &mg_strips.strips);
        pddlMutexPairsAddMGroups(&mutex, &mg_strips.mg);
        pddlH2(&mg_strips.strips, &mutex, NULL, NULL, -1, &err);
        heur_cfg.mutex = &mutex;
    }

    pddl_heur_t *heur = NULL;
    if (opt.ground_planner.heur_op_mutex){
        pddl_op_mutex_pairs_t opm;
        pddlOpMutexPairsInit(&opm, &mg_strips.strips);

        if (opt.ground_planner.heur_op_mutex_ts > 0){
            size_t max_mem = 0;
            pddlOpMutexInferTransSystems(&opm, &mg_strips, &mutex,
                                         opt.ground_planner.heur_op_mutex_ts,
                                         max_mem, 1, &err);

        }else if (opt.ground_planner.heur_op_mutex_op_fact > 0){
            pddlOpMutexInferHmOpFactCompilation(&opm, opt.ground_planner.heur_op_mutex_op_fact,
                                                &mg_strips.strips, &err);

        }else if (opt.ground_planner.heur_op_mutex_hm_op > 0){
            pddlOpMutexInferHmFromEachOp(&opm,
                                         opt.ground_planner.heur_op_mutex_hm_op,
                                         &mg_strips.strips, &mutex,
                                         NULL, &err);
        }else{
            // TODO
        }

        pddl_heur_config_t opm_cfg = PDDL_HEUR_CONFIG_INIT;
        opm_cfg.fdr = heur_cfg.fdr;
        opm_cfg.mg_strips = heur_cfg.mg_strips;
        opm_cfg.mutex = heur_cfg.mutex;
        opm_cfg.heur = PDDL_HEUR_OP_MUTEX;
        opm_cfg.op_mutex.op_mutex = &opm;
        opm_cfg.op_mutex.cfg = &heur_cfg;
        heur = pddlHeur(&opm_cfg, &err);
    }else{
        heur = pddlHeur(&heur_cfg, &err);
    }

    if (heur == NULL)
        PDDL_TRACE_RET(&err, -1);

    pddl_search_config_t search_cfg = PDDL_SEARCH_CONFIG_INIT;
    search_cfg.fdr = &fdr;
    search_cfg.heur = heur;
    switch (opt.ground_planner.search){
        case GROUND_PLAN_ASTAR:
            PDDL_LOG(&err, "Search: astar");
            search_cfg.alg = PDDL_SEARCH_ASTAR;
            break;
        case GROUND_PLAN_GBFS:
            PDDL_LOG(&err, "Search: gbfs");
            search_cfg.alg = PDDL_SEARCH_GBFS;
            break;
        case GROUND_PLAN_LAZY:
            PDDL_LOG(&err, "Search: lazy");
            search_cfg.alg = PDDL_SEARCH_LAZY;
            break;
        default:
            PDDL_PANIC("Unknown planner %d", opt.ground_planner.search);
    }

    pddl_search_t *search = pddlSearchNew(&search_cfg, &err);
    if (search == NULL)
        PDDL_TRACE_RET(&err, -1);

    int ret = pddlSearchInitStep(search);
    search_started = 1;

    pddl_timer_t info_timer;
    pddlTimerStart(&info_timer);
    for (int step = 1; ret == PDDL_SEARCH_CONT; ++step){
        if (search_terminate){
            pddlSearchStatLog(search, &err);
            PDDL_LOG(&err, "Search aborted.");
            pddlSearchDel(search);
            pddlHeurDel(heur);
            PDDL_CTXEND(&err);
            return -1;
        }

        ret = pddlSearchStep(search);

        // TODO: parametrize
        if (step >= 100){
            pddlTimerStop(&info_timer);
            if (pddlTimerElapsedInSF(&info_timer) >= 1.){
                pddlSearchStatLog(search, &err);
                pddlTimerStart(&info_timer);
            }
            step = 0;
        }
    }
    pddlSearchStatLog(search, &err);

    if (ret == PDDL_SEARCH_UNSOLVABLE){
        PDDL_LOG(&err, "Problem is unsolvable.");

    }else if (ret == PDDL_SEARCH_FOUND){
        PDDL_LOG(&err, "Plan found.");
        pddl_plan_t plan;
        pddlPlanInit(&plan);
        pddlSearchExtractPlan(search, &plan);
        pddlPlanUpdateAuxiliaryOps(&plan, &fdr);
        PDDL_LOG(&err, "Plan Cost: %d", plan.cost);
        PDDL_LOG(&err, "Plan Length: %d", plan.length);
        PRINT_TO_FILE(&err, opt.ground_planner.plan_out, "plan",
                      pddlPlanPrint(&plan, &fdr.op, fout));
        pddlPlanFree(&plan);
    }else{
        PDDL_PANIC("Unkown return status: %d", ret);
    }

    if (search_terminate){
        PDDL_LOG(&err, "Search aborted.");
        pddlSearchDel(search);
        pddlHeurDel(heur);
        PDDL_CTXEND(&err);
        return -1;
    }

    pddlSearchDel(search);
    pddlHeurDel(heur);
    if (heur_cfg.mg_strips != NULL)
        pddlMGStripsFree(&mg_strips);
    if (heur_cfg.mutex != NULL)
        pddlMutexPairsFree(&mutex);
    return 0;
}

static int fdrHasTNFOps(const pddl_fdr_t *fdr)
{
    for (int oi = 0; oi < fdr->op.op_size; ++oi){
        const pddl_fdr_op_t *op = fdr->op.op[oi];
        for (int i = 0; i < op->eff.fact_size; ++i){
            if (!pddlFDRPartStateIsSet(&op->pre, op->eff.fact[i].var))
                return 0;
        }
        for (int cei = 0; cei < op->cond_eff_size; ++cei){
            const pddl_fdr_op_cond_eff_t *ce = op->cond_eff + cei;
            for (int i = 0; i < ce->eff.fact_size; ++i){
                if (!pddlFDRPartStateIsSet(&ce->pre, ce->eff.fact[i].var))
                    return 0;
            }
        }
    }

    return 1;
}

static void symbaPlanPrint(const pddl_fdr_t *fdr,
                           const pddl_iarr_t *plan,
                           int cost,
                           FILE *fout)
{
    fprintf(fout, ";; Cost: %d\n", cost);
    fprintf(fout, ";; Length: %d\n", pddlIArrSize(plan));
    int op_id;
    PDDL_IARR_FOR_EACH(plan, op_id){
        const pddl_fdr_op_t *op = fdr->op.op[op_id];
        fprintf(fout, "(%s) ;; cost: %ld\n", op->name, (long)op->cost);
    }
}

static int stepSymba(void)
{
    if (opt.symba.search == SYMBA_NONE)
        return 0;

    PDDL_CTX(&err, "SYMBA");

    int is_tnf = fdrHasTNFOps(&fdr);
    if (opt.symba.cfg.fw.use_pot_heur){
        if (is_tnf){
            PDDL_LOG(&err, "fw: Using consistent potential heuristic");
        }else{
            opt.symba.cfg.fw.use_pot_heur = 0;
            opt.symba.cfg.fw.use_pot_heur_inconsistent = 1;
            PDDL_LOG(&err, "fw: Using inconsistent potential heuristic");
        }
    }else{
        PDDL_LOG(&err, "fw: Using blind heuristic");
    }

    if (opt.symba.cfg.bw.use_pot_heur){
        if (is_tnf && opt.symba.cfg.bw.use_goal_splitting){
            PDDL_LOG(&err, "bw: Using consistent potential heuristic"
                       " (with goal splitting)");
        }else{
            opt.symba.cfg.bw.use_pot_heur = 0;
            opt.symba.cfg.bw.use_pot_heur_inconsistent = 1;
            PDDL_LOG(&err, "bw: Using inconsistent potential heuristic");
        }
    }else{
        PDDL_LOG(&err, "bw: Using blind heuristic");
    }

    if (opt.symba.search == SYMBA_FW){
        opt.symba.cfg.fw.enabled = 1;
        opt.symba.cfg.bw.enabled = 0;
    }else if (opt.symba.search == SYMBA_BW){
        opt.symba.cfg.fw.enabled = 0;
        opt.symba.cfg.bw.enabled = 1;
    }else{
        opt.symba.cfg.fw.enabled = 1;
        opt.symba.cfg.bw.enabled = 1;
    }

    pddl_symbolic_task_t *task;
    if ((task = pddlSymbolicTaskNew(&fdr, &opt.symba.cfg, &err)) == NULL)
        PDDL_TRACE_RET(&err, -1);

    PDDL_IARR(plan);
    int res;
    if (opt.symba.search == SYMBA_FWBW
            && opt.symba.bw_off_if_constr_failed
            && pddlSymbolicTaskGoalConstrFailed(task)){
        PDDL_LOG(&err, "Switching to fw-only search.");
        res = pddlSymbolicTaskSearchFw(task, &plan, &err);
    }else{
        res = pddlSymbolicTaskSearch(task, &plan, &err);
    }


    if (res == PDDL_SYMBOLIC_PLAN_FOUND){
        int cost = 0;
        int op;
        PDDL_IARR_FOR_EACH(&plan, op)
            cost += fdr.op.op[op]->cost;
        PDDL_LOG(&err, "Plan Cost: %d", cost);
        PDDL_LOG(&err, "Plan Length: %d", pddlIArrSize(&plan));
        PRINT_TO_FILE(&err, opt.symba.out, "plan",
                      symbaPlanPrint(&fdr, &plan, cost, fout));

    }else if (res == PDDL_SYMBOLIC_PLAN_NOT_EXIST){
        PDDL_LOG(&err, "Task proved unsolvable.");
    }

    pddlIArrFree(&plan);
    pddlSymbolicTaskDel(task);

    PDDL_CTXEND(&err);
    return 0;
}

void freeData(void)
{
    if (fdr_set)
        pddlFDRFree(&fdr);
    if (strips_set){
        pddlStripsFree(&strips);
        pddlMGroupsFree(&mgroup);
        pddlMutexPairsFree(&mutex);
    }
    if (monotonicity_invariants_set)
        pddlLiftedMGroupsFree(&monotonicity_invariants);
    if (lifted_mgroups_set)
        pddlLiftedMGroupsFree(&lifted_mgroups);
    if (pddl_set)
        pddlFree(&pddl);
    if (log_out != NULL)
        closeFile(log_out);
    optsFree();
}

int main(int argc, char *argv[])
{
    pddl_timer_t timer;
    pddlTimerStart(&timer);
    int ret = 0;
    if ((ret = setOptions(argc, argv, &err)) != 0
            || (ret = stepPDDL()) != 0
            || (ret = stepReportLiftedMGroups()) != 0
            || (ret = stepLiftedMGroups()) != 0
            || (ret = stepLiftedEndomorph()) != 0
            || (ret = stepPddlOutput()) != 0
            || (ret = stepLiftedPlanner()) != 0
            || (ret = stepGround()) != 0
            || (ret = stepReportMGroups()) != 0
            || (ret = stepGroundMGroups()) != 0
            || (ret = stepReportPotStrips()) != 0
            || (ret = stepInferMGroups()) != 0
            || (ret = stepProcessStrips()) != 0
            || (ret = stepPotConjFind()) != 0
            || (ret = stepExtendStripsWithConjunctions()) != 0
            || (ret = stepReportPotConjMaxInitHValue()) != 0
            || (ret = stepReportReversibility()) != 0
            || (ret = stepRedBlackFDR()) != 0
            || (ret = stepFDR()) != 0
            || (ret = stepReportPotConjExactMaxInitHValue()) != 0
            || (ret = stepPotConjExactFind()) != 0
            || (ret = stepGroundPlanner()) != 0
            || (ret = stepSymba()) != 0){
        if (ret < 0){
            pddlErrPrint(&err, 1, stderr);
            freeData();
            return -1;
        }
    }

    pddlTimerStop(&timer);
    PDDL_LOG(&err, "Overall Elapsed Time: %.4fs",
             pddlTimerElapsedInSF(&timer));
    freeData();
    return 0;
}
