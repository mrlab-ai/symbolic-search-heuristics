/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/lp.h"
#include "pddl/libs_info.h"
#include "_lp.h"

#ifdef PDDL_GUROBI
#include <dlfcn.h>
#include <gurobi_c.h>
#include "_lp_compressed_row_problem.h"

typedef void (*api_version_t)(int *majorP, int *minorP, int *technicalP);
typedef int (*api_emptyenv_t)(GRBenv **envP);
typedef int (*api_startenv_t)(GRBenv *env);
typedef void (*api_freeenv_t)(GRBenv *env);
typedef int (*api_newmodel_t)(GRBenv *env, GRBmodel **modelP, const char *Pname, int numvars,
                              double *obj, double *lb, double *ub, char *vtype,
                              char **varnames);
typedef int (*api_freemodel_t)(GRBmodel *model);
typedef int (*api_addconstrs_t)(GRBmodel *model, int numconstrs, int numnz,
                                int *cbeg, int *cind, double *cval,
                                char *sense, double *rhs, char **constrnames);
typedef int (*api_addgenconstrIndicator_t)(GRBmodel *model, const char *name,
                                           int binvar, int binval, int nvars,
                                           const int *ind, const double *val,
                                           char sense, double rhs);
typedef int (*api_updatemodel_t)(GRBmodel *model);
typedef int (*api_optimize_t)(GRBmodel *model);
typedef int (*api_setintparam_t)(GRBenv *env, const char *paramname, int value);
typedef int (*api_setdblparam_t)(GRBenv *env, const char *paramname, double value);
typedef int (*api_setintattr_t)(GRBmodel *model, const char *attrname, int newvalue);
typedef int (*api_getintattr_t)(GRBmodel *model, const char *attrname, int *valueP);
typedef int (*api_getdblattr_t)(GRBmodel *model, const char *attrname, double *valueP);
typedef int (*api_setdblattrelement_t)(GRBmodel *model, const char *attrname,
                                       int element, double valueP);
typedef int (*api_getdblattrelement_t)(GRBmodel *model, const char *attrname,
                                       int element, double *valueP);
typedef const char * (*api_geterrormsg_t)(GRBenv *env);
typedef int (*api_cbget_t)(void *cbdata, int where, int what, void *resultP);
typedef int (*api_setcallbackfunc_t)(GRBmodel *model,
                                     int (__stdcall *cb)(CB_ARGS),
                                     void  *usrdata);

struct gurobi_api {
    api_version_t version;
    api_emptyenv_t emptyenv;
    api_startenv_t startenv;
    api_freeenv_t freeenv;
    api_newmodel_t newmodel;
    api_freemodel_t freemodel;
    api_addconstrs_t addconstrs;
    api_addgenconstrIndicator_t addgenconstrIndicator;
    api_updatemodel_t updatemodel;
    api_optimize_t optimize;
    api_setintparam_t setintparam;
    api_setdblparam_t setdblparam;
    api_setintattr_t setintattr;
    api_getintattr_t getintattr;
    api_getdblattr_t getdblattr;
    api_setdblattrelement_t setdblattrelement;
    api_getdblattrelement_t getdblattrelement;
    api_geterrormsg_t geterrormsg;
    api_cbget_t cbget;
    api_setcallbackfunc_t setcallbackfunc;
};

#ifdef PDDL_GUROBI_ONLY_API
static struct gurobi_api api = { 0 };
const char * const pddl_gurobi_version = NULL;
const char * const pddl_gurobi_api_version =
    PDDL_TOSTR(GRB_VERSION_MAJOR.GRB_VERSION_MINOR.GRB_VERSION_TECHNICAL);

#else /* PDDL_GUROBI_ONLY_API */

static struct gurobi_api api = {
    GRBversion,
    GRBemptyenv,
    GRBstartenv,
    GRBfreeenv,
    GRBnewmodel,
    GRBfreemodel,
    GRBaddconstrs,
    GRBaddgenconstrIndicator,
    GRBupdatemodel,
    GRBoptimize,
    GRBsetintparam,
    GRBsetdblparam,
    GRBsetintattr,
    GRBgetintattr,
    GRBgetdblattr,
    GRBsetdblattrelement,
    GRBgetdblattrelement,
    GRBgeterrormsg,
    GRBcbget,
    GRBsetcallbackfunc
};

const char * const pddl_gurobi_version =
    PDDL_TOSTR(GRB_VERSION_MAJOR.GRB_VERSION_MINOR.GRB_VERSION_TECHNICAL);
const char * const pddl_gurobi_api_version = NULL;
#endif /* PDDL_GUROBI_ONLY_API */

#define LOAD(NAME) \
    do { \
        api.NAME = (api_##NAME##_t)dlsym(dl_handle, "GRB" #NAME); \
        if (api.NAME == NULL){ \
            ZEROIZE(&api); \
            dlclose(dl_handle); \
            ERR_RET(err, -1, "Could not find GRB" #NAME " function: %s", dlerror()); \
        } \
    } while (0)

static void *dl_handle = NULL;
static char dl_version[32] = { 0 };
int pddlLPLoadGurobi(const char *so_fn, pddl_err_t *err)
{
    if (pddl_gurobi_version != NULL){
        ERR_RET(err, -1, "Cannot dynamically load Gurobi library, because"
                " it was already linked at compile time.");
    }

    if (dl_handle != NULL)
        dlclose(dl_handle);

    dl_version[0] = '\x0';
    dl_handle = dlopen(so_fn, RTLD_NOW);
    if (dl_handle == NULL)
        ERR_RET(err, -1, "Could not load Gurobi library: %s", dlerror());

    LOAD(version);
    LOAD(emptyenv);
    LOAD(startenv);
    LOAD(freeenv);
    LOAD(newmodel);
    LOAD(freemodel);
    LOAD(addconstrs);
    LOAD(addgenconstrIndicator);
    LOAD(updatemodel);
    LOAD(optimize);
    LOAD(setintparam);
    LOAD(setdblparam);
    LOAD(setintattr);
    LOAD(getintattr);
    LOAD(getdblattr);
    LOAD(setdblattrelement);
    LOAD(getdblattrelement);
    LOAD(geterrormsg);
    LOAD(cbget);
    LOAD(setcallbackfunc);

    int major, minor, technical;
    api.version(&major, &minor, &technical);
    snprintf(dl_version, 31, "%d.%d.%d", major, minor, technical);
    dl_version[31] = '\x0';
    LOG(err, "Gurobi library successfully loaded from %s. version: %s",
        so_fn, dl_version);

    return 0;
}

pddl_bool_t pddlLPIsGurobiAvailable(void)
{
    return api.version != NULL;
}

const char * const pddlLPGurobiVersion(void)
{
    if (api.version == NULL)
        return NULL;
    if (dl_version[0] == '\x0')
        return pddl_gurobi_version;
    return dl_version;
}

static pddl_lp_status_t grbErr(GRBenv *env, GRBmodel *model,
                               pddl_lp_solution_t *sol, const char *s,
                               pddl_err_t *err)
{
    if (env != NULL){
        ERR(err, "Gurobi: %s: %s", s, api.geterrormsg(env));
    }else{
        ERR(err, "Gurobi: %s", s);
    }
    if (model != NULL)
        api.freemodel(model);
    if (env != NULL)
        api.freeenv(env);

    sol->solved_optimally = pddl_false;
    sol->solved_suboptimally = pddl_false;
    sol->unsolvable = pddl_false;
    sol->not_solved = pddl_false;
    sol->error = pddl_true;
    sol->timed_out = pddl_false;
    return PDDL_LP_STATUS_ERR;
}

static int cb(GRBmodel *model, void *cbdata, int where, void *ud)
{
    pddl_err_t *err = ud;
    if (where == GRB_CB_MESSAGE){
        char *msg;
        if (api.cbget(cbdata, where, GRB_CB_MSG_STRING, (void *)&msg) == 0){
            char out[128];
            int msglen = strlen(msg);
            msglen = PDDL_MIN(128, msglen - 1);
            memcpy(out, msg, msglen * sizeof(char));
            out[msglen] = '\x0';
            LOG(err, "log: %s", out);
        }

    }else if (where == GRB_CB_MIPSOL){
        double obj_val = 0;
        if (api.cbget(cbdata, where, GRB_CB_MIPSOL_OBJ, &obj_val) == 0){
            LOG(err, "log: New solution. objective value: %f", obj_val);
        }

    }
    return 0;
}


pddl_lp_status_t pddlLPSolveGurobi(const pddl_lp_t *lp,
                                   pddl_lp_solution_t *sol,
                                   pddl_err_t *err)
{
    CTX_NO_TIME(err, "LP-Gurobi");
    int major, minor, technical;
    api.version(&major, &minor, &technical);
    LOG(err, "version: %d.%d.%d", major, minor, technical);
    LOG(err, "problem: cols: %d, rows: %d, maximize: %s, time_limit: %.2f,"
        " tune-int-op-pot: %s",
        lp->col_size, lp->row_size, F_BOOL(lp->cfg.maximize), lp->cfg.time_limit,
        F_BOOL(lp->cfg.tune_int_operator_potential));
    GRBenv *env = NULL;
    GRBmodel *model = NULL;
    int ret;

    _pddlLPSolutionInit(sol, lp);

    if ((ret = api.emptyenv(&env)) != 0){
        char msg[1024];
        snprintf(msg, 1024, "Could not create environment (error code: %d)", ret);
        msg[1023] = '\x0';
        CTXEND(err);
        return grbErr(NULL, NULL, sol, msg, err);
    }

    // Disable output
    if (api.setintparam(env, "OutputFlag", 0) != 0){
        CTXEND(err);
        return grbErr(env, NULL, sol, "Could not set OutputFlag", err);
    }

    if ((ret = api.startenv(env)) != 0){
        if (ret == GRB_ERROR_NO_LICENSE)
            WARN(err, "It seems license file wasn't found. Don't forget to"
                  " set GRB_LICENSE_FILE environment variable.");
        CTXEND(err);
        return grbErr(env, NULL, sol, "Could not start Gurobi environment", err);
    }

    // Set number of threads -- this apparently has to be done before model
    // is created.
    int num_threads = PDDL_MAX(1, lp->cfg.num_threads);
    if (api.setintparam(env, "Threads", num_threads) != 0){
        CTXEND(err);
        return grbErr(env, model, sol, "Could not set number of threads", err);
    }

    // Set up time limit
    if (lp->cfg.time_limit > 0.){
        if (api.setdblparam(env, "TimeLimit", lp->cfg.time_limit) != 0){
            CTXEND(err);
            return grbErr(env, model, sol, "Could not set time limit", err);
        }
    }

    pddl_lp_compressed_row_problem_t P;
    compressedRowProblemInit(&P, lp, 
                             GRB_CONTINUOUS,
                             GRB_INTEGER,
                             GRB_BINARY,
                             pddl_false,
                             -GRB_INFINITY,
                             GRB_INFINITY);
    LOG(err, "problem: non-zero coefficients: %d", P.num_nz);
    LOG(err, "problem: non-zero indicator coefficients: %d", P.indicator_num_nz);

    if (api.newmodel(env, &model, NULL, P.num_col,
                    P.col_obj, P.col_lb, P.col_ub, P.col_type, NULL) != 0){
        CTXEND(err);
        return grbErr(env, NULL, sol, "Could not create a model", err);
    }

    int num_starts = 0;
    for (int v = 0; v < lp->col_size; ++v){
        if (lp->col[v].start_enabled){
            if (api.setdblattrelement(model, "Start", v, lp->col[v].start) != 0){
                CTXEND(err);
                return grbErr(env, model, sol,
                              "Cannot set start value for variable", err);
            }
            ++num_starts;
        }
    }
    if (num_starts > 0)
        LOG(err, "Set %d mip-start values.", num_starts);

    if (P.num_row > 0){
        if (api.addconstrs(model, P.num_row, P.num_nz, P.row_beg, P.row_ind,
                    P.row_val, P.row_sense, P.row_rhs, NULL) != 0){
            CTXEND(err);
            return grbErr(env, model, sol, "Could not add constraints", err);
        }
    }
    if (P.indicator_num_row > 0){
        for (int row = 0; row < P.indicator_num_row; ++row){
            int binvar = P.indicator_var[row];
            int binval = 1;
            if (P.indicator_complemented[row])
                binval = 0;

            int next_beg = P.indicator_num_nz;
            if (row < P.indicator_num_row - 1)
                next_beg = P.indicator_row_beg[row + 1];
            int nvars = next_beg - P.indicator_row_beg[row];
            const int *ind = P.indicator_row_ind + P.indicator_row_beg[row];
            const double *val = P.indicator_row_val + P.indicator_row_beg[row];
            char sense = P.indicator_row_sense[row];
            double rhs = P.indicator_row_rhs[row];
            if (api.addgenconstrIndicator(model, NULL, binvar, binval,
                                          nvars, ind, val, sense, rhs) != 0){
                CTXEND(err);
                return grbErr(env, model, sol, "Could not add indicator constraint", err);
            }
        }
    }
    api.updatemodel(model);
    compressedRowProblemFree(&P);

    api.setcallbackfunc(model, cb, err);


    int minmax = GRB_MINIMIZE;
    if (lp->cfg.maximize)
        minmax = GRB_MAXIMIZE;
    if (api.setintattr(model, GRB_INT_ATTR_MODELSENSE, minmax) != 0){
        CTXEND(err);
        return grbErr(env, model, sol, "Could not set minimization/maximization", err);
    }

    if (api.optimize(model) != 0){
        CTXEND(err);
        return grbErr(env, model, sol, "Could not optimize model", err);
    }

    int st;
    if (api.getintattr(model, "Status", &st) != 0){
        CTXEND(err);
        return grbErr(env, model, sol, "Could not obtain solution status", err);
    }

    if (st == GRB_OPTIMAL){
        sol->solved = pddl_true;
        sol->solved_optimally = pddl_true;

    }else if (st == GRB_SUBOPTIMAL){
        sol->solved = pddl_true;
        sol->solved_suboptimally = pddl_true;

    }else if (st == GRB_INFEASIBLE
                || st == GRB_INF_OR_UNBD
                || st == GRB_UNBOUNDED){
        sol->unsolvable = pddl_true;

    }else if (st == GRB_TIME_LIMIT
                || st == GRB_CUTOFF
                || st == GRB_ITERATION_LIMIT
                || st == GRB_NODE_LIMIT
                || st == GRB_SOLUTION_LIMIT
                || st == GRB_INTERRUPTED
                || st == GRB_NUMERIC
                || st == GRB_USER_OBJ_LIMIT
                || st == GRB_WORK_LIMIT){
        int val;
        if (api.getintattr(model, "SolCount", &val) != 0){
            CTXEND(err);
            return grbErr(env, model, sol, "Could not obtain number of solutions", err);
        }

        if (val <= 0){
            sol->not_solved = pddl_true;
        }else{
            sol->solved = pddl_true;
            sol->solved_suboptimally = pddl_true;
        }
        if (st == GRB_TIME_LIMIT){
            LOG(err, "Time limit reached: solutions: %d", val);
            sol->timed_out = pddl_true;
        }

    }else{
        char msg[1024];
        snprintf(msg, 1024, "Unrecognized solution status %d", st);
        msg[1023] = '\x0';
        CTXEND(err);
        return grbErr(env, model, sol, msg, err);
    }

    if (sol->solved){
        if (api.getdblattr(model, "ObjVal", &sol->obj_val) != 0){
            CTXEND(err);
            return grbErr(env, model, sol, "Could not obtain objective value", err);
        }

        if (sol->var_val != NULL){
            int num_cols;
            if (api.getintattr(model, "NumVars", &num_cols) != 0){
                CTXEND(err);
                return grbErr(env, model, sol, "Could not obtain number of columns", err);
            }
            PANIC_IF(num_cols != lp->col_size, "Invalid number of columns.");
            for (int i = 0; i < lp->col_size; ++i){
                if (api.getdblattrelement(model, "X", i, sol->var_val + i) != 0){
                    CTXEND(err);
                    return grbErr(env, model, sol, "Could not obtain variable value", err);
                }
            }
        }
    }

    api.freemodel(model);
    api.freeenv(env);
    CTXEND(err);
    return _pddlLPSolutionToStatus(sol);
}

#else /* PDDL_GUROBI */
const char * const pddl_gurobi_version = NULL;
const char * const pddl_gurobi_api_version = NULL;

int pddlLPLoadGurobi(const char *so_fn, pddl_err_t *err)
{
    ERR_RET(err, -1, "Cannot load Gurobi, because cpddl was compiled"
            " without Gurobi header files.");
}

pddl_bool_t pddlLPIsGurobiAvailable(void)
{
    return pddl_false;
}

const char * const pddlLPGurobiVersion(void)
{
    return NULL;
}

pddl_lp_status_t pddlLPSolveGurobi(const pddl_lp_t *lp,
                                   pddl_lp_solution_t *sol,
                                   pddl_err_t *err)
{
    PANIC("Missing Gurobi solver");
    return PDDL_LP_STATUS_ERR;
}

#endif /* PDDL_GUROBI */
