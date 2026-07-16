/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/lp.h"
#include "pddl/libs_info.h"
#include "_lp.h"

#if defined(PDDL_CPLEX)
static pddl_lp_solver_t default_solver = PDDL_LP_CPLEX;
#elif defined(PDDL_GUROBI)
static pddl_lp_solver_t default_solver = PDDL_LP_GUROBI;
#elif defined(PDDL_HIGHS)
static pddl_lp_solver_t default_solver = PDDL_LP_HIGHS;
#else
static pddl_lp_solver_t default_solver = PDDL_LP_NO_SOLVER;
#endif

static pddl_lp_solver_t defaultSolver(void)
{
    if (pddlLPSolverAvailable(default_solver))
        return default_solver;
    if (pddlLPSolverAvailable(PDDL_LP_CPLEX))
        return PDDL_LP_CPLEX;
    if (pddlLPSolverAvailable(PDDL_LP_GUROBI))
        return PDDL_LP_GUROBI;
    if (pddlLPSolverAvailable(PDDL_LP_HIGHS))
        return PDDL_LP_HIGHS;
    return PDDL_LP_NO_SOLVER;
}

static const char * const _getSolverVersion(pddl_lp_solver_t solver)
{
    if (solver == PDDL_LP_DEFAULT)
        solver = defaultSolver();
    switch (solver){
        case PDDL_LP_CPLEX:
            return pddlLPCPLEXVersion();
        case PDDL_LP_GUROBI:
            return pddlLPGurobiVersion();
        case PDDL_LP_HIGHS:
            return pddl_highs_version;
        default:
            return NULL;
    }
}

static const char * const getSolverVersion(pddl_lp_solver_t solver)
{
    const char * const ver = _getSolverVersion(solver);
    if (ver == NULL)
        return "";
    return ver;
}

static const char *getSolverName(pddl_lp_solver_t solver)
{
    if (solver == PDDL_LP_DEFAULT)
        solver = defaultSolver();
    switch (solver){
        case PDDL_LP_CPLEX:
            return "cplex";
        case PDDL_LP_GUROBI:
            return "gurobi";
        case PDDL_LP_HIGHS:
            return "highs";
        default:
            return "No Solver";
    }
}


void pddlLPConfigLog(const pddl_lp_config_t *cfg, pddl_err_t *err)
{
    LOG_CONFIG_INT(cfg, rows, err);
    LOG_CONFIG_INT(cfg, cols, err);
    LOG_CONFIG_BOOL(cfg, maximize, err);
    LOG(err, "default solver = %s %s", getSolverName(cfg->solver),
        getSolverVersion(cfg->solver));
    LOG_CONFIG_INT(cfg, num_threads, err);
    LOG_CONFIG_DBL(cfg, time_limit, err);
    LOG_CONFIG_BOOL(cfg, tune_int_operator_potential, err);
}

pddl_bool_t pddlLPSolverAvailable(pddl_lp_solver_t solver)
{
    if (solver == PDDL_LP_NO_SOLVER)
        return pddl_false;
    if (solver == PDDL_LP_DEFAULT){
        return pddlLPSolverAvailable(PDDL_LP_CPLEX)
                || pddlLPSolverAvailable(PDDL_LP_GUROBI)
                || pddlLPSolverAvailable(PDDL_LP_HIGHS);
    }
    return _getSolverVersion(solver) != NULL;
}

int pddlLPSetDefault(pddl_lp_solver_t solver, pddl_err_t *err)
{
    if (!pddlLPSolverAvailable(solver)){
        switch (solver){
            case PDDL_LP_CPLEX:
                WARN(err, "The CPLEX LP solver is not available");
                break;
            case PDDL_LP_GUROBI:
                WARN(err, "The Gurobi LP solver is not available");
                break;
            case PDDL_LP_HIGHS:
                WARN(err, "The HiGHS LP solver is not available");
                break;
            default:
                WARN(err, "Unkown LP solver identifier!");
        }
        return -1;
    }

    if (solver == PDDL_LP_CPLEX
            || solver == PDDL_LP_GUROBI
            || solver == PDDL_LP_HIGHS){
        default_solver = solver;
    }

    return 0;
}

static void freeRow(pddl_lp_row_t *row)
{
    if (row->coef != NULL)
        FREE(row->coef);
}

pddl_lp_t *pddlLPNew(const pddl_lp_config_t *cfg, pddl_err_t *err)
{
    CTX_NO_TIME(err, "LP-Init");
    pddl_lp_t *lp = ZALLOC(pddl_lp_t);
    lp->err = err;
    lp->cfg = *cfg;
    if (lp->cfg.solver == PDDL_LP_DEFAULT)
        lp->cfg.solver = defaultSolver();
    CTX_NO_TIME(err, "Cfg");
    pddlLPConfigLog(&lp->cfg, err);
    CTXEND(err);

    if (cfg->cols > 0)
        pddlLPAddCols(lp, cfg->cols);
    if (cfg->rows > 0){
        double rhs = 0.;
        char sense = 'L';
        for (int i = 0; i < cfg->rows; ++i)
            pddlLPAddRows(lp, 1, &rhs, &sense);
    }
    CTXEND(err);
    return lp;
}

void pddlLPDel(pddl_lp_t *lp)
{
    if (lp->col != NULL)
        FREE(lp->col);
    for (int ri = 0; ri < lp->row_size; ++ri)
        freeRow(lp->row + ri);
    if (lp->row != NULL)
        FREE(lp->row);
    FREE(lp);
}

const char *pddlLPSolverName(const pddl_lp_t *lp)
{
    return getSolverName(lp->cfg.solver);
}

int pddlLPSolverID(const pddl_lp_t *lp)
{
    return lp->cfg.solver;
}

void pddlLPSetObj(pddl_lp_t *lp, int i, double coef)
{
    PANIC_IF(i < 0 || i >= lp->col_size, "Column %d out of range", i);
    lp->col[i].obj = coef;
}

void pddlLPSetVarRange(pddl_lp_t *lp, int i, double lb, double ub)
{
    PANIC_IF(i < 0 || i >= lp->col_size, "Column %d out of range", i);
    if (lb <= PDDL_LP_MIN_BOUND)
        lb = PDDL_LP_MIN_BOUND;
    if (ub >= PDDL_LP_MAX_BOUND)
        ub = PDDL_LP_MAX_BOUND;
    lp->col[i].lb = lb;
    lp->col[i].ub = ub;
}

void pddlLPSetVarFree(pddl_lp_t *lp, int i)
{
    pddlLPSetVarRange(lp, i, PDDL_LP_MIN_BOUND, PDDL_LP_MAX_BOUND);
}

void pddlLPSetVarInt(pddl_lp_t *lp, int i)
{
    PANIC_IF(i < 0 || i >= lp->col_size, "Column %d out of range", i);
    lp->col[i].type = PDDL_LP_COL_TYPE_INT;
}

void pddlLPSetVarBinary(pddl_lp_t *lp, int i)
{
    PANIC_IF(i < 0 || i >= lp->col_size, "Column %d out of range", i);
    lp->col[i].type = PDDL_LP_COL_TYPE_BINARY;
}

void pddlLPSetCoef(pddl_lp_t *lp, int row, int col, double coef)
{
    PANIC_IF(row < 0 || row >= lp->row_size, "Row %d out of range", row);
    PANIC_IF(col < 0 || col >= lp->col_size, "Column %d out of range", col);
    pddl_lp_row_t *r = lp->row + row;
    if (r->coef_size == r->coef_alloc){
        if (r->coef_alloc == 0)
            r->coef_alloc = 8;
        r->coef_alloc *= 2;
        r->coef = REALLOC_ARR(r->coef, pddl_lp_coef_t, r->coef_alloc);
    }

    if (r->coef_size == 0 || r->coef[r->coef_size - 1].col < col){
        pddl_lp_coef_t *c = r->coef + r->coef_size++;
        c->col = col;
        c->coef = coef;

    }else{
        int idx;
        for (idx = r->coef_size - 1; idx >= 0; --idx){
            if (r->coef[idx].col <= col)
                break;
        }

        if (idx < 0 || r->coef[idx].col < col){
            for (int i = r->coef_size - 1; i > idx; --i)
                r->coef[i + 1] = r->coef[i];
            r->coef[idx + 1].col = col;
            r->coef[idx + 1].coef = coef;
            ++r->coef_size;

        }else{ // r->coef[idx].col == col
            r->coef[idx].coef = coef;
        }
    }

    // TODO: If coef == 0. delete coef
}

void pddlLPSetRHS(pddl_lp_t *lp, int row, double rhs, char sense)
{
    PANIC_IF(row < 0 || row >= lp->row_size, "Row %d out of range", row);
    if (sense == 'L'){
        lp->row[row].rhs = rhs;

    }else if (sense == 'G'){
        lp->row[row].rhs = rhs;

    }else if (sense == 'E'){
        lp->row[row].rhs = rhs;

    }else{
        PANIC_IF(1, "Unkown sense '%c'", sense);
    }
    lp->row[row].sense = sense;
}

void pddlLPSetIndicator(pddl_lp_t *lp, int row, int var, pddl_bool_t val)
{
    PANIC_IF(row < 0 || row >= lp->row_size, "Row %d out of range", row);
    PANIC_IF(var < 0 || var >= lp->col_size, "Variable %d out of range", var);
    PANIC_IF(lp->col[var].type != PDDL_LP_COL_TYPE_BINARY,
             "Indicator variable has to be binary variable.");
    lp->row[row].indicator.enabled = pddl_true;
    lp->row[row].indicator.var = var;
    lp->row[row].indicator.val = val;
}

static void addRow(pddl_lp_t *lp, const double rhs, const char sense)
{
    if (lp->row_size == lp->row_alloc){
        if (lp->row_alloc == 0)
            lp->row_alloc = 16;
        lp->row_alloc *= 2;
        lp->row = REALLOC_ARR(lp->row, pddl_lp_row_t, lp->row_alloc);
    }
    pddl_lp_row_t *row = lp->row + lp->row_size++;
    ZEROIZE(row);
    pddlLPSetRHS(lp, lp->row_size - 1, rhs, sense);
}

void pddlLPAddRows(pddl_lp_t *lp, int cnt, const double *rhs, const char *sense)
{
    for (int i = 0; i < cnt; ++i)
        addRow(lp, rhs[i], sense[i]);
}

void pddlLPDelRows(pddl_lp_t *lp, int begin, int end)
{
    for (int i = begin; i < end + 1; ++i)
        freeRow(lp->row + i);
    int ins = begin;
    for (int i = end + 1; i < lp->row_size; ++i)
        lp->row[ins++] = lp->row[i];
    lp->row_size = ins;
}

int pddlLPNumRows(const pddl_lp_t *lp)
{
    return lp->row_size;
}

static void addCol(pddl_lp_t *lp)
{
    if (lp->col_size == lp->col_alloc){
        if (lp->col_alloc == 0)
            lp->col_alloc = 16;
        lp->col_alloc *= 2;
        lp->col = REALLOC_ARR(lp->col, pddl_lp_col_t, lp->col_alloc);
    }
    pddl_lp_col_t *col = lp->col + lp->col_size++;
    ZEROIZE(col);
    col->obj = 0.;
    col->type = PDDL_LP_COL_TYPE_REAL;
    col->lb = PDDL_LP_MIN_BOUND;
    col->ub = PDDL_LP_MAX_BOUND;
    col->start = 0.;
    col->start_enabled = pddl_false;
}

void pddlLPAddCols(pddl_lp_t *lp, int cnt)
{
    for (int i = 0; i < cnt; ++i)
        addCol(lp);
}

int pddlLPNumCols(const pddl_lp_t *lp)
{
    return lp->col_size;
}

void pddlLPSetColStart(pddl_lp_t *lp, int var, double value)
{
    lp->col[var].start = value;
    lp->col[var].start_enabled = pddl_true;
}

pddl_lp_status_t pddlLPSolve(const pddl_lp_t *lp,
                             pddl_lp_solution_t *sol,
                             pddl_err_t *err)
{
    _pddlLPSolutionInit(sol, lp);
    switch (lp->cfg.solver){
        case PDDL_LP_CPLEX:
            return pddlLPSolveCPLEX(lp, sol, err);
        case PDDL_LP_GUROBI:
            return pddlLPSolveGurobi(lp, sol, err);
        case PDDL_LP_HIGHS:
            return pddlLPSolveHiGHS(lp, sol, err);
        case PDDL_LP_NO_SOLVER:
            sol->error = pddl_true;
            ERR_RET(err, PDDL_LP_STATUS_ERR, "Missing an MIP/LP solver."
                    " Recompile with a support of one of the supported solvers.");
        default:
            sol->error = pddl_true;
            ERR_RET(err, PDDL_LP_STATUS_ERR, "Unknown solver %d", lp->cfg.solver);
    }
}

void pddlLPWrite(const pddl_lp_t *lp, const char *fn)
{
    FILE *fout = fopen(fn, "w");
    PANIC_IF(fout == NULL, "Could not open file %s", fn);
    if (lp->cfg.maximize){
        fprintf(fout, "Maximize\n");
    }else{
        fprintf(fout, "Minimize\n");
    }
    fprintf(fout, "  obj:");
    int num_written = 0;
    for (int c = 0; c < lp->col_size; ++c){
        if (lp->col[c].obj != 0.){
            fprintf(fout, " %+.4f x%d", lp->col[c].obj, c + 1);
            if (++num_written % 5 == 0)
                fprintf(fout, "\n ");
        }
    }
    fprintf(fout, "\n");

    fprintf(fout, "Subject To\n");
    for (int r = 0; r < lp->row_size; ++r){
        if (lp->row[r].coef_size == 0)
            continue;
        fprintf(fout, "c%d:", r + 1);
        int num_written = 0;
        for (int c = 0; c < lp->row[r].coef_size; ++c){
            fprintf(fout, " %+.4f x%d", lp->row[r].coef[c].coef,
                    lp->row[r].coef[c].col + 1);

            if (++num_written % 5 == 0)
                fprintf(fout, "\n ");
        }
        switch (lp->row[r].sense){
            case 'L':
                fprintf(fout, " <= ");
                break;
            case 'G':
                fprintf(fout, " >= ");
                break;
            case 'E':
                fprintf(fout, " = ");
                break;
        }
        fprintf(fout, "%.4f\n", lp->row[r].rhs);
    }

    pddl_bool_t has_bound_header = pddl_false;
    for (int c = 0; c < lp->col_size; ++c){
        if (lp->col[c].lb > PDDL_LP_MIN_BOUND || lp->col[c].ub < PDDL_LP_MAX_BOUND){
            if (!has_bound_header){
                fprintf(fout, "Bounds\n");
                has_bound_header = pddl_true;
            }
            if (lp->col[c].lb > PDDL_LP_MIN_BOUND)
               fprintf(fout, "  %.4f <=", lp->col[c].lb);
            fprintf(fout, " x%d", c + 1);
            if (lp->col[c].ub < PDDL_LP_MAX_BOUND)
               fprintf(fout, "  <= %.4f", lp->col[c].ub);
        }
    }

    pddl_bool_t has_general_header = pddl_false;
    for (int c = 0; c < lp->col_size; ++c){
        if (lp->col[c].type == PDDL_LP_COL_TYPE_INT){
            if (!has_general_header){
                fprintf(fout, "General\n");
                has_general_header = pddl_true;
            }
            fprintf(fout, "  x%d\n", c + 1);
        }
    }

    pddl_bool_t has_binary_header = pddl_false;
    for (int c = 0; c < lp->col_size; ++c){
        if (lp->col[c].type == PDDL_LP_COL_TYPE_BINARY){
            if (!has_binary_header){
                fprintf(fout, "Binary\n");
                has_binary_header = pddl_true;
            }
            fprintf(fout, "  x%d\n", c + 1);
        }
    }

    fprintf(fout, "End\n");
    fclose(fout);
}

void _pddlLPSolutionInit(pddl_lp_solution_t *sol, const pddl_lp_t *lp)
{
    sol->solved = pddl_false;
    sol->solved_optimally = pddl_false;
    sol->solved_suboptimally = pddl_false;
    sol->unsolvable = pddl_false;
    sol->not_solved = pddl_false;
    sol->error = pddl_false;
    sol->timed_out = pddl_false;
    if (sol->var_val != NULL)
        ZEROIZE_ARR(sol->var_val, lp->col_size);
    sol->obj_val = 0.;
}

pddl_lp_status_t _pddlLPSolutionToStatus(const pddl_lp_solution_t *sol)
{
    if (sol->solved_optimally)
        return PDDL_LP_STATUS_OPTIMAL;
    if (sol->solved_suboptimally)
        return PDDL_LP_STATUS_SUBOPTIMAL;
    if (sol->unsolvable)
        return PDDL_LP_STATUS_INFEASIBLE;
    if (sol->not_solved)
        return PDDL_LP_STATUS_NO_SOLUTION_FOUND;
    if (sol->error)
        return PDDL_LP_STATUS_ERR;
    PANIC("Unkown status of the LP solver. This is definitely a bug!");
    return PDDL_LP_STATUS_ERR;
}
