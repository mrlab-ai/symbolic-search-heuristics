/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "_parser.h"
#include "internal.h"
#include "parse_tokenizer.h"

#define PERR_SRC(E, TOK, T) \
    pddlErrSetSourceFilePointer((E), (TOK)->fn, (T)->line, (T)->column, 3)

#define _ERR(E, RET, TOK, T, MSG) \
    do { \
        PERR_SRC((E), (TOK), (T)); \
        ERR_RET((E), (RET), MSG " line: %d, column: %d", (T)->line, (T)->column); \
    } while (0)

#define _ERRV(E, RET, TOK, T, FMT, ...) \
    do { \
        PERR_SRC((E), (TOK), (T)); \
        ERR_RET((E), (RET), FMT " line: %d, column: %d", __VA_ARGS__, \
                (T)->line, (T)->column); \
    } while (0)

struct tokenize {
    pddl_parse_tokenizer_t *tok;
    char *data;
    size_t data_size;
    char *data_end;
    char *cur;
    int cur_line;
    int cur_column;
};
typedef struct tokenize tokenize_t;

#define IS_WS(c) ((c) == ' ' || (c) == '\n' || (c) == '\r' || (c) == '\t')
#define IS_STR(c) (!IS_WS(c) && (c) != ')' && (c) != '(' && (c) != ';')
#define IS_NUM(c) ((c) >= '0' && (c) <= '9')

struct kw {
    const char *text;
    int text_size;
    int token;
};
typedef struct kw kw_t;

#define KW_DEF(S, T) \
    { \
        .text = S, \
        .text_size = sizeof(S) - 1, \
        .token = T, \
    }

static kw_t kw[] = {
    KW_DEF("define", PDDL_TOKEN_DEFINE),
    KW_DEF(":domain", PDDL_TOKEN_PROB_DOMAIN),
    KW_DEF(":requirements", PDDL_TOKEN_REQUIREMENTS),
    KW_DEF(":types", PDDL_TOKEN_TYPES),
    KW_DEF(":predicates", PDDL_TOKEN_PREDICATES),
    KW_DEF(":constants", PDDL_TOKEN_CONSTANTS),
    KW_DEF(":action", PDDL_TOKEN_ACTION),
    KW_DEF(":parameters", PDDL_TOKEN_PARAMETERS),
    KW_DEF(":precondition", PDDL_TOKEN_PRECONDITION),
    KW_DEF(":effect", PDDL_TOKEN_EFFECT),
    KW_DEF(":derived", PDDL_TOKEN_DERIVED),

    KW_DEF(":strips", PDDL_TOKEN_REQUIRE_STRIPS),
    KW_DEF(":typing", PDDL_TOKEN_REQUIRE_TYPING),
    KW_DEF(":negative-preconditions", PDDL_TOKEN_REQUIRE_NEGATIVE_PRE),
    KW_DEF(":disjunctive-preconditions", PDDL_TOKEN_REQUIRE_DISJUNCTIVE_PRE),
    KW_DEF(":equality", PDDL_TOKEN_REQUIRE_EQUALITY),
    KW_DEF(":existential-preconditions", PDDL_TOKEN_REQUIRE_EXISTENTIAL_PRE),
    KW_DEF(":universal-preconditions", PDDL_TOKEN_REQUIRE_UNIVERSAL_PRE),
    KW_DEF(":conditional-effects", PDDL_TOKEN_REQUIRE_CONDITIONAL_EFF),
    KW_DEF(":numeric-fluents", PDDL_TOKEN_REQUIRE_NUMERIC_FLUENT),
    KW_DEF(":numeric-fluents", PDDL_TOKEN_REQUIRE_OBJECT_FLUENT),
    KW_DEF(":durative-actions", PDDL_TOKEN_REQUIRE_DURATIVE_ACTION),
    KW_DEF(":duration-inequalities", PDDL_TOKEN_REQUIRE_DURATION_INEQUALITY),
    KW_DEF(":continuous-effects", PDDL_TOKEN_REQUIRE_CONTINUOUS_EFF),
    KW_DEF(":derived-predicates", PDDL_TOKEN_REQUIRE_DERIVED_PRED),
    KW_DEF(":timed-initial-literals", PDDL_TOKEN_REQUIRE_TIMED_INITIAL_LITERAL),
    KW_DEF(":preferences", PDDL_TOKEN_REQUIRE_PREFERENCE),
    KW_DEF(":constraints", PDDL_TOKEN_REQUIRE_CONSTRAINT),
    KW_DEF(":action-costs", PDDL_TOKEN_REQUIRE_ACTION_COST),
    KW_DEF(":quantified-preconditions", PDDL_TOKEN_REQUIRE_QUANTIFIED_PRE),
    KW_DEF(":fluents", PDDL_TOKEN_REQUIRE_FLUENTS),
    KW_DEF(":adl", PDDL_TOKEN_REQUIRE_ADL),

    KW_DEF(":functions", PDDL_TOKEN_FUNCTIONS),
    KW_DEF("number", PDDL_TOKEN_NUMBER),
    KW_DEF(":objects", PDDL_TOKEN_OBJECTS),
    KW_DEF(":init", PDDL_TOKEN_INIT),
    KW_DEF(":goal", PDDL_TOKEN_GOAL),
    KW_DEF(":metric", PDDL_TOKEN_METRIC),
    KW_DEF("minimize", PDDL_TOKEN_MINIMIZE),
    KW_DEF("maximize", PDDL_TOKEN_MAXIMIZE),
    KW_DEF("increase", PDDL_TOKEN_INCREASE),
    KW_DEF("decrease", PDDL_TOKEN_DECREASE),
    KW_DEF("assign", PDDL_TOKEN_ASSIGN),
    KW_DEF("scale-up", PDDL_TOKEN_SCALE_UP),
    KW_DEF("scale-down", PDDL_TOKEN_SCALE_DOWN),

    KW_DEF("=", PDDL_TOKEN_CMP_EQ),
    KW_DEF(">=", PDDL_TOKEN_CMP_GE),
    KW_DEF("<=", PDDL_TOKEN_CMP_LE),
    KW_DEF(">", PDDL_TOKEN_CMP_GT),
    KW_DEF("<", PDDL_TOKEN_CMP_LT),

    KW_DEF("+", PDDL_TOKEN_PLUS),
    KW_DEF("*", PDDL_TOKEN_MULT),
    KW_DEF("/", PDDL_TOKEN_DIV),

    KW_DEF("and", PDDL_TOKEN_AND),
    KW_DEF("or", PDDL_TOKEN_OR),
    KW_DEF("not", PDDL_TOKEN_NOT),
    KW_DEF("imply", PDDL_TOKEN_IMPLY),
    KW_DEF("exists", PDDL_TOKEN_EXISTS),
    KW_DEF("forall", PDDL_TOKEN_FORALL),
    KW_DEF("when", PDDL_TOKEN_WHEN),

    KW_DEF("either", PDDL_TOKEN_EITHER),

    // These are sometimes re-used as identifiers
    //KW_DEF("domain", PDDL_TOKEN_DOMAIN),
    //KW_DEF("problem", PDDL_TOKEN_PROBLEM),
};
static int kw_size = sizeof(kw) / sizeof(kw_t);

static void dataPreprocess(unsigned char *data, size_t size)
{
    char remap[256];
    for (int i = 32; i < 127; ++i)
        remap[i] = i;
    for (int i = 0; i < 32; ++i)
        remap[i] = ' ';
    remap['\n'] = '\n';
    for (int i = 'A'; i <= 'Z'; ++i)
        remap[i] = remap[i] - 'A' + 'a';
    for (int i = 128; i < 256; ++i)
        remap[i] = ' ';

    for (int i = 0; i < size; ++i)
        data[i] = remap[data[i]];
}

static void tokenizerSkipWhitespace(tokenize_t *tok)
{
    while (tok->cur < tok->data_end && IS_WS(*tok->cur)){
        if (*tok->cur == '\n'){
            tok->cur_line += 1;
            tok->cur_column = 0;
        }
        ++tok->cur;
        ++tok->cur_column;
    }
}

static void tokenizerSkipComment(tokenize_t *tok)
{
    if (tok->cur < tok->data_end && *tok->cur == ';'){
        while (tok->cur < tok->data_end && *tok->cur != '\n'){
            ++tok->cur;
            ++tok->cur_column;
        }
        tokenizerSkipWhitespace(tok);
    }
}

static int _tokenizerSkip(tokenize_t *tok)
{
    char *start = tok->cur;
    tokenizerSkipWhitespace(tok);
    tokenizerSkipComment(tok);
    if (start != tok->cur)
        return 1;
    return 0;
}

static void tokenizerSkip(tokenize_t *tok)
{
    while (_tokenizerSkip(tok));
}

static char peek1(const tokenize_t *tok, char *cur)
{
    if (cur == tok->data_end)
        return 0;
    return cur[1];
}

static int tokenizerMatchToken(tokenize_t *tok, pddl_parse_token_t *t,
                               pddl_err_t *err)
{
    int smaxlen = tok->data_end - tok->cur;
    char next = peek1(tok, tok->cur);

    int shift = 0;
    if (*tok->cur == '('){
        t->token = PDDL_TOKEN_LPAREN;
        shift = 1;

    }else if (*tok->cur == ')'){
        t->token = PDDL_TOKEN_RPAREN;
        shift = 1;

    }else if (*tok->cur == '-' && (IS_WS(next) || next == 0)){
        t->token = PDDL_TOKEN_DASH;
        shift = 1;

    }else if (IS_NUM(*tok->cur) || (*tok->cur == '-' && IS_NUM(next))){
        t->token = PDDL_TOKEN_INUM;
        for (shift = 1; shift < smaxlen && IS_NUM(tok->cur[shift]); ++shift);

        if (shift < smaxlen && tok->cur[shift] == '.'){
            t->token = PDDL_TOKEN_FNUM;
            for (++shift; shift < smaxlen && IS_NUM(tok->cur[shift]); ++shift);
        }


    }else if (*tok->cur == '?'){
        for (shift = 0; shift < smaxlen && IS_STR(tok->cur[shift]); ++shift);
        t->token = PDDL_TOKEN_VAR_IDNT;

    }else{
        int found = 0;
        for (int kwi = 0; kwi < kw_size; ++kwi){
            const kw_t *k = kw + kwi;
            if (k->text_size > smaxlen)
                continue;

            if (strncmp(tok->cur, k->text, k->text_size) == 0
                    && (k->text_size == smaxlen
                            || !IS_STR(tok->cur[k->text_size]))){
                shift = k->text_size;
                t->token = k->token;
                found = 1;
                break;
            }
        }

        if (!found){
            for (shift = 0; shift < smaxlen && IS_STR(tok->cur[shift]); ++shift);
            t->token = PDDL_TOKEN_IDNT;
            if (*tok->cur == ':')
                t->token = PDDL_TOKEN_UNKNOWN_KW;
        }
    }

    if (shift == 0){
        ERR_RET(err, -1, "Cannot find next token. Something went seriously"
                " wrong. Stopped tokenization on line %d and column %d",
                tok->cur_line, tok->cur_column);
    }

    t->str_id = pddlStrPoolAddSize(&tok->tok->str_pool, tok->cur, shift);
    t->str = pddlStrPoolGet(&tok->tok->str_pool, t->str_id);
    t->line = tok->cur_line;
    t->column = tok->cur_column;

    if (t->token == PDDL_TOKEN_VAR_IDNT && t->str[1] == '\x0'){
        _ERR(err, -1, tok->tok, t, "Lonely '?' is not allowed."); 
    }

    if (t->token == PDDL_TOKEN_IDNT && t->str[0] == '-'){
        PERR_SRC(err, tok->tok, t);
        ERR_RET(err, -1, "Identifiers starting with '-' are not allowed."
                " line: %d, column: %d\n"
                "Strictly speaking, the PDDL language allows that, but it"
                " is source of so many mistakes in definitions of types"
                " that we decided not to support it at all.",
                t->line, t->column);
    }
    
    if ((t->token == PDDL_TOKEN_INUM || t->token == PDDL_TOKEN_FNUM)
            && shift < smaxlen
            && IS_STR(tok->cur[shift])){
        _ERRV(err, -1, tok->tok, t, "Malformed number token %s.", t->str);
    }

    tok->cur += shift;
    tok->cur_column += shift;

    return 0;
}

static int tokenizeNext(tokenize_t *tok, pddl_err_t *err)
{
    tokenizerSkip(tok);
    if (tok->cur < tok->data_end){
        pddl_parse_token_t token = {
            .token = -1,
            .str_id = -1,
            .str = NULL,
            .line = -1,
            .column = -1,
            .processed = 0,
        };

        if (tokenizerMatchToken(tok, &token, err) != 0)
            TRACE_RET(err, -1);

        if (tok->tok->token_size == tok->tok->token_alloc){
            if (tok->tok->token_alloc == 0)
                tok->tok->token_alloc = 128;
            tok->tok->token_alloc *= 2;
            tok->tok->token = REALLOC_ARR(tok->tok->token, pddl_parse_token_t,
                                          tok->tok->token_alloc);
        }
        tok->tok->token[tok->tok->token_size++] = token;
        return 0;

    }else{
        return 1;
    }
}


static int tokenize(pddl_parse_tokenizer_t *tok,
                    void *data,
                    size_t data_size,
                    pddl_err_t *err)
{
    tokenize_t tokenize = {
        .tok = tok,
        .data = data,
        .data_size = data_size,
        .data_end = ((char *)data) + data_size,
        .cur = data,
        .cur_line = 1,
        .cur_column = 1,
    };

    int ret = 0;
    while ((ret = tokenizeNext(&tokenize, err)) == 0);
    if (ret < 0)
        return ret;
    return 0;
}

int pddlParseTokenizerInit(pddl_parse_tokenizer_t *tok, const char *fnin,
                            pddl_err_t *err)
{
    CTX(err, "TOK");
    ZEROIZE(tok);

    char fn[PATH_MAX + 1];
    if (realpath(fnin, fn) == NULL){
        ERR_RET(err, -1, "Cannot resolve the path `%s': %s",
                fnin, strerror(errno));
    }

    int fd = open(fn, O_RDONLY);
    if (fd == -1){
        ERR_RET(err, -1, "Cannot not open file `%s': %s", fn, strerror(errno));
    }

    struct stat st;
    if (fstat(fd, &st) != 0){
        ERR(err, "Cannot determine size of the file `%s'.", fn);
        close(fd);
        return -1;
    }

    void *data = mmap(NULL, st.st_size, PROT_READ | PROT_WRITE, MAP_PRIVATE, fd, 0);
    close(fd);
    if (data == MAP_FAILED){
        CTXEND(err);
        ERR_RET(err, -1, "Cannot not mmap file `%s': %s", fn, strerror(errno));
    }

    dataPreprocess(data, st.st_size);

    LOG(err, "mmaped %ld bytes from file %s", (long)st.st_size, fn);

    pddlStrPoolInit(&tok->str_pool);
    tok->fn = STRDUP(fn);
    int ret = tokenize(tok, data, st.st_size, err);
    LOG(err, "File %s tokenized. tokens: %d, strings: %d",
        tok->fn, tok->token_size, tok->str_pool.str_size);

    if (data != NULL)
        munmap((void *)data, st.st_size);

    if (ret != 0)
        pddlStrPoolFree(&tok->str_pool);
    CTXEND(err);
    return ret;
}

void pddlParseTokenizerFree(pddl_parse_tokenizer_t *tok)
{
    if (tok->token != NULL)
        FREE(tok->token);
    if (tok->fn != NULL)
        FREE(tok->fn);
    pddlStrPoolFree(&tok->str_pool);
}

static const char *sectionNameFromToken(int token)
{
    for (int kwi = 0; kwi < kw_size; ++kwi){
        const kw_t *k = kw + kwi;
        if (k->token == token)
            return k->text;
    }
    return NULL;
}

void pddlParseTokenizerRestart(pddl_parse_tokenizer_t *tok)
{
    tok->start_token_id = 0;
}

void pddlParseTokenizerStart(pddl_parse_tokenizer_t *tok)
{
    tok->start_token_id = 0;
    tok->next_token_id = 0;
}

int pddlParseTokenizerStartSection(pddl_parse_tokenizer_t *tok, int token,
                                   pddl_err_t *err)
{
    tok->next_token_id = -1;

    for (int i = tok->start_token_id; i < tok->token_size; ++i){
        if (tok->token[i].processed)
            continue;

        // This is not very nice, but it seems there are domains that re-use
        // what would otherwise were keywords.
        // For example, unsolve-ipc-2016/over-tpp uses a type 'domain'
        if (token == PDDL_TOKEN_DOMAIN
                && tok->token[i].token == PDDL_TOKEN_IDNT
                && strcmp(tok->token[i].str, "domain") == 0
                && i > 1
                && tok->token[i - 1].token == PDDL_TOKEN_LPAREN){
            tok->token[i].token = PDDL_TOKEN_DOMAIN;
        }

        if (token == PDDL_TOKEN_PROBLEM
                && tok->token[i].token == PDDL_TOKEN_IDNT
                && strcmp(tok->token[i].str, "problem") == 0
                && i > 1
                && tok->token[i - 1].token == PDDL_TOKEN_LPAREN){
            tok->token[i].token = PDDL_TOKEN_PROBLEM;
        }

        if (tok->token[i].token == token){
            if (i == 0 || tok->token[i - 1].token != PDDL_TOKEN_LPAREN){
                const char *name = sectionNameFromToken(token);
                if (name == NULL)
                    name = "UNKOWN SECTION";

                _ERRV(err, -1, tok, tok->token + i,
                      "Invalid definition of the section %s, missing left"
                      " parenthesis '('.", name);
            }

            tok->paren_counter = 0;
            tok->next_token_id = i - 1;
            return 0;
        }
    }

    return 1;
}

int pddlParseTokenizerNext(pddl_parse_tokenizer_t *tok,
                           pddl_parse_token_t *tout,
                           pddl_err_t *err)
{
    while (tok->next_token_id >= 0
            && tok->next_token_id < tok->token_size
            && tok->token[tok->next_token_id].processed){
        ++tok->next_token_id;
    }

    if (tok->next_token_id < 0 || tok->next_token_id == tok->token_size)
        return 1;

    *tout = tok->token[tok->next_token_id];
    tok->token[tok->next_token_id].processed = 1;
    if (tout->token == PDDL_TOKEN_LPAREN){
        ++tok->paren_counter;
    }else if (tout->token == PDDL_TOKEN_RPAREN){
        --tok->paren_counter;
    }

    if (tok->paren_counter == 0){
        tok->next_token_id = -1;
    }else{
        ++tok->next_token_id;
        ++tok->start_token_id;
    }

    return 0;
}
