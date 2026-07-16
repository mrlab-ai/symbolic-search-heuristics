/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL__LP_COMPRESSED_ROW_PROBLEM_H__
#define __PDDL__LP_COMPRESSED_ROW_PROBLEM H__

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

#ifndef COMPRESSED_INT
#define COMPRESSED_INT int
#endif /* COMPRESSED_INT */

#ifndef COMPRESSED_COL_TYPE
#define COMPRESSED_COL_TYPE char
#endif /* COMPRESSED_COL_TYPE */

struct pddl_lp_compressed_row_problem {
    int num_col;
    double *col_obj;
    double *col_lb;
    double *col_ub;
    COMPRESSED_COL_TYPE *col_type;

    // TODO: Refactor with indicator_* part
    int num_row;
    int num_nz;
    double *row_lb;
    double *row_ub;
    double *row_rhs;
    char *row_sense;
    COMPRESSED_INT *row_beg;
    COMPRESSED_INT *row_ind;
    double *row_val;

    int indicator_num_row;
    int indicator_num_nz;
    COMPRESSED_INT *indicator_var;
    int *indicator_complemented;
    double *indicator_row_lb;
    double *indicator_row_ub;
    double *indicator_row_rhs;
    char *indicator_row_sense;
    COMPRESSED_INT *indicator_row_beg;
    COMPRESSED_INT *indicator_row_ind;
    double *indicator_row_val;

    pddl_bool_t is_mip;
};
typedef struct pddl_lp_compressed_row_problem pddl_lp_compressed_row_problem_t;

static void compressedRowProblemInit(pddl_lp_compressed_row_problem_t *p,
                                     const pddl_lp_t *lp,
                                     COMPRESSED_COL_TYPE col_type_real,
                                     COMPRESSED_COL_TYPE col_type_int,
                                     COMPRESSED_COL_TYPE col_type_bin,
                                     pddl_bool_t use_row_ub_lb,
                                     double min_bound,
                                     double max_bound)
{
    ZEROIZE(p);
    p->num_col = lp->col_size;
    p->col_obj = ALLOC_ARR(double, lp->col_size);
    p->col_lb = ALLOC_ARR(double, lp->col_size);
    p->col_ub = ALLOC_ARR(double, lp->col_size);
    p->col_type = ALLOC_ARR(COMPRESSED_COL_TYPE, lp->col_size);
    for (int ci = 0; ci < lp->col_size; ++ci){
        p->col_obj[ci] = lp->col[ci].obj;
        p->col_lb[ci] = lp->col[ci].lb;
        p->col_ub[ci] = lp->col[ci].ub;
        if (p->col_lb[ci] <= PDDL_LP_MIN_BOUND)
            p->col_lb[ci] = min_bound;
        if (p->col_ub[ci] >= PDDL_LP_MAX_BOUND)
            p->col_ub[ci] = max_bound;
        switch (lp->col[ci].type){
            case PDDL_LP_COL_TYPE_REAL:
                p->col_type[ci] = col_type_real;
                break;
            case PDDL_LP_COL_TYPE_INT:
                p->col_type[ci] = col_type_int;
                p->is_mip = pddl_true;
                break;
            case PDDL_LP_COL_TYPE_BINARY:
                p->col_type[ci] = col_type_bin;
                p->is_mip = pddl_true;
                p->col_lb[ci] = 0.;
                p->col_ub[ci] = 1.;
                break;
        }
    }

    p->num_row = 0;
    p->num_nz = 0;
    p->indicator_num_row = 0;
    p->indicator_num_nz = 0;
    for (int ri = 0; ri < lp->row_size; ++ri){
        if (lp->row[ri].indicator.enabled){
            p->indicator_num_nz += lp->row[ri].coef_size;
            ++p->indicator_num_row;
        }else{
            p->num_nz += lp->row[ri].coef_size;
            ++p->num_row;
        }
    }

    if (use_row_ub_lb){
        if (p->num_row > 0){
            p->row_lb = ALLOC_ARR(double, p->num_row);
            p->row_ub = ALLOC_ARR(double, p->num_row);
        }
        if (p->indicator_num_row > 0){
            p->indicator_row_lb = ALLOC_ARR(double, p->indicator_num_row);
            p->indicator_row_ub = ALLOC_ARR(double, p->indicator_num_row);
        }
    }else{
        if (p->num_row > 0){
            p->row_rhs = ALLOC_ARR(double, p->num_row);
        }
        if (p->indicator_num_row > 0){
            p->indicator_row_rhs = ALLOC_ARR(double, p->indicator_num_row);
        }
    }
    if (p->num_row > 0){
        p->row_sense = ALLOC_ARR(char, p->num_row);
    }
    if (p->indicator_num_row > 0){
        p->indicator_var = ALLOC_ARR(COMPRESSED_INT, p->indicator_num_row);
        p->indicator_complemented = ALLOC_ARR(int, p->indicator_num_row);
        p->indicator_row_sense = ALLOC_ARR(char, p->indicator_num_row);
    }
    for (int i = 0, row = 0, ind_row = 0; i < lp->row_size; ++i){
        if (lp->row[i].indicator.enabled){
            p->indicator_var[ind_row] = lp->row[i].indicator.var;
            p->indicator_complemented[ind_row] = 0;
            if (!lp->row[i].indicator.val)
                p->indicator_complemented[ind_row] = 1;

            p->indicator_row_sense[ind_row] = lp->row[i].sense;
            if (use_row_ub_lb){
                switch (lp->row[ind_row].sense){
                    case 'L':
                        p->indicator_row_lb[ind_row] = min_bound;
                        p->indicator_row_ub[ind_row] = lp->row[i].rhs;
                        break;
                    case 'G':
                        p->indicator_row_lb[ind_row] = lp->row[i].rhs;
                        p->indicator_row_ub[ind_row] = max_bound;
                        break;
                    case 'E':
                        p->indicator_row_lb[ind_row] = lp->row[i].rhs;
                        p->indicator_row_ub[ind_row] = lp->row[i].rhs;
                        break;
                    default:
                        PANIC("Unkown row sense '%c'", lp->row[i].sense);
                        break;
                }
            }else{
                p->indicator_row_rhs[ind_row] = lp->row[i].rhs;
                if (p->indicator_row_rhs[ind_row] <= PDDL_LP_MIN_BOUND){
                    p->indicator_row_rhs[ind_row] = min_bound;
                }else if (p->indicator_row_rhs[ind_row] >= PDDL_LP_MAX_BOUND){
                    p->indicator_row_rhs[ind_row] = max_bound;
                }
            }

            ++ind_row;

        }else{
            p->row_sense[row] = lp->row[i].sense;
            if (use_row_ub_lb){
                switch (lp->row[row].sense){
                    case 'L':
                        p->row_lb[row] = min_bound;
                        p->row_ub[row] = lp->row[i].rhs;
                        break;
                    case 'G':
                        p->row_lb[row] = lp->row[i].rhs;
                        p->row_ub[row] = max_bound;
                        break;
                    case 'E':
                        p->row_lb[row] = lp->row[i].rhs;
                        p->row_ub[row] = lp->row[i].rhs;
                        break;
                    default:
                        PANIC("Unkown row sense '%c'", lp->row[i].sense);
                        break;
                }
            }else{
                p->row_rhs[row] = lp->row[i].rhs;
                if (p->row_rhs[row] <= PDDL_LP_MIN_BOUND){
                    p->row_rhs[row] = min_bound;
                }else if (p->row_rhs[row] >= PDDL_LP_MAX_BOUND){
                    p->row_rhs[row] = max_bound;
                }
            }

            ++row;
        }
    }

    if (p->num_row > 0){
        p->row_beg = ALLOC_ARR(COMPRESSED_INT, p->num_row);
        p->row_ind = ALLOC_ARR(COMPRESSED_INT, p->num_nz);
        p->row_val = ALLOC_ARR(double, p->num_nz);
    }
    if (p->indicator_num_row > 0){
        p->indicator_row_beg = ALLOC_ARR(COMPRESSED_INT, p->indicator_num_row);
        p->indicator_row_ind = ALLOC_ARR(COMPRESSED_INT, p->indicator_num_nz);
        p->indicator_row_val = ALLOC_ARR(double, p->indicator_num_nz);
    }
    int ins = 0;
    int ind_ins = 0;
    for (int ri = 0, row = 0, ind_row = 0; ri < lp->row_size; ++ri){
        if (lp->row[ri].indicator.enabled){
            p->indicator_row_beg[ind_row] = ind_ins;
            for (int ci = 0; ci < lp->row[ri].coef_size; ++ci){
                p->indicator_row_ind[ind_ins] = lp->row[ri].coef[ci].col;
                p->indicator_row_val[ind_ins] = lp->row[ri].coef[ci].coef;
                ++ind_ins;
            }
            ++ind_row;

        }else{
            p->row_beg[row] = ins;
            for (int ci = 0; ci < lp->row[ri].coef_size; ++ci){
                p->row_ind[ins] = lp->row[ri].coef[ci].col;
                p->row_val[ins] = lp->row[ri].coef[ci].coef;
                ++ins;
            }
            ++row;
        }
    }
    ASSERT(ins == p->num_nz && ind_ins == p->indicator_num_nz);
}

static void compressedRowProblemFree(pddl_lp_compressed_row_problem_t *p)
{
    if (p->col_obj != NULL)
        FREE(p->col_obj);
    if (p->col_lb != NULL)
        FREE(p->col_lb);
    if (p->col_ub != NULL)
        FREE(p->col_ub);
    if (p->col_type != NULL)
        FREE(p->col_type);

    if (p->row_lb != NULL)
        FREE(p->row_lb);
    if (p->row_ub != NULL)
        FREE(p->row_ub);
    if (p->row_rhs != NULL)
        FREE(p->row_rhs);
    if (p->row_sense != NULL)
        FREE(p->row_sense);
    if (p->row_beg != NULL)
        FREE(p->row_beg);
    if (p->row_ind != NULL)
        FREE(p->row_ind);
    if (p->row_val != NULL)
        FREE(p->row_val);

    if (p->indicator_var != NULL)
        FREE(p->indicator_var);
    if (p->indicator_complemented != NULL)
        FREE(p->indicator_complemented);
    if (p->indicator_row_lb != NULL)
        FREE(p->indicator_row_lb);
    if (p->indicator_row_ub != NULL)
        FREE(p->indicator_row_ub);
    if (p->indicator_row_rhs != NULL)
        FREE(p->indicator_row_rhs);
    if (p->indicator_row_sense != NULL)
        FREE(p->indicator_row_sense);
    if (p->indicator_row_beg != NULL)
        FREE(p->indicator_row_beg);
    if (p->indicator_row_ind != NULL)
        FREE(p->indicator_row_ind);
    if (p->indicator_row_val != NULL)
        FREE(p->indicator_row_val);
}

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL__LP_COMPRESSED_ROW_PROBLEM H__ */
