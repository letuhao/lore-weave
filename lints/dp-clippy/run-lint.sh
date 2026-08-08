#!/usr/bin/env bash
# Build dp-clippy and run it over a crate. The ONLY supported entry point --
# `cargo dylint` needs the library named `<lib>@<toolchain>` on
# DYLINT_LIBRARY_PATH, which is not obvious and is easy to get subtly wrong.
#
#   ./run-lint.sh <path-to-crate>        # lint one crate
#   ./run-lint.sh --self-test            # prove the lint fires, exempts, and stays quiet
#
# TOOLCHAIN MATCHING IS THE WHOLE DIFFICULTY. Recorded because it cost real
# time: `cargo-dylint`'s version must match the `dylint_linting` the lint links.
# 3.1.2 against dylint_linting 3.5.1 fails with
# `could not find RunCompiler in rustc_driver` -- the driver compiled against a
# nightly whose API had moved. Install the matching driver:
#     cargo +nightly install cargo-dylint --version 3.5.1 --locked
# and the nightly + rustc-dev this crate's rust-toolchain.toml pins.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLCHAIN="nightly-2025-09-12-x86_64-pc-windows-msvc"

build() {
    ( cd "$HERE" && cargo build --quiet )
    mkdir -p "$HERE/libs"
    for ext in dll so dylib; do
        if [ -f "$HERE/target/debug/dp_clippy.$ext" ]; then
            cp "$HERE/target/debug/dp_clippy.$ext" "$HERE/libs/dp_clippy@${TOOLCHAIN}.$ext"
        fi
    done
}

# --all-features IS LOAD-BEARING, not thoroughness theatre.
#
# `crates/meta-rs` declares `#[cfg(feature = "sqlx-pg")] pub mod sqlx_pg;` and
# that module holds `use sqlx::postgres::PgPool`. A default-feature run compiles
# neither, so the lint reported meta-rs CLEAN while it held a raw client --
# default-uncovered (`NV-3`) at the feature level rather than the directory
# level. Measured: default features exit 0, `--features sqlx-pg` reds.
#
# Any CI leg that runs this without --all-features is reporting coverage it does
# not have.
lint() {
    ( cd "$1" && DYLINT_LIBRARY_PATH="$HERE/libs" cargo dylint --all -- --all-features )
}

if [ "${1:-}" = "--self-test" ]; then
    build
    fail=0

    # 1. It FIRES on a violation. A lint that never fires is not a lint.
    if lint "$HERE/fixtures/violator" >/dev/null 2>&1; then
        echo "VACUOUS: the lint did not fire on fixtures/violator"; fail=1
    else
        echo "OK  fires on a raw sqlx::PgPool import"
    fi

    # 2. It stays QUIET on clean code. Otherwise it is noise, not a rule.
    if lint "$HERE/fixtures/clean" >/dev/null 2>&1; then
        echo "OK  silent on a crate with no kernel client"
    else
        echo "FALSE POSITIVE: the lint fired on fixtures/clean"; fail=1
    fi

    # 3. It EXEMPTS the data plane (2F-2). DP-R3's literal wording would fire on
    #    dp-kernel, which is where the database code is supposed to live.
    if lint "$HERE/fixtures/dp_kernel" >/dev/null 2>&1; then
        echo "OK  exempts a dp-crate that legitimately holds a client"
    else
        echo "OVER-BROAD: the lint fired on the data plane itself"; fail=1
    fi

    exit $fail
fi

build
lint "${1:?usage: run-lint.sh <crate-path> | --self-test}"
