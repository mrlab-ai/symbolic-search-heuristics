/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/strips_ground_datalog.h"
#include "pddl/strips_ground_clingo.h"
#include "pddl/strstream.h"
#include "pddl/subprocess.h"
#include "pddl/strips_maker.h"

#ifdef PDDL_CLINGO
# include <clingo.h>

static void clingoLogger(clingo_warning_t code,
                         char const *message,
                         void *userdata)
{
    if (message == NULL || *message == '\x0')
        return;

    pddl_err_t *err = userdata;
    size_t msglen = strlen(message);

    char *msg = ALLOC_ARR(char, msglen);
    char *line = msg;
    memcpy(msg, message, sizeof(char) * msglen);
    int end = 0;
    while (end < msglen){
        for (; msg[end] != '\n' && msg[end] != '\x0'; ++end);
        msg[end] = '\x0';
        LOG(err, "Clingo Log: %s", line);

        ++end;
        line = msg + end;
    }

    FREE(msg);
}

static char *clingoEncode(const pddl_t *pddl,
                          const pddl_action_t *action,
                          const pddl_strips_t *strips,
                          const char *lpopt_bin,
                          pddl_err_t *err)
{
    char *enc = NULL;
    size_t enc_size;
    FILE *enc_fin = pddl_strstream(&enc, &enc_size);

    // Add all relevants facts
    // TODO: Here restrict to predicates that are mentioned in the action's
    // precondition.
    for (int fact_id = 0; fact_id < strips->fact.fact_size; ++fact_id){
        const pddl_fact_t *fact = strips->fact.fact[fact_id];
        ASSERT(fact->ground_atom != NULL);
        const pddl_ground_atom_t *atom = fact->ground_atom;

        fprintf(enc_fin, "p%d(", atom->pred);
        for (int i = 0; i < atom->arg_size; ++i){
            if (i > 0)
                fprintf(enc_fin, ",");
            fprintf(enc_fin, "o%d", atom->arg[i]);
        }
        fprintf(enc_fin, ").\n");
    }

    // Encode types
    PDDL_ISET(types);
    for (int parami = 0; parami < action->param.param_size; ++parami){
        const pddl_param_t *param = action->param.param + parami;
        pddlISetAdd(&types, param->type);
    }

    int type_id;
    PDDL_ISET_FOR_EACH(&types, type_id){
        int size = pddlTypeNumObjs(&pddl->type, type_id);
        for (int i = 0; i < size; ++i){
            int obj_id = pddlTypeGetObj(&pddl->type, type_id, i);
            fprintf(enc_fin, "type%d(o%d).\n", type_id, obj_id);
        }
    }
    pddlISetFree(&types);

    // Encode selection of variables
    for (int parami = 0; parami < action->param.param_size; ++parami){
        const pddl_param_t *param = action->param.param + parami;

        fprintf(enc_fin, "1{ v%d(X) : type%d(X) }1.\n",
                parami, param->type);

    }

    // Encode the preconditions of the action.
    const pddl_fm_atom_t *catom;
    pddl_fm_const_it_atom_t it;
    PDDL_FM_FOR_EACH_ATOM(action->pre, &it, catom){
        fprintf(enc_fin, ":- ");

        PDDL_ISET(params);
        for (int i = 0; i < catom->arg_size; ++i){
            if (catom->arg[i].param >= 0)
                pddlISetAdd(&params, catom->arg[i].param);
        }
        int param_id;
        PDDL_ISET_FOR_EACH(&params, param_id)
            fprintf(enc_fin, "v%d(X%d), ", param_id, param_id);
        pddlISetFree(&params);

        if (catom->pred == pddl->pred.eq_pred){
            // Clingo supports equality predicates directly
            if (catom->arg[0].param >= 0){
                fprintf(enc_fin, "X%d", catom->arg[0].param);
            }else{
                fprintf(enc_fin, "o%d", catom->arg[0].obj);
            }
            if (catom->neg){
                fprintf(enc_fin, " = ");
            }else{
                fprintf(enc_fin, " != ");
            }
            if (catom->arg[1].param >= 0){
                fprintf(enc_fin, "X%d", catom->arg[1].param);
            }else{
                fprintf(enc_fin, "o%d", catom->arg[1].obj);
            }

        }else{
            if (!catom->neg)
                fprintf(enc_fin, "not ");
            fprintf(enc_fin, "p%d(", catom->pred);
            for (int i = 0; i < catom->arg_size; ++i){
                if (i > 0)
                    fprintf(enc_fin, ",");
                if (catom->arg[i].param >= 0){
                    fprintf(enc_fin, "X%d", catom->arg[i].param);
                }else{
                    fprintf(enc_fin, "o%d", catom->arg[i].obj);
                }
            }
            fprintf(enc_fin, ")");
        }
        fprintf(enc_fin, ".\n");
    }

    // Add show directives
    for (int parami = 0; parami < action->param.param_size; ++parami)
        fprintf(enc_fin, "#show v%d/1.\n", parami);

    fflush(enc_fin);
    fclose(enc_fin);
    LOG(err, "Encoded ASP program: %zu bytes", enc_size);

    char *out = NULL;
    out = ALLOC_ARR(char, enc_size + 1);
    memcpy(out, enc, sizeof(char) * enc_size);
    out[enc_size] = '\x0';

    free(enc);
    return out;
}

static int clingoInsertAction(int action_id,
                              const clingo_model_t *model,
                              pddl_strips_maker_t *strips_maker,
                              pddl_err_t *err)
{
    size_t symbols_size;
    if (!clingo_model_symbols_size(model, clingo_show_type_shown, &symbols_size)){
        ERR_RET(err, -1, "Obtaining number of symbols from the model failed: %d:%s",
                clingo_error_code(),
                (clingo_error_message() != NULL ? clingo_error_message() : ""));
    }
    if (symbols_size == 0)
        return 0;

    clingo_symbol_t *symbols = ALLOC_ARR(clingo_symbol_t, symbols_size);
    if (!clingo_model_symbols(model, clingo_show_type_shown,
                              symbols, symbols_size)){
        ERR_RET(err, -1, "Obtaining symbols from the model failed: %d:%s",
                clingo_error_code(),
                (clingo_error_message() != NULL ? clingo_error_message() : ""));
    }

    int action_args[symbols_size];
    for (int si = 0; si < symbols_size; ++si){
        clingo_symbol_t symbol = symbols[si];

        const char *name;
        clingo_symbol_name(symbol, &name);
        if (name == NULL || *name != 'v')
            continue;

        ASSERT(name != NULL && *name == 'v');
        int vari = atoi(name + 1);
        ASSERT(vari >= 0);

        const clingo_symbol_t *args;
        size_t args_size;
        clingo_symbol_arguments(symbol, &args, &args_size);
        ASSERT(args_size == 1);

        const char *objname;
        clingo_symbol_name(args[0], &objname);
        ASSERT(objname != NULL && *objname == 'o');
        int obj_id = atoi(objname + 1);
        action_args[vari] = obj_id;
    }
    FREE(symbols);

    pddlStripsMakerAddAction(strips_maker, action_id, 0, action_args, NULL);

    return 0;
}

static int clingoSolve(int action_id,
                       const char *prog,
                       pddl_strips_maker_t *strips_maker,
                       pddl_err_t *err)
{
    clingo_control_t *ctl = NULL;
    // --models=0 ensures that all models all listed
    //const char *cl_argv[] = { "-V", "--output-debug=all", "--models=0" };
    const char *cl_argv[] = { "--models=0" };
    int cl_args = sizeof(cl_argv) / sizeof(const char *);
    if (!clingo_control_new(cl_argv, cl_args, clingoLogger, err, 100, &ctl)){
        ERR_RET(err, -1, "Initialization of clingo failed: %d:%s",
                clingo_error_code(),
                (clingo_error_message() != NULL ? clingo_error_message() : ""));
    }

    // Pass the encoded datalog program to clingo
    if (!clingo_control_add(ctl, "base", NULL, 0, prog)){
        clingo_control_free(ctl);
        ERR_RET(err, -1, "Problem with encoding of the datalog program: %d:%s",
                clingo_error_code(),
                (clingo_error_message() != NULL ? clingo_error_message() : ""));
    }
    LOG(err, "ASP program parsed.");

    // Ground the program
    LOG(err, "Grounding of ASP program...");
    clingo_part_t parts[] = {{ "base", NULL, 0 }};
    if (!clingo_control_ground(ctl, parts, 1, NULL, NULL)){
        clingo_control_free(ctl);
        ERR_RET(err, -1, "Grounding failed: %d:%s",
                clingo_error_code(),
                (clingo_error_message() != NULL ? clingo_error_message() : ""));
    }
    LOG(err, "ASP program grounded.");

    // Start solving of the program
    clingo_solve_handle_t *handle;
    if (!clingo_control_solve(ctl, clingo_solve_mode_yield, NULL, 0, NULL,
                              NULL, &handle)){
        clingo_control_free(ctl);
        ERR_RET(err, -1, "Solving failed: %d:%s",
                clingo_error_code(),
                (clingo_error_message() != NULL ? clingo_error_message() : ""));
    }

    // Iterate over all solutions
    int action_count = 0;
    for (;;){
        if (!clingo_solve_handle_resume(handle)){
            clingo_control_free(ctl);
            ERR_RET(err, -1, "Solving failed: %d:%s",
                    clingo_error_code(),
                    (clingo_error_message() != NULL ? clingo_error_message() : ""));
        }

        clingo_model_t const *model;
        if (!clingo_solve_handle_model(handle, &model)){
            clingo_control_free(ctl);
            ERR_RET(err, -1, "Obtaining model failed: %d:%s",
                    clingo_error_code(),
                    (clingo_error_message() != NULL ? clingo_error_message() : ""));
        }
        if (model == NULL)
            break;

        clingo_model_type_t model_type;
        clingo_model_type(model, &model_type);
        ASSERT(model_type == clingo_model_type_stable_model);

        if (clingoInsertAction(action_id, model, strips_maker, err) != 0){
            clingo_control_free(ctl);
            TRACE_RET(err, -1);
        }
        ++action_count;
    }

    clingo_solve_result_bitset_t result;
    if (!clingo_solve_handle_get(handle, &result)){
        clingo_control_free(ctl);
        TRACE_RET(err, -1);
    }
    clingo_solve_handle_close(handle);
    ASSERT(result != clingo_solve_result_satisfiable);

    LOG(err, "Found actions: %d", action_count);

    clingo_control_free(ctl);
    return 0;
}

#endif /* PDDL_CLINGO */

int pddlStripsGroundClingo(pddl_strips_t *strips,
                           const pddl_t *pddl,
                           const pddl_ground_config_t *cfg,
                           pddl_err_t *err)
{
#ifndef PDDL_CLINGO
    ERR_RET(err, -1, "Clingo grounder requires Clingo library; cpddl must be"
            " re-compiled with the Clingo support.");
#else /* PDDL_CLINGO */
    if (cfg->ground_only_facts){
        CTX(err, "Ground Clingo");
        LOG(err, "Passing the Gringo grounder...");
        int ret = pddlStripsGroundGringo(strips, pddl, cfg, err);
        CTXEND(err);
        return ret;
    }

    pddl_strips_maker_t strips_maker;
    pddlStripsMakerInit(&strips_maker, pddl);

    CTX(err, "Ground Clingo");
    LOG(err, "Ground all facts while ignoring actions.");
    pddl_strips_t strips_facts;
    pddl_ground_config_t facts_cfg = PDDL_GROUND_CONFIG_INIT;
    facts_cfg.method = PDDL_GROUND_GRINGO;
    facts_cfg.lifted_mgroups = NULL;
    facts_cfg.remove_static_facts = pddl_false;
    facts_cfg.keep_action_args = pddl_false;
    facts_cfg.keep_all_static_facts = pddl_true;
    facts_cfg.ground_only_facts = pddl_true;
    facts_cfg.gringo_lpopt = cfg->gringo_lpopt;
    if (pddlStripsGroundGringo(&strips_facts, pddl, &facts_cfg, err) != 0){
        pddlStripsMakerFree(&strips_maker);
        CTXEND(err);
        TRACE_RET(err, -1);
    }

    pddlStripsMakerAddInit(&strips_maker, pddl);
    for (int fact_id = 0; fact_id < strips_facts.fact.fact_size; ++fact_id){
        const pddl_fact_t *fact = strips_facts.fact.fact[fact_id];
        ASSERT(fact->ground_atom != NULL);
        int pred = fact->ground_atom->pred;
        const int *arg = fact->ground_atom->arg;
        int argsize = fact->ground_atom->arg_size;

        if (pddlPredIsStatic(&pddl->pred.pred[pred])){
            pddlStripsMakerAddStaticAtomPred(&strips_maker, pred,
                                             arg, argsize, NULL);
        }else{
            pddlStripsMakerAddAtomPred(&strips_maker, pred, arg, argsize, NULL);
        }

    }

    for (int action_id = 0; action_id < pddl->action.action_size; ++action_id){
        const pddl_action_t *action = pddl->action.action + action_id;
        CTX(err, "Action %s", action->name);
        char *enc = clingoEncode(pddl, action, &strips_facts, cfg->gringo_lpopt, err);
        //fprintf(stderr, "ENC: %s\n", enc);
        if (enc == NULL){
            pddlStripsMakerFree(&strips_maker);
            CTXEND(err);
            CTXEND(err);
            TRACE_RET(err, -1);
        }

        if (clingoSolve(action_id, enc, &strips_maker, err) != 0){
            pddlStripsMakerFree(&strips_maker);
            FREE(enc);
            CTXEND(err);
            CTXEND(err);
            TRACE_RET(err, -1);
        }

        FREE(enc);
        CTXEND(err);
    }

    pddlStripsFree(&strips_facts);
    LOG(err, "Grounding of all facts finished. num facts: %d",
        strips->fact.fact_size);

    int ret = pddlStripsMakerMakeStrips(&strips_maker, pddl, cfg, strips, err);
    pddlStripsMakerFree(&strips_maker);
    if (ret != 0){
        CTXEND(err);
        TRACE_RET(err, -1);
    }

    LOG(err, "Grounding finished.");
    CTXEND(err);
    pddlStripsLogInfo(strips, err);
    return 0;
#endif /* PDDL_CLINGO */
}
