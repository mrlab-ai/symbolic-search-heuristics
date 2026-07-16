# cpddl

**cpddl** is a library and a set of programs for PDDL-based automated planning
written in C.

If you use this software in an academic publication, please cite the Zenodo DOI:
> Daniel Fišer (2025). *cpddl*. Zenodo. https://doi.org/10.5281/zenodo.16423301

For reproducibility, you may consider citing the specific version you used.  
A full list of versions is available at the link above.

[[_TOC_]]

## Prebuilt Images
If you don't intend to use cpddl as a library, but as a standalone command line
tool, you can consider using the prebuilt [Apptainer](https://apptainer.org/)
images. The latest version of the (almost) full built of the cpddl command line
tool can be obtained from gitlab:
```sh
  $ apptainer pull oras://registry.gitlab.com/danfis/cpddl:latest
```
It is built with the support for symmetries ([bliss](https://users.aalto.fi/~tjunttil/bliss)),
symbolic search ([cudd](https://davidkebo.com/cudd)), LP/MIP solver
([HiGHS](https://highs.dev), a COP
solver ([minizinc](https://www.minizinc.org/)), and
[Gringo/Clingo](https://potassco.org/clingo/) grounders.
It also supports the [CPLEX](https://www.ibm.com/analytics/cplex-optimizer)
solver, but it is not directly linked-in (as it requires academic or
commercial license). Instead, you can dymanically link it during runtime. If,
for example, your installation of CPLEX is located in `/opt/cplex/v22.1.1`, then
you can pull the CPLEX library using to option `--cplex-lib`:
```sh
  $ ./cpddl_latest.sif --cplex-lib /opt/cplex/v22.1.1/cplex/bin/x86-64_linux/libcplex2211.so ...
```

The very same apptainer image is now part of [planutils](https://github.com/AI-Planning/planutils)
under the name `cpddl`.


There is also available a much smaller "barebone" image that does not include any
depdendecies:
```sh
  $ apptainer pull oras://registry.gitlab.com/danfis/cpddl:barebone-latest
```


## Building with Makefile

This project is built with [GNU Make](https://www.gnu.org/software/make), and
the compilation can be configured by adding a ``Makefile.config`` file with the
configuration setting to the top directory. It is recommended to start by
copying ``Makefile.config.tpl`` to ``Makefile.config`` and modify it to your
liking.

The easiest and fastest way the build the working system is by calling:
```sh
  $ cp Makefile.config.tpl Makefile.config
      # Edit Makefile.config if you need/want to.
  $ ./scripts/build.sh
```
It builds the cpddl library and binaries with [bliss](https://users.aalto.fi/~tjunttil/bliss)
(used for symmetries) and [cudd](https://davidkebo.com/cudd) (used for BDDs in
the symbolic search) libraries which are compiled from local
copies in the `third-party/` directory. It also uses the configuration options
placed in the `Makefile.config` file. `Makefile.config.tpl` contains
detailed instructions how to change the configuration. In particular, you might
consider compiling cpddl with the support of LP/MIP/CP solvers required by some
parts of cpddl (the [CPLEX Optimizer](https://www.ibm.com/analytics/cplex-optimizer)
is the recommended option here; see License section below for more information).

Another useful commands are:
- Check the current configuration:
```sh
  $ make help
```
- Build the (static) library ``libpddl.a``:
```sh
  $ make
```
- Build the binaries in the ``bin/`` directory:
```sh
  $ make bin
```
- Remove generated/object/temporary files:
```sh
  $ make clean
```
- Remove all generated/object/temporary files including the ones in the
``third-party`` directory:
```sh
  $ make mrproper
```
- Compile all libraries from the ``third-party/`` directory:
```sh
  $ make third-party
```
- Compile the [bliss](https://users.aalto.fi/~tjunttil/bliss) library for
handling symmetries:
```sh
  $ make bliss
```
Compile the [cudd](https://davidkebo.com/cudd) library for handling binary
decision diagrams:
```sh
  $ make cudd
```

If you tried everything described above and you still cannot build the project,
then:

0. If you try to compile it on Windows, then you are out of luck. Although, it
shouldn't be problem to compile and run it, I'll not provide any support (nor
will I accept any Windows-specific patches).

   If you run Mac, then first check that you run GNU Make in version 4.0 or
higher. The default make in Mac seems to be some ancient version from 20
years ago. If you installed newer GNU Make, you may need to replace the
command `make` with `gmake`.

1. Run ``make mrproper``.

2. Repeat all steps that you used for (unsuccessfully) building the project and record all
commands and all their outputs to both stdout and stderr.

3. Contact me at <danfis@danfis.cz>, describe what are you trying to achieve and where is
the problem, and attach all information gathered in step 2.


## Building Apptainer Image

The script ``scripts/build-apptainer.py`` can be used to build
[Apptainer](https://apptainer.org/) images of the main binary program
``./bin/pddl``. It has a lot of options which are printed when the script is
called without any arguments.
Here is a list of recommendations how to use it:

1. If you don't need any dependencies, the following will build the smallest
possible image:
```sh
  $ ./scripts/build-apptainer.py --no-bliss --no-cudd alpine
```

2. If you want to work with symmetries or binary decision diagrams (e.g., you
want to use symbolic search), use:
```sh
  $ ./scripts/build-apptainer.py alpine
```

3. If you want symmetries, binary decision diagrams, and LP/MIP/CSP CPLEX
solver, then download the installation binary for CPLEX to the location, say,
``/opt/cplex/cplex_studio2211.linux_x86_64.bin`` and call:
```sh
  $ ./scripts/build-apptainer.py --cplex /opt/cplex/cplex_studio2211.linux_x86_64.bin photon
```

4. If you want the same as above but with the HiGHS LP/MIP solver and Minizinc
as the CSP solver, call:
```sh
  $ ./scripts/build-apptainer.py --highs --minizinc debian-bookworm
```


## Usage Examples

**cpddl** is first and foremost a C library, but it also comes with several
programs that can be called from the command line. The main program is
``./bin/pddl``, but there are several other programs that implement a subset of
features of ``./bin/pddl`` and have a different default values for some options.
Running any of those programs without an argument (or with ``-h`` or ``--help``)
prints a (long) list of available options.

### Validation of PDDL Tasks
To check correctness of the input PDDL files, call
```sh
  $ ./bin/pddl --pddl-stop --pedantic domain.pddl problem.pddl
```

If there is an issue with the PDDL files, it tries to report what exactly is the
problem and where it occurs. For example, parsing the original storage domain
from IPC 2006 results in the following error message:
```
Error: The type 'area' is defined for the second time. line: 9, column: 9
/home/danfis/dev/plan/downward-benchmarks/storage/domain.pddl:9:9:
     6 | (:types hoist surface place area - object
     7 |         container depot - place
     8 |         storearea transitarea - area
     9 |         area crate - surface)
       |         ^--- here
```

### PDDL Normalization
cpddl can be used to normalize PDDL input files, i.e., as a translator that
takes input domain and problem PDDL files and outputs domain and problem PDDL
files without disjunctions, quantifiers, or (dynamic) negative conditions.
```sh
  $ ./bin/pddl --pddl-domain-out d.pddl --pddl-problem-out p.pddl --pddl-stop domain.pddl problem.pddl
```
It is also possible to compile away conditional effects (the option
``--pddl-ce``), enforce unit cost (``--pddl-unit-cost``), or more precisely
control which forms of negative conditions are compiled away
(``--pddl-neg-cond``).

It is also possible to apply pruning of unreachable or dead-end operators via
a compilation of **lifted fact-alternating mutex groups** on the PDDL level
(``--pddl-compile-in-lmg``). For description of this method, see
> Daniel Fišer.
> *Operator Pruning using Lifted Mutex Groups via Compilation on Lifted Level*,
> ICAPS 2023

Another pruning on the PDDL level available in cpddl is the method based on
**PDDL endomorphisms** (options ``--lendo`` and ``--lendo-ignore-costs``). For
details, see
> Rostislav Horčík, Daniel Fišer.
> *Endomorphisms of Lifted Planning Problems*,
> ICAPS 2021

### Lifted Planning
cpddl implements lifted planning algorithms, i.e., planning that operates
directly on the PDDL level without fully grounding the task first. Note that the
PDDL tasks are normalized first, so the options related PDDL normalization takes
effect here too.

The blind lifted A\* can be invoked by
```sh
  $ ./bin/pddl --lplan astar --lplan-out plan.out domain.pddl problem.pddl
```

The "lazy" greedy best-first search with the lifted $h^\mathrm{add}$ heuristic
described in
> Augusto B. Corrêa, Guillem Francès, Florian Pommerening and Malte Helmert.
> *Delete-Relaxation Heuristics for Lifted Classical Planning*,
> ICAPS 2021
```sh
  $ ./bin/pddl --lplan lazy --lplan-h add domain.pddl problem.pddl
```

The search with the heuristic computed in the reduced planning task using
**homomorphisms** is described in
> Rostislav Horčík, Daniel Fišer, Álvaro Torralba.
> *Homomorphisms of Lifted Planning Tasks: The Case for Delete-free Relaxation Heuristics*,
> AAAI 2022

The best-performing variant of the optimal search from this paper:
```sh
  $ ./bin/pddl --lplan astar --lplan-h homo-lmc \
               --lplan-h-homo type=rnd-objs,rm-ratio=.95,samples=50 \
               --lplan-out plan.out \
               domain.pddl problem.pddl
```

The selection of homomorphisms using **Gaifman Graphs** can be enabled by
setting `type=gaif` in the `--lplan-h-homo`option.
> Rostislav Horčík, Daniel Fišer.
> *Gaifman Graphs in Lifted Planning*,
> ECAI 2023

The best-performing variant of the optimal planner from the ECAI'23 paper:
```sh
  $ ./bin/pddl --lendo --pddl-compile-in-lmg \
               --lplan astar --lplan-h homo-lmc \
               --lplan-h-homo type=gaif,rm-ratio=.95,samples=50,sampling-max-time=60 \
               --lplan-out plan.out \
               domain.pddl problem.pddl
```


### Translation to FDR
cpddl can ground the input PDDL files and translate them into the Finite Domain
Representaition (FDR). The following command applies forward/backward $h^2$
pruning, irrelevance analysis, and few other pruning tehchniques, and it writes
the FDR encoding in the Fast Downward [format](https://www.fast-downward.org/TranslatorOutputFormat)
to the ``output.sas`` file:
```sh
  $ ./bin/pddl --h2 --fdr-out output.sas domain.pddl problem.pddl
```

By default, the translator infers *lifted fact-alternating mutex groups*
(fam-groups) according to the following paper:
> Daniel Fišer.
> *Lifted Fact-Alternating Mutex Groups and Pruned Grounding of Classical Planning Problems*,
> AAAI 2020

However, it is possible to switch to the Fast Downard (and weaker) variant of
the lifted fam-groups by using the option ``--lmg-fd``.

It is also possible to use a complete set of **fam-groups** inferred on the
ground level using the option ``--mg fam`` (this option requires a MIP solver).
> Daniel Fišer, Antonín Komenda.
> *Fact-Alternating Mutex Groups for Classical Planning*,
> JAIR 61: 475-521 (2018)

Pruning using **operator mutexes** can be applied using the option ``--P-opm``.
> Daniel Fišer, Álvaro Torralba, Alexander Shleyfman.
> *Operator Mutexes and Symmetries for Simplifying Planning Tasks*,
> AAAI 2019

For example, the following command prunes operators using operator mutexes
inferred using the so-called op-fact compilation and symmetries (requires bliss
is compiled-in):
```sh
  $ ./bin/pddl --h2 --P-opm op-fact=2,p=greedy --fdr-out output.sas domain.pddl problem.pddl
```

Pruning using **endomorphisms** on the ground level can be applied using the
``--P-endo`` option.
> Rostislav Horčík, Daniel Fišer.
> *Endomorphisms of Classical Planning Tasks*,
> AAAI 2021


Translation to the FDR targeting Red-Black planning can be turned on by the
option ``--rb-fdr``.
> Daniel Fišer, Daniel Gnad, Michael Katz, Jörg Hoffmann
> *Custom-Design of FDR Encodings: The Case of Red-Black Planning*,
> IJCAI 2021


### Potential Heuristics
cpddl also implements ground search algorithms with several potential heuristics.

**Potential heuristics** strengthened with **disambiguations** is described in
> Daniel Fišer, Rostislav Horčík, Antonín Komenda.
> *Strengthening Potential Heuristics with Mutexes and Disambiguations*,
> ICAPS 2020

The best-peforming variant can be run by
```sh
  $ ./bin/pddl --h2 --gplan astar --gplan-h pot --gplan-pot A+I domain.pddl problem.pddl
```

Computing **higher-order potential heuristics** via either $P^C$ or
$P^C_{exact}$ compilations is described in the paper:
> Daniel Fišer, Marcel Steinmetz.
> *Towards Feasible Higher-Dimensional Potential Heuristics*,
> ICAPS 2024

For both cases, it is necessary to have a configuration file describing the
conjunctions that are used. This configuration file can be either created
manually, or it can be generated using the algorithm described in the paper
(Algorithm 1).

For finding the conjunctions for $P^C$ compilation with 5 minutes time limit,
maximum of 1000 epochs (i.e., maximal number of improvements) and using
potentials maximizing for the initial state, use:
```sh
  $ ./bin/pddl --h2 --pot-conj-find time-limit=300,out=conj,max-epochs=1000,random=false \
               --pot-conj-find-pot I domain.pddl problem.pddl
```

And the same except for the $P^C_{exact}$ compilation:
```sh
  $ ./bin/pddl --h2 --pot-conj-exact-find time-limit=300,out=conj,max-epochs=1000,random=false \
               --pot-conj-find-pot I domain.pddl problem.pddl
```

In both cases, the program generates files `conj.EEEE` for each epoch E that
leads to an improvement of the objective value. This means that the last
generated file corresponds to the best set of conjunctions found (but also with
the highest number of conjunctions).

Once we have a configuration file defining the set of conjunctions, say
`conj.0001`, we can run search with potential heuristics computed for all atomic
facts plus the provided set of conjunctions.

For $P^C$ with optimization for all syntactic states + maximizing h-value for
the initial state:
```sh
  $ ./bin/pddl --h2 --gplan-out plan.out --gplan astar --gplan-h pot-conj \
               --gplan-pot A+I --gplan-pot-conj-file conj.0001 domain.pddl problem.pddl
```

For $P^C_{exact}$:
```sh
  $ ./bin/pddl --h2 --gplan-out plan.out --gplan astar --gplan-h pot-conj-exact \\
               --gplan-pot A+I --gplan-pot-conj-exact-file conj.0001 domain.pddl problem.pddl
```


**Weakening of consistency constraints** of potential heuristics so that
$\max(h^\mathtt{P},0)$ is forward-consistent (instead of $h^\mathtt{P}$) is
described in
> Pascal Lauer, Daniel Fišer.
> *Potential Heuristics: Weakening Consistency Constraints*,
> ICAPS 2025

It can be invoked by using the additional parameter `hmax0` in the `--gplan-pot`
option, for example:
```sh
  $ ./bin/pddl --h2 --gplan astar --gplan-h pot --gplan-pot I,hmax0,lp-time-limit=120 domain.pddl problem.pddl
```


### Symbolic Search
Symbolic search using binary decision diagrams requires that cpddl is compiled
with the cudd library.

Besides blind search, we developed also so-called **operator-potential heuristics**
that significantly improve the performance.
> Daniel Fišer, Álvaro Torralba, Jörg Hoffmann.
> *Operator-Potential Heuristics for Symbolic Search*,
> AAAI 2022

> Daniel Fišer, Álvaro Torralba, Jörg Hoffmann.
> *Operator-Potentials in Symbolic Search: From Forward to Bi-Directional Search*,
> ICAPS 2022

The bi-directional symbolic search with the blind backward search and the best
variant of the operator-potential heuristic for the forward direction can be
invoked by
```sh
  $ ./bin/pddl-symba --fdr-tnfm --symba bi --symba-fw-pot --symba-fw-pot-cfg A+I \
                     domain.pddl problem.pddl
```


### Action Schema Networks
cpddl includes implementation of Action Schema Networks (ASNets) using the
[DyNet](https://github.com/clab/dynet) library.
> Sam Toyer, Sylvie Thiébaux, Felipe Trevizan, Lexing Xie
> *ASNets: Deep Learning for Generalised Planning*,
> JAIR 2020

To enable DyNet, set `DYNET_ROOT`, or `DYNET_CPPFLAGS` and `DYNET_LDFLAGS`
variables in ``Makefile.config``.

ASNets are implemented in the ``bin/pddl-asnets`` binary. It uses configuration
files: you can either generate a sample config file (see below), or see the
[pddl-data](https://gitlab.com/danfis/pddl-data) repository, directory
`learn-policy/deterministic`. The default configuration file can be
generated by
```sh
  $ ./bin/pddl-asnets gen-train-config-file config.toml
```

To train a policy while saving the current policy after each epoch with prefix
`policy`:
```sh
  $ ./bin/pddl-asnets train /path/to/config-file.toml policy
```

To evaluate policy on the given list of PDDL problems:
```sh
  $ ./bin/pddl-asnets eval trained.policy /path/to/domain.pddl /path/to/prob1.pddl /path/to/prob2.pddl ...
```

#### Training ASNets with External Teacher

1. The external teacher is specified in the configuration file via options
`teacher` and `teacher_external_cmd`.

2. When the option `teacher` is set to the value "external-fd", the command
specified via `teacher_external_cmd` is called as the external teacher for every
state obtained from the rollout of the policy (see the paper by Toyer et al. how
the training data generation works in ASNets).

3. The command `teacher_external_cmd` is called exactly as specified without
any additional arguments.

4. The external teacher program/script needs to read the problem specification
from stdin. The format of this specification is the
[Fast Downward translator format](https://www.fast-downward.org/TranslatorOutputFormat).
In other words, when using, e.g., Fast Downward as the external teacher, it is
called without the translator component, just the "search" component is used.
Note that the problem specification passed to the external teacher is
constructed so that (a) the initial state is the input state (i.e., not the
original initial state), and (b) operator names are different from the
original task so that it is possible to map them back to the internal
representation of the task. Therefore, the external teacher should completely
disregard the input PDDL files, including the domain file (although there might
be hacky ways how to do that for some particular application).

5. The program/script needs to write the resulting plan to stdout and exit 0.
   - If it does not write anything to stdout and exists 0, then it is considered
as "no plan was found", and training continues (as if, for example, the
teacher timed-out).

   - If it writes something else than a plan (one operator name per line) to stdout,
then the rest of the output is simply ignored (it's not a very nice behaviour,
but it at least ignores comments).

   - If the teacher exits with any other code than 0 (or with a signal), the
whole training is terminated. Therefore, the teacher can terminate the whole
training process.

   - If there is anything written to stderr, it is reported (verbatim) in the log and
training is aborted. So, it should be possible to debug the teacher at
least to some degree.

6. Here is a sample bash script that can be used as an external teacher (also
see `scripts/asnets-external-teacher-example.sh`):

```sh
#!/bin/bash
FD_PATH=/home/danfis/dev/FD/fast-downward/builds/release/bin/downward
rm -f plan.sas
cat | \
    timeout 5s $FD_PATH \
            --search 'astar(lmcut())' \
            --internal-plan-file plan.sas >/dev/null 2>&1
if [ -f plan.sas ]; then
    cat plan.sas
    rm -f plan.sas
fi
exit 0
```

To use it, save it to, say, teacher.sh, replace the path /home/danfis/.../downward
to the actual FD binary program downward, and set 
```toml
    teacher = "external-fd"
    teacher_external_cmd = ["/bin/bash", "/path/to/teacher.sh"]
```
in the configuration file.

Notice that the output of .../downward cannot be passed to stdout/stderr of
the script (but you can, of course, save it to a file for later inspection
instead of redirecting to /dev/null). Also note that since Fast Downward
writes the plan to a file, the script picks up the file and writes it to
stdout. (This also means you need to be a bit careful how to run this script
on a cluster so that parallel training of multiple models does not
overwrite each others' files.)

**Please refer to the listed papers when documenting work that uses the
corresponding parts of cpddl.**


## License

cpddl is licensed under OSI-approved 3-clause
[BSD License](https://opensource.org/licenses/BSD-3-Clause), text of license
is distributed along with source code in the LICENSE file.

cpddl directly incorporates several third-party works:
- The SQL library [sqlite](https://www.sqlite.org/index.html) which is in
[public-domain](https://www.sqlite.org/copyright.html);

- The [SHA256](https://github.com/B-Con/crypto-algorithms)
hash function from public-domain authored by Brad Conte;

- Two hash functions copyrighted by Google and released under the MIT
license [CityHash](https://code.google.com/p/cityhash) and
[FastHash](https://code.google.com/p/fast-hash);

- [Timsort](https://github.com/swenson/sort/) licensed under MIT
(Copyright (c) 2010-2019 Christopher Swenson, 2012 Vojtech Fried, 2012 Google Inc);

- [Toml](https://github.com/cktan/tomlc99) licensed under MIT (Copyright (c) CK Tan);


Other than that, cpddl can be compiled without any other
dependecies besides standard C-related tools.
However, certain functionalities require external libraries:
- symmetries require
[bliss](https://users.aalto.fi/~tjunttil/bliss) library licensed under LGPL
(a slightly modified copy located in the ``third-party`` directory).

- binary decision diagrams require
[cudd](https://davidkebo.com/cudd) library licensed under 3-clause BSD
License
(a copy is located in the ``third-party`` directory).

- (I)LP solver requires
[CPLEX Optimizer](https://www.ibm.com/analytics/cplex-optimizer),
[Gurobi](https://www.gurobi.com/), or
[HiGHS](https://highs.dev). CPLEX Optimizer and
Gurobi are commercial products, but it is possible to obtain an academic
license. HiGHS is licensed under MIT license.

  The recommended and most tested option is the CPLEX Optimizer.

- constraint optimization requires either
[CPLEX CP Optimizer](https://www.ibm.com/analytics/cplex-cp-optimizer), or
[minizinc](https://www.minizinc.org/). CPLEX CP Optimizer is a commercial
library, but it is possible to obtain an academic license. Minizinc is
licensed under Mozilla Public License v2.0 (and itself depends on other
solvers), but it is called as a subprocess from cpddl, i.e., it is never
statically or dynamically linked to cpddl.

  The recommended option is the CPLEX CP Optimizer.

- Action Schema Networks require the [DyNet](https://github.com/clab/dynet)
library licensed under Apache 2.0 license.
- Gringo and Clingo grounders require the [clingo](https://potassco.org/clingo)
library. Clingo is distributed under the MIT License.

- Memory allocator can be switched to [mimalloc](https://microsoft.github.io/mimalloc)
distributed under the MIT License.
