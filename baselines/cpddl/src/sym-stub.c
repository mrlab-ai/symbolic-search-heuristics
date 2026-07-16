#include "internal.h"
#include "pddl/libs_info.h"
#include "pddl/sym.h"
const char * const pddl_bliss_version = NULL;
#define ERROR PANIC("Symmetries require the Bliss library; cpddl must be re-compiled with the Bliss support.")
void pddlStripsSymInitPDG(pddl_strips_sym_t *sym, const pddl_strips_t *strips)
{ ERROR;}
void pddlStripsSymFree(pddl_strips_sym_t *sym)
{ ERROR;}
void pddlStripsSymAllFactSetSymmetries(const pddl_strips_sym_t *sym,
                                       pddl_set_iset_t *sym_set)
{ ERROR;}
void pddlStripsSymAllOpSetSymmetries(const pddl_strips_sym_t *sym,
                                     pddl_set_iset_t *sym_set)
{ ERROR;}
void pddlStripsSymOpTransitiveClosure(const pddl_strips_sym_t *sym,
                                      int op_id,
                                      pddl_iset_t *transitive_closure)
{ ERROR;}
void pddlStripsSymOpSet(const pddl_strips_sym_t *sym,
                        int gen_id,
                        const pddl_iset_t *inset,
                        pddl_iset_t *outset)
{ ERROR;}
void pddlStripsSymPrintDebug(const pddl_strips_sym_t *sym, FILE *fout)
{ ERROR;}
