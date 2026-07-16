/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_PARSE_TOKENIZER_H__
#define __PDDL_PARSE_TOKENIZER_H__

#include <pddl/err.h>
#include <pddl/str_pool.h>
#include <pddl/strstream.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_parse_token {
    /** ID of the token -- see src/_parser.{y,h} */
    int token;
    /** String ID in the tokenizer->str_pool */
    int str_id;
    /** Direct pointer to the string */
    const char *str;
    /** Start line of the token in the input file*/
    int line;
    /** Start column */
    int column;
    /** Set to true if the token was already processed, i.e., returned by
     *  tokenizer. */
    int processed;
};
typedef struct pddl_parse_token pddl_parse_token_t;

struct pddl_parse_tokenizer {
    pddl_str_pool_t str_pool;
    pddl_parse_token_t *token;
    int token_size;
    int token_alloc;

    char *fn;

    int start_token_id;
    int next_token_id;
    int paren_counter;
};
typedef struct pddl_parse_tokenizer pddl_parse_tokenizer_t;

/**
 * Initializes tokenizer for the given file.
 * Returns 0 if the was successfully read and the tokenizer initialized.
 */
int pddlParseTokenizerInit(pddl_parse_tokenizer_t *tok, const char *fn,
                           pddl_err_t *err);

/**
 * Free allocated memory.
 */
void pddlParseTokenizerFree(pddl_parse_tokenizer_t *tok);

/**
 * Finds section starting with the specified {token} and prepares tokenizer
 * for producing tokens within that section. It start the search from the
 * last returned token unless pddlParseTokenizerRestart() is called.
 * Returns 0 on success, 1 if there is no such section, and -1 on error.
 */
int pddlParseTokenizerStartSection(pddl_parse_tokenizer_t *tok, int token,
                                   pddl_err_t *err);

/**
 * Resets the internal starting poisition for *StartSection() function to zero.
 */
void pddlParseTokenizerRestart(pddl_parse_tokenizer_t *tok);

/**
 * Start tokenizing from the beginning.
 */
void pddlParseTokenizerStart(pddl_parse_tokenizer_t *tok);

/**
 * Returns next token. This function assumes that
 * pddlParseTokenizerStartSection() was called at some point.
 * Returns 0 if token was produced, 1 if there are no more tokens, and
 * -1 on error.
 */
int pddlParseTokenizerNext(pddl_parse_tokenizer_t *tok,
                           pddl_parse_token_t *tout,
                           pddl_err_t *err);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_PARSE_TOKENIZER_H__ */
