-- Lint a descriptor's PATH against its declared identity.
--
-- The filename is NOT part of a package's identity — mcpp resolves
-- identity-first and verifies every candidate against the descriptor's declared
-- `package.{namespace,name}` (mcpp design 2026-06-26, "Filename Is Not a Key").
-- A non-canonically-named file still resolves.
--
-- It is still worth pinning, for two reasons this index has actually hit:
--
--   1. Discovery is bounded by a candidate-filename list, not by an index-wide
--      scan (mcpp `compat::xpkg_lua_candidates`). Canonical names keep a
--      package on the first, cheapest probe instead of a COMPAT fallback that
--      is scheduled for removal in mcpp 1.0.0.
--   2. Two files can carry the SAME identity without anyone noticing —
--      `pkgs/c/capi.lua.lua` and `pkgs/m/mcpplibs.capi.lua.lua` were
--      byte-identical duplicates of `(mcpplibs.capi, lua)`. Whichever the
--      directory scan reached first won; edits to the other were dead.
--
-- Canonical layout (mirrors mcpp `compat::xpkg_lua_candidates`):
--
--     namespace ""  or  "mcpplibs"  →  pkgs/<short[1]>/<short>.lua
--     any other namespace           →  pkgs/<fqn[1]>/<fqn>.lua
--
--     (mcpplibs, cmdline)    → pkgs/c/cmdline.lua
--     (compat,   zlib)       → pkgs/c/compat.zlib.lua
--     (aimol,    tensorvia-cpu) → pkgs/a/aimol.tensorvia-cpu.lua
--     (mcpplibs.capi, lua)   → pkgs/m/mcpplibs.capi.lua.lua
--
-- Run check_package_name.lua first; this lint assumes identity is already
-- well-formed and reports nothing when it is not.
--
-- Usage: lua5.4 tests/check_package_filename.lua <pkgs/x/file.lua>

local DEFAULT_NS = "mcpplibs"

function import(...)
    return setmetatable({}, {__index = function() return function() end end})
end

local path = assert(arg[1], "usage: check_package_filename.lua <file>")
package = nil
local chunk = assert(loadfile(path, "t"))
chunk()

local p = package
if type(p) ~= "table" then os.exit(0) end

local name = p.name
local ns   = p.namespace or ""
if type(name) ~= "string" or name == "" then os.exit(0) end
if type(ns) ~= "string" then os.exit(0) end

-- Identity must already be well-formed; check_package_name.lua owns that.
local short = name
if ns ~= "" then
    local prefix = ns .. "."
    if name:sub(1, #prefix) ~= prefix then os.exit(0) end
    short = name:sub(#prefix + 1)
    if short == "" or short:find(".", 1, true) then os.exit(0) end
elseif name:find(".", 1, true) then
    os.exit(0)
end

local basename = (ns == "" or ns == DEFAULT_NS) and short or name
local expected = string.format("pkgs/%s/%s.lua", basename:sub(1, 1):lower(), basename)

if path ~= expected then
    io.stderr:write(string.format(
        "::error file=%s::descriptor for identity (%s, %s) should live at %q, " ..
        "not %q. The filename is only a lookup hint — mcpp verifies identity " ..
        "from the file's own package.{namespace,name} — but the canonical path " ..
        "keeps it on the first probe and makes duplicate descriptors for one " ..
        "identity impossible to add unnoticed.\n",
        path, ns == "" and "<none>" or ns, short, expected, path))
    os.exit(1)
end

os.exit(0)
