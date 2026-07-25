-- Lint `package.name` against `package.namespace`.
--
-- Rule: a namespaced descriptor MUST spell `name` as the fully-qualified
-- `<namespace>.<short>`. The split form (namespace = "chriskohlhoff",
-- name = "asio") parses fine and passes `mcpp xpkg parse` — mcpp's own
-- identity layer normalizes both spellings to the same package — but it is
-- NOT installable from an index:
--
--   * xlings/libxpkg keys the index on the literal `package.name`
--     (libxpkg build_index → entries[package.name]), so the entry lands
--     under `asio`;
--   * mcpp asks xlings for the FQN it reconstructs from the consumer's
--     `[dependencies.<ns>] <short>`, i.e. `chriskohlhoff.asio`
--     (mcpp src/build/prepare.cppm — "xlings resolves packages by the full
--     qualified name (ns.shortName) as it appears in the index's name field").
--
-- The two never meet → E_NOT_FOUND at install time, on every platform, after
-- the workspace job has already burned an hour. No consumer-side spelling can
-- work around it; the descriptor is the only place it can be fixed.
--
-- Upstream: mcpp-community/mcpp#278 — LANDED in mcpp 0.0.105, which enforces
-- the same rule inside `mcpp xpkg parse` (INV-NAME) and again on the install
-- path. This lint is now a redundant-but-cheap second gate: it runs before the
-- pinned mcpp is even downloaded, and it keeps the rule readable in-repo.
--
-- ── Rule 2: the short segment must be ATOMIC ────────────────────────
--
-- Identity is a 2-tuple `(namespace, name)` where `namespace` is a
-- HIERARCHICAL, dotted path and `name` is a SINGLE atomic segment (mcpp design
-- 2026-06-20 §4.2). Any depth therefore belongs in `namespace`, never in the
-- short half of `name`:
--
--     ✅ namespace = "mcpplibs.capi", name = "mcpplibs.capi.lua"  → (mcpplibs.capi, lua)
--     ❌ namespace = "mcpplibs",      name = "mcpplibs.capi.lua"  → declared ns
--                                                                   disagrees with
--                                                                   canonical ns
--
-- Both spellings survive mcpp's normalizer (it splits the FQN on its LAST dot,
-- so the second one silently resolves to `(mcpplibs.capi, lua)` — a namespace
-- the descriptor never declared). That silent disagreement is what this rule
-- removes: after it, the declared namespace and the canonical one are always
-- the same string, and `a.b.c` can only ever live in `namespace`.
--
-- Zero-namespace packages (the public default-namespace module packages —
-- imgui / ffmpeg / opencv) are a deliberate, legal form: their bare `name` IS
-- the FQN. Rule 2 still applies to them — a dotted name with no declared
-- namespace would resolve to a namespace that isn't written down anywhere.
--
-- Usage: lua5.4 tests/check_package_name.lua <file.lua>

function import(...)
    return setmetatable({}, {__index = function() return function() end end})
end

local path = assert(arg[1], "usage: check_package_name.lua <file>")
package = nil
local chunk = assert(loadfile(path, "t"))
chunk()

local p = package
if type(p) ~= "table" then os.exit(0) end

local fail = 0
local function err(msg)
    io.stderr:write(string.format("::error file=%s::%s\n", path, msg))
    fail = 1
end

local name = p.name
local ns   = p.namespace or ""

if type(name) ~= "string" or name == "" then
    err("package.name must be a non-empty string")
    os.exit(fail)
end
if type(ns) ~= "string" then
    err("package.namespace must be a string")
    os.exit(fail)
end

-- ── Rule 1: `name` is the fully-qualified `<namespace>.<short>` ─────
local short = name
if ns ~= "" then
    local prefix = ns .. "."
    if name:sub(1, #prefix) ~= prefix then
        err(string.format(
            "package.name must be the fully-qualified '<namespace>.<short>': " ..
            "namespace = %q but name = %q — write name = %q. " ..
            "The split form registers the index entry under %q, which no " ..
            "consumer request can ever resolve (E_NOT_FOUND at install). " ..
            "See mcpp-community/mcpp#278.",
            ns, name, prefix .. name, name))
        os.exit(fail)
    elseif #name == #prefix then
        err(string.format(
            "package.name = %q has an empty short name after the %q prefix",
            name, prefix))
        os.exit(fail)
    end
    short = name:sub(#prefix + 1)
end

-- ── Rule 2: the short segment is a SINGLE atomic segment ───────────
-- Depth belongs in `namespace`. When the short half carries dots, mcpp's
-- split-on-last-dot normalizer attributes the package to a namespace the
-- descriptor never declared — the identity silently disagrees with itself.
if short:find(".", 1, true) then
    local canonicalNs = name:sub(1, #name - #short:match("[^.]*$") - 1)
    if ns == "" then
        err(string.format(
            "package.name = %q is dotted but declares no namespace: it would " ..
            "resolve to namespace %q, which is written down nowhere. Put the " ..
            "hierarchy in `namespace` — namespace = %q, name = %q.",
            name, canonicalNs, canonicalNs, name))
    else
        err(string.format(
            "package.name = %q has a non-atomic short name %q under namespace " ..
            "%q. Identity is (namespace, name) where `namespace` is the dotted " ..
            "path and `name` is ONE segment, so this resolves to namespace %q " ..
            "— not the %q you declared. Move the depth into `namespace`: " ..
            "namespace = %q.",
            name, short, ns, canonicalNs, ns, canonicalNs))
    end
end

os.exit(fail)
