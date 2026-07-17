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
  `2827b229972be80cdb14e5497962fa393d1adf036b5869e2b9c99f644daadacc`.
- Windows archive: the same tag's ZIP encoding, SHA-256
  `c4557a5a07ff8aa9c37bd141b7d1a6ba2b1bad5557d97762ad27aaf0091c665b`.

Two independent downloads of each archive encoding produced the same
platform-specific SHA-256. Both archives are wrapped in
`asio-asio-1-38-1/`, and their public entry header is
`asio-asio-1-38-1/include/asio.hpp`. Therefore `*/include` is the required
consumer include root.

The tag tarball also contains `asio/include -> ../include` and
`asio/src -> ../src` POSIX symlinks. The Windows xlings extraction path exited
with code 127 immediately after downloading that tarball. The Windows entry
therefore uses GitHub's ZIP encoding of the same tagged commit, following the
repository's existing platform-specific archive pattern.

The upstream tag is annotated but not cryptographically signed. Reproducibility
is enforced by the descriptor's pinned archive digest.

## 3. Package shape and descriptor contract

Asio is a third-party project without an mcpp manifest in the selected release,
so the package uses an inline Form B descriptor at
`pkgs/c/compat.asio.lua`:

- namespace: `compat`;
- full package name: `compat.asio`;
- published version: bare version `1.38.1`;
- platforms: Linux and macOS use the tag tarball; Windows uses the tag ZIP to
  avoid the tarball's POSIX symlink extraction failure;
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
- `ASIO_DISABLE_BOOST_CONTEXT_FIBER`.

mcpp 0.0.94 accepts feature `defines` in the current xpkg parser and propagates
them to consumers. The Asio surface test rejects builds where any of these
defines is absent, and generated compile commands are inspected during local
verification to confirm that the flags reach every consumer translation unit.

The descriptor uses grammar already accepted by the live index contract. This
contribution does not change `index.toml` (`min_mcpp = "0.0.87"`) or the active
workflow pin (`MCPP_VERSION = "0.0.94"`).

## 4. URL and mirror decision

No authorized, byte-identical `mcpp-res` CN asset is available for this
contribution. The descriptor therefore uses the plain canonical upstream URL,
which is the current repository's supported fallback. It does not fabricate a
CN entry or alias the upstream URL as a CN mirror.

A maintainer may add a legitimate CN mirror later by uploading the exact same
bytes for each platform archive and retaining its pinned SHA-256.

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
