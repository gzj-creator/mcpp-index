-- Form A descriptor: the godot-cpp module package ships its own mcpp.toml.
-- mcpp's default lookup finds <verdir>/*/mcpp.toml inside the GitHub source
-- tarball wrap.
--
-- The package is the thin C++23 module layer over godot-cpp's unchanged C++
-- API: `import godot_cpp;` re-exports the whole public `godot` namespace, so
-- code that used to open with a stack of `#include <godot_cpp/...>` opens with
-- one import and is otherwise the same. godot-cpp's sources and its
-- pre-generated GDExtension bindings arrive through the package's own
-- compat.godot-cpp dependency (1022-TU source build -- see
-- pkgs/c/compat.godot-cpp.lua).
--
-- Module name: ONE segment, `godot_cpp`, matching the library and the
-- `#include <godot_cpp/...>` root users already type. The dotted spelling is
-- reserved here for packages that expose several submodules (opencv.cv,
-- ffmpeg.av); this one has a single interface unit.
--
-- What the module cannot carry: MACROS. GDCLASS, GDREGISTER_CLASS,
-- GDVIRTUAL_*, D_METHOD, memnew/memdelete and the ERR_* family are
-- preprocessor constructs, and GDExtension code is written in them. The
-- package ships `<godot-cpp-m/macros.h>` for exactly that, to be included
-- next to the import; godot-cpp's headers sit in the module's global module
-- fragment, so the two spellings denote the same entities and mixing them is
-- well-formed. The package's own tests cover both shapes.
--
-- Also not re-exported (upstream's shape, not a wrapper choice): the internal
-- container templates HashMap/HashSet and their default hashers. Their inline
-- bodies reach `hash_murmur3_one_float/double`, which are `static` AND declare
-- an unnamed union -- and exposing a TU-local TYPE from a module interface is
-- a hard error, not the -Wexpose-global-module-tu-local warning. Extension
-- code uses Dictionary/Array/TypedArray; the headers still have the rest.
--
-- Three platforms, one OS-neutral tarball: godot-cpp is portable C++ and
-- compat.godot-cpp covers all three.
package = {
    spec        = "1",
    name        = "godot-cpp",
    namespace   = "godotengine",
    description = "C++23 module package for godot-cpp (import godot_cpp) — Godot GDExtension API, C++ API unchanged",
    licenses    = {"MIT"},   -- module layer; upstream godot-cpp is MIT as well
    repo        = "https://github.com/mcpplibs/godot-cpp-m",
    type        = "package",

    xpm = {
        linux = {
            ["0.0.1"] = {
                url = {
                    GLOBAL = "https://github.com/mcpplibs/godot-cpp-m/archive/refs/tags/v0.0.1.tar.gz",
                    CN     = "https://gitcode.com/mcpp-res/godot-cpp/releases/download/v0.0.1/godot-cpp-m-0.0.1.tar.gz",
                },
                sha256 = "5145f1e539b4b42bdb4064a2df0dcb54ffac4d70f88edc42f38bf2304a37a344",
            },
        },
        macosx = {
            ["0.0.1"] = {
                url = {
                    GLOBAL = "https://github.com/mcpplibs/godot-cpp-m/archive/refs/tags/v0.0.1.tar.gz",
                    CN     = "https://gitcode.com/mcpp-res/godot-cpp/releases/download/v0.0.1/godot-cpp-m-0.0.1.tar.gz",
                },
                sha256 = "5145f1e539b4b42bdb4064a2df0dcb54ffac4d70f88edc42f38bf2304a37a344",
            },
        },
        windows = {
            ["0.0.1"] = {
                url = {
                    GLOBAL = "https://github.com/mcpplibs/godot-cpp-m/archive/refs/tags/v0.0.1.tar.gz",
                    CN     = "https://gitcode.com/mcpp-res/godot-cpp/releases/download/v0.0.1/godot-cpp-m-0.0.1.tar.gz",
                },
                sha256 = "5145f1e539b4b42bdb4064a2df0dcb54ffac4d70f88edc42f38bf2304a37a344",
            },
        },
    },

    -- (no `mcpp` field -- default lookup will find <verdir>/*/mcpp.toml)
}
