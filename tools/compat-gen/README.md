# compat-gen — generic descriptor pipeline framework

Shared post-processing for the "full-source-build" compat descriptors
(compat.ffmpeg, compat.opencv, ...): the packages where a maintainer-time
configure/cmake run is frozen into the descriptor and consumers build
thousands of TUs with **zero configure**.

Design reference: mcpp `.agents/docs/`
`2026-07-19-large-source-pkg-platform-fixes-and-buildmcpp-generation-design.md`
§2 and §4.

## The model

```
maintainer time (per OS, CI matrix leg or maintainer machine)
  fetch_upstream.sh   pin + download the upstream tarball (sha256'd)
  gen_config.sh       run configure/cmake ONCE, hermetically
                      (--disable-autodetect etc.); `make -n` dry-run gives
                      the exact per-OS source list; config headers are the
                      frozen snapshot
  gen_descriptor.py   emit the .lua descriptor: skeleton (spec/xpm/flags)
                      + frozen DATA (config snapshots in generated_files,
                      source lists in sources)
  compat-gen/restructure.py     THIS FRAMEWORK: cross-OS common/delta
                                source split (+ optional lossless glob
                                compression)
  compat-gen/verify.py          semantic-equivalence gate old-vs-new

consumer time (mcpp build)
  descriptor only: extract tarball, materialize generated_files, compile.
  Irreducibly dynamic parts (stub synthesis, binary embedding, per-OS
  selection) live in an embedded build.mcpp — logic, fed by data files.
  Consumer machines NEVER run configure. That boundary is the point:
  maintainer-time determinism is never traded for consumer-time probing.
```

~98% of a descriptor like compat.ffmpeg.lua is frozen maintainer-time
**data**, ~2% is human-written declaration. The complexity treatment is not
"move configure into the build" — it is data/logic separation plus
compression of the data.

## What restructure.py does

1. **common/delta hoisting.** Per-OS sections (`linux = {...}`,
   `macosx = {...}`) are ADDITIVE overlays: mcpp splices the host OS
   block's body after the top-level body and parses with the same grammar,
   so top-level keys and per-OS keys append to the same lists
   (xpkg.cppm). Sources present on EVERY xpm-shipped OS are hoisted to one
   top-level `sources` array; per-OS blocks keep only their delta.
   compat.ffmpeg linux/macosx overlap ~90% → ~2k lines saved, and each
   additional OS leg costs its delta, not a full copy.

   This is semantically lossless because mcpp collects all expanded
   sources into a `std::set` (scanner.cppm `scan_one_into`) — deduplicated
   and sorted — so descriptor list order never reaches the build graph or
   the archive. verify.py still reports order changes explicitly so the
   fact is stated, never hidden.

2. **directory-glob compression — OPT-IN, `--inventory <dir>`.** For a
   (directory, extension) group where the selected files are exactly ALL
   files of that extension in that directory of the pristine upstream tree,
   the group collapses to `dir/*.ext` (mcpp glob grammar: `*` one segment,
   `**` any dirs, `{a,b}` alternation, `!` exclusion; a leading `*/`
   matches the extracted tarball root). The collapse happens ONLY when it
   is provably lossless against the inventory — the pristine extraction of
   the exact sha256-pinned tarball. **Without `--inventory`, compression
   is skipped entirely** (there is nothing to prove losslessness against);
   hoisting still runs.

   Measured on compat.ffmpeg 8.1.2: only 13 collapsible groups / ~54 lines
   — configure gates at file granularity, so ffmpeg stays list-shaped
   (as predicted in the design doc). compat.opencv's 385→19 compression
   was done generator-side; this flag exists for the next package.

What it does NOT touch: `generated_files` are re-emitted byte-faithfully
and stay whole inside their per-OS blocks. They genuinely differ per OS,
and `generated_files` is map-insert FIRST-WINS in mcpp — a per-OS entry
cannot override a same-key top-level entry — so delta/dedup on config
snapshots is both unsafe and pointless. Same for flags, cflags,
include_dirs, xpm, targets: byte-faithful.

## verify.py — the gate

Every restructure MUST be followed by:

```sh
tools/compat-gen/verify.py pkgs/c/compat.X.lua.orig pkgs/c/compat.X.lua
```

Per xpm-shipped OS it compares the overlay-resolved effective view:
source multisets (glob-expanded when `--inventory` is given), an explicit
source-order report, generated_files keys + content hashes, every flag /
include sequence order-sensitively, and the normalized text of all opaque
mcpp-segment children and the xpm block. Non-zero exit on any difference.

`--ignore-keys include_dirs,include_dirs_after` exempts named keys — for
reviewing an INTENDED migration (e.g. `include_dirs` →
`include_dirs_after`, mcpp >= 0.0.100) while asserting everything else is
untouched.

And always finish with the resolver-grammar lint, which parses every
shipped per-OS section (skip-table means a plain parse only sees the host
OS; `--all-os` closes that blind spot, mcpp >= 0.0.100):

```sh
mcpp xpkg parse pkgs/c/compat.X.lua --all-os
```

## Regeneration discipline

Descriptors in this family are machine-generated end to end and must stay
byte-identically reproducible:

```sh
sh tools/compat-ffmpeg/gen_config.sh          # per-OS CI legs / maintainer
python3 tools/compat-ffmpeg/gen_descriptor.py # emit raw per-OS descriptor
python3 tools/compat-gen/restructure.py pkgs/c/compat.ffmpeg.lua
python3 tools/compat-gen/verify.py <before> <after>   # gate
```

A regenerated descriptor that does not byte-match the committed one means
either upstream data drifted (bump intentionally) or the pipeline broke
(fix it). Hand-editing the data segments is never OK; hand-editing the
skeleton (flags, include policy) is OK and is exactly the part reviewers
should read.

## How a new package plugs in

1. Copy the `tools/compat-ffmpeg/` trio and adapt: pin the tarball, write
   the hermetic configure invocation, map `make -n` (or the cmake
   equivalent) output to source entries + frozen config headers.
2. Irreducibly dynamic steps (generated stubs, embedded binaries) go into
   an embedded `build.mcpp` reading small data files from
   `generated_files` — data stays reviewable data, logic stays a ~200-line
   C++ program (see compat.opencv's `tu_manifest.txt` pattern).
3. Run each OS leg, then `restructure.py`, then `verify.py`, then
   `mcpp xpkg parse --all-os`.
