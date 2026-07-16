/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_TYPE_H__
#define __PDDL_TYPE_H__

#include <pddl/iset.h>
#include <pddl/common.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/** Forward declaration */
struct pddl_objs;

struct pddl_type {
    char *name;        /*!< Name of the type */
    int parent;        /*!< ID of the parent type */
    pddl_iset_t child;  /*!< IDs of children types */
    pddl_iset_t either; /*!< type IDs for special (either ...) type */
    pddl_iset_t obj; /*!< Objs of this type */
    /** IDs of "either" types this type is part of */
    pddl_iset_t parent_either;
};
typedef struct pddl_type pddl_type_t;

struct pddl_types {
    pddl_type_t *type;
    int type_size;
    int type_alloc;

    char *obj_type_map;
    size_t obj_type_map_memsize;
};
typedef struct pddl_types pddl_types_t;

/**
 * Initialize types with the default "object" type.
 */
void pddlTypesInit(pddl_types_t *types);

/**
 * Initialize dst as a deep copy of src.
 */
void pddlTypesInitCopy(pddl_types_t *dst, const pddl_types_t *src);

/**
 * Frees allocated resources.
 */
void pddlTypesFree(pddl_types_t *types);

/**
 * Returns ID of the type corresponding to the name.
 */
int pddlTypesGet(const pddl_types_t *t, const char *name);

/**
 * Adds a new type with the given name and the specified parent.
 * If a type with the same name already exists, nothing is added and its ID
 * is returned, otherwise the new type's ID is returned.
 */
int pddlTypesAdd(pddl_types_t *t, const char *name, int parent);

/**
 * Adds or returns existing (either ...) type.
 */
int pddlTypesAddEither(pddl_types_t *ts, const pddl_iset_t *either);

/**
 * Prints list of types to the specified output.
 */
void pddlTypesPrint(const pddl_types_t *t, FILE *fout);

/**
 * Returns true if the specified type is (either ...) type.
 */
pddl_bool_t pddlTypesIsEither(const pddl_types_t *ts, int tid);

/**
 * Record the given object as being of the given type.
 */
void pddlTypesAddObj(pddl_types_t *ts, int obj_id, int type_id);

/**
 * Build mapping for fast testing whether an object is of a specified type.
 */
void pddlTypesBuildObjTypeMap(pddl_types_t *ts, int obj_size);

/**
 * Returns list of object IDs of the specified type.
 */
const int *pddlTypesObjsByType(const pddl_types_t *ts, int type_id, int *size);

/**
 * Returns number of objects of the specified type.
 */
int pddlTypeNumObjs(const pddl_types_t *ts, int type_id);

/**
 * Returns idx's object of the given type.
 */
int pddlTypeGetObj(const pddl_types_t *ts, int type_id, int idx);

/**
 * Returns true if the object compatible with the specified type.
 */
pddl_bool_t pddlTypesObjHasType(const pddl_types_t *ts, int type, int obj);

/**
 * Returns true if parent is a parent type of child type.
 */
pddl_bool_t pddlTypesIsParent(const pddl_types_t *ts, int child, int parent);

/**
 * Returns true if t1 and t2 are disjunct types, i.e., there cannot be
 * object of both types at the same time.
 */
pddl_bool_t pddlTypesAreDisjunct(const pddl_types_t *ts, int t1, int t2);
pddl_bool_t pddlTypesAreDisjoint(const pddl_types_t *ts, int t1, int t2);

/**
 * Returns true if D(t1) \subseteq D(t2)
 */
pddl_bool_t pddlTypesIsSubset(const pddl_types_t *ts, int t1, int t2);

/**
 * Returns true if {type} is a minimal type, i.e., it has no sub-types.
 */
pddl_bool_t pddlTypesIsMinimal(const pddl_types_t *ts, int type);

/**
 * Returns true if:
 * 1. for every pair of types t1,t2 it holds that D(t1) \subseteq D(t2) or
 *    D(t2) \subseteq D(t1) or D(t1) \cap D(t2) = \emptyset; and
 * 2. union of minimal types (i.e., without subtypes) equals the whole set
 *    of objects.
 */
pddl_bool_t pddlTypesHasStrictPartitioning(const pddl_types_t *ts,
                                           const struct pddl_objs *obj);

/**
 * Remap objects
 */
void pddlTypesRemapObjs(pddl_types_t *ts, const int *remap);

/**
 * Returns a type ID that is complement of t with respect to p, or -1 if
 * there is no such type.
 * That is, x is complement of t with respect to p if p is a parent of t
 * and D(x) = D(p) \setminus D(t).
 */
int pddlTypesComplement(const pddl_types_t *ts, int t, int p);

/**
 * Remove empty types, but always keep the top type "object"
 */
void pddlTypesRemoveEmpty(pddl_types_t *ts, int obj_size, int *type_remap);

/**
 * Print requirements in PDDL format.
 */
void pddlTypesPrintPDDL(const pddl_types_t *ts, FILE *fout);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_TYPE_H__ */
