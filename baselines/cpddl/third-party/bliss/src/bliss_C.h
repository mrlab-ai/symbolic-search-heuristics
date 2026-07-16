#ifndef BLISS_C_H
#define BLISS_C_H

#define BLISS_VERSION "0.77"

/*
  Copyright (c) 2003-2021 Tommi Junttila
  Released under the GNU Lesser General Public License version 3.
  
  This file is part of bliss.
  
  bliss is free software: you can redistribute it and/or modify
  it under the terms of the GNU Lesser General Public License as published by
  the Free Software Foundation, version 3 of the License.

  bliss is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU Lesser General Public License for more details.

  You should have received a copy of the GNU Lesser General Public License
  along with bliss.  If not, see <http://www.gnu.org/licenses/>.
*/

/**
 * \file
 * \brief The bliss C API.
 *
 * This is the C language API to <a href="https://users.aalto.fi/tjunttil/bliss">bliss</a>.
 * Note that this C API is only a subset of the C++ API;
 * please consider using the C++ API whenever possible.
 */

#include <stdlib.h>
#include <stdio.h>


/**
 * \brief The true bliss graph is hiding behind this typedef.
 */
typedef struct pddl_bliss_graph_struct PddlBlissGraph;


/**
 * \brief The C API version of the statistics returned by
 * the bliss search algorithm.
 */
typedef struct pddl_bliss_stats_struct
{
  /**
   * \brief An approximation (due to possible rounding errors) of
   * the size of the automorphism group.
   */
  long double group_size_approx;
  /** \brief The number of nodes in the search tree. */
  long unsigned int nof_nodes;
  /** \brief The number of leaf nodes in the search tree. */
  long unsigned int nof_leaf_nodes;
  /** \brief The number of bad nodes in the search tree. */
  long unsigned int nof_bad_nodes;
  /** \brief The number of canonical representative updates. */
  long unsigned int nof_canupdates;
  /** \brief The number of generator permutations. */
  long unsigned int nof_generators;
  /** \brief The maximal depth of the search tree. */
  unsigned long int max_level;
} PddlBlissStats;


/**
 * Create a new graph instance with \a N vertices and no edges.
 * \a N can be zero and pddl_bliss_add_vertex() called afterwards
 * to add new vertices on-the-fly.
 */
PddlBlissGraph *pddl_bliss_new(const unsigned int N);
PddlBlissGraph *pddl_bliss_new_digraph(const unsigned int N);


/**
 * Read an undirected graph from a file in the DIMACS format into a new bliss
 * instance.
 * Returns 0 if an error occurred.
 * Note that in the DIMACS file the vertices are numbered from 1 to N while
 * in the bliss C API they are from 0 to N-1.
 * Thus the vertex n in the file corresponds to the vertex n-1 in the API.
 */
PddlBlissGraph *pddl_bliss_read_dimacs(FILE *fp);


/**
 * Output the graph in the file stream \a fp in the DIMACS format.
 * See the User's Guide for the file format details.
 * Note that in the DIMACS file the vertices are numbered from 1 to N while
 * in bliss they are from 0 to N-1.
 */
void pddl_bliss_write_dimacs(PddlBlissGraph *graph, FILE *fp);


/**
 * Release the graph.
 * Note that the memory pointed by the arguments of hook functions for
 * pddl_bliss_find_automorphisms() and pddl_bliss_find_canonical_labeling()
 * is deallocated and thus should not be accessed after calling this function.
 */
void pddl_bliss_release(PddlBlissGraph *graph);


/**
 * Print the graph in graphviz dot format.
 */
void pddl_bliss_write_dot(PddlBlissGraph *graph, FILE *fp);


/**
 * Return the number of vertices in the graph.
 */
unsigned int pddl_bliss_get_nof_vertices(PddlBlissGraph *graph);


/**
 * Add a new vertex with color \a c in the graph \a graph and return its index.
 * The vertex indices are always in the range
 * [0,pddl_bliss::pddl_bliss_get_nof_vertices(\a bliss)-1].
 */
unsigned int pddl_bliss_add_vertex(PddlBlissGraph *graph, unsigned int c);


/**
 * Add a new undirected edge in the graph.
 * \a v1 and \a v2 are vertex indices returned by pddl_bliss_add_vertex().
 * If duplicate edges are added, they will be ignored (however, they are not
 * necessarily physically ignored immediately but may consume memory for
 * a while so please try to avoid adding duplicate edges whenever possible).
 */
void pddl_bliss_add_edge(PddlBlissGraph *graph, unsigned int v1, unsigned int v2);


/**
 * Get a hash value for the graph.
 */
unsigned int pddl_bliss_hash(PddlBlissGraph *graph);


/**
 * Permute the graph with the given permutation \a perm.
 * Returns the permuted graph, the original graph is not modified.
 * The argument \a perm should be an array of
 * N=pddl_bliss::pddl_bliss_get_nof_vertices(\a graph) elements describing
 * a bijection on {0,...,N-1}.
 */
PddlBlissGraph *pddl_bliss_permute(PddlBlissGraph *graph, const unsigned int *perm);


/**
 * Find a set of generators for the automorphism group of the graph.
 * The hook function \a hook (if non-null) is called each time a new generator
 * for the automorphism group is found.
 * The first argument \a user_param for the hook function is
 * the \a hook_user_param argument,
 * the second argument \a N is the length of the automorphism (equal to
 * pddl_bliss::pddl_bliss_get_nof_vertices(\a graph)) and
 * the third argument \a aut is the automorphism (a bijection on {0,...,N-1}).
 * The memory for the automorphism \a aut will be invalidated immediately
 * after the return from the hook;
 * if you want to use the automorphism later, you have to take a copy of it.
 * Do not call pddl_bliss_* functions in the hook.
 * If \a stats is non-null, then some search statistics are copied there.
 */
void
pddl_bliss_find_automorphisms(PddlBlissGraph *graph,
			 void (*hook)(void *user_param,
				      unsigned int N,
				      const unsigned int *aut),
			 void *hook_user_param,
			 PddlBlissStats *stats);


/**
 * Otherwise the same as pddl_bliss_find_automorphisms() except that
 * a canonical labeling for the graph (a bijection on {0,...,N-1}) is returned.
 * The returned canonical labeling will remain valid only until
 * the next call to a pddl_bliss_* function with the exception that
 * pddl_bliss_permute() can be called without invalidating the labeling.
 * To compute the canonical version of a graph, call this function and
 * then pddl_bliss_permute() with the returned canonical labeling.
 * Note that the computed canonical version may depend on the applied version
 * of bliss.
 */
const unsigned int *
pddl_bliss_find_canonical_labeling(PddlBlissGraph *graph,
			      void (*hook)(void *user_param,
					   unsigned int N,
					   const unsigned int *aut),
			      void *hook_user_param,
			      PddlBlissStats *stats);

#endif
