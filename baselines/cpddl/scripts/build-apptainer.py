#!/usr/bin/env python3

import sys
import os
import argparse

def setupCplex(path):
    return f'''
cp "{path}" $APPTAINER_ROOTFS/cplex.bin
chmod +x $APPTAINER_ROOTFS/cplex.bin
'''

def postCplex():
    return '''
/cplex.bin -i silent -DUSER_INSTALL_DIR=/cplex -DLICENSE_ACCEPTED=true
'''

def configCplex():
    return ['IBM_CPLEX_ROOT = /cplex']

def setupCplexApi(path):
    return f'''
mkdir -p $APPTAINER_ROOTFS/cplex/cplex/include
cp -rv {path}/* $APPTAINER_ROOTFS/cplex/cplex/include/
'''

def configCplexApi():
    return ['IBM_CPLEX_ROOT = /cplex', 'CPLEX_ONLY_API = yes']

def setupMinizinc():
    return '''
MINIZINC_LINK="https://github.com/MiniZinc/MiniZincIDE/releases/download/2.7.6/MiniZincIDE-2.7.6-bundle-linux-x86_64.tgz"
wget $MINIZINC_LINK -O $APPTAINER_ROOTFS/minizinc-ide.tgz
'''

def postMinizinc():
    return '''
cd /
tar xf /minizinc-ide.tgz
mv /MiniZinc* /minizinc
'''

def filesMinizinc():
    return ['/minizinc']

def configMinizinc():
    return ['MINIZINC_BIN = /minizinc/bin/minizinc']

def setupHighs():
    return '''
HIGHS_REPO=https://github.com/ERGO-Code/HiGHS.git
HIGHS_BRANCH=v1.5.1
git clone --depth 1 --branch $HIGHS_BRANCH $HIGHS_REPO $APPTAINER_ROOTFS/highs-src
'''

def postHighs():
    return '''
cd /highs-src
mkdir build
cd build
cmake -DCMAKE_INSTALL_PREFIX=/highs -DCMAKE_INSTALL_LIBDIR=lib -DSHARED=OFF ..
make -j8
make install
'''

def configHighs():
    return ['HIGHS_ROOT = /highs']

def setupClingo():
    return '''
CLINGO_REPO=https://github.com/potassco/clingo.git
CLINGO_BRANCH=v5.7.1
git clone --depth 1 --branch $CLINGO_BRANCH $CLINGO_REPO $APPTAINER_ROOTFS/clingo-src
'''

def postClingo():
    return '''
cd /clingo-src
mkdir build
cd build
cmake -DCMAKE_INSTALL_PREFIX=/clingo ..
make -j8
make install
cd ../..
'''

def configClingo():
    return ['CLINGO_ROOT = /clingo']

def filesClingo():
    return ['/clingo/lib*/libclingo.so*']

def setupGit(branch):
    return f'''
git clone --depth 1 --branch {branch} https://gitlab.com/danfis/cpddl $APPTAINER_ROOTFS/cpddl
'''

def setupGitDev(branch):
    return f'''
git clone --depth 1 --branch {branch} git@gitlab.com:danfis/cpddl-devel $APPTAINER_ROOTFS/cpddl
'''

def setupRunAllTests():
    return '''
git -C $APPTAINER_ROOTFS/cpddl submodule update --init --depth 1 -- t
git -C $APPTAINER_ROOTFS/cpddl/t submodule update --init --depth 1 -- pddl-data
'''

def setupDisk():
    return '''
cp -r ./ $APPTAINER_ROOTFS/cpddl
git -C $APPTAINER_ROOTFS/cpddl clean -fdx
'''

def setupClangVer():
    return '''
wget -O - https://apt.llvm.org/llvm.sh >$APPTAINER_ROOTFS/llvm.sh
'''

def postClangVer(args):
    return f'bash /llvm.sh {args.clang_ver}\n'

def baseImage(img):
    if img.startswith('debian'):
        return img.replace('-', ':') + '-slim'
    if img.startswith('ubuntu') or img.startswith('gcc'):
        return img.replace('-', ':')
    if img == 'fedora':
        return 'fedora:36'
    if img == 'photon':
        return 'photon:latest'
    return img

def postBuild(args):
    img = args.image
    post = ''
    if img.startswith('debian') or img.startswith('ubuntu') or img.startswith('gcc'):
        pkgs = []
        pkgs += ['make', 'gcc', 'g++', 'bash', 'libstdc++6', 'git']
        if not args.no_cudd is True:
            pkgs += ['autoconf', 'automake']
        if args.clang is True:
            pkgs += ['clang']
        if args.highs is True:
            pkgs += ['cmake', 'libz-dev']
        if args.clingo is True:
            pkgs += ['cmake']
        if args.run_all_tests is True:
            pkgs += ['python3', 'valgrind', 'gdb']

        if args.clang_ver is not None:
            pkgs += ['lsb-release', 'wget', 'software-properties-common', 'gnupg']

        pkgs = ' '.join(sorted(list(set(pkgs))))
        post += f'''
export DEBIAN_FRONTEND=noninteractive
apt update -y
apt upgrade -y
apt install -y {pkgs}
'''

    elif img == 'fedora':
        pkgs = []
        pkgs += ['make', 'gcc', 'g++', 'bash', 'libstdc++', 'git']
        if not args.no_cudd is True:
            pkgs += ['autoconf', 'automake']
        if args.clang is True:
            pkgs += ['clang']
        if args.highs is True:
            pkgs += ['cmake', 'zlib-devel']
        if args.clingo is True:
            pkgs += ['cmake']
        if args.run_all_tests is True:
            pkgs += ['python3', 'valgrind', 'gdb', 'diffutils']

        pkgs = ' '.join(sorted(list(set(pkgs))))
        post += f'''
dnf -y update
dnf -y install {pkgs}
'''

    elif img == 'photon':
        pkgs = []
        pkgs += ['make', 'gcc', 'glibc-devel', 'binutils', 'libstdc++', 'git',
                 'linux-api-headers', 'coreutils', 'grep', 'gawk', 'gzip']
        if not args.no_cudd is True:
            pkgs += ['autoconf', 'automake']
        if args.clang is True:
            pkgs += ['clang']
        if args.highs is True:
            pkgs += ['cmake', 'zlib-devel']
        if args.clingo is True:
            pkgs += ['cmake']
        if args.run_all_tests is True:
            pkgs += ['python3', 'gdb', 'diffutils', 'findutils']

        pkgs = ' '.join(sorted(list(set(pkgs))))
        post += f'''
tdnf -y update
tdnf -y install {pkgs}
'''

    elif img == 'alpine':
        pkgs = []
        pkgs += ['make', 'gcc', 'g++', 'bash', 'libstdc++', 'git']
        if not args.no_cudd is True:
            pkgs += ['autoconf', 'automake']
        if args.clang is True:
            pkgs += ['clang']
        if args.highs is True:
            pkgs += ['cmake', 'zlib-static', 'zlib-dev']
        if args.clingo is True:
            pkgs += ['cmake']
        if args.run_all_tests is True:
            pkgs += ['python3', 'gdb', 'diffutils',
                     'findutils', 'coreutils', 'flex', 'bison']

        pkgs = ' '.join(sorted(list(set(pkgs))))
        post += f'''
apk update
apk upgrade
apk add {pkgs}
'''
    return post

def postRun(args):
    img = args.image
    if img.startswith('debian') or img.startswith('ubuntu') or img.startswith('gcc'):
        post = '''
export DEBIAN_FRONTEND=noninteractive
apt update -y
apt install -y libstdc++6
'''
        if args.minizinc is True:
            post += 'apt install -y libgl1 libegl1 libx11-6 libfontconfig1 libfreetype6\n'
        post += '''
apt autoremove -y
apt-get clean -y
rm -rf /var/lib/apt/lists/*
rm -rf /var/lib/apt/
'''
        return post

    elif img == 'fedora':
        post = '''
dnf -y update
dnf -y install libstdc++
'''
        if args.minizinc is True:
            post += 'dnf -y install -y mesa-libGL mesa-libEGL libX11 fontconfig freetype\n'
        post += '''
dnf -y clean all
rm -rf /var/lib/dnf
rm -rf /var/lib/rpm*
'''
        return post

    elif img == 'photon':
        return '''
tdnf -y update
tdnf -y install libstdc++
tdnf -y clean all
rm -rf /var/lib/dnf
rm -rf /var/lib/rpm*
'''

    elif img == 'alpine':
        return '''
apk update
apk upgrade
apk add bash libstdc++
'''

    else:
        raise Exception()

def postMake(args, config):
    post = '\n'
    for c in config:
        post += f'echo "{c}" >>/cpddl/Makefile.config\n'

    post += '''
cd /cpddl'''
    if not args.no_cudd:
        post += '''
make cudd'''
    if not args.no_bliss:
        post += '''
make bliss'''

    post += '''
make help
make -j8
make -j8 bin
mv /cpddl/bin/pddl /
strip --strip-all /pddl
'''

    if args.run_all_tests:
        post += f'''
make -C /cpddl {args.test_rule} T='{args.test_conf}'
'''
    return post

def main():
    parser = argparse.ArgumentParser(
                    prog='build-apptainer',
                    formatter_class = argparse.RawTextHelpFormatter,
                    description='''
Build Apptainer images of cpddl binary.

Limitations:
    alpine does not support cplex or gurobi
    --gurobi supported only with debian-bullseye/bookworm
    --clang-ver supported only with debian-*, ubuntu-*
''')
    parser.add_argument('image',
                        choices = ['alpine', 'photon',
                                   'debian-bookworm',
                                   'debian-bullseye',
                                   'debian-buster',
                                   'debian-stretch',
                                   'debian-testing',
                                   'ubuntu-noble',
                                   'ubuntu-jammy',
                                   'ubuntu-focal',
                                   'ubuntu-bionic',
                                   'fedora',
                                   'gcc-9',
                                   'gcc-10',
                                   'gcc-11',
                                   'gcc-12',
                                   'gcc-13'],
                        help = 'Base image')
    parser.add_argument('-o', '--output',
                        help = 'Output .sif file')
    parser.add_argument('--no-bliss', action = 'store_true')
    parser.add_argument('--no-cudd', action = 'store_true')
    parser.add_argument('--no-sqlite', action = 'store_true')
    parser.add_argument('--highs', action = 'store_true')
    parser.add_argument('--clingo', action = 'store_true')
    parser.add_argument('--cplex',
                        help = 'Path to IBM studio installer')
    parser.add_argument('--cplex-api',
                        help = 'Path to cplex include dir')
    parser.add_argument('--gurobi', action = 'store_true')
    parser.add_argument('--minizinc', action = 'store_true')
    parser.add_argument('--git', help = 'tag/branch/sha')
    parser.add_argument('--git-dev', help = 'tag/branch/sha')
    parser.add_argument('--clang', action = 'store_true')
    parser.add_argument('--clang-ver')
    parser.add_argument('--werror', action = 'store_true')
    parser.add_argument('--run-all-tests', action = 'store_true')
    parser.add_argument('--test-conf', default = '-a -A -p6 -m600')
    parser.add_argument('--test-rule', default = 'check')

    args = parser.parse_args()

    setup = ''
    post = postBuild(args)
    files = []
    config = []

    suff = args.image

    if args.run_all_tests is True and args.git_dev is None:
        print('Error: --run-all-tests must be combined with --git-dev')
        return -1
    if args.git is not None and args.git_dev is not None:
        print('Error: --git and --git-dev cannot be used together.')
        return -1
    if args.minizinc is True and args.image in ['alpine', 'photon']:
        print(f'Error: --minizinc does not work in {args.image}')
        return -1
    if args.clang_ver is not None \
       and not args.image.startswith('debian') \
       and not args.image.startswith('ubuntu') \
       and not args.image.startswith('gcc'):
        print(f'Error: --clang-ver does not work with {args.image}')
        return -1

    if args.no_cudd is True:
        suff += '-nocudd'
    if args.no_bliss is True:
        suff += '-nobliss'
    if args.no_sqlite is True:
        suff += '-nosqlite'
    else:
        config += ['USE_SQLITE = yes']

    if args.cplex is not None:
        suff += '-cplex'
        setup += setupCplex(args.cplex)
        post += postCplex()
        config += configCplex()

    if args.cplex_api is not None:
        suff += '-cplexapi'
        setup += setupCplexApi(args.cplex_api)
        config += configCplexApi()

    if args.minizinc is True:
        suff += '-mzn'
        setup += setupMinizinc()
        post += postMinizinc()
        files += filesMinizinc()
        config += configMinizinc()

    if args.highs is True:
        suff += '-highs'
        setup += setupHighs()
        post += postHighs()
        config += configHighs()

    if args.clingo is True:
        suff += '-clingo'
        setup += setupClingo()
        post += postClingo()
        files += filesClingo()
        config += configClingo()

    if args.git is not None:
        setup += setupGit(args.git)

    elif args.git_dev is not None:
        setup += setupGitDev(args.git_dev)
        if args.run_all_tests:
            setup += setupRunAllTests()

    else:
        setup += setupDisk()

    if args.clang_ver is not None:
        suff += '-clang' + args.clang_ver
        setup += setupClangVer()
        post += postClangVer(args)
        config += [f'CC = clang-{args.clang_ver}',
                   f'CXX = clang++-{args.clang_ver}']

    if args.clang is True:
        suff += '-clang'
        config += ['CC = clang', 'CXX = clang++']

    if args.werror:
        suff += '-werror'
        config += ['WERROR = yes']


    post += postMake(args, config)
    files += ['/pddl']
    files = '\n'.join(files)
    post_run = postRun(args)

    base_image = baseImage(args.image)
    recipe = f'''
Bootstrap: docker
From: {base_image}
Stage: build

%setup
{setup.strip()}

%post
{post.strip()}

Bootstrap: docker
From: {base_image}
Stage: run

%files from build
{files.strip()}

%post
{post_run.strip()}

%runscript
/pddl "$@"

%labels
Name    cpddl
Authors Daniel Fiser <danfis@danfis.cz>
License BSD
'''
    recipe_fn = 'Apptainer-' + suff
    with open(recipe_fn, 'w') as fout:
        fout.write(recipe.strip())

    output = 'cpddl-' + suff + '.sif'
    if args.output is not None:
        output = args.output

    cmd = ['sudo', '--preserve-env=SSH_AUTH_SOCK', 'apptainer', 'build',
           output, recipe_fn]
    return os.system(' '.join(cmd))


if __name__ == '__main__':
    sys.exit(main())
