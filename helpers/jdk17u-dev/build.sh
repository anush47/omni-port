#!/usr/bin/env bash
# Runs INSIDE the Docker container — builds jdk17u-dev.
set -euo pipefail

echo "=== Building JDK for ${COMMIT_SHA:0:7} (Inside Container) ==="
echo "Using Boot JDK: ${BOOT_JDK}"
echo "Using jtreg: ${JTREG_HOME}"

# When WORKTREE_MODE=1 the pipeline has already applied synthesized hunks to the
# mounted directory; skip the destructive checkout so those changes are preserved.
if [ "${WORKTREE_MODE:-0}" != "1" ]; then
    echo "Checking out commit: ${COMMIT_SHA}"
    git checkout -f "${COMMIT_SHA}"
else
    echo "WORKTREE_MODE=1: using pre-applied worktree (HEAD=${COMMIT_SHA})"
fi

export BUILD_DIR_ABS="/repo/build_shared"
echo "--- Shared build dir: ${BUILD_DIR_ABS} ---"

NEED_CONFIGURE=false
if [ ! -f "${BUILD_DIR_ABS}/Makefile" ]; then
    echo "--- No existing Makefile — will configure ---"
    NEED_CONFIGURE=true
    mkdir -p "${BUILD_DIR_ABS}"
fi

cd "${BUILD_DIR_ABS}"

if [ "${NEED_CONFIGURE}" = true ]; then
    echo "--- Configuring build ---"
    bash ../configure \
        --with-boot-jdk="${BOOT_JDK}" \
        --with-jtreg="${JTREG_HOME}" \
        --enable-ccache \
        --disable-warnings-as-errors \
        --with-debug-level=release
else
    echo "--- Skipping configure (incremental build) ---"
fi

echo "--- Running incremental make ---"
make JOBS="${MAKE_JOBS:-$(nproc)}" images COMPILER_WARNINGS_FATAL=false

echo "=== Build OK ==="
