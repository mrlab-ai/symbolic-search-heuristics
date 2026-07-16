# Set up C and C++ compilers
#CC = clang
#CXX = clang++

# Turn on debug build. Use this to if you plan to use tools like valgrind, gdb,
# and so on. By default, it is turned off.
#DEBUG = yes

# Compile with -Werror. By default, it is turned off.
#WERROR = yes

# Turn on compilation with profiling information, it implies DEBUG=yes. Turned
# off by default.
#PROFIL = yes

# Configuration of SQLite
# ------------------------
#
# The source code of SQLite (https://www.sqlite.org/) is already part of
# the cpddl library. To enable its integration, set USE_SQLITE to yes.
#
#USE_SQLITE = no


# Configuration of IBM CPLEX Optimization Studio
# -----------------------------------------------
#
# Among all options, this is the recommended (and most tested) set of libraries
# used for LP, MIP, CSP, and COP optimizations.
#
# With full installations of IBM CPLEX Optimization Studio, it is recommended
# to set IBM_CPLEX_ROOT to the root directory of your installation.
# However, you can also set individual compile (*_CFLAGS) and link (*_LDFLAGS)
# flags individually for each CPLEX and CP Optimizer according to your
# installation.
#
# It is also possible to explicitly disable CPLEX or CP Opimization by setting
# USE_CPLEX or USE_CPOPTIMIZER to 'no'. It disables the libraries even if all
# compile and link flags are correctly set up. For example, one can decide to
# use only CPLEX and not CP Optimizer by setting IBM_CPLEX_ROOT and then setting
# USE_CPOPTIMIZER=no.
#
# The library also allows to load CPLEX dynamically at runtime (see the function
# pddlLPLoadCPLEX) in which case only header files are required. If you wish to
# do that, set CPLEX_ONLY_API to 'yes'.
#
#IBM_CPLEX_ROOT = /opt/cplex/v12.10
#CPLEX_CFLAGS = -I/opt/cplex1271/cplex/include
#CPLEX_LDFLAGS = -L/opt/cplex1271/cplex/lib/x86-64_linux/static_pic/ -lcplex
#CPOPTIMIZER_CPPFLAGS = -I/opt/cplex/v12.10/cpoptimizer/include -I/opt/cplex/v12.10/concert/include/ -I/opt/cplex/v12.10/cplex/include
#CPOPTIMIZER_LDFLAGS = -L/opt/cplex/v12.10/cpoptimizer/lib/x86-64_linux/static_pic/ -lcp -L/opt/cplex/v12.10/concert/lib/x86-64_linux/static_pic/ -lconcert -lstdc++
# Set to no to completely disable CPLEX library
#USE_CPLEX = no
# Set to no to completely disable CPLEX CP Optimizer library
#USE_CPOPTIMIZER = no

# Set to yes if CPLEX should not be linked. This allows to compile cpddl
# with ability to load CPLEX dynamically from .so library. Setting this to
# yes also disables CPOPTIMIZER, i.e., it is not possible to link to CPLEX
# CP Optimizer but not to CPLEX at the same time.
#CPLEX_ONLY_API = yes


# Configuration of Gurobi Optimizer
# ---------------------------------
#
# With full installation of Gurobi, it is recommended to set GUROBI_ROOT to the
# root directory of your installation. However, compile (*_CFLAGS) and link
# (*_LDFALGS) flags can be set individually.
#
# It is also possible to disable Gurobi even if it is configured by setting
# USE_GUROBI to 'no'.
#
# Moreover, the library also allows to load Gurobi dynamically at runtime (see
# the function pddlLPLoadGurobi) in which case only header files are required.
# To achieve that, set GUROBI_ONLY_API to 'yes'.
#
#GUROBI_ROOT = /opt/gurobi951/linux64
#GUROBI_CFLAGS = -I/opt/gurobi951/linux64/include
#GUROBI_LDFLAGS = -L/opt/gurobi951/linux64/lib -Wl,-rpath=/opt/gurobi951/linux64/lib -lgurobi95
# Set to no to completely disable Gurobi library
#USE_GUROBI = no

# As CPLEX_ONLY_API but for the Gurobi library
#GUROBI_ONLY_API = yes


# Configuration of HiGHS
# ----------------------
#
# If the HiGHS library is installed in a separate directory, set HIGHS_ROOT to
# point to that directory. Otherwise, HIGHS_CFLAGS and HIGHS_LDFLAGS can be set
# directly.
#
# USE_HIGHS can be set to 'no' to disable HiGHS even when it is configured.
#
#HIGHS_ROOT = /opt/HiGHS
#HIGHS_CFLAGS = -I/opt/HiGHS/include
#HIGHS_LDFLAGS = -L/opt/HiGHS/lib -lhighs
# Set to no to completely disable HiGHS library
#USE_HIGHS = no


# Minizinc
# --------
#
# Minizinc is called as a subprocess. MINIZINC_BIN can be set as a default path.
#
#MINIZINC_BIN = /opt/minizinc/bin/minizinc


# DyNet
# -----
#
# If the DyNet library is installed in a separate directory, set DYNET_ROOT to
# the that directory. Otherwise, DYNET_CPPFLAGS and DYNET_LDFLAGS can be set
# directly.
#
#DYNET_ROOT = /opt/dynet
#DYNET_CPPFLAGS = -I/opt/dynet/include
#DYNET_LDFLAGS = -L/opt/dynet/lib -ldynet


# Clingo
# -------
# https://github.com/potassco/clingo
#
# If the Clingo library is installed in a separate directory, set CLINGO_ROOT
# to the that directory. Otherwise, CLINGO_CFLAGS and CLINGO_LDFLAGS can be set
# directly.
#
#CLINGO_ROOT = /opt/clingo/v5.6.2
#CLINGO_CFLAGS = -I/opt/clingo/v5.6.2/include
#CLINGO_LDFLAGS = -L/opt/clingo/v5.6.2/lib -Wl,-rpath=/opt/clingo/v5.6.2/lib -lclingo


# mimalloc
# ---------
# https://microsoft.github.io/mimalloc
#
#MIMALLOC_CFLAGS =
#MIMALLOC_LDFLAGS = -lmimalloc
