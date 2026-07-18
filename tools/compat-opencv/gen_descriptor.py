#!/usr/bin/env python3
"""gen_descriptor.py — emit pkgs/c/compat.opencv.lua from the reference build.

Inputs: <opencv-src> <cmake-build-dir> <version> <sha256> <out.lua>
The build dir must contain ninja-cmds.log (`ninja -t commands`) and the
completed generator outputs (see gen_config.sh). When the reference build was
configured WITH_FFMPEG=ON (gen_config.sh does this via a local static FFmpeg
prefix), pass its prefix via env FFMPEG_PREFIX so its include dirs can be
translated to the compat.ffmpeg dependency.

Descriptor anatomy (v2, "full source-build + build.mcpp synthesis", mcpp >=
0.0.97):
- xpm: official GitHub tag tarball + gitcode CN mirror, sha256-pinned.
- generated_files: the small frozen config snapshot (cvconfig.h,
  cv_cpu_config.h, dispatch stubs, simd_declarations, 3rdparty configs …),
  plus build.mcpp (consumer-side synthesizer: fonts, OpenCL kernel
  embeddings, and the jpeg12/jpeg16 re-compile stubs) and tu_manifest.txt
  (now only drives the jpeg12/16 stubs).
- sources: REAL tarball paths (mcpp 0.0.97 fixed the obj-path collision
  #233 and spacey defines #234, so the v1 whole-build forwarding-stub layer
  is gone) + the snapshot dispatch-stub .cpp + the NASM .asm units. Only
  the BITS_IN_JSAMPLE=12/16 same-source re-compiles still need stubs (one
  source, three compiles — inexpressible as plain sources), with
  group-prefixed unique basenames (dodges mcpp#239 abs-path obj escape).
- flags: layered per-glob entries over real paths — per-group dirs
  (**/modules/<mod>/**, **/3rdparty/<lib>/**), per-ISA suffixes
  (**/*.avx2.cpp …), per-file extras; verified by exact reconstruction
  against every reference compile command. Spacey defines ride directly
  (#234 fixed).
- deps: compat.ffmpeg when the profile has HAVE_FFMPEG (videoio backend).
"""
import os, re, shlex, sys
from collections import defaultdict
from pathlib import Path

SRC = Path(sys.argv[1]).resolve()
BLD = Path(sys.argv[2]).resolve()
VERSION = sys.argv[3]
SHA256 = sys.argv[4]
OUT = Path(sys.argv[5])
HERE = Path(__file__).resolve().parent
FF_PREFIX = os.environ.get("FFMPEG_PREFIX", "")
FFMPEG_DEP_VERSION = os.environ.get("FFMPEG_DEP_VERSION", "8.1.2")

# ── parse `ninja -t commands` ───────────────────────────────────────────
compiles = []
for line in (BLD / "ninja-cmds.log").read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        toks = shlex.split(line)
    except ValueError:
        continue
    if not toks:
        continue
    tool = Path(toks[0]).name
    if tool not in ("g++", "gcc", "cc", "c++", "clang", "clang++", "nasm"):
        continue
    tool = "nasm" if tool == "nasm" else ("g++" if tool in ("g++", "c++", "clang++") else "gcc")
    src = None; defs = set(); mflags = []; incs = []; std = None
    skip = False
    for i in range(1, len(toks)):
        t = toks[i]
        if skip: skip = False; continue
        if t in ("-o", "-MF", "-MT", "-MQ"): skip = True; continue
        if t == "-MD":
            if tool == "nasm": skip = True
            continue
        if t == "-c" or t == "-isystem": continue
        if t.startswith("-std="): std = t; continue
        if t.startswith("-D"): defs.add(t); continue
        if t.startswith("-I"): incs.append(t[2:].strip('"')); continue
        if t.startswith("-m") or t in ("-O3", "-O2"): mflags.append(t); continue
        if re.search(r"\.(c|cc|cpp|cxx|asm)$", t) and not t.startswith("-"):
            src = t
    if src is None:
        continue
    src_abs = src if src.startswith("/") else str(BLD / src)
    compiles.append((tool, src_abs, frozenset(defs), tuple(mflags), incs, std))
assert compiles, "no compile commands parsed"
print(f"parsed {len(compiles)} compiles")

ISA_RE = re.compile(r"\.(sse4_1|sse4_2|avx512_skx|avx2|avx|fp16)\.cpp$")
MODS = ("core", "imgproc", "imgcodecs", "highgui", "videoio", "flann", "geometry")

have_ffmpeg = any("cap_ffmpeg" in c[1] for c in compiles)
print(f"HAVE_FFMPEG in profile: {have_ffmpeg}")
if have_ffmpeg:
    assert FF_PREFIX, "reference build has cap_ffmpeg TUs but FFMPEG_PREFIX unset"

def dir_key(src_abs, defs):
    s = src_abs
    if "3rdparty/libjpeg-turbo" in s:
        if s.endswith(".asm"): return "jpeg-asm"
        if "-DBITS_IN_JSAMPLE=12" in defs: return "jpeg12"
        if "-DBITS_IN_JSAMPLE=16" in defs: return "jpeg16"
        return "jpeg"
    if "3rdparty/libpng" in s: return "png"
    if "3rdparty/zlib" in s: return "zlib"
    for mod in MODS:
        if f"modules/{mod}/" in s: return mod
    raise SystemExit(f"unclassified source: {s}")

groups = defaultdict(list)
for c in compiles:
    isa = ISA_RE.search(c[1])
    groups[(dir_key(c[1], c[2]), isa.group(1) if isa else None)].append(c)

dir_defs, dir_m, file_extras = {}, {}, {}
for (dk, isa), cs in groups.items():
    if isa: continue
    common = frozenset.intersection(*[c[2] for c in cs])
    dir_defs[dk], dir_m[dk] = common, cs[0][3]
    for c in cs:
        if c[2] - common:
            file_extras[c[1]] = c[2] - common

isa_defs, isa_m = {}, {}
for (dk, isa), cs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
    if not isa: continue
    for c in cs:
        extra = c[2] - dir_defs[dk]
        extram = tuple(f for f in c[3] if f not in dir_m[dk])
        if isa not in isa_defs:
            isa_defs[isa], isa_m[isa] = extra, extram
        else:
            assert isa_defs[isa] == extra and isa_m[isa] == extram, \
                f"ISA overlay mismatch for {isa}: {c[1]}"

# exact reconstruction check
for tool, src_abs, defs, mflags, incs, std in compiles:
    dk = dir_key(src_abs, defs)
    isa = ISA_RE.search(src_abs)
    want = set(dir_defs[dk]) | (set(isa_defs[isa.group(1)]) if isa else set()) \
         | set(file_extras.get(src_abs, ()))
    assert want == set(defs), f"reconstruction failed for {src_abs}: {want ^ set(defs)}"
print("exact flag reconstruction: OK")

# common -m flags across every non-asm group must agree (baseline)
baselines = {dir_m[dk] for dk in dir_defs if dk != "jpeg-asm"}
assert len(baselines) == 1, f"baseline -m flags differ between groups: {baselines}"
baseline_m = [f for f in next(iter(baselines)) if f.startswith("-m")]

# ── group glob table (v2: real paths; jpeg12/16 stay stub dirs) ─────────
# `**/modules/<mod>/**` deliberately matches BOTH the tarball tree
# (*/modules/<mod>/…) and the snapshot dispatch stubs
# (mcpp_generated/modules/<mod>/…) — same group, same flags in the
# reference build (asserted below by reconstruction).
GROUP_GLOB = {
    "jpeg":   "**/3rdparty/libjpeg-turbo/**",
    "png":    "**/3rdparty/libpng/**",
    "zlib":   "**/3rdparty/zlib/**",
    "jpeg12": "**/tu/jpeg12/**",
    "jpeg16": "**/tu/jpeg16/**",
}
for mod in MODS:
    GROUP_GLOB[mod] = f"**/modules/{mod}/**"

# ── sources (real paths) + tu manifest (jpeg12/16 only) ─────────────────
def wrap_rel(src_abs):
    return str(Path(src_abs).relative_to(SRC))

manifest, sources_real, sources_asm, kernel_files, seen = [], [], [], [], set()
per_file_flag_entries = []
for tool, src_abs, defs, mflags, incs, std in compiles:
    dk = dir_key(src_abs, defs)
    if tool == "nasm":
        e = f"*/{wrap_rel(src_abs)}"
        if e not in seen:
            seen.add(e); sources_asm.append(e)
        continue
    if dk in ("jpeg12", "jpeg16"):
        tgt = wrap_rel(src_abs)
        key = (dk, tgt)
        if key not in seen:
            seen.add(key)
            manifest.append(f"{dk}\t{tgt}")
        continue
    if src_abs.startswith(str(SRC)):
        e = f"*/{wrap_rel(src_abs)}"
    elif "opencl_kernels_" in src_abs:
        # synthesized by build.mcpp on the consumer (clsrc/…); flags via
        # per-file globs below, source via mcpp:generated= — skip here
        m = re.search(r"opencl_kernels_(\w+)\.cpp$", src_abs)
        kernel_files.append((m.group(1), dir_key(src_abs, defs)))
        continue
    else:
        # snapshot file compiled from the build dir (dispatch stubs)
        e = f"mcpp_generated/{Path(src_abs).relative_to(BLD)}"
    if e in seen: continue
    seen.add(e); sources_real.append(e)
    if src_abs in file_extras:
        per_file_flag_entries.append((e, file_extras[src_abs]))
n_tus = len(sources_real) + len([l for l in manifest]) + len(kernel_files)
print(f"sources: {len(sources_real)} real C/C++ + {len(sources_asm)} asm; "
      f"jpeg12/16 stubs: {len(manifest)}; kernels: {len(kernel_files)}")

# compress the real-source list: whole-directory globs where the compiled
# set equals every same-extension file in that directory of the tarball
by_dir = defaultdict(list)
for e in sources_real:
    if e.startswith("*/"):
        p = Path(e[2:])
        by_dir[("*", str(p.parent), p.suffix)].append(p.name)
    else:  # mcpp_generated/...
        p = Path(e)
        by_dir[("g", str(p.parent), p.suffix)].append(p.name)
sources_out = []
for (kind, d, suf), names in sorted(by_dir.items()):
    if kind == "*":
        on_disk = sorted(x.name for x in (SRC / d).glob(f"*{suf}"))
        if sorted(names) == on_disk and len(names) > 1:
            sources_out.append(f"*/{d}/*{suf}")
            continue
        base = f"*/{d}"
    else:
        base = d
    if len(names) == 1:
        sources_out.append(f"{base}/{names[0]}")
    else:
        stems = ",".join(sorted(n[: -len(suf)] for n in names))
        sources_out.append(f"{base}/{{{stems}}}{suf}")
print(f"sources compressed: {len(sources_real)} files -> {len(sources_out)} globs")

# ── snapshot files (exclude synthesized classes) ────────────────────────
def rewrite(text):
    out = (text.replace(f'"{SRC}/', '"').replace(f'{SRC}/', '')
               .replace(f'"{BLD}/', '"').replace(f'{BLD}/', ''))
    if FF_PREFIX:
        assert FF_PREFIX not in out, "ffmpeg prefix path leaked into snapshot"
    return out

snapshot = {}
for p in sorted(BLD.rglob("*")):
    if p.is_dir() or "CMakeFiles" in p.parts:
        continue
    if p.name.startswith(("CMake", "cmake_", "CPack", ".ninja", "ninja")):
        continue
    if p.suffix not in (".h", ".hpp", ".inc", ".cpp", ".c", ".asm"):
        continue
    if "builtin_font" in p.name or "opencl_kernels" in p.name:
        continue    # build.mcpp synthesizes these
    rel = p.relative_to(BLD)
    content = rewrite(p.read_text(errors="replace"))
    assert "]==]" not in content, f"lua long-bracket collision in {rel}"
    assert len(content) < 200_000, f"unexpectedly large snapshot file {rel}"
    snapshot[f"mcpp_generated/{rel}"] = content
print(f"snapshot: {len(snapshot)} files, {sum(len(v) for v in snapshot.values())//1024} KiB inline")

build_mcpp_src = (HERE / "build_mcpp_template.cpp").read_text()
assert "]==]" not in build_mcpp_src

# ── include dirs ────────────────────────────────────────────────────────
incdirs, iseen = ["mcpp_generated", "*"], {"mcpp_generated", "*"}
for c in compiles:
    for i in c[4]:
        if FF_PREFIX and i.startswith(FF_PREFIX):
            continue    # served by the compat.ffmpeg dependency's include dirs
        if i.startswith(str(SRC)):
            r = "*/" + str(Path(i).relative_to(SRC)) if i != str(SRC) else "*"
        elif i.startswith(str(BLD)):
            r = "mcpp_generated/" + str(Path(i).relative_to(BLD)) if i != str(BLD) else "mcpp_generated"
        else:
            continue
        if r not in iseen:
            iseen.add(r); incdirs.append(r)

# ── emit lua ────────────────────────────────────────────────────────────
def D(x): return x[2:]
def lua_list(items, ind):
    return ("\n" + ind).join(f'"{i}",' for i in items)

def defines_lua(defset):
    return "defines = { " + ", ".join(f'"{D(f)}"' for f in sorted(defset)) + " }"

flags_entries = []
for dk in sorted(dir_defs):
    if dk == "jpeg-asm": continue
    key = "cflags" if dk in ("zlib", "png", "jpeg", "jpeg12", "jpeg16") else "cxxflags"
    parts = [f'glob = "{GROUP_GLOB[dk]}"']
    if dir_defs[dk]: parts.append(defines_lua(dir_defs[dk]))
    flags_entries.append("{ " + ", ".join(parts) + " },")
if ("jpeg-asm", None) in groups:
    cs = groups[("jpeg-asm", None)]
    common = frozenset.intersection(*[c[2] for c in cs])
    flags_entries.append('{ glob = "**/*.asm", ' + defines_lua(common) + " },")
for isa in sorted(isa_defs):
    ds = ", ".join(f'"{D(f)}"' for f in sorted(isa_defs[isa]))
    ms = ", ".join(f'"{m}"' for m in isa_m[isa])
    flags_entries.append(
        f'{{ glob = "**/*.{isa}.cpp", defines = {{ {ds} }}, cxxflags = {{ {ms} }} }},')
for mod, dk in sorted(kernel_files):
    flags_entries.append(
        f'{{ glob = "**/clsrc/opencl_kernels_{mod}.cpp", ' + defines_lua(dir_defs[dk]) + " },")
for g, extra in sorted(per_file_flag_entries):
    flags_entries.append(f'{{ glob = "{g}", ' + defines_lua(extra) + " },")

# upstream reference uses -std=c++17; the index floor is c++23 and the whole
# TU set builds green under gcc16 -std=c++23 (validated by the O0 spike).
cxx_std = {c[5] for c in compiles if c[0] == "g++" and c[5]}
assert cxx_std == {"-std=c++17"}, f"unexpected upstream C++ std set: {cxx_std}"

deps_line = ""
profile_note = "V4L2 videoio"
if have_ffmpeg:
    deps_line = f'        deps = {{ ["compat.ffmpeg"] = "{FFMPEG_DEP_VERSION}" }},\n'
    profile_note = "V4L2 + FFmpeg videoio (compat.ffmpeg dependency)"

L = []
L.append(f"""-- Auto-generated by tools/compat-opencv/gen_descriptor.py — do not edit by hand.
-- Recipe: OpenCV {VERSION} built FROM SOURCE by mcpp (no CMake at build
-- time). Scope: core imgproc imgcodecs highgui videoio (+ flann, geometry
-- dependency closure); hermetic profile (all external probes OFF, vendored
-- zlib/libpng/libjpeg-turbo incl. NASM SIMD units, headless highgui,
-- {profile_note}, WITH_UNIFONT=OFF); SIMD runtime
-- dispatch KEPT (per-ISA glob flags). Sources are the real tarball paths
-- (mcpp >= 0.0.97: obj-path disambiguation #233 + quoted spacey defines
-- #234 made the v1 forwarding-stub layer obsolete); only the libjpeg-turbo
-- BITS_IN_JSAMPLE=12/16 re-compiles and the build-time generators (fonts,
-- OpenCL kernel embeddings) are synthesized on the consumer by the embedded
-- build.mcpp — byte-faithful ports verified against the reference CMake
-- build. Regenerate: sh tools/compat-opencv/gen_config.sh (this repo).
package = {{
    spec        = "1",
    namespace   = "compat",
    name        = "compat.opencv",
    description = "OpenCV {VERSION} (core/imgproc/imgcodecs/highgui/videoio incl. FFmpeg backend), full source build with SIMD dispatch",
    licenses    = {{"Apache-2.0"}},
    repo        = "https://github.com/opencv/opencv",
    type        = "package",

    xpm = {{
        -- linux-x86_64 only for now: the config snapshot is target-specific.
        linux = {{
            ["{VERSION}"] = {{
                url    = {{
                    GLOBAL = "https://github.com/opencv/opencv/archive/refs/tags/{VERSION}.tar.gz",
                    CN     = "https://gitcode.com/mcpp-res/opencv/releases/download/{VERSION}/opencv-{VERSION}.tar.gz",
                }},
                sha256 = "{SHA256}",
            }},
        }},
    }},

    mcpp = {{
        language     = "c++23",  -- upstream min c++17; c++23 spike-validated (457 TU green)
{deps_line}        include_dirs = {{
            {lua_list(incdirs, " " * 12)}
        }},
        cxxflags = {{ {", ".join(f'"{m}"' for m in baseline_m)}, "-w" }},
        cflags   = {{ {", ".join(f'"{m}"' for m in baseline_m)}, "-w" }},
        flags = {{
            {("\n" + " " * 12).join(flags_entries)}
        }},
        targets = {{
            opencv = {{ kind = "lib" }},
        }},
        -- `unifont`: Unicode/CJK putText coverage. Pulls the font asset
        -- package and defines HAVE_UNIFONT (drawing_text.cpp gates on it);
        -- build.mcpp sees MCPP_FEATURE_UNIFONT=1 and hex-embeds the font
        -- (builtin_font_uni.h). Not part of the reference profile — the
        -- embed machinery is byte-faithful to cmake's ocv_blob2hdr either way.
        features = {{
            ["unifont"] = {{
                deps    = {{ ["compat.opencv-unifont"] = "1.0.0" }},
                defines = {{ "HAVE_UNIFONT" }},
            }},
        }},
        linux = {{
            ldflags = {{ "-lpthread", "-ldl" }},
        }},
        sources = {{
            {lua_list(sources_out + sources_asm, " " * 12)}
        }},
        generated_files = {{
""")
L.append(f'        ["build.mcpp"] = [==[\n{build_mcpp_src}]==],\n')
L.append('        ["mcpp_generated/tu_manifest.txt"] = [==[\n' + "\n".join(manifest) + "\n]==],\n")
for rel in sorted(snapshot):
    L.append(f'        ["{rel}"] = [==[\n{snapshot[rel]}]==],\n')
L.append("""        },
    },
}
""")
OUT.write_text("".join(L))
kb = OUT.stat().st_size // 1024
print(f"gen_descriptor: {OUT} written — {len(sources_out)} source globs "
      f"(+{len(sources_asm)} asm), {len(manifest)} jpeg12/16 stub TUs, "
      f"{len(snapshot)} inline snapshot files, {kb} KiB")
