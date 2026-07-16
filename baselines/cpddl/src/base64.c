/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

/**
 * Based on the code by Jouni Malinen:
 *
 * Base64 encoding/decoding (RFC1341)
 * Copyright (c) 2005-2011, Jouni Malinen <j@w1.fi>
 * This software may be distributed under the terms of the BSD license.
 */

#include "internal.h"
#include "pddl/base64.h"

static const unsigned char base64_table[65] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/**
 * base64_encode - Base64 encode
 * @src: Data to be encoded
 * @len: Length of the data to be encoded
 * @out_len: Pointer to output length variable, or %NULL if not used
 * Returns: Allocated buffer of out_len bytes of encoded data,
 * or %NULL on failure
 *
 * Caller is responsible for freeing the returned buffer. Returned buffer is
 * nul terminated to make it easier to use as a C string. The nul terminator is
 * not included in out_len.
 */
unsigned char *pddlBase64Encode(const unsigned char *src, int len,
                                int *out_len, pddl_err_t *err)
{
    unsigned char *out, *pos;
    const unsigned char *end, *in;
    size_t olen;
    int line_len;

    olen = len * 4 / 3 + 4; /* 3-byte blocks to 4-byte */
    olen += olen / 72; /* line feeds */
    olen++; /* nul termination */
    if (olen < len){
        /* integer overflow */
        ERR_RET(err, NULL, "Base64-Encode: input data are too large.");
    }

    out = ALLOC_ARR(unsigned char, olen);
    if (out == NULL)
        ERR_RET(err, NULL, "Allocation of %lu bytes failed", (unsigned long)olen);

    end = src + len;
    in = src;
    pos = out;
    line_len = 0;
    while (end - in >= 3) {
        *pos++ = base64_table[in[0] >> 2];
        *pos++ = base64_table[((in[0] & 0x03) << 4) | (in[1] >> 4)];
        *pos++ = base64_table[((in[1] & 0x0f) << 2) | (in[2] >> 6)];
        *pos++ = base64_table[in[2] & 0x3f];
        in += 3;
        line_len += 4;
        if (line_len >= 72) {
            *pos++ = '\n';
            line_len = 0;
        }
    }

    if (end - in) {
        *pos++ = base64_table[in[0] >> 2];
        if (end - in == 1) {
            *pos++ = base64_table[(in[0] & 0x03) << 4];
            *pos++ = '=';
        } else {
            *pos++ = base64_table[((in[0] & 0x03) << 4) |
                          (in[1] >> 4)];
            *pos++ = base64_table[(in[1] & 0x0f) << 2];
        }
        *pos++ = '=';
        line_len += 4;
    }

    if (line_len)
        *pos++ = '\n';

    *pos = '\0';
    if (out_len)
        *out_len = pos - out;
    return out;
}


/**
 * base64_decode - Base64 decode
 * @src: Data to be decoded
 * @len: Length of the data to be decoded
 * @out_len: Pointer to output length variable
 * Returns: Allocated buffer of out_len bytes of decoded data,
 * or %NULL on failure
 *
 * Caller is responsible for freeing the returned buffer.
 */
unsigned char *pddlBase64Decode(const unsigned char *src, int len,
                                int *out_len, pddl_err_t *err)
{
    unsigned char dtable[256], *out, *pos, block[4], tmp;
    size_t count, olen;
    int pad = 0;

    memset(dtable, 0x80, 256);
    for (int i = 0; i < sizeof(base64_table) - 1; i++)
        dtable[base64_table[i]] = (unsigned char) i;
    dtable['='] = 0;

    count = 0;
    for (int i = 0; i < len; i++) {
        if (dtable[src[i]] != 0x80)
            count++;
    }

    if (count == 0 || count % 4)
        ERR_RET(err, NULL, "Base64-Decode: Invalid input.");

    olen = count / 4 * 3;
    pos = out = ALLOC_ARR(unsigned char, olen);
    if (out == NULL)
        ERR_RET(err, NULL, "Allocation of %lu bytes failed", (unsigned long)olen);

    count = 0;
    for (int i = 0; i < len; i++) {
        tmp = dtable[src[i]];
        if (tmp == 0x80)
            continue;

        if (src[i] == '=')
            pad++;
        block[count] = tmp;
        count++;
        if (count == 4) {
            *pos++ = (block[0] << 2) | (block[1] >> 4);
            *pos++ = (block[1] << 4) | (block[2] >> 2);
            *pos++ = (block[2] << 6) | block[3];
            count = 0;
            if (pad) {
                if (pad == 1)
                    pos--;
                else if (pad == 2)
                    pos -= 2;
                else {
                    /* Invalid padding */
                    FREE(out);
                    ERR_RET(err, NULL, "Base64-Decode: Invalid padding");
                }
                break;
            }
        }
    }

    *out_len = pos - out;
    return out;
}
