#include "internal.h"
#include "pddl/libs_info.h"
#include "pddl/asnets_convert_from_sql.h"
#define ERROR PANIC("Conversion from old ASNets models require the sqlite library: Re-compile with the USE_SQLITE=yes flag in Makefile.config.")
int pddlASNetsConvertFromSql(const char *input_model_sql,
                             const char *output_model,
                             pddl_err_t *err)
{ ERROR;return -1;}
