/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/cp.h"
#include "pddl/subprocess.h"
#include "pddl/strstream.h"
#include "pddl/pddl_file.h"
#include "_cp.h"

static char pddl_minizinc_bin[PDDL_FILE_MAX_PATH_LEN];

void pddlCPSetDefaultMinizincBin(const char *fn)
{
    strncpy(pddl_minizinc_bin, fn, PDDL_FILE_MAX_PATH_LEN - 1);
}

const char *pddlCPDefaultMinizincBin(void)
{
    if (pddl_minizinc_bin[0] != '\x0')
        return pddl_minizinc_bin;
#ifdef PDDL_MINIZINC_BIN
    return PDDL_MINIZINC_BIN;
#else /* PDDL_MINIZINC_BIN */
    return NULL;
#endif /* PDDL_MINIZINC_BIN */
}

int pddlCPSolve_Minizinc(const pddl_cp_t *cp,
                         const pddl_cp_solve_config_t *cfg,
                         pddl_cp_sol_t *sol,
                         pddl_err_t *err)
{
    ZEROIZE(sol);

    char *minizinc_bin = (char *)cfg->minizinc;
    if (minizinc_bin == NULL){
        minizinc_bin = (char *)pddlCPDefaultMinizincBin();
        LOG(err, "default minizinc [%s]", minizinc_bin);
    }else{
        LOG(err, "minizinc [%s]", minizinc_bin);
    }
    char *buf = NULL;
    size_t bufsize = 0;

    FILE *fout = pddl_strstream(&buf, &bufsize);
    PANIC_IF(fout == NULL, "Cannot open string stream!");
    pddlCPWriteMinizinc(cp, fout);
    fflush(fout);
    fclose(fout);
    LOG(err, "Problem written in mzn format");
    {FILE *f = fopen("x", "w");
    fprintf(f, "%s\n", buf);
    fclose(f);}

    char *argv[] = {
        minizinc_bin,
        "-a", // list all solutions
        "--soln-sep", "", // empty solution separator
        "--unsat-msg", "UNSAT", // message for unsatisfiable problem
        "--unknown-msg", "UNKNOWN", // message for unknown output
        "--unbounded-msg", "UNBOUND", // message for unbounded problem
        "--unsatorunbnd-msg", "UNSATorUNBOUND", // unsat or unbound message
        "--unknown-msg", "UNKNOWN", // "unknown" message
        "--error-msg", "ERR", // error message
        "--search-complete-msg", "SAT", // successfuly found solution message
        "-", // read .mzn from stdin
        NULL, NULL, // placeholders for other arguments
        NULL
    };
    char arg_time_limit[64];

    if (cfg->max_search_time > 0.){
        ASSERT(strcmp(argv[17], "SAT") == 0);
        sprintf(arg_time_limit, "%lu", (unsigned long)(1000. * cfg->max_search_time));
        argv[18] = "--time-limit";
        argv[19] = arg_time_limit;
        argv[20] = "-";
    }
    ASSERT(argv[21] == NULL);

    int ret = PDDL_CP_UNKNOWN;
    pddl_exec_status_t status;
    char *solbuf = NULL;
    int solbuf_size = 0;
    char *errbuf = NULL;
    int errbuf_size = 0;
    int execret = pddlExecvp(argv, &status, buf, bufsize,
                             &solbuf, &solbuf_size, &errbuf, &errbuf_size, err);
    if (execret != 0){
        ret = PDDL_CP_UNKNOWN;
        goto minizinc_end;
    }
    if (status.exit_status != 0){
        LOG(err, "Something went wrong.");
        LOG(err, "Minizinc return status was %d", status.exit_status);
        LOG(err, "Error output: %s", errbuf);
        ret = PDDL_CP_UNKNOWN;
        goto minizinc_end;
    }
    if (status.signaled){
        LOG(err, "Something went wrong.");
        LOG(err, "Minizinc was killed by a signal.");
        LOG(err, "Error output: %s", errbuf);
        ret = PDDL_CP_UNKNOWN;
        goto minizinc_end;
    }
    if (solbuf_size == 0){
        LOG(err, "Something went wrong.");
        LOG(err, "Minizinc did not print any output.");
        ret = PDDL_CP_UNKNOWN;
        goto minizinc_end;
    }

    // Read solution(s)
    int *solarr = ALLOC_ARR(int, cp->ivar.ivar_size);
    int solidx = 0;
    int offset = 0;
    int have_solution = 0;
    int sread;
    while (sscanf(solbuf + offset, "%d%n", solarr + solidx, &sread) > 0){
        // TODO: More solutions, for now only reading until we get the last
        //       solution
        offset += sread;
        solidx = (solidx + 1) % cp->ivar.ivar_size;
        have_solution = 1;
    }

    if (solidx != 0){
        LOG(err, "Something went wrong.");
        LOG(err, "Minizinc did not print the full output.");
        if (solarr != NULL)
            FREE(solarr);
        ret = PDDL_CP_UNKNOWN;
        goto minizinc_end;
    }

    // Skip whitespace before reading the result
    while (solbuf[offset] != '\x0'
            && (solbuf[offset] == ' '
                || solbuf[offset] == '\n'
                || solbuf[offset] == '\t')){
        ++offset;
    }

    if (strncmp(solbuf + offset, "SAT", 3) == 0){
        ret = PDDL_CP_FOUND;
        LOG(err, "Solved optimally");
    }else if (strncmp(solbuf + offset, "UNKNOWN", 7) == 0){
        if (have_solution){
            ret = PDDL_CP_FOUND_SUBOPTIMAL;
            LOG(err, "Solved sub-optimally");
        }else{
            ret = PDDL_CP_ABORTED;
            LOG(err, "No solution found before time limit");
        }
    }else if (strncmp(solbuf + offset, "UNSAT", 5) == 0){
        ret = PDDL_CP_NO_SOLUTION;
        LOG(err, "Unsolvable");
    }else if (strncmp(solbuf + offset, "UNBOUND", 7) == 0){
        ret = PDDL_CP_NO_SOLUTION;
        LOG(err, "Unbounded");
    }else if (strncmp(solbuf + offset, "UNSATorUNBOUND", 15) == 0){
        ret = PDDL_CP_NO_SOLUTION;
        LOG(err, "Unsolvable or unbounded");
    }else if (strncmp(solbuf + offset, "ERR", 3) == 0){
        ret = PDDL_CP_ABORTED;
        LOG(err, "Error Detected");
        LOG(err, "Error output: %s", errbuf);
    }else{
        LOG(err, "Something went wrong.");
        LOG(err, "Minizinc did not print the full output -- missing result indicator.");
        if (solarr != NULL)
            FREE(solarr);
        ret = PDDL_CP_UNKNOWN;
        goto minizinc_end;
    }

    if (ret == PDDL_CP_FOUND || ret == PDDL_CP_FOUND_SUBOPTIMAL)
        pddlCPSolAdd(cp, sol, solarr);


    if (solarr != NULL)
        FREE(solarr);
minizinc_end:
    if (solbuf != NULL)
        FREE(solbuf);
    if (errbuf != NULL)
        FREE(errbuf);
    if (buf != NULL)
        free(buf);
    return ret;
}
