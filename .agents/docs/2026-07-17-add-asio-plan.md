# Add standalone Asio 1.38.1 as a header-only package

Date: 2026-07-17

This document defines the contribution scope for `compat.asio@1.38.1`. It is
based on the current `origin/main`, its active validation workflow, and mcpp
0.0.94. Dated repository guidance is treated as historical when it conflicts
with those live contracts.

## 1. Scope

This contribution adds only the upstream standalone, header-only Asio package.
Consumers use `#include <asio.hpp>` and related upstream headers.

The following work is intentionally excluded:

- a native C++ module or `import asio;` interface;
- OpenSSL or wolfSSL integration;
- Boost.Context, Boost.Regex, or Boost.Date_Time integration;
- liburing integration;
- changes to repository contribution guidance or README content.

Native module adaptation remains separate because it has a different build and
consumer contract and requires its own compatibility evidence.

## 2. Upstream identity and archive evidence

- Canonical repository: `https://github.com/chriskohlhoff/asio`.
- Release tag: `asio-1-38-1`, the latest numeric Asio tag observed on
  2026-07-17.
- Tag commit: `bbecff21a23b97c34641f0f1f08b28c91b9c77cf`.
- License: Boost Software License 1.0 (`BSL-1.0`), confirmed from upstream
  `COPYING` and `LICENSE_1_0.txt` at the tag.
- Linux/macOS archive: tag tarball, SHA-256
  `2827b229972be80cdb14e5497962fa393d1adf036b5869e2b9c99f644daadacc`,
  CN-mirrored byte-identically at
  `https://gitcode.com/mcpp-res/asio/releases/download/1.38.1/asio-1.38.1.tar.gz`.
- Windows archive: `asio-1.38.1-nosymlinks.tar.gz`, SHA-256
  `77f74094bb12cd867a6edbf5736bbed816c6ce0906e880de8573097a81714d89`, hosted at
  `https://github.com/xlings-res/asio/releases/download/1.38.1/` (GLOBAL) and
  `https://gitcode.com/mcpp-res/asio/releases/download/1.38.1/` (CN).

Two independent downloads of the upstream tarball produced the same SHA-256.
All archives are wrapped in `asio-asio-1-38-1/`, and their public entry header
is `asio-asio-1-38-1/include/asio.hpp`. Therefore `*/include` is the required
consumer include root.

Both upstream tag archive encodings (tar.gz and zip) contain
`asio/include -> ../include` and `asio/src -> ../src` POSIX symlink entries.
The Windows extraction path (`tar.exe` via xlings) cannot materialize them, so
both encodings fail on the Windows runner, and upstream publishes no
symlink-free asset for 1.38.x (GitHub has no release assets; SourceForge stops
at 1.36.0). The Windows entry therefore uses a repackaged variant of the
upstream tag tarball with only those two symlink entries removed
(`tar --delete` + `gzip -n -9`); all 1544 regular files are byte-identical to
upstream. Provenance is documented in the `xlings-res/asio` repository README.

The upstream tag is annotated but not cryptographically signed. Reproducibility
is enforced by the descriptor's pinned archive digest.

## 3. Package shape and descriptor contract

Asio is a third-party project without an mcpp manifest in the selected release,
so the package uses an inline Form B descriptor at
`pkgs/c/compat.asio.lua`:

- namespace: `compat`;
- full package name: `compat.asio`;
- published version: bare version `1.38.1`;
- platforms: Linux and macOS use the tag tarball; Windows uses the repackaged
  symlink-free tarball to avoid the POSIX symlink extraction failure;
- include root: `*/include`;
- build target: a generated C anchor provides the buildable library target
  required by the current package resolver;
- Linux link interface: `-pthread`;
- `import_std = false` because this package is consumed through textual headers.

The intended post-publication CLI token is `compat:asio@1.38.1`, which maps to
the consumer declaration `[dependencies.compat] asio = "1.38.1"`. Before the
replacement PR is opened, that token must be exercised with the current mcpp
CLI in an isolated project rather than inferred only from the descriptor name.

The default `standalone` feature contributes these public preprocessor defines:

- `ASIO_STANDALONE`;
- `ASIO_HEADER_ONLY`;
- `ASIO_DISABLE_BOOST_CONTEXT_FIBER`;
- `ASIO_HAS_THREADS` — asio's own thread detection keys off CRT macros
  (`_MT`/`_REENTRANT`/`_POSIX_THREADS`) that the workspace's llvm-on-Windows
  toolchain does not define. Without the pin asio silently selects
  `null_thread` and every internal-thread operation (notably the
  waitable-timer wait thread behind `steady_timer`) throws
  `operation_not_supported` (10045) at runtime — observed as the core,
  coroutine, and network consumer tests failing on the Windows runner while
  the thread-free tests passed. asio only ever tests
  `defined(ASIO_HAS_THREADS)`, and the POSIX pthread selection still runs
  beneath it, so the pin is a no-op on platforms where detection already
  works (re-verified by the Linux consumer suite).

mcpp 0.0.94 accepts feature `defines` in the current xpkg parser and propagates
them to consumers. The Asio surface test rejects builds where any of these
defines is absent, and generated compile commands are inspected during local
verification to confirm that the flags reach every consumer translation unit.

The descriptor uses grammar already accepted by the live index contract. This
contribution does not change `index.toml` (`min_mcpp = "0.0.87"`) or the active
workflow pin (`MCPP_VERSION = "0.0.94"`).

## 4. URL and mirror decision

Linux/macOS keep the canonical upstream GitHub tarball as GLOBAL; a
byte-identical copy of that tarball is uploaded to
`gitcode.com/mcpp-res/asio` as the CN mirror (same SHA-256, verified after
upload).

Windows cannot use either upstream tag archive encoding (both carry the POSIX
symlinks), so its GLOBAL asset is the repackaged symlink-free tarball hosted
in the ecosystem's resource org `github.com/xlings-res/asio`, with a
byte-identical CN copy on `gitcode.com/mcpp-res/asio`. Both hosts were
sha256-verified after upload against the descriptor's pinned digest.

## 5. Consumer and test design

The consumer project is `tests/examples/asio`, registered in the root workspace
and resolved through the local `compat` index. The current repository workflow
uses `mcpp test --workspace`, so the example follows the active `tests/*.cpp`
layout instead of the historical `src/main.cpp` runner layout.

Six executable tests provide failure-capable assertions:

- `core`: timers, executor work, dispatch, defer, and post behavior;
- `coroutine`: `co_spawn`, `use_awaitable`, and completion behavior;
- `experimental`: experimental channel send/receive behavior;
- `network`: loopback TCP accept/connect/read/write behavior;
- `platform`: platform-specific public types guarded by target macros;
- `surface`: representative public headers, public types, and required package
  defines.

The tests do not include or exercise the separate native module adapter.

## 6. Validation contract

The active workflow pins mcpp 0.0.94. Before opening the replacement PR, the
branch must provide fresh evidence for all locally available checks:

1. run the descriptor syntax and mirror lint with the available local Lua 5.5;
2. parse `pkgs/c/compat.asio.lua` with mcpp 0.0.94;
3. run the targeted Asio consumer tests from isolated build state with
   `MCPP_INDEX_MIRROR=GLOBAL`;
4. inspect the generated compile commands for all three public defines;
5. exercise `mcpp add compat:asio@1.38.1` in an isolated consumer project;
6. run `git diff --check` and confirm README is identical to `origin/main`.

The replacement PR must then pass every check instantiated by the live
workflow, including the Linux, macOS, and Windows workspace matrix. Local macOS
success is not evidence for the other declared platforms.

## 7. Documentation and change boundary

README remains byte-identical to `origin/main`. This package contribution does
not update historical contribution instructions, even where they describe old
CI job names or old feature limitations. Any correction to those documents
requires a separate, evidence-backed audit and a separately scoped change.

The replacement PR is limited to:

- this design record;
- `pkgs/c/compat.asio.lua`;
- the root workspace registration;
- `tests/examples/asio` consumer configuration and tests.

## 8. Acceptance criteria

- upstream version, license, layout, and repeated archive digest are recorded;
- local descriptor lint passes with Lua 5.5, and the workflow's Lua 5.4 lint
  passes in GitHub Actions;
- the CLI dependency token is verified through an isolated `mcpp add`;
- the six targeted consumer tests pass from isolated build state;
- the Windows workspace job downloads the ZIP and completes the Asio tests;
- README has no diff;
- the replacement PR contains no native module adaptation;
- all required GitHub Actions jobs pass before maintainer merge;
- publication remains the repository's automatic post-merge responsibility.
