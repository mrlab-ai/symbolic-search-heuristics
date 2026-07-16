#include "internal.h"
#include "pddl/libs_info.h"
#include "pddl/sql_grounder.h"
const char * const pddl_sqlite_version = NULL;
#define ERROR PANIC("SQL Grounder requires the sqlite library: Re-compile with the USE_SQLITE=yes flag in Makefile.config.")
pddl_sql_grounder_t *pddlSqlGrounderNew(const pddl_t *pddl, pddl_err_t *err)
{ ERROR;return NULL;}
void pddlSqlGrounderDel(pddl_sql_grounder_t *g)
{ ERROR;}
int pddlSqlGrounderPrepActionSize(const pddl_sql_grounder_t *g)
{ ERROR;return -1;}
const pddl_prep_action_t *pddlSqlGrounderPrepAction(
                const pddl_sql_grounder_t *g, int action_id)
{ ERROR;return NULL;}
int pddlSqlGrounderInsertAtomArgs(pddl_sql_grounder_t *g,
                                  int pred_id,
                                  const int *args,
                                  pddl_err_t *err)
{ ERROR;return -1;}
int pddlSqlGrounderInsertGroundAtom(pddl_sql_grounder_t *g,
                                    const pddl_ground_atom_t *ga,
                                    pddl_err_t *err)
{ ERROR;return -1;}
int pddlSqlGrounderInsertAtom(pddl_sql_grounder_t *g,
                              const pddl_fm_atom_t *a,
                              pddl_err_t *err)
{ ERROR;return -1;}
int pddlSqlGrounderClearNonStatic(pddl_sql_grounder_t *g, pddl_err_t *err)
{ ERROR;return -1;}
int pddlSqlGrounderActionStart(pddl_sql_grounder_t *g,
                               int action_id,
                               pddl_err_t *err)
{ ERROR;return -1;}
int pddlSqlGrounderActionNext(pddl_sql_grounder_t *g,
                              int *args,
                              pddl_err_t *err)
{ ERROR;return -1;}
