#!/usr/bin/env python3
"""compat-gen verify: semantic-equivalence gate between two descriptors.

For each OS shipped in xpm, compares the overlay-resolved ("effective")
view — per-OS sections are additive overlays, so the effective list for a
key is top-level entries followed by per-OS entries; generated_files is
map-insert FIRST-WINS (top-level beats per-OS on a same key):

  1. sources — order-insensitive MULTISET equality (the hard gate).  By
     default entries compare literally; with --inventory the entries are
     glob-EXPANDED against a pristine upstream tree first (required when one
     side uses directory globs the other spells out).  Entries that match
     nothing in the inventory (e.g. mcpp_generated/* paths, which are
     materialized at build time, or stray non-matching entries) are kept as
     literal residue so they still participate in the comparison.
     Order is ALSO checked — does the concatenated top-level-then-delta
     sequence preserve the original per-OS relative order? — but as a
     REPORT, not a gate, unless --strict-order: mcpp collects sources into a
     std::set (scanner.cppm scan_one_into), i.e. deduplicated and SORTED, so
     descriptor list order never reaches the build graph or the archive.
     Common/delta hoisting necessarily interleaves differently, so expect
     "order changed" on hoisted descriptors; it is stated, not hidden.
  2. generated_files — effective key set + per-key content hash.
  3. every other string-array key (cflags, cxxflags, ldflags, asflags,
     include_dirs, include_dirs_after, ...) — order-SENSITIVE sequence
     equality (flag order matters), plus the normalized text of all opaque
     mcpp-segment children (targets, flags, features, ...) and of the xpm
     block (comment-only and blank lines ignored).

Exit status: 0 = semantically equivalent; 1 = differences found (a compact
diff is printed); 2 = parse error.

Usage:
    verify.py OLD.lua NEW.lua [--inventory DIR] [--strict-order]
              [--ignore-keys include_dirs,include_dirs_after]

--ignore-keys exempts named string-array keys from comparison — for
reviewing an INTENDED semantic change (e.g. the include_dirs ->
include_dirs_after migration) while still asserting everything else is
untouched.  Never use it to wave through an unexplained diff.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from desclua import (  # noqa: E402
    Descriptor,
    ParseError,
    array_keys,
    effective_array,
    effective_gen_files,
    parse_descriptor,
    raw_text,
)


# ---------------------------------------------------------------------------
# glob expansion against an inventory tree (mirrors mcpp expand_glob:
# `*` = one segment, `**` = any number of segments, `{a,b}` brace
# alternation, leading `*/` matches the extracted tarball root; `!pattern`
# entries subtract).  The inventory dir itself plays the role of the
# extracted root, i.e. it matches the leading `*` segment.
# ---------------------------------------------------------------------------


def expand_braces(pat: str) -> list[str]:
    i = pat.find("{")
    if i < 0:
        return [pat]
    depth = 0
    for j in range(i, len(pat)):
        if pat[j] == "{":
            depth += 1
        elif pat[j] == "}":
            depth -= 1
            if depth == 0:
                break
    else:
        return [pat]  # unbalanced — literal passthrough (mcpp does the same)
    prefix, inner, suffix = pat[:i], pat[i + 1 : j], pat[j + 1 :]
    alts, depth, start = [], 0, 0
    for k, c in enumerate(inner):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "," and depth == 0:
            alts.append(inner[start:k])
            start = k + 1
    alts.append(inner[start:])
    out = []
    for alt in alts:
        for branch in expand_braces(alt):
            for suf in expand_braces(suffix):
                out.append(prefix + branch + suf)
    return out


def _match_segments(segs: list[str], root: str, cur: str) -> list[str]:
    if not segs:
        return [cur] if os.path.isfile(os.path.join(root, cur)) else []
    seg, rest = segs[0], segs[1:]
    base = os.path.join(root, cur) if cur else root
    if not os.path.isdir(base):
        return []
    out: list[str] = []
    if seg == "**":
        # any number of directories, including zero
        out.extend(_match_segments(rest, root, cur))
        for name in sorted(os.listdir(base)):
            if os.path.isdir(os.path.join(base, name)):
                out.extend(
                    _match_segments(segs, root, os.path.join(cur, name) if cur else name)
                )
        return out
    for name in sorted(os.listdir(base)):
        if fnmatch.fnmatchcase(name, seg):
            nxt = os.path.join(cur, name) if cur else name
            out.extend(_match_segments(rest, root, nxt))
    return out


def expand_entry(entry: str, inv_root: str) -> list[str]:
    """Expand one source glob against the inventory.  The leading path
    segment of the pattern is matched against the extracted tarball root —
    the inventory dir itself — so `*/x/y.c` becomes `<root>/x/y.c`.
    Returns matched inventory-relative paths (prefixed with `<root>/` to
    keep entries from different conventions distinct), or [] if nothing
    matched."""
    results: list[str] = []
    for pat in expand_braces(entry):
        segs = pat.split("/")
        if not segs:
            continue
        first, rest = segs[0], segs[1:]
        # the extracted root dir plays the first segment's role
        root_name = os.path.basename(os.path.abspath(inv_root))
        if first == "**":
            matched_root = True  # ** may also descend; handled below
            results.extend("<root>/" + p for p in _match_segments(segs, inv_root, ""))
            continue
        if fnmatch.fnmatchcase(root_name, first):
            results.extend("<root>/" + p for p in _match_segments(rest, inv_root, ""))
    return results


def effective_sources_expanded(
    entries: list[str], inv_root: str | None
) -> Counter:
    if inv_root is None:
        return Counter(entries)
    positive: list[str] = [e for e in entries if not e.startswith("!")]
    negative = [e[1:] for e in entries if e.startswith("!")]
    files: Counter = Counter()
    for e in positive:
        hits = expand_entry(e, inv_root)
        if hits:
            for h in hits:
                files[h] += 1
        else:
            files[f"<literal>{e}"] += 1  # residue: unmatched entry
    excluded = set()
    for e in negative:
        excluded.update(expand_entry(e, inv_root))
    for x in excluded:
        files.pop(x, None)
    return files


# ---------------------------------------------------------------------------
# comparison
# ---------------------------------------------------------------------------


def _counter_diff(name: str, old: Counter, new: Counter, limit: int = 10) -> list[str]:
    msgs = []
    only_old = list((old - new).elements())
    only_new = list((new - old).elements())
    if only_old:
        msgs.append(f"{name}: {len(only_old)} entr{'y' if len(only_old)==1 else 'ies'} only in OLD:")
        msgs += [f"    - {e}" for e in only_old[:limit]]
        if len(only_old) > limit:
            msgs.append(f"    ... and {len(only_old) - limit} more")
    if only_new:
        msgs.append(f"{name}: {len(only_new)} entr{'y' if len(only_new)==1 else 'ies'} only in NEW:")
        msgs += [f"    + {e}" for e in only_new[:limit]]
        if len(only_new) > limit:
            msgs.append(f"    ... and {len(only_new) - limit} more")
    return msgs


def _seq_diff(name: str, old: list[str], new: list[str], limit: int = 10) -> list[str]:
    if old == new:
        return []
    msgs = [f"{name}: sequences differ (old {len(old)} vs new {len(new)} items)"]
    for i, (a, b) in enumerate(zip(old, new)):
        if a != b:
            msgs.append(f"    first divergence at index {i}: old={a!r} new={b!r}")
            break
    else:
        i = min(len(old), len(new))
        longer, tag = (old, "old") if len(old) > len(new) else (new, "new")
        msgs.append(f"    extra in {tag} from index {i}: {longer[i:i+limit]!r}")
    return msgs


def order_preserved(old: list[str], new: list[str]) -> bool:
    """Is old's relative order preserved in new, restricted to entries
    common to both (duplicates compared positionally)?"""
    common = set(old) & set(new)
    return [e for e in old if e in common] == [e for e in new if e in common]


def verify(old: Descriptor, new: Descriptor, *, inv_root, strict_order, ignore) -> int:
    failures: list[str] = []
    notes: list[str] = []

    if old.xpm_oses != new.xpm_oses:
        failures.append(
            f"xpm OS set differs: old={old.xpm_oses} new={new.xpm_oses}"
        )

    oses = [o for o in old.xpm_oses if o in new.xpm_oses]
    for os_name in oses:
        tag = f"[{os_name}]"
        # 1. sources: multiset gate + order report -------------------------
        so, sn = effective_array(old, os_name, "sources"), effective_array(
            new, os_name, "sources"
        )
        co = effective_sources_expanded(so, inv_root)
        cn = effective_sources_expanded(sn, inv_root)
        if co != cn:
            failures.append(f"{tag} sources multiset differs:")
            failures += _counter_diff(f"{tag} sources", co, cn)
        else:
            notes.append(
                f"{tag} sources: {sum(co.values())} "
                f"{'expanded files' if inv_root else 'entries'} — multiset equal"
            )
        if order_preserved(so, sn):
            notes.append(f"{tag} sources: relative order preserved")
        else:
            msg = (
                f"{tag} sources: relative ORDER CHANGED by the restructure "
                "(expected for common/delta hoisting). Harmless for mcpp: "
                "sources are collected into a sorted std::set "
                "(scanner.cppm), so list order never reaches the build."
            )
            if strict_order:
                failures.append(msg + "  [--strict-order: treated as failure]")
            else:
                notes.append(msg)

        # 2. generated_files ----------------------------------------------
        go, gn = effective_gen_files(old, os_name), effective_gen_files(new, os_name)
        if set(go) != set(gn):
            failures.append(f"{tag} generated_files keys differ:")
            failures += _counter_diff(
                f"{tag} generated_files", Counter(go), Counter(gn)
            )
        else:
            changed = [
                k
                for k in go
                if hashlib.sha256(go[k].encode()).hexdigest()
                != hashlib.sha256(gn[k].encode()).hexdigest()
            ]
            if changed:
                failures.append(
                    f"{tag} generated_files content differs for: {changed}"
                )
            else:
                notes.append(
                    f"{tag} generated_files: {len(go)} files — keys+content equal"
                )

        # 3. every other string-array key (order-sensitive) ----------------
        keys = [
            k
            for k in dict.fromkeys(array_keys(old) + array_keys(new))
            if k != "sources" and k not in ignore
        ]
        for key in keys:
            d = _seq_diff(
                f"{tag} {key}",
                effective_array(old, os_name, key),
                effective_array(new, os_name, key),
            )
            if d:
                failures += d
        if not any(f.startswith(f"{tag} ") and "sources" not in f and "generated" not in f for f in failures):
            notes.append(f"{tag} flag/include sequences: equal ({', '.join(keys) or 'none'})")

    # 4. opaque children (targets, flags tables, features, ...) + xpm ------
    for os_name in ["<top>"] + oses:
        if os_name == "<top>":
            ro, rn = raw_text(old, old.top), raw_text(new, new.top)
        else:
            ro = raw_text(old, old.os_scopes.get(os_name, type(old.top)()))
            rn = raw_text(new, new.os_scopes.get(os_name, type(new.top)()))
        d = _seq_diff(f"[{os_name}] opaque mcpp children (normalized)", ro, rn)
        if d:
            failures += d

    xo = [
        t.strip()
        for t in (old.lines[i] for i in range(old.xpm_span[0], old.xpm_span[1] + 1))
        if t.strip() and not t.strip().startswith("--")
    ]
    xn = [
        t.strip()
        for t in (new.lines[i] for i in range(new.xpm_span[0], new.xpm_span[1] + 1))
        if t.strip() and not t.strip().startswith("--")
    ]
    failures += _seq_diff("xpm block (normalized)", xo, xn)

    for n in notes:
        print("  ok:", n)
    if ignore:
        print(f"  !! ignored keys (intended change, review by hand): {sorted(ignore)}")
    if failures:
        print("\nDIFFERENCES FOUND:")
        for f in failures:
            print(" ", f)
        return 1
    print("\nsemantically equivalent.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--inventory", help="pristine extracted upstream tree; "
                    "compare glob-EXPANDED source sets instead of literal entries")
    ap.add_argument("--strict-order", action="store_true",
                    help="treat source order changes as failures")
    ap.add_argument("--ignore-keys", default="",
                    help="comma-separated string-array keys to exempt")
    args = ap.parse_args()

    try:
        old = parse_descriptor(open(args.old, encoding="utf-8").read())
        new = parse_descriptor(open(args.new, encoding="utf-8").read())
    except ParseError as e:
        print(f"parse error: {e}", file=sys.stderr)
        return 2
    ignore = {k.strip() for k in args.ignore_keys.split(",") if k.strip()}
    return verify(old, new, inv_root=args.inventory,
                  strict_order=args.strict_order, ignore=ignore)


if __name__ == "__main__":
    raise SystemExit(main())
