/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_SET_H__
#define __PDDL_SET_H__

#include <pddl/hashset.h>
#include <pddl/iset.h>
#include <pddl/strips.h>
#include <pddl/fdr.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_set_iset {
    pddl_hashset_t set;
};
typedef struct pddl_set_iset pddl_set_iset_t;

#define PDDL_SET_ISET_FOR_EACH_ID(SS, ID) \
    for (int ID = 0; ID < (SS)->set.size; ++ID)
#define PDDL_SET_ISET_FOR_EACH_ID_SET(SS, ID, SET) \
    for (int ID = 0; \
            ID < (SS)->set.size \
                && ((SET) = pddlSetISetGet((SS), ID)); \
            ++ID)
#define PDDL_SET_ISET_FOR_EACH(SS, SET) \
    PDDL_SET_ISET_FOR_EACH_ID_SET(SS, __set_iset_i, SET)

_pddl_inline void pddlSetISetInit(pddl_set_iset_t *ss)
{
    pddlHashSetInitISet(&ss->set);
}

void pddlSetISetInitCopy(pddl_set_iset_t *ss, const pddl_set_iset_t *sin);

_pddl_inline void pddlSetISetFree(pddl_set_iset_t *ss)
{
    pddlHashSetFree(&ss->set);
}

_pddl_inline int pddlSetISetAdd(pddl_set_iset_t *ss, const pddl_iset_t *set)
{
    return pddlHashSetAdd(&ss->set, set);
}

_pddl_inline int pddlSetISetFind(pddl_set_iset_t *ss, const pddl_iset_t *set)
{
    return pddlHashSetFind(&ss->set, set);
}

_pddl_inline const pddl_iset_t *pddlSetISetGet(const pddl_set_iset_t *ss, int id)
{
    return (const pddl_iset_t *)pddlHashSetGet(&ss->set, id);
}

_pddl_inline int pddlSetISetSize(const pddl_set_iset_t *ss)
{
    return ss->set.size;
}

_pddl_inline void pddlSetISetUnion(pddl_set_iset_t *dst,
                                   const pddl_set_iset_t *src)
{
    for (int i = 0; i < pddlSetISetSize(src); ++i)
        pddlSetISetAdd(dst, pddlSetISetGet(src, i));
}

/**
 * Generate all subsets of size at least {min_size}; {ss} is both input and
 * output set of sets.
 */
void pddlSetISetGenAllSubsets(pddl_set_iset_t *ss, int min_size);

/**
 * Load conjunctions from the input .toml file, where there is expected to
 * be a key 'conj' assigned array of arrays of strings. Each string is then
 * matched agains facts either in {strips} or {fdr} to find the
 * corresponding facts. The set {ss} is extended with the conjunctions
 * found in the file {filename}.
 * Excatly one of {strips} and {fdr} has to be non-NULL.
 */
int pddlSetISetLoadFromFile(pddl_set_iset_t *ss,
                            const pddl_strips_t *strips,
                            const pddl_fdr_t *fdr,
                            const char *filename,
                            pddl_err_t *err);

void pddlISetPrintCompressed(const pddl_iset_t *set, FILE *fout);
void pddlISetPrint(const pddl_iset_t *set, FILE *fout);
void pddlISetPrintln(const pddl_iset_t *set, FILE *fout);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_SET_H__ */
