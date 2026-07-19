#!/usr/bin/env python3
"""compat-gen restructure: common/delta source split (+ optional glob
compression) for machine-generated mcpp-index descriptors.

What it does
------------
1. common/delta hoisting (always, when >= 2 OSes ship in xpm and every
   shipped OS has a per-OS `sources` array):
   per-OS sections are ADDITIVE overlays in mcpp — the host OS block's body
   is spliced after the top-level body and parsed with the same grammar, so
   top-level keys and per-OS keys append to the same lists.  Sources present
   on EVERY shipped OS are therefore hoisted into one top-level `sources`
   array; each per-OS block keeps only its delta.  Semantically lossless:
   mcpp collects sources into a std::set (scanner.cppm) — deduplicated and
   sorted — so descriptor list order never reaches the build.

2. directory-glob compression (OPT-IN via --inventory <dir>):
   for a (directory, extension) group where the selected files are EXACTLY
   all files of that extension in that directory of the pristine upstream
   tree (the inventory), the group collapses to `dir/*.ext`.  The collapse
   is only performed when it is provably lossless against the inventory —
   `*` matches a single path segment, so the glob expands to precisely the
   inventory listing.  WITHOUT --inventory the compression step is SKIPPED
   entirely (there is nothing to prove losslessness against); hoisting still
   runs.  The inventory dir must be the pristine extraction of the exact
   tarball pinned by the descriptor's sha256 (the `*/` leading segment of a
   source entry matches the extracted tarball root dir).

Everything else — generated_files (which genuinely differ per OS and are
map-insert FIRST-WINS, so they must stay whole inside their per-OS blocks),
flags, cflags, include_dirs, xpm, targets — is re-emitted byte-faithfully:
only the source-array spans are rewritten.

Usage:
    restructure.py DESCRIPTOR.lua [-o OUT.lua] [--inventory DIR]

With no -o the file is rewritten in place.  Always run
tools/compat-gen/verify.py old new afterwards; it is the semantic
equivalence gate.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from desclua import (  # noqa: E402
    Descriptor,
    ParseError,
    StringArray,
    parse_descriptor,
)


# ---------------------------------------------------------------------------
# glob compression (opt-in, inventory-proven)
# ---------------------------------------------------------------------------


def _inventory_listing(inv_root: str, rel_dir: str, ext: str) -> set[str] | None:
    """All plain files with `ext` directly in `rel_dir` of the inventory."""
    d = os.path.join(inv_root, rel_dir) if rel_dir else inv_root
    if not os.path.isdir(d):
        return None
    return {
        f
        for f in os.listdir(d)
        if f.endswith(ext) and os.path.isfile(os.path.join(d, f))
    }


def compress_list(entries: list[str], inv_root: str) -> tuple[list[str], int]:
    """Collapse provably-complete (dir, ext) groups to `dir/*.ext`.

    Only literal `*/dir/file.ext` entries participate (a single leading `*/`
    segment — the extracted-tarball-root convention — and no other glob
    metacharacters).  Returns (new_entries, groups_collapsed).
    """
    groups: dict[tuple[str, str], list[str]] = OrderedDict()
    for e in entries:
        if not e.startswith("*/"):
            continue
        rel = e[2:]
        if any(ch in rel for ch in "*?{}[]!"):
            continue
        d, f = os.path.split(rel)
        ext = os.path.splitext(f)[1]
        if not ext:
            continue
        groups.setdefault((d, ext), []).append(f)

    collapse: dict[tuple[str, str], str] = {}
    for (d, ext), files in groups.items():
        if len(files) < 2:
            continue
        inv = _inventory_listing(inv_root, d, ext)
        if inv is None or set(files) != inv:
            continue  # not provably lossless — keep the explicit list
        collapse[(d, ext)] = f"*/{d}/*{ext}" if d else f"*/*{ext}"

    out: list[str] = []
    emitted: set[tuple[str, str]] = set()
    for e in entries:
        key = None
        if e.startswith("*/") and not any(ch in e[2:] for ch in "*?{}[]!"):
            d, f = os.path.split(e[2:])
            key = (d, os.path.splitext(f)[1])
        if key in collapse:
            if key not in emitted:
                out.append(collapse[key])
                emitted.add(key)
            continue
        out.append(e)
    return out, len(emitted)


# ---------------------------------------------------------------------------
# restructuring
# ---------------------------------------------------------------------------


def restructure(text: str, inventory: str | None) -> tuple[str, dict]:
    desc = parse_descriptor(text)
    stats: dict = {"oses": desc.xpm_oses}

    if len(desc.xpm_oses) < 2:
        raise SystemExit(
            "nothing to hoist: fewer than 2 OSes ship in xpm "
            f"({desc.xpm_oses}); common/delta split needs a cross-OS "
            "intersection. (Glob compression of a single-OS descriptor is "
            "not wired up on purpose — revisit when needed.)"
        )

    per_os: dict[str, StringArray] = {}
    for os_name in desc.xpm_oses:
        scope = desc.os_scopes.get(os_name)
        arr = scope.arrays().get("sources") if scope else None
        if arr is None:
            raise SystemExit(
                f"xpm ships {os_name!r} but its mcpp section has no `sources` "
                "array — hoisting would ADD sources to that OS. Refusing."
            )
        if arr.single_line:
            raise SystemExit(f"{os_name}: single-line sources array unsupported")
        per_os[os_name] = arr

    # common = present on EVERY shipped OS; hoist order = first OS's order
    first = desc.xpm_oses[0]
    common_set = set(per_os[first].entries)
    for os_name in desc.xpm_oses[1:]:
        common_set &= set(per_os[os_name].entries)
    hoisted = [e for e in per_os[first].entries if e in common_set]
    deltas = {
        os_name: [e for e in per_os[os_name].entries if e not in common_set]
        for os_name in desc.xpm_oses
    }
    stats["common"] = len(hoisted)
    stats["deltas"] = {k: len(v) for k, v in deltas.items()}

    existing_top = desc.top.arrays().get("sources")
    if existing_top is not None and existing_top.single_line:
        raise SystemExit("top-level single-line sources array unsupported")
    if existing_top is not None:
        keep = set(existing_top.entries)
        hoisted = existing_top.entries + [e for e in hoisted if e not in keep]

    stats["compressed_groups"] = 0
    if inventory:
        inv_root = inventory.rstrip("/")
        hoisted, g0 = compress_list(hoisted, inv_root)
        stats["compressed_groups"] += g0
        for os_name in deltas:
            deltas[os_name], g = compress_list(deltas[os_name], inv_root)
            stats["compressed_groups"] += g

    # --- re-emit -----------------------------------------------------------
    lines = desc.lines

    # spans to replace: per-OS sources arrays (and the existing top-level
    # sources array, if hoisting merged into it)
    replaced: dict[int, tuple[int, list[str]]] = {}  # start -> (end, newlines)

    def array_block(indent: str, entries: list[str], comment: list[str]) -> list[str]:
        out = [indent + c for c in comment]
        out.append(f"{indent}sources = {{")
        out.extend(f'{indent}    "{e}",' for e in entries)
        out.append(f"{indent}}},")
        return out

    for os_name, arr in per_os.items():
        indent = lines[arr.span[0]][: len(lines[arr.span[0]]) - len(lines[arr.span[0]].lstrip())]
        delta = deltas[os_name]
        if delta:
            block = array_block(
                indent,
                delta,
                [f"-- {os_name}-only delta (common sources are hoisted to the"
                 " top-level `sources`; per-OS sections are additive overlays)"],
            )
        else:
            block = [f"{indent}-- (no {os_name}-only sources: everything is in"
                     " the top-level common `sources`)"]
        replaced[arr.span[0]] = (arr.span[1], block)

    # top-level sources block: reuse existing span, or insert before the
    # first per-OS section
    first_os_line = min(s.span[0] for s in desc.os_scopes.values())  # type: ignore[attr-defined]
    os_indent = lines[first_os_line][: len(lines[first_os_line]) - len(lines[first_os_line].lstrip())]
    top_comment = [
        "-- sources common to every shipped OS (hoisted by"
        " tools/compat-gen/restructure.py;",
        "-- per-OS sections below are additive overlays holding only their"
        " delta)",
    ]
    top_block = array_block(os_indent, hoisted, top_comment)
    if existing_top is not None:
        replaced[existing_top.span[0]] = (existing_top.span[1], top_block)
        insert_at = None
    else:
        insert_at = first_os_line

    out: list[str] = []
    i = 0
    while i < len(lines):
        if insert_at is not None and i == insert_at:
            out.extend(top_block)
            insert_at = None
        if i in replaced:
            end, block = replaced[i]
            out.extend(block)
            i = end + 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("descriptor")
    ap.add_argument("-o", "--output", help="output path (default: in place)")
    ap.add_argument(
        "--inventory",
        help="pristine extracted upstream tree; enables lossless directory-"
        "glob compression. Omit to SKIP compression (hoisting still runs).",
    )
    args = ap.parse_args()

    text = open(args.descriptor, encoding="utf-8").read()
    try:
        new_text, stats = restructure(text, args.inventory)
    except ParseError as e:
        print(f"parse error: {e}", file=sys.stderr)
        return 2

    out_path = args.output or args.descriptor
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(new_text)

    old_n, new_n = text.count("\n") + 1, new_text.count("\n") + 1
    print(f"oses: {', '.join(stats['oses'])}")
    print(f"hoisted common sources: {stats['common']}")
    for os_name, n in stats["deltas"].items():
        print(f"  {os_name} delta: {n}")
    if args.inventory:
        print(f"glob groups collapsed: {stats['compressed_groups']}")
    else:
        print("glob compression: skipped (no --inventory)")
    print(f"lines: {old_n} -> {new_n}  ({old_n - new_n:+d} removed)")
    print(f"wrote {out_path}")
    print("now run: tools/compat-gen/verify.py <old> <new>  (the gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
