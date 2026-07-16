/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_GROUND_ATOM_H__
#define __PDDL_GROUND_ATOM_H__

#include <pddl/common.h>
#include <pddl/obj.h>
#include <pddl/pred.h>
#include <pddl/fm.h>
#include <pddl/iset.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

#define PDDL_GROUND_ATOM_MAX_NAME_SIZE 256

struct pddl_ground_atom {
    int id;
    uint64_t hash;
    pddl_list_t htable;

    int func_val; /*!< Assigned value in the case of function */
    int pred;     /*!< Predicate ID */
    int arg_size; /*!< Number of arguments */
    int *arg; /*!< Object IDs are arguments */

    int layer; /*!< Layer in RPG */
};
typedef struct pddl_ground_atom pddl_ground_atom_t;

/**
 * Frees allocated memory.
 */
void pddlGroundAtomDel(pddl_ground_atom_t *);

/**
 * Clones a ground atom.
 */
pddl_ground_atom_t *pddlGroundAtomClone(const pddl_ground_atom_t *);

struct pddl_ground_atoms {
    pddl_ground_atom_t **atom;
    int atom_size;
    int atom_alloc;
    pddl_htable_t *htable;
};
typedef struct pddl_ground_atoms pddl_ground_atoms_t;


/**
 * Initialize set of facts.
 */
void pddlGroundAtomsInit(pddl_ground_atoms_t *fs);

/**
 * Free allocated resources.
 */
void pddlGroundAtomsFree(pddl_ground_atoms_t *fs);

/**
 * Adds a unique ground atom. Returns the newly added atom or the atom that
 * was added in the past.
 */
pddl_ground_atom_t *pddlGroundAtomsAddAtom(pddl_ground_atoms_t *ga,
                                           const pddl_fm_atom_t *c,
                                           const int *arg);

/**
 * Adds a unique ground predicate atom (fact). Returns the newly added atom
 * or the atom that was added in the past if it was already there.
 */
pddl_ground_atom_t *pddlGroundAtomsAddPred(pddl_ground_atoms_t *ga,
                                           int pred,
                                           const int *arg,
                                           int arg_size);

/**
 * Find the grounded fact.
 */
pddl_ground_atom_t *pddlGroundAtomsFindAtom(const pddl_ground_atoms_t *ga,
                                            const pddl_fm_atom_t *c,
                                            const int *arg);
pddl_ground_atom_t *pddlGroundAtomsFindPred(const pddl_ground_atoms_t *ga,
                                            int pred,
                                            const int *arg,
                                            int arg_size);

/**
 * Add all atoms from the initial state.
 */
void pddlGroundAtomsAddInit(pddl_ground_atoms_t *ga, const pddl_t *pddl);

void pddlGroundAtomsPrint(const pddl_ground_atoms_t *ga,
                          const pddl_t *pddl,
                          FILE *fout);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_GROUND_ATOM_H__ */
