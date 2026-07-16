/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/pddl.h"
#include "pddl/opts.h"
#include "pddl/asnets_convert_from_sql.h"
#include "print_to_file.h"

enum {
    CMD_TRAIN = 1,
    CMD_EVAL,
    CMD_GEN_FD_ENC,
    CMD_GEN_FD_OSP_ENC,
    CMD_CONVERT_OLD_MODEL,
    CMD_GEN_TRAIN_CONFIG_FILE,
};

static struct {
    pddl_opts_t o;
    pddl_bool_t help;
    pddl_bool_t version;
    int max_mem;
    char *log_out;

    struct {
        char *in_file;
        char *model_file_prefix;

        int seed;
        pddl_bool_t cont;
    } train;

    struct {
        char *model_file;
        char *pddl_domain;
        char **pddl_problem;
        int pddl_problem_size;

        int max_steps;
        char *out;
        pddl_bool_t verbose;
    } eval;

    struct {
        char *pddl_domain;
        char *pddl_problem;
        char *out;
    } gen_enc;

    struct {
        char *in;
        char *out;
    } convert;

    struct {
        char *out;
    } gen_cfg;

    int cmd;
} opt;



static pddl_err_t err = PDDL_ERR_INIT;
static FILE *log_out = NULL;

static void help(const char *argv0, FILE *fout)
{
    fprintf(fout, "version: %s\n", pddl_version);
    if (opt.cmd != 0){
        pddlOptsPrintCmd(&opt.o, argv0, opt.cmd, stdout);
    }else{
        pddlOptsPrint(&opt.o, argv0, stdout);
    }
}

static int parseOpts(int argc, char *argv[])
{
    opt.log_out = "stdout";

    pddlOptsBool(&opt.o, "help", 'h', &opt.help, "Print this help.");
    pddlOptsBool(&opt.o, "version", 0x0, &opt.version,
                 "Print version and exit.");
    pddlOptsInt(&opt.o, "max-mem", 0x0, &opt.max_mem,
                "Maximum memory in MB (if >0).");
    pddlOptsStr(&opt.o, "log-out", 0x0, &opt.log_out,
                "Set output file for logs.");

    pddlOptsCmd(&opt.o, CMD_TRAIN, "train",
                "Train an ASNets model according to the configuration.");
    pddlOptsReqStr(&opt.o, "config.toml", &opt.train.in_file,
                   "Input configuration file.");
    pddlOptsReqStr(&opt.o, "model-file-prefix", &opt.train.model_file_prefix,
                   "After each epoch, the current model is written into a"
                   " file prefixed with this string.");
    pddlOptsInt(&opt.o, "seed", 0x0, &opt.train.seed,
                "Overwrites the random_seed parameter from the configutation file.");
    pddlOptsBool(&opt.o, "continue", 'c', &opt.train.cont,
                 "Continue training from the given model, i.e., the input"
                 " file {config.toml} is treated as a full model with stored"
                 " weights, and it is used loaded before first training epoch.");

    pddlOptsCmd(&opt.o, CMD_EVAL, "eval",
        "Evaluate the given ASNets model for all specified problems");
    pddlOptsReqStr(&opt.o, "model.toml", &opt.eval.model_file,
                   "Input model file.");
    pddlOptsReqStr(&opt.o, "domain.pddl", &opt.eval.pddl_domain,
                   "PDDL domain file.");
    pddlOptsReqStrRemainder(&opt.o, "problem.pddl",
                            &opt.eval.pddl_problem,
                            &opt.eval.pddl_problem_size,
                            "One or more PDDL problem files to be evaluated.");
    pddlOptsInt(&opt.o, "max-steps", 0x0, &opt.eval.max_steps,
                "Sets the maximum number of steps a policy can take"
                " (it overwrites 'policy_rollout_limit' option in the input file.");
    pddlOptsStr(&opt.o, "out", 0x0, &opt.eval.out,
                "If set, it specifies a {prefix} for files where found plans"
                " are written, namely they are written to {prefix}-{task_index}.plan.");
    pddlOptsBool(&opt.o, "verbose", 0x0, &opt.eval.verbose,
                 "Increases logging.");

    pddlOptsCmd(&opt.o, CMD_GEN_FD_ENC, "gen-fd-encoding",
        "Generate FD encoding of the specified task as it is used by ASNets.");
    pddlOptsReqStr(&opt.o, "domain.pddl", &opt.gen_enc.pddl_domain,
                   "PDDL domain file.");
    pddlOptsReqStr(&opt.o, "problem.pddl", &opt.gen_enc.pddl_problem,
                   "PDDL problem file.");
    pddlOptsReqStr(&opt.o, "output.fd", &opt.gen_enc.out,
                   "Output file in the FD format.");

    pddlOptsCmd(&opt.o, CMD_GEN_FD_OSP_ENC, "gen-fd-osp-encoding",
                "Same as gen-fd-encoding, but it uses a variant of FD format"
                " for OSP tasks and all goals are specified as soft-goals.");
    pddlOptsReqStr(&opt.o, "domain.pddl", &opt.gen_enc.pddl_domain,
                   "PDDL domain file.");
    pddlOptsReqStr(&opt.o, "problem.pddl", &opt.gen_enc.pddl_problem,
                   "PDDL problem file.");
    pddlOptsReqStr(&opt.o, "output.fd", &opt.gen_enc.out,
                   "Output file in the FD format.");

    pddlOptsCmd(&opt.o, CMD_CONVERT_OLD_MODEL, "convert-old-model",
                "Convert old sqlite-based model files to the current format.");
    pddlOptsReqStr(&opt.o, "input.sql", &opt.convert.in,
                   "Input model file in sql format.");
    pddlOptsReqStr(&opt.o, "output.toml", &opt.convert.out,
                   "Output model file in TOML.");

    pddlOptsCmd(&opt.o, CMD_GEN_TRAIN_CONFIG_FILE, "gen-train-config-file",
                "Generates a training config file with default values.");
    pddlOptsReqStr(&opt.o, "output.toml", &opt.gen_cfg.out,
                   "Output config file.");

    if (argc <= 1){
        help(argv[0], stdout);
        return -1;
    }

    int st = pddlOptsParse(&opt.o, argc, argv, &opt.cmd);

    if (opt.help){
        help(argv[0], stdout);
        return -1;
    }

    if (st != 0)
        return -1;
    return 0;
}

static int train(void)
{
    pddl_asnets_config_t cfg;
    if (pddlASNetsConfigInitFromFile(&cfg, opt.train.in_file, &err) != 0)
        PDDL_TRACE_RET(&err, -1);

    if (opt.train.seed > 0)
        cfg.random_seed = opt.train.seed;

    cfg.save_model_prefix = opt.train.model_file_prefix;

    pddl_asnets_t *asnets = pddlASNetsNew(&cfg, &err);
    if (asnets == NULL)
        PDDL_TRACE_RET(&err, -1);

    if (opt.train.cont){
        if (pddlASNetsLoad(asnets, opt.train.in_file, &err) != 0){
            pddlASNetsDel(asnets);
            PDDL_TRACE_RET(&err, -1);
        }
    }

    int ret = pddlASNetsTrain(asnets, &err);
    pddlASNetsConfigFree(&cfg);
    pddlASNetsDel(asnets);
    return ret;
}

struct eval_stats {
    pddl_bool_t solved;
    int plan_length;
    int osp_goal_size;
    int osp_msgs_size;
};

static int evaluate(void)
{
    pddl_asnets_config_t cfg_new;
    if (pddlASNetsConfigInitFromFile(&cfg_new, opt.eval.model_file, &err) != 0)
        PDDL_TRACE_RET(&err, -1);

    cfg_new.domain_pddl = PDDL_STRDUP(opt.eval.pddl_domain);
    pddlASNetsConfigRemoveProblems(&cfg_new);

    pddl_asnets_t *asnets = pddlASNetsNew(&cfg_new, &err);
    pddlASNetsConfigFree(&cfg_new);
    if (asnets == NULL)
        PDDL_TRACE_RET(&err, -1);

    if (pddlASNetsLoad(asnets, opt.eval.model_file, &err) != 0){
        pddlASNetsDel(asnets);
        PDDL_TRACE_RET(&err, -1);
    }

    const pddl_asnets_config_t *cfg = pddlASNetsGetConfig(asnets);
    const pddl_asnets_lifted_task_t *lt = pddlASNetsGetLiftedTask(asnets);

    int policy_rollout_limit = cfg->policy_rollout_limit;
    if (opt.eval.max_steps > 0)
        policy_rollout_limit = opt.eval.max_steps;

    int num_probs = opt.eval.pddl_problem_size;
    struct eval_stats stats[num_probs];

    int num_solved = 0;
    for (int pi = 0; pi < num_probs; ++pi){
        PDDL_CTX(&err, "Task %d", pi);
        pddl_asnets_ground_task_t gt;
        int st = pddlASNetsGroundTaskInit(&gt, lt, opt.eval.pddl_domain,
                                          opt.eval.pddl_problem[pi],
                                          cfg, &err);
        if (st != 0){
            pddlASNetsDel(asnets);
            PDDL_CTXEND(&err);
            PDDL_TRACE_RET(&err, -1);
        }

        PDDL_LOG(&err, "Rollout of policy ...");
        pddl_asnets_policy_rollout_t rollout;
        pddlASNetsPolicyRolloutInit(&rollout, &gt);
        if (opt.eval.verbose){
            pddlASNetsPolicyRolloutVerbose(asnets, &rollout, &gt,
                                           policy_rollout_limit, &err);
        }else{
            pddlASNetsPolicyRollout(asnets, &rollout, &gt,
                                    policy_rollout_limit, &err);
        }
        PDDL_LOG(&err, "Found plan: %s", (rollout.found_plan ? "true" : "false"));
        PDDL_LOG(&err, "Num states: %d", rollout.states.num_states);
        PDDL_LOG(&err, "Num ops: %d", pddlIArrSize(&rollout.ops));
        PDDL_LOG(&err, "Plan size: %d", pddlIArrSize(&rollout.plan));
        PDDL_LOG(&err, "OSP reached goal size: %d",
                 rollout.osp_reached_goal_size);

        stats[pi].solved = rollout.found_plan;
        stats[pi].plan_length = -1;
        if (rollout.found_plan)
            stats[pi].plan_length = pddlIArrSize(&rollout.plan);
        stats[pi].osp_goal_size = rollout.osp_reached_goal_size;
        stats[pi].osp_msgs_size = gt.osp_msgs_size_for_init;

        if (stats[pi].solved)
            num_solved += 1;

        if (rollout.found_plan && opt.eval.out != NULL){
            char fn[512];
            snprintf(fn, 511, "%s-%06d.plan", opt.eval.out, pi);
            FILE *fout = fopen(fn, "w");
            if (fout != NULL){
                int op_id;
                PDDL_IARR_FOR_EACH(&rollout.plan, op_id){
                    fprintf(fout, "(%s)\n", gt.fdr.op.op[op_id]->name);
                }
                fclose(fout);

            }else{
                pddlASNetsPolicyRolloutFree(&rollout);
                pddlASNetsGroundTaskFree(&gt);
                pddlASNetsDel(asnets);
                PDDL_CTXEND(&err);
                PDDL_ERR_RET(&err, -1, "Could not open file %s", fn);
            }
        }

        pddlASNetsPolicyRolloutFree(&rollout);
        pddlASNetsGroundTaskFree(&gt);
        PDDL_CTXEND(&err);
    }

    for (int pi = 0; pi < num_probs; ++pi){
        if (cfg->osp_all_soft_goals){
            PDDL_LOG(&err, "Task %d solved: %s, length: %d, goal size: %d/%d :: %s",
                     pi, (stats[pi].solved ? "true" : "false" ),
                     stats[pi].plan_length, stats[pi].osp_goal_size,
                     stats[pi].osp_msgs_size, opt.eval.pddl_problem[pi]);
        }else{
            PDDL_LOG(&err, "Task %d solved: %s, length: %d :: %s",
                     pi, (stats[pi].solved ? "true" : "false"),
                     stats[pi].plan_length, opt.eval.pddl_problem[pi]);
        }
    }

    PDDL_LOG(&err, "Solved: %d / %d", num_solved, num_probs);
    PDDL_LOG(&err, "Success rate: %.2f", (float)num_solved / (float)num_probs);

    pddlASNetsDel(asnets);
    return 0;
}

static int genFDEnc(int osp)
{
    pddl_asnets_lifted_task_t lt;
    if (pddlASNetsLiftedTaskInit(&lt, opt.gen_enc.pddl_domain, &err) != 0){
        pddlErrPrint(&err, 1, stderr);
        return -1;
    }

    pddl_asnets_config_t cfg;
    pddlASNetsConfigInit(&cfg);

    pddl_asnets_ground_task_t gt;
    if (pddlASNetsGroundTaskInit(&gt, &lt, opt.gen_enc.pddl_domain,
                opt.gen_enc.pddl_problem, &cfg, &err) != 0){
        pddlASNetsLiftedTaskFree(&lt);
        pddlErrPrint(&err, 1, stderr);
        return -1;
    }

    pddl_fdr_write_config_t wcfg = PDDL_FDR_WRITE_CONFIG_INIT;
    wcfg.filename = opt.gen_enc.out;
    if (osp)
        wcfg.osp_all_soft_goals = pddl_true;
    wcfg.fd = pddl_true;
    pddlFDRWrite(&gt.fdr, &wcfg);

    pddlASNetsGroundTaskFree(&gt);
    pddlASNetsLiftedTaskFree(&lt);
    return 0;
}

static int convertOldModel(void)
{
    return pddlASNetsConvertFromSql(opt.convert.in, opt.convert.out, &err);
}

static int genTrainConfigFile(void)
{
    FILE *fout = fopen(opt.gen_cfg.out, "w");
    if (fout == NULL)
        PDDL_ERR_RET(&err, -1, "Could not open file %s", opt.gen_cfg.out);

    pddl_asnets_config_t cfg;
    pddlASNetsConfigInit(&cfg);
    pddlASNetsConfigWrite(&cfg, fout);
    fclose(fout);
    return 0;
}

int main(int argc, char *argv[])
{
    pddl_timer_t timer;
    pddlTimerStart(&timer);

    pddlOptsInit(&opt.o);
    if (parseOpts(argc, argv) != 0){
        if (pddlErrIsSet(&err))
            pddlErrPrint(&err, 1, stderr);
        pddlOptsFree(&opt.o);
        return -1;
    }

    if (opt.log_out != NULL){
        log_out = openFile(opt.log_out);
        pddlErrLogEnable(&err, log_out);
    }

    if (opt.max_mem > 0){
        struct rlimit mem_limit;
        mem_limit.rlim_cur = mem_limit.rlim_max = opt.max_mem * 1024UL * 1024UL;
        setrlimit(RLIMIT_AS, &mem_limit);
    }

    PDDL_LOG(&err, "Version: %s", pddl_version);

    int ret = 0;
    switch (opt.cmd){
        case CMD_TRAIN:
            ret = train();
            break;

        case CMD_EVAL:
            ret = evaluate();
            break;

        case CMD_GEN_FD_ENC:
            ret = genFDEnc(0);
            break;

        case CMD_GEN_FD_OSP_ENC:
            ret = genFDEnc(1);
            break;

        case CMD_CONVERT_OLD_MODEL:
            ret = convertOldModel();
            break;

        case CMD_GEN_TRAIN_CONFIG_FILE:
            ret = genTrainConfigFile();
            break;

        default:
            fprintf(stderr, "Error: Unkown command.\n");
            ret = -1;
    }

    if (ret != 0 && pddlErrIsSet(&err))
        pddlErrPrint(&err, 1, stderr);

    if (log_out != NULL)
        closeFile(log_out);

    pddlOptsFree(&opt.o);
    return ret;
}
