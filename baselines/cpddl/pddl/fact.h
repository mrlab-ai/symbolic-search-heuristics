/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_FACT_H__
#define __PDDL_FACT_H__

#include <pddl/common.h>
#include <pddl/obj.h>
#include <pddl/pred.h>
#include <pddl/ground_atom.h>
#include <pddl/iset.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

#define PDDL_FACT_MAX_NAME_SIZE 256

struct pddl_fact {
    int id;
    pddl_htable_key_t hash;
    pddl_list_t htable;

    /** Name of the fact */
    char *name;
    /** ID of the fact this fact is negation of, or -1 */
    int neg_of;
    /** If the fact was created from a grounded atom, its copy is stored
     *  here (may be NULL). */
    pddl_ground_atom_t *ground_atom;
    /** True if this fact corresponds to a conjunction of other facts.
     *  This is set by when constructing P^C tasks (see strips_conj module) */
    pddl_bool_t is_conjunction;
};
typedef struct pddl_fact pddl_fact_t;

/**
 * Initializes empty fact.
 */
void pddlFactInit(pddl_fact_t *f);
pddl_fact_t *pddlFactNew(void);

/**
 * Frees allocated memory
 */
void pddlFactFree(pddl_fact_t *f);
void pddlFactDel(pddl_fact_t *f);

/**
 * Compares two facts.
 */
int pddlFactCmp(const pddl_fact_t *f1, const pddl_fact_t *f2);

void pddlFactPrint(const pddl_fact_t *f,
                   const char *prefix,
                   const char *suffix,
                   FILE *fout);


struct pddl_facts {
    pddl_fact_t **fact;
    int fact_size;
    int fact_alloc;
    pddl_htable_t *htable;
};
typedef struct pddl_facts pddl_facts_t;

#define PDDL_FACTS_FOR_EACH(FACTS, FACT) \
    for (int __i = 0; \
            __i < (FACTS)->fact_size && ((FACT) = (FACTS)->fact[__i], 1); \
            ++__i) \
        if ((FACT) != NULL)

/**
 * Initialize set of facts.
 */
void pddlFactsInit(pddl_facts_t *fs);

/**
 * Free allocated resources.
 */
void pddlFactsFree(pddl_facts_t *fs);

/**
 * Adds a new copy of the given fact.
 */
int pddlFactsAdd(pddl_facts_t *fs, const pddl_fact_t *f);

/**
 * Adds a fact created from the grounded atom.
 */
int pddlFactsAddGroundAtom(pddl_facts_t *fs, const pddl_ground_atom_t *ga,
                           const pddl_t *pddl);

/**
 * Allocates and generates the remaping array for all facts assuming
 * facts from {del_facts} are deleted.
 * Returns the new number of facts after deletion, remap must have at least
 * fs->fact_size elements.
 */
int pddlFactsDelFactsGenRemap(int fact_size,
                              const pddl_iset_t *del_facts,
                              int *remap);

/**
 * Deletes fact (and frees all its memory).
 */
void pddlFactsDelFact(pddl_facts_t *fs, int fact_id);

/**
 * Same as pddlFactsDelFacts() but the input is a set of facts.
 */
void pddlFactsDelFacts(pddl_facts_t *fs, const pddl_iset_t *m, int *remap);

/**
 * Copies all facts from src to dst using pddlFactsAdd().
 */
void pddlFactsCopy(pddl_facts_t *dst, const pddl_facts_t *src);

/**
 * Sorts facts by their name and returns remapping from the old id to the
 * new id.
 */
void pddlFactsSort(pddl_facts_t *fs, int *remap);

void pddlFactsPrint(const pddl_facts_t *fs,
                    const char *prefix,
                    const char *suffix,
                    FILE *fout);

void pddlFactsPrintSet(const pddl_iset_t *fact_set,
                       const pddl_facts_t *fs,
                       const char *prefix,
                       const char *suffix,
                       FILE *fout);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_FACT_H__ */
