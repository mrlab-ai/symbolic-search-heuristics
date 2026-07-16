# Developer's Guide

[[_TOC_]]

## Creating a New Release

1. Make sure you are in the `release-X.Y` branch.

1. Merge the `master` branch so that we can just fast-forward on the master
branch later.

1. Set version number as the environment variable.
    ```sh
    export VER="X.Y"
    ```

1. Run complete tests
    - Re-compile with CUDD, SQLite and CPLEX and run:
        ```sh
        make check-all
        make check-bin-all
        ```

1. Run complete build tests
    ```sh
    ./t/scripts/test-build-apptainer.sh --git-dev release-${VER}
    ./t/scripts/test-build-apptainer.sh --git-dev release-${VER} --cplex /opt/cplex/cplex_studio2211.linux_x86_64.bin
    ```

1. Run complete automatic tests with different build configurations
    ```sh
    ./t/scripts/build-and-check-apptainer.sh --git-dev release-${VER}
    ```

1. Update `CHANGELOG.md` and `pddl/version.h`:
    - Change `Unreleased` to the new version and created a new `Unreleased` section.
    - Update `pddl/version.h`
    - Commit the changes with commit message "Version ${VER}"
        ```sh
        git add CHANGELOG.md pddl/version.h && git commit -m "Version ${VER}"
        git push
        ```

1. Add tag
    ```sh
    git tag -a v${VER} -m "Version ${VER}"
    git push origin v${VER}
    ```

1. Build Apptainer images:
    ```sh
    ./scripts/build-apptainer.py --no-bliss --no-cudd --git-dev v${VER} \
                                 -o cpddl-barebone-${VER}.sif alpine
    ./scripts/build-apptainer.py --cplex-api /opt/cplex/v22.1.1/cplex/include \
                                 --highs --clingo --minizinc \
                                 --git-dev v${VER} -o cpddl-${VER}.sif debian-bookworm

    apptainer push cpddl-barebone-${VER}.sif oras://registry.gitlab.com/danfis/cpddl:barebone-v${VER}
    apptainer push cpddl-${VER}.sif oras://registry.gitlab.com/danfis/cpddl:v${VER}

    apptainer push cpddl-barebone-${VER}.sif oras://registry.gitlab.com/danfis/cpddl:barebone-latest
    apptainer push cpddl-${VER}.sif oras://registry.gitlab.com/danfis/cpddl:latest
    ```

1. Switch to the `master` branch and merge
    ```sh
    git switch master
    git merge --ff-only release-${VER}
    git push
    ```

1. Push to the public repo
    ```sh
    git push public master
    git push public v${VER}
    ```

1. Create a new release on the cpddl gitlab page: [releases](https://gitlab.com/danfis/cpddl/-/releases)
