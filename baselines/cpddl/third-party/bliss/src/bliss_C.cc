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

#include <stdlib.h>
#include <stdio.h>
#include <assert.h>
#include "graph.hh"
#include "digraph.hh"
extern "C" {
#include "bliss_C.h"
}

/**
 * \brief The true bliss graph is hiding in this struct.
 */
struct pddl_bliss_graph_struct {
  pddl_bliss::AbstractGraph* g;
};

extern "C"
PddlBlissGraph *pddl_bliss_new(const unsigned int n)
{
  PddlBlissGraph *graph = new pddl_bliss_graph_struct;
  assert(graph);
  graph->g = new pddl_bliss::Graph(n);
  assert(graph->g);
  return graph;
}

extern "C"
PddlBlissGraph *pddl_bliss_new_digraph(const unsigned int n)
{
  PddlBlissGraph *graph = new pddl_bliss_graph_struct;
  assert(graph);
  graph->g = new pddl_bliss::Digraph(n);
  assert(graph->g);
  return graph;
}

extern "C"
PddlBlissGraph *pddl_bliss_read_dimacs(FILE *fp)
{
  pddl_bliss::Graph *g = pddl_bliss::Graph::read_dimacs(fp);
  if(!g)
    return 0;
  PddlBlissGraph *graph = new pddl_bliss_graph_struct;
  assert(graph);
  graph->g = g;
  return graph;
}

extern "C"
void pddl_bliss_write_dimacs(PddlBlissGraph *graph, FILE *fp)
{
  assert(graph);
  assert(graph->g);
  graph->g->write_dimacs(fp);
}

extern "C"
void pddl_bliss_release(PddlBlissGraph *graph)
{
  assert(graph);
  assert(graph->g);
  delete graph->g; graph->g = 0;
  delete graph;
}

extern "C"
void pddl_bliss_write_dot(PddlBlissGraph *graph, FILE *fp)
{
  assert(graph);
  assert(graph->g);
  graph->g->write_dot(fp);
}

extern "C"
unsigned int pddl_bliss_get_nof_vertices(PddlBlissGraph *graph)
{
  assert(graph);
  assert(graph->g);
  return graph->g->get_nof_vertices();
}

extern "C"
unsigned int pddl_bliss_add_vertex(PddlBlissGraph *graph, unsigned int l)
{
  assert(graph);
  assert(graph->g);
  return graph->g->add_vertex(l);
}

extern "C"
void pddl_bliss_add_edge(PddlBlissGraph *graph, unsigned int v1, unsigned int v2)
{
  assert(graph);
  assert(graph->g);
  graph->g->add_edge(v1, v2);
}

extern "C"
unsigned int pddl_bliss_hash(PddlBlissGraph *graph)
{
  assert(graph);
  assert(graph->g);
  return graph->g->get_hash();
}

extern "C"
PddlBlissGraph *pddl_bliss_permute(PddlBlissGraph *graph, const unsigned int *perm)
{
  assert(graph);
  assert(graph->g);
  assert(graph->g->get_nof_vertices() == 0 || perm);
  PddlBlissGraph *permuted_graph = new pddl_bliss_graph_struct;
  assert(permuted_graph);
  permuted_graph->g = graph->g->permute(perm);
  return permuted_graph;
}

extern "C"
void
pddl_bliss_find_automorphisms(PddlBlissGraph *graph,
			 void (*hook)(void *user_param,
				      unsigned int n,
				      const unsigned int *aut),
			 void *hook_user_param,
			 PddlBlissStats *stats)
{
  pddl_bliss::Stats s;
  assert(graph);
  assert(graph->g);
  
  auto report_aut = [&](unsigned int n, const unsigned int *aut) -> void {
    if(hook)
      (*hook)(hook_user_param, n, aut);
  };
  
  graph->g->find_automorphisms(s, report_aut);

  if(stats)
    {
      stats->group_size_approx = s.get_group_size_approx();
      stats->nof_nodes = s.get_nof_nodes();
      stats->nof_leaf_nodes = s.get_nof_leaf_nodes();
      stats->nof_bad_nodes = s.get_nof_bad_nodes();
      stats->nof_canupdates = s.get_nof_canupdates();
      stats->nof_generators = s.get_nof_generators();
      stats->max_level = s.get_max_level();
    }
}


extern "C"
const unsigned int *
pddl_bliss_find_canonical_labeling(PddlBlissGraph *graph,
			      void (*hook)(void *user_param,
					   unsigned int n,
					   const unsigned int *aut),
			      void *hook_user_param,
			      PddlBlissStats *stats)
{
  pddl_bliss::Stats s;
  const unsigned int *canonical_labeling = 0;
  assert(graph);
  assert(graph->g);
  
  auto report_aut = [&](unsigned int n, const unsigned int *aut) -> void {
    if(hook)
      (*hook)(hook_user_param, n, aut);
  };
  
  canonical_labeling = graph->g->canonical_form(s, report_aut);

  if(stats)
    {
      stats->group_size_approx = s.get_group_size_approx();
      stats->nof_nodes = s.get_nof_nodes();
      stats->nof_leaf_nodes = s.get_nof_leaf_nodes();
      stats->nof_bad_nodes = s.get_nof_bad_nodes();
      stats->nof_canupdates = s.get_nof_canupdates();
      stats->nof_generators = s.get_nof_generators();
      stats->max_level = s.get_max_level();
    }

  return canonical_labeling;
}
