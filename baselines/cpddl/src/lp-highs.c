/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/lp.h"
#include "pddl/libs_info.h"
#include "_lp.h"

#ifdef PDDL_HIGHS
#include <interfaces/highs_c_api.h>
#define COMPRESSED_INT HighsInt
#define COMPRESSED_COL_TYPE HighsInt
#include "_lp_compressed_row_problem.h"

const char * const pddl_highs_version =
    PDDL_TOSTR(HIGHS_VERSION_MAJOR.HIGHS_VERSION_MINOR.HIGHS_VERSION_PATCH);

#define TOLERANCE 1E-5
#define MIP_TOLERANCE 1E-5
#define MIN_BOUND -1E20
#define MAX_BOUND 1E20


static void *createModel(const pddl_lp_t *lp, pddl_err_t *err)
{
    void *model = Highs_create();
    if (model == NULL)
        ERR_RET(err, NULL, "HiGHS: Could not create the problem instance");

    int num_threads = PDDL_MAX(lp->cfg.num_threads, 1);
    Highs_setIntOptionValue(model, "threads", num_threads);
    if (lp->cfg.time_limit > 0.)
        Highs_setDoubleOptionValue(model, "time_limit", lp->cfg.time_limit);
    Highs_setBoolOptionValue(model, "output_flag", 0);
    //Highs_setIntOptionValue(model, "log_dev_level", 2);
    //Highs_setIntOptionValue(model, "highs_debug_level", 2);
    Highs_setDoubleOptionValue(model, "primal_feasibility_tolerance", TOLERANCE);
    Highs_setDoubleOptionValue(model, "dual_feasibility_tolerance", TOLERANCE);
    Highs_setDoubleOptionValue(model, "mip_feasibility_tolerance", MIP_TOLERANCE);

    pddl_lp_compressed_row_problem_t P;
    compressedRowProblemInit(&P, lp, 
                             kHighsVarTypeContinuous,
                             kHighsVarTypeInteger,
                             kHighsVarTypeInteger,
                             pddl_true,
                             MIN_BOUND,
                             MAX_BOUND);
    LOG(err, "problem: non-zero coefficients: %d", P.num_nz);
    LOG(err, "problem: non-zero indicator coefficients: %d", P.indicator_num_nz);
    if (P.indicator_num_row > 0){
        compressedRowProblemFree(&P);
        Highs_destroy(model);
        ERR_RET(err, NULL, "HiGHS does not support indicator constraints.");
    }

    int sense = kHighsObjSenseMinimize;
    if (lp->cfg.maximize)
        sense = kHighsObjSenseMaximize;

    int a_format = kHighsMatrixFormatRowwise;
    double offset = 0.;

    HighsInt st = 0;
    if (P.is_mip){
        st = Highs_passMip(model, P.num_col, P.num_row, P.num_nz, a_format,
                           sense, offset, P.col_obj, P.col_lb, P.col_ub,
                           P.row_lb, P.row_ub, P.row_beg, P.row_ind, P.row_val,
                           P.col_type);
    }else{
        st = Highs_passLp(model, P.num_col, P.num_row, P.num_nz, a_format,
                          sense, offset, P.col_obj, P.col_lb, P.col_ub,
                          P.row_lb, P.row_ub, P.row_beg, P.row_ind, P.row_val);
    }

    compressedRowProblemFree(&P);

    if (st == kHighsStatusError){
        ERR_RET(err, NULL, "HiGHS: Could not create the problem instance");

    }else if (st == kHighsStatusWarning){
        ERR_RET(err, NULL, "HiGHS: Could not create the problem instance");
    }

    return model;
}

pddl_lp_status_t pddlLPSolveHiGHS(const pddl_lp_t *lp,
                                  pddl_lp_solution_t *sol,
                                  pddl_err_t *err)
{
    CTX_NO_TIME(err, "LP-HiGHS");
    LOG(err, "version: %s", pddl_highs_version);
    LOG(err, "problem: cols: %d, rows: %d, maximize: %s, time_limit: %.2f,"
        " tune-int-op-pot: %s",
        lp->col_size, lp->row_size, F_BOOL(lp->cfg.maximize), lp->cfg.time_limit,
        F_BOOL(lp->cfg.tune_int_operator_potential));
    _pddlLPSolutionInit(sol, lp);

    void *model = createModel(lp, err);
    if (model == NULL){
        sol->error = pddl_true;
        TRACE_RET(err, PDDL_LP_STATUS_ERR);
    }

    HighsInt st = Highs_run(model);
    if (st == kHighsStatusError){
        Highs_destroy(model);
        sol->error = pddl_true;
        CTXEND(err);
        ERR_RET(err, PDDL_LP_STATUS_ERR,
                "Something went wrong during solving the model!");

    }else if (st == kHighsStatusWarning){
        Highs_destroy(model);
        sol->error = pddl_true;
        CTXEND(err);
        ERR_RET(err, PDDL_LP_STATUS_ERR,
                "Something went wrong during solving the model!");
    }

    HighsInt modelst = Highs_getModelStatus(model);
    if (modelst == kHighsModelStatusNotset){
        Highs_destroy(model);
        sol->error = pddl_true;
        CTXEND(err);
        ERR_RET(err, PDDL_LP_STATUS_ERR, "Model status not set");

    }else if (modelst == kHighsModelStatusLoadError){
        Highs_destroy(model);
        sol->error = pddl_true;
        CTXEND(err);
        ERR_RET(err, PDDL_LP_STATUS_ERR, "Model load error");

    }else if (modelst == kHighsModelStatusModelError){
        Highs_destroy(model);
        sol->error = pddl_true;
        CTXEND(err);
        ERR_RET(err, PDDL_LP_STATUS_ERR, "Model error");

    }else if (modelst == kHighsModelStatusPresolveError){
        Highs_destroy(model);
        sol->error = pddl_true;
        CTXEND(err);
        ERR_RET(err, PDDL_LP_STATUS_ERR, "Presolve error");

    }else if (modelst == kHighsModelStatusSolveError){
        Highs_destroy(model);
        sol->error = pddl_true;
        CTXEND(err);
        ERR_RET(err, PDDL_LP_STATUS_ERR, "Solve error");

    }else if (modelst == kHighsModelStatusPostsolveError){
        Highs_destroy(model);
        sol->error = pddl_true;
        CTXEND(err);
        ERR_RET(err, PDDL_LP_STATUS_ERR, "Postsolve error");

    }else if (modelst == kHighsModelStatusModelEmpty){
        Highs_destroy(model);
        sol->error = pddl_true;
        CTXEND(err);
        ERR_RET(err, PDDL_LP_STATUS_ERR, "Model is empty.");

    }else if (modelst == kHighsModelStatusOptimal){
        sol->solved = pddl_true;
        sol->solved_optimally = pddl_true;

        HighsInt solst;
        Highs_getIntInfoValue(model, "primal_solution_status", &solst);
        PANIC_IF(solst != kHighsSolutionStatusFeasible,
                 "Model status is 'optimal', but solution is not feasible");

    }else if (modelst == kHighsModelStatusInfeasible){
        sol->unsolvable = pddl_true;

    }else if (modelst == kHighsModelStatusUnboundedOrInfeasible){
        sol->unsolvable = pddl_true;

    }else if (modelst == kHighsModelStatusUnbounded){
        sol->unsolvable = pddl_true;

    }else if (modelst == kHighsModelStatusTimeLimit){
        sol->timed_out = pddl_true;

        HighsInt solst;
        Highs_getIntInfoValue(model, "primal_solution_status", &solst);
        if (solst == kHighsSolutionStatusFeasible){
            sol->solved_suboptimally = pddl_true;
        }else{
            sol->not_solved = pddl_true;
        }

    }else if (modelst == kHighsModelStatusObjectiveBound
                || modelst == kHighsModelStatusObjectiveTarget
                || modelst == kHighsModelStatusIterationLimit){
        HighsInt solst;
        Highs_getIntInfoValue(model, "primal_solution_status", &solst);
        if (solst == kHighsSolutionStatusFeasible){
            sol->solved_suboptimally = pddl_true;
        }else{
            sol->not_solved = pddl_true;
        }

    }else if (modelst == kHighsModelStatusUnknown){
        Highs_destroy(model);
        sol->error = pddl_true;
        CTXEND(err);
        ERR_RET(err, PDDL_LP_STATUS_ERR, "Unkown solution status");

    }else{
        Highs_destroy(model);
        sol->error = pddl_true;
        CTXEND(err);
        ERR_RET(err, PDDL_LP_STATUS_ERR, "Unkown solution status: %d", (int)modelst);
    }

    sol->obj_val = Highs_getObjectiveValue(model);
    if (sol->var_val != NULL)
        Highs_getSolution(model, sol->var_val, NULL, NULL, NULL);

    Highs_destroy(model);

    CTXEND(err);
    return _pddlLPSolutionToStatus(sol);
}


#else /* PDDL_HIGHS */
const char * const pddl_highs_version = NULL;

pddl_lp_status_t pddlLPSolveHiGHS(const pddl_lp_t *lp,
                                  pddl_lp_solution_t *sol,
                                  pddl_err_t *err)
{
    PANIC("Missing HiGHS solver");
    return PDDL_LP_STATUS_ERR;
}
#endif /* PDDL_HIGHS */
