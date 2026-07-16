/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/lp.h"
#include "pddl/libs_info.h"
#include "_lp.h"

#ifdef PDDL_CPLEX
#include <dlfcn.h>
# include <ilcplex/cplex.h>
#include "_lp_compressed_row_problem.h"


typedef CPXCCHARptr (*api_version_t)(CPXCENVptr env);
typedef CPXENVptr (*api_openCPLEX_t)(int *status_p);
typedef int (*api_closeCPLEX_t)(CPXENVptr *env_p);
typedef CPXLPptr (*api_createprob_t)(CPXCENVptr env, int *status_p,
                                     char const *probname_str);
typedef int (*api_freeprob_t)(CPXCENVptr env, CPXLPptr *lp_p);
typedef int (*api_setintparam_t)(CPXENVptr env, int whichparam, CPXINT newvalue);
typedef int (*api_setdblparam_t)(CPXENVptr env, int whichparam, double newvalue);
typedef int (*api_chgobjsen_t)(CPXCENVptr env, CPXLPptr lp, int maxormin);
typedef int (*api_newcols_t)(CPXCENVptr env, CPXLPptr lp, int ccnt,
                             double const *obj, double const *lb, double const *ub,
                             char const *xctype, char **colname);
typedef int (*api_addrows_t)(CPXCENVptr env, CPXLPptr lp, int ccnt, int rcnt,
                             int nzcnt, double const *rhs, char const *sense,
                             int const *rmatbeg, int const *rmatind,
                             double const *rmatval, char **colname, char **rowname);
typedef int (*api_addindconstraints_t)(CPXCENVptr env, CPXLPptr lp, int indcnt,
                                       int const *type, int const *indvar,
                                       int const *complemented, int nzcnt,
                                       double const *rhs, char const *sense,
                                       int const *linbeg, int const *linind,
                                       double const *linval, char **indname);
typedef int (*api_mipopt_t)(CPXCENVptr env, CPXLPptr lp);
typedef int (*api_lpopt_t)(CPXCENVptr env, CPXLPptr lp);
typedef int (*api_getstat_t)(CPXCENVptr env, CPXCLPptr lp);
typedef int (*api_solution_t)(CPXCENVptr env, CPXCLPptr lp, int *lpstat_p,
                              double *objval_p, double *x, double *pi, double *slack,
                              double *dj);
typedef int (*api_addmipstarts_t)(CPXCENVptr env, CPXLPptr lp, int mcnt,
                                  int nzcnt, int const *beg,
                                  int const *varindices, double const *values,
                                  int const *effortlevel, char **mipstartname);
typedef CPXCCHARptr (*api_geterrorstring_t)(CPXCENVptr env, int errcode, char *buffer_str);
typedef int (*api_callbackgetinfodbl_t)(CPXCALLBACKCONTEXTptr context,
                                        CPXCALLBACKINFO what, double *data_p);
typedef int (*api_callbackgetinfoint_t)(CPXCALLBACKCONTEXTptr context,
                                        CPXCALLBACKINFO what, CPXINT *data_p);
typedef int (*api_callbacksetfunc_t)(CPXENVptr env, CPXLPptr lp, CPXLONG contextmask,
                                     CPXCALLBACKFUNC callback, void *userhandle);
typedef int (*api_setlpcallbackfunc_t)(CPXENVptr env,
                                       int(CPXPUBLIC *callback)(CPXCENVptr, void *, int, void *),
                                       void *cbhandle);
typedef int (*api_getcallbackinfo_t)(CPXCENVptr env, void *cbdata, int wherefrom,
                                     int whichinfo, void *result_p);

struct cplex_api {
    api_version_t version;
    api_openCPLEX_t openCPLEX;
    api_closeCPLEX_t closeCPLEX;
    api_createprob_t createprob;
    api_freeprob_t freeprob;
    api_setintparam_t setintparam;
    api_setdblparam_t setdblparam;
    api_chgobjsen_t chgobjsen;
    api_newcols_t newcols;
    api_addrows_t addrows;
    api_addindconstraints_t addindconstraints;
    api_mipopt_t mipopt;
    api_lpopt_t lpopt;
    api_getstat_t getstat;
    api_solution_t solution;
    api_addmipstarts_t addmipstarts;
    api_geterrorstring_t geterrorstring;
    api_callbackgetinfodbl_t callbackgetinfodbl;
    api_callbackgetinfoint_t callbackgetinfoint;
    api_callbacksetfunc_t callbacksetfunc;
    api_setlpcallbackfunc_t setlpcallbackfunc;
    api_getcallbackinfo_t getcallbackinfo;
};

#ifdef PDDL_CPLEX_ONLY_API
static struct cplex_api api = { 0 };
const char * const pddl_cplex_version = NULL;
const char * const pddl_cplex_api_version =
    PDDL_TOSTR(CPX_VERSION_VERSION.CPX_VERSION_RELEASE.CPX_VERSION_MODIFICATION.CPX_VERSION_FIX);
#else /* PDDL_CPLEX_ONLY_API */

static struct cplex_api api = {
    CPXversion,
    CPXopenCPLEX,
    CPXcloseCPLEX,
    CPXcreateprob,
    CPXfreeprob,
    CPXsetintparam,
    CPXsetdblparam,
    CPXchgobjsen,
    CPXnewcols,
    CPXaddrows,
    CPXaddindconstraints,
    CPXmipopt,
    CPXlpopt,
    CPXgetstat,
    CPXsolution,
    CPXaddmipstarts,
    CPXgeterrorstring,
    CPXcallbackgetinfodbl,
    CPXcallbackgetinfoint,
    CPXcallbacksetfunc,
    CPXsetlpcallbackfunc,
    CPXgetcallbackinfo,
};

const char * const pddl_cplex_version =
    PDDL_TOSTR(CPX_VERSION_VERSION.CPX_VERSION_RELEASE.CPX_VERSION_MODIFICATION.CPX_VERSION_FIX);
const char * const pddl_cplex_api_version = NULL;
#endif /* PDDL_CPLEX_ONLY_API */



#define LOAD(NAME) \
    do { \
        api.NAME = (api_##NAME##_t)dlsym(dl_handle, "CPX" #NAME); \
        if (api.NAME == NULL){ \
            ZEROIZE(&api); \
            dlclose(dl_handle); \
            ERR_RET(err, -1, "Could not find CPX" #NAME " function: %s", dlerror()); \
        } \
    } while (0)

static void *dl_handle = NULL;
int pddlLPLoadCPLEX(const char *so_fn, pddl_err_t *err)
{
    if (dl_handle != NULL)
        dlclose(dl_handle);

    dl_handle = dlopen(so_fn, RTLD_NOW);
    if (dl_handle == NULL)
        ERR_RET(err, -1, "Could not load CPLEX library: %s", dlerror());

    LOAD(version);
    LOAD(openCPLEX);
    LOAD(closeCPLEX);
    LOAD(createprob);
    LOAD(freeprob);
    LOAD(setintparam);
    LOAD(setdblparam);
    LOAD(chgobjsen);
    LOAD(newcols);
    LOAD(addrows);
    LOAD(addindconstraints);
    LOAD(mipopt);
    LOAD(lpopt);
    LOAD(getstat);
    LOAD(solution);
    LOAD(addmipstarts);
    LOAD(geterrorstring);
    LOAD(callbackgetinfodbl);
    LOAD(callbackgetinfoint);
    LOAD(callbacksetfunc);
    LOAD(setlpcallbackfunc);
    LOAD(getcallbackinfo);

    int st;
    CPXENVptr env = api.openCPLEX(&st);
    if (env == NULL){
        ZEROIZE(&api);
        ERR_RET(err, -1, "CPLEX library loaded but cannot create CPLEX environment");
    }
    LOG(err, "CPLEX library successfully loaded from %s. version: %s",
        so_fn, api.version(env));
    api.closeCPLEX(&env);

    return 0;
}

pddl_bool_t pddlLPIsCPLEXAvailable(void)
{
    return api.version != NULL;
}

const char * const pddlLPCPLEXVersion(void)
{
    if (api.version == NULL)
        return NULL;

    int st;
    CPXENVptr env = api.openCPLEX(&st);
    PANIC_IF(env == NULL, "CPLEX library loaded but cannot create CPLEX environment");
    const char *version = api.version(env);
    api.closeCPLEX(&env);
    return version;
}

static pddl_lp_status_t cplexErr(CPXENVptr *env,
                                 CPXLPptr *prob,
                                 int status,
                                 pddl_lp_solution_t *sol,
                                 const char *s,
                                 pddl_err_t *err)
{
    if (status != 0 && env != NULL){
        char errmsg[1024];
        api.geterrorstring(*env, status, errmsg);
        ERR(err, "CPLEX: %s: %s", s, errmsg);
    }else{
        ERR(err, "CPLEX: %s", s);
    }

    sol->solved_optimally = pddl_false;
    sol->solved_suboptimally = pddl_false;
    sol->unsolvable = pddl_false;
    sol->not_solved = pddl_false;
    sol->error = pddl_true;
    sol->timed_out = pddl_false;

    if (prob != NULL && *prob != NULL)
        api.freeprob(*env, prob);
    if (env != NULL && *env != NULL)
        api.closeCPLEX(env);
    return PDDL_LP_STATUS_ERR;
}

struct log {
    pddl_err_t *err;
    pddl_timer_t timer;
};
typedef struct log log_t;

static int callback(CPXCALLBACKCONTEXTptr ctx, CPXLONG ctxtid, void *_log)
{
    log_t *log = _log;

    pddlTimerStop(&log->timer);
    if (pddlTimerElapsedInSF(&log->timer) < 1.)
        return 0;

    double best_sol = 0.;
    api.callbackgetinfodbl(ctx, CPXCALLBACKINFO_BEST_SOL, &best_sol);
    if (best_sol < -1E10 || best_sol > 1E10)
        best_sol = NAN;

    double best_bound = 0.;
    api.callbackgetinfodbl(ctx, CPXCALLBACKINFO_BEST_BND, &best_bound);
    if (best_bound < -1E10 || best_bound > 1E10)
        best_bound = NAN;

    int feasible = 0;
    api.callbackgetinfoint(ctx, CPXCALLBACKINFO_FEASIBLE, &feasible);

    CTX_NO_TIME(log->err, "cplex progress");
    LOG(log->err, "best solution: %.2f, best bound: %.2f, feasible: %d",
        best_sol, best_bound, feasible);
    CTXEND(log->err);
    pddlTimerStart(&log->timer);
    return 0;
}

static int callbackLP(CPXCENVptr env,
                      void *cbdata,
                      int wherefrom,
                      void *_log)
{
    log_t *log = _log;

    pddlTimerStop(&log->timer);
    if (pddlTimerElapsedInSF(&log->timer) < 1.)
        return 0;

    double primal = 0.;
    api.getcallbackinfo(env, cbdata, wherefrom,
                        CPX_CALLBACK_INFO_PRIMAL_OBJ, &primal);
    double dual = 0.;
    api.getcallbackinfo(env, cbdata, wherefrom,
                        CPX_CALLBACK_INFO_DUAL_OBJ, &dual);

    CTX_NO_TIME(log->err, "cplex progress");
    LOG(log->err, "primal: %.4f, dual: %.4f", primal, dual);
    CTXEND(log->err);
    pddlTimerStart(&log->timer);
    return 0;
}

static int setMIPStart(const pddl_lp_t *lp, CPXCENVptr env, CPXLPptr prob,
                       pddl_err_t *err)
{
    int nzcnt = 0;
    for (int var = 0; var < lp->col_size; ++var){
        if (lp->col[var].start_enabled)
            nzcnt += 1;
    }
    if (nzcnt == 0)
        return 0;

    int beg[1] = { 0 };
    int *vars = ALLOC_ARR(int, nzcnt);
    double *vals = ALLOC_ARR(double, nzcnt);
    for (int var = 0, ins = 0; var < lp->col_size; ++var){
        if (lp->col[var].start_enabled){
            vars[ins] = var;
            vals[ins] = lp->col[var].start;
            ++ins;
        }
    }
    int st = api.addmipstarts(env, prob, 1, nzcnt, beg, vars, vals, NULL, NULL);
    if (st == 0)
        LOG(err, "Set %d mip-start values.", nzcnt);

    FREE(vars);
    FREE(vals);

    return st;
}

pddl_lp_status_t pddlLPSolveCPLEX(const pddl_lp_t *lp,
                                  pddl_lp_solution_t *sol,
                                  pddl_err_t *err)
{
    PANIC_IF(api.version == NULL, "CPLEX library is not available");
    CTX_NO_TIME(err, "LP-Cplex");
    int st;
    CPXENVptr env;
    CPXLPptr prob;

    _pddlLPSolutionInit(sol, lp);

    env = api.openCPLEX(&st);
    if (env == NULL){
        CTXEND(err);
        return cplexErr(&env, NULL, 0, sol, "Could not open CPLEX environment", err);
    }
    LOG(err, "version: %s", api.version(env));
    LOG(err, "problem: cols: %d, rows: %d, maximize: %s, time_limit: %.2f,"
        " tune-int-op-pot: %s",
        lp->col_size, lp->row_size, F_BOOL(lp->cfg.maximize), lp->cfg.time_limit,
        F_BOOL(lp->cfg.tune_int_operator_potential));

    // Set number of processing threads
    int num_threads = PDDL_MAX(1, lp->cfg.num_threads);
    st = api.setintparam(env, CPX_PARAM_THREADS, num_threads);
    if (st != 0){
        CTXEND(err);
        return cplexErr(&env, NULL, st, sol, "Could not set number of threads", err);
    }

    api.setintparam(env, CPXPARAM_ScreenOutput, CPX_OFF);

    if (lp->cfg.time_limit > 0.f){
        st = api.setdblparam(env, CPXPARAM_TimeLimit, lp->cfg.time_limit);
        if (st != 0){
            CTXEND(err);
            return cplexErr(&env, NULL, st, sol, "Could not set number of threads", err);
        }
    }

    prob = api.createprob(env, &st, "");
    if (prob == NULL){
        CTXEND(err);
        return cplexErr(&env, NULL, 0, sol, "Could not create CPLEX problem", err);
    }

    if (lp->cfg.maximize){
        api.chgobjsen(env, prob, CPX_MAX);
    }else{
        api.chgobjsen(env, prob, CPX_MIN);
    }

    pddl_lp_compressed_row_problem_t P;
    compressedRowProblemInit(&P, lp, 
                             CPX_CONTINUOUS,
                             CPX_INTEGER,
                             CPX_BINARY,
                             pddl_false,
                             -CPX_INFBOUND,
                             CPX_INFBOUND);
    LOG(err, "problem: non-zero coefficients: %d", P.num_nz);
    LOG(err, "problem: non-zero indicator coefficients: %d", P.indicator_num_nz);

    pddl_bool_t is_mip = P.is_mip;
    st = api.newcols(env, prob, P.num_col, P.col_obj, P.col_lb, P.col_ub,
                     (P.is_mip ? P.col_type : NULL), NULL);
    if (st != 0){
        CTXEND(err);
        return cplexErr(&env, &prob, st, sol, "Could not create columns", err);
    }

    if (P.num_row > 0){
        st = api.addrows(env, prob, 0, P.num_row, P.num_nz, P.row_rhs,
                         P.row_sense, P.row_beg, P.row_ind, P.row_val, NULL, NULL);
        if (st != 0){
            CTXEND(err);
            return cplexErr(&env, &prob, st, sol, "Could not create rows", err);
        }
    }

    if (P.indicator_num_row > 0){
        int *type = ALLOC_ARR(int, P.indicator_num_row);
        for (int i = 0; i < P.indicator_num_row; ++i)
            type[i] = CPX_INDICATOR_IF;
        st = api.addindconstraints(env, prob, P.indicator_num_row, type,
                                   P.indicator_var, P.indicator_complemented,
                                   P.indicator_num_nz, P.indicator_row_rhs,
                                   P.indicator_row_sense, P.indicator_row_beg,
                                   P.indicator_row_ind, P.indicator_row_val, NULL);
        FREE(type);
        if (st != 0){
            CTXEND(err);
            return cplexErr(&env, &prob, st, sol, "Could not create indicator rows", err);
        }
    }

    compressedRowProblemFree(&P);

    if (lp->cfg.tune_int_operator_potential){
        api.setintparam(env, CPXPARAM_Preprocessing_Relax, CPX_ON);
        api.setintparam(env, CPXPARAM_Preprocessing_Dual, 1);
        //api.setintparam(env, CPXPARAM_Preprocessing_CoeffReduce, 2);
        //api.setintparam(env, CPXPARAM_Preprocessing_Dependency, 3);
    }

    if (is_mip){
        if (setMIPStart(lp, env, prob, err) != 0)
            return cplexErr(&env, &prob, st, sol, "Could not add mip-starts", err);
    }

    log_t log;
    log.err = err;
    pddlTimerStart(&log.timer);
    if (is_mip){
        api.callbacksetfunc(env, prob,
                            CPX_CALLBACKCONTEXT_GLOBAL_PROGRESS
                                | CPX_CALLBACKCONTEXT_LOCAL_PROGRESS
                                | CPX_CALLBACKCONTEXT_RELAXATION
                                | CPX_CALLBACKCONTEXT_CANDIDATE,
                            callback, &log);
        if ((st = api.mipopt(env, prob)) != 0){
            CTXEND(err);
            return cplexErr(&env, &prob, st, sol, "Failed to optimize MIP", err);
        }
        api.callbacksetfunc(env, prob, 0, NULL, NULL);

    }else{
        if (lp->cfg.tune_potential){
            // Default setting of CPXPARAM_LPMethod is CPX_ALG_AUTOMATIC
            // which usually selects CPX_ALG_DUAL (see https://www.ibm.com/support/pages/deciding-which-cplexs-numerous-linear-programming-algorithms-fastest-performance)
            // However, for some unclear reason, dual simplex gets
            // sometimes stuck so that not even timeout is respected.
            // Enforcing the following parameter seems to remedy the
            // problem.
            api.setintparam(env, CPXPARAM_Preprocessing_Dual, 1);
            // what also worked was changing the algorithm, e.g.,
            // api.setintparam(env, CPXPARAM_LPMethod, CPX_ALG_BARRIER);
            // but the option above seems to be less intrusive.
        }

        api.setlpcallbackfunc(env, callbackLP, &log);
        if ((st = api.lpopt(env, prob)) != 0){
            CTXEND(err);
            return cplexErr(&env, &prob, st, sol, "Failed to optimize LP", err);
        }
    }

    st = api.getstat(env, prob);
    if (st == CPX_STAT_OPTIMAL
            || st == CPX_STAT_OPTIMAL_INFEAS
            || st == CPXMIP_OPTIMAL
            || st == CPXMIP_OPTIMAL_TOL){
        sol->solved = pddl_true;
        sol->solved_optimally = pddl_true;

    }else if (st == CPXMIP_TIME_LIM_FEAS){
        sol->solved = pddl_true;
        sol->solved_suboptimally = pddl_true;
        sol->timed_out = pddl_true;

    }else if (st == CPX_STAT_INFEASIBLE
                || st == CPX_STAT_INForUNBD
                || st == CPXMIP_INFEASIBLE
                || st == CPXMIP_INForUNBD){
        sol->unsolvable = pddl_true;

    }else if (st == CPX_STAT_ABORT_DETTIME_LIM
                || st == CPX_STAT_ABORT_DUAL_OBJ_LIM
                || st == CPX_STAT_ABORT_IT_LIM
                || st == CPX_STAT_ABORT_OBJ_LIM
                || st == CPX_STAT_ABORT_PRIM_OBJ_LIM
                || st == CPX_STAT_ABORT_USER
                || st == CPX_STAT_UNBOUNDED
                || st == CPXMIP_ABORT_INFEAS
                || st == CPXMIP_DETTIME_LIM_FEAS
                || st == CPXMIP_DETTIME_LIM_INFEAS){
        sol->not_solved = pddl_true;

    }else if (st == CPX_STAT_ABORT_TIME_LIM
                || st == CPXMIP_TIME_LIM_INFEAS){
        sol->not_solved = pddl_true;
        sol->timed_out = pddl_true;

    }else{
        char msg[1024];
        msg[1023] = '\x0';
        snprintf(msg, 1024, "Unrecognized solution status %d", st);
        CTXEND(err);
        return cplexErr(&env, &prob, 0, sol, msg, err);
    }

    if (sol->solved){
        st = api.solution(env, prob, NULL, &sol->obj_val, sol->var_val,
                          NULL, NULL, NULL);
        if (st != 0){
            CTXEND(err);
            return cplexErr(&env, &prob, st, sol, "Cannot retrieve solution", err);
        }
    }
    api.freeprob(env, &prob);
    api.closeCPLEX(&env);

    CTXEND(err);
    return _pddlLPSolutionToStatus(sol);
}

#else /* PDDL_CPLEX */
const char * const pddl_cplex_version = NULL;
const char * const pddl_cplex_api_version = NULL;

int pddlLPLoadCPLEX(const char *so_fn, pddl_err_t *err)
{
    ERR_RET(err, -1, "Cannot load CPLEX, because cpddl was compiled"
            " without CPLEX header files.");
}

pddl_bool_t pddlLPIsCPLEXAvailable(void)
{
    return pddl_false;
}

const char * const pddlLPCPLEXVersion(void)
{
    return NULL;
}

pddl_lp_status_t pddlLPSolveCPLEX(const pddl_lp_t *lp,
                                  pddl_lp_solution_t *sol,
                                  pddl_err_t *err)
{
    PANIC("Missing CPLEX solver");
    return PDDL_LP_STATUS_ERR;
}
#endif /* PDDL_CPLEX */
