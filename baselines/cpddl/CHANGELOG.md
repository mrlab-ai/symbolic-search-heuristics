# Changelog

## Version 1.5

### Added
- Added check in Makefile for the minimum required version of make.
- Basic support for numerical PDDL.
- Compiling away disjunctive goals using auxiliary operators.
- Inference of minimal :requirements flags actually used in the PDDL problem.
- Added support for mimalloc memory allocator.
- Higher-order potential heuristics via compilations
- Potential heuristics such that max(h^P,0) is consistent and admissible.
- Module opts for parsing command line options.
- ASNets: More built-in teachers, easier re-loading of models.

### Changed
- :objects and :constants sections are printed based on where objects actually
occur.

### Removed
- Removed support for Coin-Or MIP/LP solver

### Fixed
- Bug in compiling away negative preconditions: When using datalog to infer
which NOT-* facts are necessary in the initial state, inequality preconditions
were treated as equality preconditions.
- ASNets: Sensible error message when no training data are available.
- ASNets: Improved README.
- Few bugs in computation of lifted homomorphisms.
- Memleak in lifted successor generator.


## Version 1.4

### Added
- ASNets: Optional logging of evaluation time per evaluated state

### Changed
- ASNets: Allowed only one instance of a model to prevent memory leak from the
  DyNet library
- ASNets: Better reporting of numerical issues from DyNet


## Version 1.3

### Added
- ASNets: Support for landmarks and action history
- Potential heuristics over conjunctions.
- Gringo and Clingo grounders.
- Allowed to ground only facts.
- Lifted FF heuristic.
- Function for compiling away equality predicates.

### Changed
- Refactored ASNets
- ASNets: Changed format of output policy files from sqlite to TOML.
- SQLite: Not included by default. It needs to be enabled in Makefile.config.


## Version 1.2

### Added
- Action Schema Networks for classical tasks
- Action Schema Networks for oversubscription tasks where all goals are
considered soft goals.
- Gaifman graphs for homomorphism-based heuristics for lifted planning
- Function for running subprocesses with time and memory limits
- High-level API for reading TOML files

### Changed
- Greedy searches terminate as soon as goal state is generated
- Log to stdout by default

### Fixed
- Errors from the LP module are propagated (or at least terminates the process)
- Fixed error in determining a directory from a path to file


## Version 1.1

### Added
- Script for building Apptainer images
- Script for generating pkg-config file
- Support for Coin-Or MIP/LP solver
- Dynamic loading of CPLEX and Gurobi libraries during runtime
- Binaries can list available LP and CP solvers
- Greedy best-first search algorithm

### Changed
- Algorithm for compiling away negative conditions: Now, it adds only the
  (potentially) relevant `NOT-*` facts to the initial state; and it can be
  configured via `pddl_config_t`.
- Unified API for grounding
- Unified A\*, Lazy, and GBFS search algorithms
- Parsing of PDDL files completely re-worked with the lemon parser; it now
  provides much nicer and more helpful error messages.

### Removed
- Suport for GLPK solver

### Fixed
- Fixed h^2 pruning of goal facts which simply removed the goal facts. Now,
  the task is marked as unsolvable.


## Unreleased

### Added

### Changed

### Removed

### Fixed
