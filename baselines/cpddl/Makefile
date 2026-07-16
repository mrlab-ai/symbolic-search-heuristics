-include Makefile.config
-include Makefile.include

MAKE_FILES := Makefile Makefile.include $(wildcard Makefile.config)

SRC  = alloc
SRC += err
SRC += opts
SRC += strstream
SRC += hfunc
SRC += sha256
SRC += base64
SRC += google-city-hash
SRC += _toml
SRC += toml
SRC += rand
SRC += sort
SRC += qsort
SRC += timsort
SRC += segmarr
SRC += extarr
SRC += pairheap
SRC += hashset
SRC += rbtree
SRC += htable
SRC += fifo
SRC += lp
SRC += lp-cplex
SRC += lp-gurobi
SRC += lp-highs
SRC += cp
SRC += cp-minizinc
SRC += require_flags
SRC += type
SRC += param
SRC += obj
SRC += pred
SRC += fact
SRC += action
SRC += prep_action
SRC += pddl
SRC += parser
SRC += parse_tokenizer
SRC += parse_tree
SRC += pddl_compile_away_neg_pre
SRC += unify
SRC += compile_in_lifted_mgroup
SRC += fm
SRC += fm_arr
SRC += strips
SRC += strips_op
SRC += strips_fact_cross_ref
SRC += strips_maker
SRC += strips_conj
SRC += ground
SRC += strips_ground_tree
SRC += strips_ground_trie
SRC += strips_ground_sql
SRC += strips_ground_datalog
SRC += strips_ground_clingo
SRC += action_args
SRC += ground_atom
SRC += profile
SRC += lifted_mgroup
SRC += lifted_mgroup_infer
SRC += lifted_mgroup_htable
SRC += mgroup
SRC += mgroup_projection
SRC += mutex_pair
SRC += pddl_file
SRC += plan_file
SRC += irrelevance
SRC += h1
SRC += h2
SRC += h3
SRC += hm
SRC += disambiguation
SRC += bitset
SRC += set
SRC += fdr_var
SRC += fdr_part_state
SRC += fdr_op
SRC += fdr
SRC += fdr_state_packer
SRC += fdr_state_pool
SRC += fdr_state_space
SRC += fdr_state_sampler
SRC += fdr_conj_exact
SRC += strips_state_space
SRC += famgroup
SRC += pot
SRC += lm_cut
SRC += hpot
SRC += pot_conj
SRC += pot_conj_exact
SRC += hflow
SRC += hmax
SRC += hadd
SRC += hff
SRC += pq
SRC += mg_strips
SRC += cg
SRC += graph
SRC += clique
SRC += biclique
SRC += fdr_app_op
SRC += random_walk
SRC += open_list
SRC += open_list_splaytree1
SRC += open_list_splaytree2
SRC += search
SRC += search_bfs
SRC += lifted_app_action
SRC += lifted_app_action_sql
SRC += lifted_app_action_datalog
SRC += lifted_search
SRC += plan
SRC += relaxed_plan
SRC += heur
SRC += heur_blind
SRC += heur_dead_end
SRC += heur_lm_cut
SRC += heur_hmax
SRC += heur_hadd
SRC += heur_hff
SRC += heur_flow
SRC += heur_op_mutex
SRC += dtg
SRC += scc
SRC += ts
SRC += op_mutex_pair
SRC += op_mutex_infer
SRC += op_mutex_infer_ts
SRC += op_mutex_redundant
SRC += op_mutex_redundant_greedy
SRC += op_mutex_redundant_max
SRC += reversibility
SRC += invertibility
SRC += cascading_table
SRC += transition
SRC += label
SRC += labeled_transition
SRC += trans_system
SRC += trans_system_abstr_map
SRC += trans_system_graph
SRC += bdds
SRC += symbolic_vars
SRC += symbolic_constr
SRC += symbolic_trans
SRC += symbolic_state
SRC += symbolic_task
SRC += symbolic_split_goal
SRC += cost
SRC += black_mgroup
SRC += red_black_fdr
SRC += outbox
SRC += datalog
SRC += datalog_pddl
SRC += endomorphism_fdr
SRC += endomorphism_ts
SRC += endomorphism_lifted
SRC += homomorphism
SRC += homomorphism_heur
SRC += prune_strips
SRC += iset
SRC += iarr
SRC += sarr
SRC += lifted_heur
SRC += lifted_heur_relaxed
SRC += lifted_heur_gaifman
SRC += subprocess
SRC += task
SRC += asnets
SRC += asnets_policy_distribution
SRC += asnets_task
SRC += asnets_train_data
SRC += str_pool
SRC += gaifman

SRC += _version

SRC_CPP =
SRC_CPP += cp-cp-optimizer

SRC_STUB =

ifeq '$(USE_SQLITE)' 'yes'
  SRC += sqlite3
  SRC += sql_grounder
  SRC += asnets_convert_from_sql
else
  SRC_STUB += sql_grounder
  SRC_STUB += asnets_convert_from_sql
endif

ifeq '$(USE_BLISS)' 'yes'
  SRC += sym
else
  SRC_STUB += sym
endif

ifeq '$(USE_CUDD)' 'yes'
  SRC += bdd
else
  SRC_STUB += bdd
endif

ifeq '$(USE_DYNET)' 'yes'
  SRC_CPP += asnets_dynet
else
  SRC_STUB += asnets_dynet
endif

OBJS_PIC := $(foreach obj,$(SRC),.objs/$(obj).pic.o) \
            $(foreach obj,$(SRC_CPP),.objs/$(obj).pic.cpp.o) \
            $(foreach obj,$(SRC_STUB),.objs/$(obj)-stub.pic.o)

OBJS := $(foreach obj,$(SRC),.objs/$(obj).o) \
        $(foreach obj,$(SRC_CPP),.objs/$(obj).cpp.o) \
        $(foreach obj,$(SRC_STUB),.objs/$(obj)-stub.o)

GEN  = pddl/iset.h
GEN += src/iset.c
GEN += pddl/iarr.h
GEN += src/iarr.c
GEN += pddl/sarr.h
GEN += src/sarr.c
GEN += src/_version.c

all: libpddl.a

bin: libpddl.a
	$(MAKE) -C bin

libpddl.a: $(OBJS) $(MAKE_FILES)
	rm -f $@
	$(AR) cr $@ $(OBJS)
	$(RANLIB) $@

libpddl.pic.a: $(OBJS_PIC) $(MAKE_FILES)
	rm -f $@
	$(AR) cr $@ $(OBJS_PIC)
	$(RANLIB) $@

libpddl.so: $(OBJS_PIC) $(MAKE_FILES)
	$(CC) -shared -o $@ $(OBJS_PIC)

pddl/config.h: $(MAKE_FILES)
	$(file >$@,#ifndef __PDDL_CONFIG_H__)
	$(file >>$@,#define __PDDL_CONFIG_H__)
	$(file >>$@,)
	$(if $(filter yes,$(DEBUG)), $(file >>$@,#define PDDL_DEBUG))
	$(if $(filter yes,$(USE_SQLITE)), $(file >>$@,#define PDDL_SQLITE))
	$(if $(filter yes,$(USE_CLIQUER)), $(file >>$@,#define PDDL_CLIQUER))
	$(if $(filter yes,$(USE_CUDD)), $(file >>$@,#define PDDL_CUDD))
	$(if $(filter yes,$(USE_BLISS)), $(file >>$@,#define PDDL_BLISS))
	$(if $(filter yes,$(USE_CPLEX)), $(file >>$@,#define PDDL_CPLEX))
	$(if $(filter yesyes,$(USE_CPLEX)$(CPLEX_ONLY_API)), $(file >>$@,#define PDDL_CPLEX_ONLY_API))
	$(if $(filter yes,$(USE_CPOPTIMIZER)), $(file >>$@,#define PDDL_CPOPTIMIZER))
	$(if $(filter yes,$(USE_GUROBI)), $(file >>$@,#define PDDL_GUROBI))
	$(if $(filter yesyes,$(USE_GUROBI)$(GUROBI_ONLY_API)), $(file >>$@,#define PDDL_GUROBI_ONLY_API))
	$(if $(filter yes,$(USE_HIGHS)), $(file >>$@,#define PDDL_HIGHS))
	$(if $(findstring yes,$(USE_CPLEX)$(USE_GUROBI)$(USE_HIGHS)), $(file >>$@,#define PDDL_LP))
	$(if $(MINIZINC_BIN), $(file >>$@,#define PDDL_MINIZINC))
	$(if $(MINIZINC_BIN), $(file >>$@,#define PDDL_MINIZINC_BIN "$(MINIZINC_BIN)"))
	$(if $(MINIZINC_BIN), $(file >>$@,#define PDDL_MINIZINC_VERSION "$(MINIZINC_VERSION)"))
	$(if $(filter yes,$(USE_DYNET)), $(file >>$@,#define PDDL_DYNET))
	$(if $(filter yes,$(USE_CLINGO)), $(file >>$@,#define PDDL_CLINGO))
	$(if $(filter yes,$(USE_MIMALLOC)), $(file >>$@,#define PDDL_MIMALLOC))
	$(file >>$@,)
	$(file >>$@,#endif /* __PDDL_CONFIG_H__ */)

pddl/iset.h: src/_set_arr.h scripts/fmt_set.sh pddl/config.h
	$(SH) scripts/fmt_set.sh set Set int i I I <$< >$@
src/iset.c: src/_set_arr.c scripts/fmt_set.sh pddl/config.h
	$(SH) scripts/fmt_set.sh set Set int i I I <$< >$@
pddl/lset.h: src/_set_arr.h scripts/fmt_set.sh pddl/config.h
	$(SH) scripts/fmt_set.sh set Set long l L L <$< >$@
src/lset.c: src/_set_arr.c scripts/fmt_set.sh pddl/config.h
	$(SH) scripts/fmt_set.sh set Set long l L L <$< >$@
pddl/cset.h: src/_set_arr.h scripts/fmt_set.sh pddl/config.h
	$(SH) scripts/fmt_set.sh set Set long c C C <$< >$@
src/cset.c: src/_set_arr.c scripts/fmt_set.sh pddl/config.h
	$(SH) scripts/fmt_set.sh set Set long c C C <$< >$@
pddl/iarr.h: src/_arr.h scripts/fmt_set.sh pddl/config.h
	$(SH) scripts/fmt_set.sh arr Arr int i I I <$< >$@
src/iarr.c: src/_arr.c scripts/fmt_set.sh pddl/config.h
	$(SH) scripts/fmt_set.sh arr Arr int i I I <$< >$@
pddl/sarr.h: src/_arr.h scripts/fmt_set.sh pddl/config.h
	$(SH) scripts/fmt_set.sh arr Arr "const char *" s S S <$< >$@
src/sarr.c: src/_arr.c scripts/fmt_set.sh pddl/config.h
	$(SH) scripts/fmt_set.sh arr Arr "const char *" s S S <$< >$@

src/_version.c: pddl/version.h pddl/config.h
	$(file >$@,#include "pddl/version.h")
	$(file >>$@,const char *pddl_build_commit = "$(shell git rev-parse HEAD)";)
	$(file >>$@,const char *pddl_version = PDDL_VERSION_STR "-$(shell git rev-parse HEAD)";)
.objs/_version.o: src/_version.c pddl/version.h
	$(CC) -I. -c -o $@ $<
.objs/_version.pic.o: src/_version.c pddl/version.h
	$(CC) -I. -fPIC -c -o $@ $<

src/tmp.cudd-version.h: third-party/cudd/configure.ac
	$(file >$@,#define CUDD_VERSION "$(shell grep 'AC_INIT' <$< | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+')")

.objs/parser.o: src/parser.c src/_parser.c $(GEN) pddl/config.h
	$(CC) $(CFLAGS) -c -o $@ $<
.objs/parse_%.o: src/parse_%.c src/parse_%.h src/_parser.c $(GEN) pddl/config.h
	$(CC) $(CFLAGS) -c -o $@ $<
src/_parser%c: src/_parser%y src/lemon $(GEN) pddl/config.h
	./src/lemon $<
src/lemon: src/lemon.c src/lempar.c
	$(CC) -o $@ $<

.objs/alloc.o: src/alloc.c pddl/alloc.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) $(MIMALLOC_CFLAGS) -c -o $@ $<
.objs/alloc.pic.o: src/alloc.c pddl/alloc.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) -fPIC $(MIMALLOC_CFLAGS) -c -o $@ $<
.objs/bdd.o: src/bdd.c pddl/bdd.h src/tmp.cudd-version.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) $(CUDD_CFLAGS) -c -o $@ $<
.objs/bdd.pic.o: src/bdd.c pddl/bdd.h src/tmp.cudd-version.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) -fPIC $(CUDD_CFLAGS) -c -o $@ $<
.objs/sym.o: src/sym.c pddl/sym.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) $(BLISS_CFLAGS) -c -o $@ $<
.objs/sym.pic.o: src/sym.c pddl/sym.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) -fPIC $(BLISS_CFLAGS) -c -o $@ $<
.objs/clique.o: src/clique.c pddl/clique.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) $(CLIQUER_CFLAGS) -c -o $@ $<
.objs/clique.pic.o: src/clique.c pddl/clique.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) -fPIC $(CLIQUER_CFLAGS) -c -o $@ $<
.objs/lp-cplex.o: src/lp-cplex.c src/_lp.h pddl/lp.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) $(CPLEX_CFLAGS) -Wno-pedantic -c -o $@ $<
.objs/lp-cplex.pic.o: src/lp-cplex.c src/_lp.h pddl/lp.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) $(CPLEX_CFLAGS) -Wno-pedantic -fPIC -c -o $@ $<
.objs/lp-gurobi.o: src/lp-gurobi.c src/_lp.h pddl/lp.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) $(GUROBI_CFLAGS) -Wno-pedantic -c -o $@ $<
.objs/lp-gurobi.pic.o: src/lp-gurobi.c src/_lp.h pddl/lp.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) $(GUROBI_CFLAGS) -Wno-pedantic -fPIC -c -o $@ $<
.objs/lp-highs.o: src/lp-highs.c src/_lp.h pddl/lp.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) $(HIGHS_CFLAGS) -c -o $@ $<
.objs/lp-highs.pic.o: src/lp-highs.c src/_lp.h pddl/lp.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) $(HIGHS_CFLAGS) -fPIC -c -o $@ $<
.objs/sqlite3.o: src/sqlite3.c pddl/config.h $(GEN)
	$(CC) $(SQLITE_CFLAGS) -c -o $@ $<
.objs/sqlite3.pic.o: src/sqlite3.c pddl/config.h $(GEN)
	$(CC) $(SQLITE_CFLAGS) -fPIC -c -o $@ $<
.objs/datalog.o: src/datalog.c pddl/datalog.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) $(CLINGO_CFLAGS) -c -o $@ $<
.objs/datalog.pic.o: src/datalog.c pddl/datalog.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) -fPIC $(CLINGO_CFLAGS) -c -o $@ $<
.objs/strips_ground_clingo.o: src/strips_ground_clingo.c pddl/strips_ground_clingo.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) $(CLINGO_CFLAGS) -c -o $@ $<
.objs/strips_ground_clingo.pic.o: src/strips_ground_clingo.c pddl/strips_ground_clingo.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) -fPIC $(CLINGO_CFLAGS) -c -o $@ $<

.objs/cp-cp-optimizer.cpp.o: src/cp-cp-optimizer.cpp src/_cp.h pddl/cp.h pddl/config.h $(GEN)
	$(CXX) $(CPPFLAGS) $(CPOPTIMIZER_CPPFLAGS) -c -o $@ $<
.objs/cp-cp-optimizer.pic.cpp.o: src/cp-cp-optimizer.cpp src/_cp.h pddl/cp.h pddl/config.h $(GEN)
	$(CXX) $(CPPFLAGS) $(CPOPTIMIZER_CPPFLAGS) -fPIC -c -o $@ $<
.objs/asnets_dynet.cpp.o: src/asnets_dynet.cpp pddl/asnets_dynet.h pddl/asnets.h pddl/config.h $(GEN)
	$(CXX) $(CPPFLAGS) $(DYNET_CPPFLAGS) -c -o $@ $<
.objs/asnets_dynet.pic.cpp.o: src/asnets_dynet.cpp pddl/asnets.h pddl/config.h $(GEN)
	$(CXX) $(CPPFLAGS) $(DYNET_CPPFLAGS) -fPIC -c -o $@ $<

.objs/%.o: src/%.c pddl/%.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) -c -o $@ $<
.objs/%.pic.o: src/%.c pddl/%.h pddl/config.h $(GEN)
	$(CC) $(CFLAGS) -fPIC -c -o $@ $<
.objs/%.o: src/%.c pddl/config.h $(GEN)
	$(CC) $(CFLAGS) -c -o $@ $<
.objs/%.pic.o: src/%.c pddl/config.h $(GEN)
	$(CC) $(CFLAGS) -fPIC -c -o $@ $<
.objs/%.cpp.o: src/%.cpp pddl/%.h pddl/config.h $(GEN)
	$(CXX) $(CPPFLAGS) -c -o $@ $<
.objs/%.pic.cpp.o: src/%.cpp pddl/%.h pddl/config.h $(GEN)
	$(CXX) $(CPPFLAGS) -fPIC -c -o $@ $<
.objs/%.cpp.o: src/%.cpp pddl/config.h $(GEN)
	$(CXX) $(CPPFLAGS) -c -o $@ $<
.objs/%.pic.cpp.o: src/%.cpp pddl/config.h $(GEN)
	$(CXX) $(CPPFLAGS) -fPIC -c -o $@ $<

%.h: pddl/config.h
%.c: pddl/config.h

gen-stubs:
	$(SH) scripts/gen-stub.sh pddl/bdd.h "Binary decision diagrams require the CUDD library; cpddl must be re-compiled with the CUDD support." pddl_cudd_version >src/bdd-stub.c
	$(SH) scripts/gen-stub.sh pddl/sym.h "Symmetries require the Bliss library; cpddl must be re-compiled with the Bliss support." pddl_bliss_version >src/sym-stub.c
	$(SH) scripts/gen-stub.sh pddl/asnets_dynet.h "ASNets require the DyNet library; cpddl must be re-compiled with the DyNet support." pddl_dynet_version >src/asnets_dynet-stub.c
	$(SH) scripts/gen-stub.sh pddl/sql_grounder.h "SQL Grounder requires the sqlite library: Re-compile with the USE_SQLITE=yes flag in Makefile.config." pddl_sqlite_version >src/sql_grounder-stub.c
	$(SH) scripts/gen-stub.sh pddl/asnets_convert_from_sql.h "Conversion from old ASNets models require the sqlite library: Re-compile with the USE_SQLITE=yes flag in Makefile.config." "" >src/asnets_convert_from_sql-stub.c


clean:
	rm -f .objs/*.o
	rm -f src/_parser.c
	rm -f src/_parser.h
	rm -f src/_parser.out
	rm -f src/lemon
	rm -f *.a
	rm -f *.so
	rm -f pddl/config.h
	rm -f src/tmp.*
	rm -f $(GEN)
	if [ -d bin ]; then $(MAKE) -C bin clean; fi;
	if [ -f t/Makefile ]; then $(MAKE) -C t clean; fi;

mrproper: clean third-party-clean

fetch-submodules:
	git submodule update --init --recursive

check check-all check-valgrind check-segfault check-gdb: libpddl.a
	if [ -f t/Makefile ]; then $(MAKE) -C t $@; fi

check-bin check-bin-all: bin
	if [ -f t/Makefile ]; then $(MAKE) -C t $@; fi

analyze: clean
	$(SCAN_BUILD) $(MAKE)

tidy:
	find src/ -name '*.c' \
              -a -not -name google-city-hash.c \
              -a -not -name sqlite3.c \
              -a -not -name toml.c \
              -a -not -name sha256.c \
        | xargs -n1 bash scripts/tidy-code.sh
	find pddl/ -name '*.h' \
              -a -not -name google-city-hash.c \
              -a -not -name sqlite3.c \
              -a -not -name toml.c \
              -a -not -name sha256.c \
        | xargs -n1 bash scripts/tidy-code.sh

list-global-symbols: libpddl.a
	readelf -s libpddl.a \
        | grep GLOBAL \
        | awk '{print $$8}' \
        | sort \
        | uniq \
        | grep -v '^pddl' \
        | grep -v '^_pddl' \
        | grep -v '^__pddl' \
        | grep -v '^_Z.*Ilo' \
        | grep -v '^_Z.*Ilo' \
        | grep -v '^_Z.*dynet' \
        | grep -v '^CPX' \
        | grep -v '^GRB' \
        | grep -v '^glp_' \
        | grep -v '^bliss_' \
        | grep -v '^Cudd_' \
        | less

third-party: bliss cudd
third-party-clean: bliss-clean cudd-clean

bliss: third-party/bliss/libbliss.a
bliss-clean:
	$(MAKE) -C third-party/bliss clean
	rm -f third-party/bliss/libbliss.a
	rm -f third-party/bliss/bliss_C.h
third-party/bliss/libbliss.a:
	$(MAKE) CC=$(CXX) AR=$(AR) RANLIB=$(RANLIB) -C third-party/bliss lib_static
	cp third-party/bliss/src/bliss_C.h third-party/bliss/
	mv third-party/bliss/libbliss_static.a $@

cudd: third-party/cudd/libcudd.a
cudd-clean:
	git clean -fdx third-party/cudd
	rm -f third-party/cudd/lib*.a
	rm -f third-party/cudd/cudd.h
third-party/cudd/libcudd.a:
	cd third-party/cudd && aclocal
	cd third-party/cudd && autoheader
	cd third-party/cudd && autoconf
	cd third-party/cudd && automake
	cd third-party/cudd && ./configure --disable-shared CC=$(CC) CXX=$(CXX) AR=$(AR) RANLIB=$(RANLIB)
	$(MAKE) -C third-party/cudd
	cp third-party/cudd/cudd/.libs/libcudd.a $@
	cp third-party/cudd/cudd/cudd.h third-party/cudd/cudd.h

sqlite-amalgam:
	unzip $(SQLITE_SRC_ZIP)
	mv sqlite-src-*/ sqlite
	cd sqlite/ && ./configure --disable-json --disable-load-extension --disable-readline --disable-tcl
	cd sqlite/ && make OPTS="$(SQLITE_GEN_CFLAGS)" sqlite3.c
	cat sqlite/sqlite3.c | sed 's/sqlite3/pddl_sqlite3/g' >src/sqlite3.c
	cat sqlite/sqlite3.h | sed 's/sqlite3/pddl_sqlite3/g' >src/sqlite3.h
	rm -rf sqlite/

gen-pkgconfig: cpddl.pc
cpddl.pc: libpddl.a
	$(SH) ./scripts/gen-pkgconfig.sh "$(BASEPATH_)" "$(LDFLAGS)" >$@

help:
	@echo "Targets:"
	@echo "  all         - Build library (default)"
	@echo "  bin         - Bild binaries in bin/"
	@echo "  bliss       - Build Bliss library from third-party/"
	@echo "  cudd        - Bild Cudd library from third-party/"
	@echo "  third-party - Alias for 'bliss cudd'"
	@echo ""
	@echo "  clean             - Remove all generated files"
	@echo "  c                 - Like clean but does not remove sqlite object file"
	@echo "  mrproper          - Clean library and third-party/"
	@echo "  third-party-clean - Clean all third-party projects."
	@echo ""
	@echo "  check               - Run (short) automated tests"
	@echo "  check-valgrind      - Run tests with valgrind(1)"
	@echo "  check-segfault      - Run tests with valgrind(1) set up to detect only segfaults"
	@echo "  check-gdb           - Run tests in gdb"
	@echo ""
	@echo "  fetch-submodules - Fetch all submodules using git"
	@echo "  gen-pkgconfig - Generates pkg-config file cpddl.pc referring to this directory"
	@echo "  analyze - Static analysis with clang's scan-build (SCAN_BUILD = $(SCAN_BUILD))"
	@echo ""
	@echo "  tidy - Tidy up source code"
	@echo "  list-global-symbols - List all global symbols in libpddl.a"
	@echo "  sqlite-amalgam - Generate src/sqlite3.{c,h} from SQLite zip file defined in SQLITE_SRC_ZIP"
	@echo ""
	@echo "Variables:"
	@echo "  SYSTEM  = $(SYSTEM)"
	@echo "  CC      = $(CC)"
	@echo "  CXX     = $(CXX)"
	@echo "  AR      = $(AR)"
	@echo "  RANLIB  = $(RANLIB)"
	@echo "  SH      = $(SH)"
	@echo "  SCAN_BUILD = $(SCAN_BUILD)"
	@echo "  DEBUG   = $(DEBUG)"
	@echo "  PROFIL  = $(PROFIL)"
	@echo "  WERROR  = $(WERROR)"
	@echo "  CFLAGS  = $(CFLAGS)"
	@echo "  LDFLAGS = $(LDFLAGS)"
	@echo ""
	@echo "  LDFLAGS_EXTRA = $(LDFLAGS_EXTRA)"
	@echo "  SYSTEM_LDFLAGS = $(SYSTEM_LDFLAGS)"
	@echo ""
	@echo "  USE_BLISS         = $(USE_BLISS)"
	@echo "  BLISS_CFLAGS      = $(BLISS_CFLAGS)"
	@echo "  BLISS_LDFLAGS     = $(BLISS_LDFLAGS)"
	@echo "  USE_CUDD          = $(USE_CUDD)"
	@echo "  CUDD_CFLAGS       = $(CUDD_CFLAGS)"
	@echo "  CUDD_LDFLAGS      = $(CUDD_LDFLAGS)"
	@echo ""
	@echo "  USE_SQLITE    = $(USE_SQLITE)"
	@echo "  SQLITE_CFLAGS = $(SQLITE_CFLAGS)"
	@echo ""
	@echo "  IBM_CPLEX_ROOT    = $(IBM_CPLEX_ROOT)"
	@echo "  USE_CPLEX         = $(USE_CPLEX)"
	@echo "  CPLEX_CFLAGS      = $(CPLEX_CFLAGS)"
	@echo "  CPLEX_LDFLAGS     = $(CPLEX_LDFLAGS)"
	@echo "  CPLEX_ONLY_API    = $(CPLEX_ONLY_API)"
	@echo "  GUROBI_ROOT       = $(GUROBI_ROOT)"
	@echo "  USE_GUROBI        = $(USE_GUROBI)"
	@echo "  GUROBI_CFLAGS     = $(GUROBI_CFLAGS)"
	@echo "  GUROBI_LDFLAGS    = $(GUROBI_LDFLAGS)"
	@echo "  GUROBI_ONLY_API   = $(GUROBI_ONLY_API)"
	@echo "  HIGHS_ROOT        = $(HIGHS_ROOT)"
	@echo "  USE_HIGHS         = $(USE_HIGHS)"
	@echo "  HIGHS_CFLAGS      = $(HIGHS_CFLAGS)"
	@echo "  HIGHS_LDFLAGS     = $(HIGHS_LDFLAGS)"
	@echo "  LP_LDFLAGS        = $(LP_LDFLAGS)"
	@echo "  LP_CFLAGS         = $(LP_CFLAGS)"
	@echo ""
	@echo "  USE_CPOPTIMIZER      = $(USE_CPOPTIMIZER)"
	@echo "  CPOPTIMIZER_CPPFLAGS = $(CPOPTIMIZER_CPPFLAGS)"
	@echo "  CPOPTIMIZER_LDFLAGS  = $(CPOPTIMIZER_LDFLAGS)"
	@echo "  MINIZINC_BIN         = $(MINIZINC_BIN)"
	@echo "  MINIZINC_VERSION     = $(MINIZINC_VERSION)"
	@echo ""
	@echo "  DYNET_ROOT        = $(DYNET_ROOT)"
	@echo "  USE_DYNET         = $(USE_DYNET)"
	@echo "  DYNET_CPPFLAGS    = $(DYNET_CPPFLAGS)"
	@echo "  DYNET_LDFLAGS     = $(DYNET_LDFLAGS)"
	@echo ""
	@echo "  CLINGO_ROOT    = $(CLINGO_ROOT)"
	@echo "  USE_CLINGO     = $(USE_CLINGO)"
	@echo "  CLINGO_CFLAGS  = $(CLINGO_CFLAGS)"
	@echo "  CLINGO_LDFLAGS = $(CLINGO_LDFLAGS)"
	@echo ""
	@echo "  USE_MIMALLOC     = $(USE_MIMALLOC)"
	@echo "  MIMALLOC_CFLAGS  = $(MIMALLOC_CFLAGS)"
	@echo "  MIMALLOC_LDFLAGS = $(MIMALLOC_LDFLAGS)"
	@echo ""
	@echo "  USE_CLIQUER       = $(USE_CLIQUER)"
	@echo "  CLIQUER_CFLAGS    = $(CLIQUER_CFLAGS)"
	@echo "  CLIQUER_LDFLAGS   = $(CLIQUER_LDFLAGS)"

.PHONY: all bin clean help doc install analyze \
  examples mrproper \
  check check-all \
  check-valgrind check-segfault check-gdb check-bin check-bin-all \
  third-party third-party-clean \
  bliss bliss-clean \
  sqlite-amalgam gen-stubs
.DELETE_ON_ERROR:
