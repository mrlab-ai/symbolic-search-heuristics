/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "toml.h"
#include "pddl/set.h"

void pddlSetISetInitCopy(pddl_set_iset_t *ss, const pddl_set_iset_t *sin)
{
    pddlSetISetInit(ss);
    for (int i = 0; i < pddlSetISetSize(sin); ++i)
        pddlSetISetAdd(ss, pddlSetISetGet(sin, i));
}

static void _genAllSubsetsRec(pddl_set_iset_t *ss,
                              const pddl_iset_t *set,
                              int cur_idx,
                              int subset_size,
                              int *subset,
                              int subset_pos)
{
    subset[subset_pos] = pddlISetGet(set, cur_idx);
    if (subset_pos == subset_size - 1){
        PDDL_ISET(newset);
        for (int i = 0; i < subset_size; ++i)
            pddlISetAdd(&newset, subset[i]);
        pddlSetISetAdd(ss, &newset);
        pddlISetFree(&newset);
        return;
    }

    for (int idx = cur_idx + 1;
            idx <= pddlISetSize(set) - subset_size + subset_pos + 1; ++idx){
        _genAllSubsetsRec(ss, set, idx, subset_size, subset, subset_pos + 1);
    }

}

static void genAllSubsetsRec(pddl_set_iset_t *ss,
                             const pddl_iset_t *set,
                             int subset_size)
{
    ASSERT(subset_size < pddlISetSize(set));
    int subset[subset_size];

    for (int idx = 0; idx <= pddlISetSize(set) - subset_size; ++idx)
        _genAllSubsetsRec(ss, set, idx, subset_size, subset, 0);
}

static void genAllSubsets(pddl_set_iset_t *ss,
                          const pddl_iset_t *set,
                          int min_size)
{
    if (min_size >= pddlISetSize(set)){
        return;

    }else if (min_size == 0){
        PDDL_ISET(newset);
        pddlSetISetAdd(ss, &newset);
        pddlISetFree(&newset);
        genAllSubsets(ss, set, 1);

    }else if (min_size == 1){
        PDDL_ISET(newset);
        int el;
        PDDL_ISET_FOR_EACH(set, el){
            pddlISetEmpty(&newset);
            pddlISetAdd(&newset, el);
            pddlSetISetAdd(ss, &newset);
        }
        pddlISetFree(&newset);
        genAllSubsets(ss, set, 2);

    }else if (min_size == 2){
        PDDL_ISET(newset);
        int set_size = pddlISetSize(set);
        for (int i = 0; i < set_size - 1; ++i){
            int el1 = pddlISetGet(set, i);
            for (int j = i + 1; j < set_size; ++j){
                int el2 = pddlISetGet(set, j);
                PDDL_ISET_SET(&newset, el1, el2);
                pddlSetISetAdd(ss, &newset);
            }
        }
        pddlISetFree(&newset);
        genAllSubsets(ss, set, 3);

    }else if (min_size == 3){
        PDDL_ISET(newset);
        int set_size = pddlISetSize(set);
        for (int i = 0; i < set_size - 2; ++i){
            int el1 = pddlISetGet(set, i);
            for (int j = i + 1; j < set_size - 1; ++j){
                int el2 = pddlISetGet(set, j);
                for (int k = j + 1; k < set_size; ++k){
                    int el3 = pddlISetGet(set, k);
                    PDDL_ISET_SET(&newset, el1, el2, el3);
                    pddlSetISetAdd(ss, &newset);
                }
            }
        }
        pddlISetFree(&newset);
        genAllSubsets(ss, set, 4);

    }else{
        for (int size = min_size; size < pddlISetSize(set); ++size)
            genAllSubsetsRec(ss, set, size);
    }
}

void pddlSetISetGenAllSubsets(pddl_set_iset_t *ss, int min_size)
{
    int input_size = pddlSetISetSize(ss);
    for (int seti = 0; seti < input_size; ++seti){
        const pddl_iset_t *set = pddlSetISetGet(ss, seti);
        if (pddlISetSize(set) > min_size)
            genAllSubsets(ss, set, min_size);
    }
}

int pddlSetISetLoadFromFile(pddl_set_iset_t *ss,
                            const pddl_strips_t *strips,
                            const pddl_fdr_t *fdr,
                            const char *filename,
                            pddl_err_t *err)
{
    if ((strips == NULL && fdr == NULL) || (strips != NULL && fdr != NULL)){
        ERR_RET(err, -1, "Exactly one of strips and fdr parameters must be non-NULL.");
    }

    FILE *fin = fopen(filename, "r");
    if (fin == NULL)
        ERR_RET(err, -1, "Cannot open file %s", filename);

    pddl_toml_table_t *table = pddl_toml_parse_file(fin, err);
    fclose(fin);
    if (table == NULL)
        TRACE_RET(err, -1);

    const pddl_toml_array_t *arr = pddl_toml_array_in(table, "conj");
    if (arr == NULL){
        pddl_toml_free(table);
        ERR_RET(err, -1, "Cannot find array 'conj' in the file %s", filename);
    }
    int conj_size = pddl_toml_array_nelem(arr);
    for (int conji = 0; conji < conj_size; ++conji){
        const pddl_toml_array_t *conj_arr = pddl_toml_array_at(arr, conji);
        if (conj_arr == NULL){
            pddl_toml_free(table);
            ERR_RET(err, -1, "Input file %s is maloformed: 'conj' has to be"
                    " array of arrays of strings", filename);
        }
        PDDL_ISET(conj);
        int size = pddl_toml_array_nelem(conj_arr);
        for (int i = 0; i < size; ++i){
            pddl_toml_datum_t d = pddl_toml_string_at(conj_arr, i);
            if (!d.ok){
                pddl_toml_free(table);
                pddlISetFree(&conj);
                ERR_RET(err, -1, "Input file %s is maloformed: 'conj' has to be"
                        " array of arrays of strings", filename);
            }

            int fact = -1;
            if (strips != NULL){
                for (fact = 0; fact < strips->fact.fact_size; ++fact){
                    if (strcmp(strips->fact.fact[fact]->name, d.u.s) == 0)
                        break;
                }
                if (fact >= strips->fact.fact_size)
                    fact = -1;

            }else if (fdr != NULL){
                for (fact = 0; fact < fdr->var.global_id_size; ++fact){
                    const pddl_fdr_val_t *v = fdr->var.global_id_to_val[fact];
                    if (strcmp(v->name, d.u.s) == 0)
                        break;
                }
                if (fact >= fdr->var.global_id_size)
                    fact = -1;
            }

            if (fact < 0){
                pddl_toml_free(table);
                pddlISetFree(&conj);
                ERR_RET(err, -1, "Could not find fact (%s). The input file %s"
                        " probably does not match the planning task.",
                        d.u.s, filename);
            }
            pddlISetAdd(&conj, fact);
        }
        pddlSetISetAdd(ss, &conj);
        pddlISetFree(&conj);
    }

    return 0;
}

void pddlISetPrintCompressed(const pddl_iset_t *set, FILE *fout)
{
    for (int i = 0; i < pddlISetSize(set); ++i){
        if (i != 0)
            fprintf(fout, " ");
        if (i == pddlISetSize(set) - 1){
            fprintf(fout, "%d", pddlISetGet(set, i));
        }else{
            int j;
            for (j = i + 1; j < pddlISetSize(set)
                    && pddlISetGet(set, j) == pddlISetGet(set, j - 1) + 1;
                    ++j);
            if (j - 1 == i){
                fprintf(fout, "%d", pddlISetGet(set, i));
            }else{
                fprintf(fout, "%d-%d",
                        pddlISetGet(set, i), pddlISetGet(set, j - 1));
            }
            i = j - 1;
        }
    }
}

void pddlISetPrint(const pddl_iset_t *set, FILE *fout)
{
    int not_first = 0;
    int v;
    PDDL_ISET_FOR_EACH(set, v){
        if (not_first)
            fprintf(fout, " ");
        fprintf(fout, "%d", v);
        not_first = 1;
    }
}

void pddlISetPrintln(const pddl_iset_t *set, FILE *fout)
{
    pddlISetPrint(set, fout);
    fprintf(fout, "\n");
}
