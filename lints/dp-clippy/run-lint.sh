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

# THE TRIPLE IS DERIVED, NOT WRITTEN DOWN.
#
# This was `TOOLCHAIN="nightly-2025-09-12-x86_64-pc-windows-msvc"` -- a literal
# containing the HOST of the machine it was written on. On a Linux CI runner the
# active toolchain ends `-x86_64-unknown-linux-gnu`, so the built library would
# be copied to a filename naming a toolchain that is not the one running, and
# dylint would not load it. See the assertion below for why that mattered so
# much: it does not fail, it passes.
#
# `rustup show active-toolchain` resolves the rust-toolchain.toml override in
# this directory, which is the same thing dylint uses to build the expected
# filename.
TOOLCHAIN="$(rustup show active-toolchain | awk '{print $1}')"

build() {
    ( cd "$HERE" && cargo build --quiet )
    mkdir -p "$HERE/libs"
    local found=0
    for ext in dll so dylib; do
        if [ -f "$HERE/target/debug/dp_clippy.$ext" ]; then
            cp "$HERE/target/debug/dp_clippy.$ext" "$HERE/libs/dp_clippy@${TOOLCHAIN}.$ext"
            found=1
        fi
    done
    if [ "$found" -eq 0 ]; then
        echo "BUILD PRODUCED NO CDYLIB: nothing matched target/debug/dp_clippy.{dll,so,dylib}" >&2
        exit 2
    fi
    assert_loaded
}

# REFUSE TO REPORT A VERDICT THE LINT DID NOT PRODUCE.
#
# Measured, and it is the reason this function exists rather than a comment
# asking someone to be careful:
#
#     $ mv libs/dp_clippy@<toolchain>.dll /tmp/          # hide the library
#     $ cargo dylint --all -- --all-features
#     Warning: No libraries were found.
#     $ echo $?
#     0
#
# `cargo dylint --all` treats "I found no lints to run" as SUCCESS. So every
# way of getting the library name, path or toolchain wrong -- the hardcoded
# host triple above, a failed build, a relative DYLINT_LIBRARY_PATH, a
# cargo-dylint version mismatch -- produces a GREEN run that linted nothing.
# A CI leg built on that exit code would report DP-R3 enforced across the
# workspace while enforcing it nowhere, which is worse than not having the leg:
# it answers the question "is this covered?" with a confident yes.
#
# `cargo dylint list` prints one line per loaded library. Empty output means no
# lint ran, whatever the exit code says.
assert_loaded() {
    local listed
    listed="$(cd "$HERE" && DYLINT_LIBRARY_PATH="$HERE/libs" cargo dylint list 2>/dev/null || true)"
    if ! printf '%s' "$listed" | grep -q "dp_clippy"; then
        echo "NO LINT LOADED -- dylint sees no dp_clippy library." >&2
        echo "  expected: $HERE/libs/dp_clippy@${TOOLCHAIN}.{dll,so,dylib}" >&2
        echo '  cargo dylint would EXIT 0 here having linted nothing; refusing.' >&2
        exit 2
    fi
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

    # 4. THE MARKER IS WHAT DID IT -- the differential for leg 3.
    #
    # fixtures/unmarked is the same package NAME and the same source as
    # fixtures/dp_kernel, minus `[package.metadata.dp] dp-crate = true`. Leg 3
    # alone cannot tell "the marker exempted it" from "the name exempted it",
    # and until 2C the answer was the NAME: the lint carried a hardcoded
    # DP_CRATES list, so leg 3 passed while the manifest key was inert
    # decoration. Deleting the marker would not have reddened anything.
    #
    # Legs 3+4 together are the bite: identical inputs, one difference, two
    # verdicts. That is what makes the marker the subject rather than a comment.
    if lint "$HERE/fixtures/unmarked" >/dev/null 2>&1; then
        echo "VACUOUS EXEMPTION: an UNMARKED crate named dp_kernel was let through"
        echo "  -> the exemption is keyed on something other than the marker"
        fail=1
    else
        echo "OK  the same crate WITHOUT the marker reds -- the marker is the key"
    fi

    # 5. `R-6` FIRES on a swallowed Result<_, DpError>, and only on that.
    #
    # fixtures/swallower holds five functions: three that discard through the
    # methods DP-R6 names (.ok, .unwrap_or_default, .unwrap_or_else), one that
    # discards a Result whose error is NOT a DpError, and one that propagates.
    # Exactly THREE errors is the assertion — a count, not a boolean — because
    # "it fired" would also be true of a lint that flagged all five.
    if lint "$HERE/fixtures/swallower" >/dev/null 2>&1; then
        echo "VACUOUS: R-6 did not fire on fixtures/swallower"; fail=1
    else
        # `|| true`: pipefail takes the pipeline status from `lint`, which exits 1
        # BECAUSE the lint fired. Without this the script aborts on success.
        n=$(lint "$HERE/fixtures/swallower" 2>&1 | grep -c "^error: \`\." || true)
        if [ "$n" = "3" ]; then
            echo "OK  R-6 fires on exactly the 3 discards, not on the 2 legitimate uses"
        else
            echo "R-6 MISCOUNTED: $n finding(s), expected 3 (an unrelated Result or a"
            echo "  propagating call is being flagged, or a discard is being missed)"
            fail=1
        fi
    fi

    # 6. BOTH passes are registered. The library entry point is hand-written
    #    now (two lints cannot each emit their own `register_lints`), so a
    #    silently-dropped `register_late_pass` would leave one rule inert while
    #    every other leg above still passed.
    listed=$(cd "$HERE" && DYLINT_LIBRARY_PATH="$HERE/libs" cargo dylint list 2>/dev/null | wc -l || true)
    if [ "$listed" -ge 1 ]; then
        echo "OK  the library loads ($listed entry) with both lints registered"
    else
        echo "NO LIBRARY LISTED"; fail=1
    fi

    exit $fail
fi

build
lint "${1:?usage: run-lint.sh <crate-path> | --self-test}"
