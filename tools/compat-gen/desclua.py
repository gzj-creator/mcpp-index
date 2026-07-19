#!/usr/bin/env python3
"""Structural parser for mcpp-index xpkg descriptor .lua files.

Scope: the machine-generated "frozen snapshot" descriptors (compat.ffmpeg,
compat.opencv, ...) whose layout is rigid: one key per line, string-array
entries one per line (or a single balanced line), generated_files entries as
``["path"] = [==[ ... ]==],`` long-string blocks.  This is a targeted parser
for that layout — it PARSES (tracks quotes, Lua long strings, ``--``
comments, brace depth) rather than regex-mangling, and it hard-errors on any
shape it does not recognize instead of guessing.  It is NOT a general Lua
parser and must not be pointed at hand-written descriptors with exotic
formatting.

The model it extracts (everything else is preserved as opaque raw spans, so
re-emission is byte-faithful for untouched regions):

    Descriptor
      .lines            original file lines (no trailing newlines)
      .xpm_oses         OS names shipped in package.xpm ("linux", ...)
      .xpm_span         (start, end) line span of the xpm block
      .mcpp_span        (start, end) line span of the mcpp block
      .top              Scope: direct children of `mcpp = {` minus OS sections
      .os_scopes        {os: Scope} for linux/macosx/windows sections

    Scope.items — ordered list of:
      StringArray(key, span, entries, single_line)   e.g. sources, cflags
      GenFiles(key='generated_files', span, entries OrderedDict key->content)
      Raw(span)                                      anything else (targets,
                                                     flags, features, ...)

Per-OS sections are ADDITIVE overlays in mcpp (the host OS block's body is
spliced after the top-level body and parsed with the same grammar), so the
"effective" value of a list key for an OS is: top-level entries followed by
the per-OS entries.  `generated_files` is map-insert FIRST-WINS: a per-OS
entry cannot override a same-key top-level entry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

OS_SECTIONS = ("linux", "macosx", "windows")  # xpkg.cppm per-OS section keys


class ParseError(Exception):
    pass


# ---------------------------------------------------------------------------
# Char-level line scanner: brace depth aware of "…" strings, [=*[ long
# strings and -- comments.  State carries across lines only for long strings
# (quoted strings never span lines in these files).
# ---------------------------------------------------------------------------

_LONG_OPEN = re.compile(r"\[(=*)\[")


@dataclass
class ScanState:
    long_close: str | None = None  # e.g. "]==]" while inside a long string


def scan_line(line: str, state: ScanState) -> int:
    """Advance `state` across `line`; return the net {…} depth delta."""
    delta = 0
    i = 0
    n = len(line)
    in_dq = False
    while i < n:
        if state.long_close is not None:
            j = line.find(state.long_close, i)
            if j < 0:
                return delta  # whole remainder is long-string content
            i = j + len(state.long_close)
            state.long_close = None
            continue
        c = line[i]
        if in_dq:
            if c == "\\":
                i += 2
            elif c == '"':
                in_dq = False
                i += 1
            else:
                i += 1
            continue
        if c == '"':
            in_dq = True
            i += 1
        elif c == "[":
            m = _LONG_OPEN.match(line, i)
            if m:
                state.long_close = "]" + m.group(1) + "]"
                i = m.end()
            else:
                i += 1
        elif c == "-" and line.startswith("--", i):
            break  # line comment to EOL (long comments are not used here)
        elif c == "{":
            delta += 1
            i += 1
        elif c == "}":
            delta -= 1
            i += 1
        else:
            i += 1
    if in_dq:
        raise ParseError(f"unterminated string literal: {line!r}")
    return delta


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


@dataclass
class StringArray:
    key: str
    span: tuple[int, int]  # [start, end] inclusive line indices
    entries: list[str]
    single_line: bool


@dataclass
class GenFiles:
    key: str
    span: tuple[int, int]
    entries: dict[str, str]  # path -> raw long-string content


@dataclass
class Raw:
    span: tuple[int, int]


@dataclass
class Scope:
    items: list = field(default_factory=list)

    def arrays(self) -> dict[str, StringArray]:
        return {it.key: it for it in self.items if isinstance(it, StringArray)}

    def gen_files(self) -> GenFiles | None:
        for it in self.items:
            if isinstance(it, GenFiles):
                return it
        return None

    def raw_spans(self) -> list[tuple[int, int]]:
        return [it.span for it in self.items if isinstance(it, Raw)]


@dataclass
class Descriptor:
    lines: list[str]
    xpm_oses: list[str]
    xpm_span: tuple[int, int]
    mcpp_span: tuple[int, int]
    top: Scope
    os_scopes: dict[str, Scope]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_KEY_OPEN = re.compile(r"^(\s*)([A-Za-z_][A-Za-z_0-9]*)\s*=\s*\{\s*$")
_KEY_LINE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z_0-9]*)\s*=\s*\{(.*)\}\s*,?\s*$")
_ENTRY = re.compile(r'^\s*"((?:[^"\\]|\\.)*)"\s*,?\s*$')
_CLOSE = re.compile(r"^\s*\}\s*,?\s*$")
_GF_OPEN = re.compile(r'^\s*\["((?:[^"\\]|\\.)*)"\]\s*=\s*\[(=*)\[\s*$')
_SINGLE_STRINGS = re.compile(r'^\s*(?:"(?:[^"\\]|\\.)*"\s*,?\s*)+$')
_SINGLE_STRING_PULL = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _block_end(lines: list[str], start: int) -> int:
    """Line index of the line that closes the block opened at `start`.

    The opening line may open more than one level (e.g. xpm's
    ``linux = { ["1.2.3"] = {``); the block ends where the running depth
    returns to the depth before `start`.
    """
    state = ScanState()
    depth = 0
    for i in range(start, len(lines)):
        depth += scan_line(lines[i], state)
        if depth <= 0 and i > start:
            if depth < 0:
                raise ParseError(f"unbalanced braces at line {i + 1}")
            return i
        if i == start and depth <= 0:
            return i  # single-line block
    raise ParseError(f"unclosed block starting at line {start + 1}")


def _comment_or_blank(line: str) -> bool:
    t = line.strip()
    return not t or t.startswith("--")


def _parse_string_array(lines: list[str], start: int, end: int, key: str) -> StringArray:
    entries = []
    for i in range(start + 1, end):
        if _comment_or_blank(lines[i]):
            continue  # interior comments are non-semantic
        m = _ENTRY.match(lines[i])
        if not m:
            raise ParseError(
                f"{key}: line {i + 1} is not a quoted string entry: {lines[i]!r}"
            )
        entries.append(m.group(1))
    if not _CLOSE.match(lines[end]):
        raise ParseError(f"{key}: unexpected close line {end + 1}: {lines[end]!r}")
    return StringArray(key, (start, end), entries, single_line=False)


def _is_string_array(lines: list[str], start: int, end: int) -> bool:
    if end - start < 1:
        return False
    seen_entry = False
    for i in range(start + 1, end):
        if _comment_or_blank(lines[i]):
            continue
        if not _ENTRY.match(lines[i]):
            return False
        seen_entry = True
    return seen_entry


def _parse_gen_files(lines: list[str], start: int, end: int) -> GenFiles:
    entries: dict[str, str] = {}
    i = start + 1
    while i < end:
        line = lines[i]
        if not line.strip() or line.strip().startswith("--"):
            i += 1
            continue
        m = _GF_OPEN.match(line)
        if not m:
            raise ParseError(
                f"generated_files: line {i + 1} is not a "
                f'["path"] = [=[ opener: {line!r}'
            )
        path, eqs = m.group(1), m.group(2)
        closer = f"]{eqs}]"
        content: list[str] = []
        i += 1
        while i < end:
            if closer in lines[i]:
                if not re.fullmatch(rf"\s*\]{re.escape(eqs)}\]\s*,?\s*", lines[i]):
                    raise ParseError(
                        f"generated_files[{path}]: long-string closer not on "
                        f"its own line at {i + 1}: {lines[i]!r}"
                    )
                break
            content.append(lines[i])
            i += 1
        else:
            raise ParseError(f"generated_files[{path}]: unterminated long string")
        if path in entries:
            raise ParseError(f"generated_files: duplicate key {path!r}")
        entries[path] = "\n".join(content)
        i += 1
    return GenFiles("generated_files", (start, end), entries)


def _parse_scope(lines: list[str], start: int, end: int, *, allow_os: bool):
    """Parse direct children of a block body (lines start+1 .. end-1).

    Returns (Scope, {os: Scope}).  OS sections are only recognized when
    `allow_os` (i.e. when parsing the mcpp block itself).
    """
    scope = Scope()
    os_scopes: dict[str, Scope] = {}
    i = start + 1
    raw_start: int | None = None

    def flush_raw(upto: int):
        nonlocal raw_start
        if raw_start is not None:
            scope.items.append(Raw((raw_start, upto)))
            raw_start = None

    while i < end:
        line = lines[i]
        m_open = _KEY_OPEN.match(line)
        m_line = _KEY_LINE.match(line)
        if m_open:
            key = m_open.group(2)
            bend = _block_end(lines, i)
            if bend >= end:
                raise ParseError(f"block {key!r} at line {i + 1} escapes its parent")
            flush_raw(i - 1)
            if allow_os and key in OS_SECTIONS:
                sub, nested = _parse_scope(lines, i, bend, allow_os=False)
                if nested:
                    raise ParseError(f"nested OS section inside {key}")
                os_scopes[key] = sub
                sub.span = (i, bend)  # type: ignore[attr-defined]
            elif key == "generated_files":
                scope.items.append(_parse_gen_files(lines, i, bend))
            elif _is_string_array(lines, i, bend):
                scope.items.append(_parse_string_array(lines, i, bend, key))
            else:
                scope.items.append(Raw((i, bend)))
            i = bend + 1
            continue
        if m_line and _SINGLE_STRINGS.match(m_line.group(3) or " "):
            # single-line string array, e.g. ldflags = { "-lpthread", "-ldl" },
            key = m_line.group(2)
            flush_raw(i - 1)
            entries = _SINGLE_STRING_PULL.findall(m_line.group(3))
            scope.items.append(StringArray(key, (i, i), entries, single_line=True))
            i += 1
            continue
        # anything else (scalars, comments, single-line tables, blanks)
        st = ScanState()
        d = scan_line(line, st)
        if st.long_close is not None or d != 0:
            # multi-line construct that is not `key = {` — e.g. a long-string
            # assignment; swallow it as raw via depth tracking
            bend = _block_end(lines, i) if d > 0 else i
            if st.long_close is not None:
                j = i + 1
                while j <= end and st.long_close is not None:
                    scan_line(lines[j], st)
                    j += 1
                bend = j - 1
            flush_raw(i - 1)
            scope.items.append(Raw((i, bend)))
            i = bend + 1
            continue
        if raw_start is None:
            raw_start = i
        i += 1
    flush_raw(end - 1)
    return scope, os_scopes


def parse_descriptor(text: str) -> Descriptor:
    lines = text.split("\n")

    def find_block(key: str) -> tuple[int, int]:
        pat = re.compile(rf"^\s*{key}\s*=\s*\{{\s*$")
        state = ScanState()
        for i, line in enumerate(lines):
            if state.long_close is None and pat.match(line):
                return i, _block_end(lines, i)
            scan_line(line, state)
        raise ParseError(f"no `{key} = {{` block found")

    xpm_start, xpm_end = find_block("xpm")
    mcpp_start, mcpp_end = find_block("mcpp")

    # xpm OS names: direct children of the xpm block
    xpm_oses: list[str] = []
    state = ScanState()
    depth = 0
    for i in range(xpm_start, xpm_end + 1):
        if depth == 1:
            m = re.match(r"^\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*\{", lines[i])
            if m and m.group(1) in OS_SECTIONS:
                xpm_oses.append(m.group(1))
        depth += scan_line(lines[i], state)

    top, os_scopes = _parse_scope(lines, mcpp_start, mcpp_end, allow_os=True)
    return Descriptor(
        lines=lines,
        xpm_oses=xpm_oses,
        xpm_span=(xpm_start, xpm_end),
        mcpp_span=(mcpp_start, mcpp_end),
        top=top,
        os_scopes=os_scopes,
    )


# ---------------------------------------------------------------------------
# Effective (overlay-resolved) views
# ---------------------------------------------------------------------------


def effective_array(desc: Descriptor, os_name: str, key: str) -> list[str]:
    """top-level entries followed by per-OS entries (additive overlay)."""
    out: list[str] = []
    arr = desc.top.arrays().get(key)
    if arr:
        out.extend(arr.entries)
    scope = desc.os_scopes.get(os_name)
    if scope:
        arr = scope.arrays().get(key)
        if arr:
            out.extend(arr.entries)
    return out


def effective_gen_files(desc: Descriptor, os_name: str) -> dict[str, str]:
    """map-insert FIRST-WINS: top-level entry beats a same-key per-OS entry."""
    out: dict[str, str] = {}
    gf = desc.top.gen_files()
    if gf:
        out.update(gf.entries)
    scope = desc.os_scopes.get(os_name)
    if scope:
        gf = scope.gen_files()
        if gf:
            for k, v in gf.entries.items():
                out.setdefault(k, v)
    return out


def array_keys(desc: Descriptor) -> list[str]:
    """All StringArray keys seen anywhere (top-level or per-OS), in order."""
    seen: list[str] = []
    for scope in [desc.top, *desc.os_scopes.values()]:
        for it in scope.items:
            if isinstance(it, StringArray) and it.key not in seen:
                seen.append(it.key)
    return seen


def raw_text(desc: Descriptor, scope: Scope) -> list[str]:
    """Normalized raw-item text of a scope: comment-only and blank lines
    dropped, trailing whitespace stripped (comments are non-semantic)."""
    out: list[str] = []
    for s, e in scope.raw_spans():
        for i in range(s, e + 1):
            t = desc.lines[i].rstrip()
            if not t or t.lstrip().startswith("--"):
                continue
            out.append(t.strip())
    return out
