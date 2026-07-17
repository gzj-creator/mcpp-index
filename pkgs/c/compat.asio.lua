-- compat.asio — standalone Asio 1.38.1, exposed in upstream's default
-- header-only mode. The package intentionally does not provide optional
-- OpenSSL/wolfSSL, Boost.Context/Regex/Date_Time, or liburing dependencies.
package = {
    spec        = "1",
    namespace   = "compat",
    name        = "compat.asio",
    description = "Standalone asynchronous I/O and networking library (header-only)",
    licenses    = {"BSL-1.0"},
    repo        = "https://github.com/chriskohlhoff/asio",
    type        = "package",

    xpm = {
        linux = {
            ["1.38.1"] = {
                url = {
                    GLOBAL = "https://github.com/chriskohlhoff/asio/archive/refs/tags/asio-1-38-1.tar.gz",
                    CN     = "https://gitcode.com/mcpp-res/asio/releases/download/1.38.1/asio-1.38.1.tar.gz",
                },
                sha256 = "2827b229972be80cdb14e5497962fa393d1adf036b5869e2b9c99f644daadacc",
            },
        },
        macosx = {
            ["1.38.1"] = {
                url = {
                    GLOBAL = "https://github.com/chriskohlhoff/asio/archive/refs/tags/asio-1-38-1.tar.gz",
                    CN     = "https://gitcode.com/mcpp-res/asio/releases/download/1.38.1/asio-1.38.1.tar.gz",
                },
                sha256 = "2827b229972be80cdb14e5497962fa393d1adf036b5869e2b9c99f644daadacc",
            },
        },
        windows = {
            ["1.38.1"] = {
                -- Upstream's tag archives (tar.gz AND zip) both carry two POSIX
                -- symlinks (asio/include -> ../include, asio/src -> ../src) that
                -- tar.exe cannot materialize on the Windows runner, and upstream
                -- publishes no symlink-free asset for 1.38.x. This asset is the
                -- upstream tag tarball with only those two symlink entries
                -- removed (tar --delete); all 1544 regular files are
                -- byte-identical to upstream. Provenance: xlings-res/asio README.
                url = {
                    GLOBAL = "https://github.com/xlings-res/asio/releases/download/1.38.1/asio-1.38.1-nosymlinks.tar.gz",
                    CN     = "https://gitcode.com/mcpp-res/asio/releases/download/1.38.1/asio-1.38.1-nosymlinks.tar.gz",
                },
                sha256 = "77f74094bb12cd867a6edbf5736bbed816c6ce0906e880de8573097a81714d89",
            },
        },
    },

    mcpp = {
        language     = "c++23",
        import_std   = false,
        c_standard   = "c11",
        -- GitHub wraps the tag as asio-asio-1-38-1/; expose its public include root.
        include_dirs = { "*/include" },
        -- Header-only packages still need a buildable target in mcpp.
        generated_files = {
            ["mcpp_generated/asio_anchor.c"] = [==[
int mcpp_compat_asio_headers_anchor(void) { return 0; }
]==],
        },
        sources = { "mcpp_generated/asio_anchor.c" },
        targets = { ["asio"] = { kind = "lib" } },
        -- Explicitly pin the package's public configuration. `standalone` is a
        -- default feature so its defines propagate to every consumer TU.
        --
        -- ASIO_HAS_THREADS: asio's own thread detection keys off CRT macros
        -- (_MT/_REENTRANT/_POSIX_THREADS) that the workspace's llvm-on-Windows
        -- toolchain does not define, so asio silently selects null_thread and
        -- every internal-thread operation (e.g. the waitable-timer wait thread)
        -- throws operation_not_supported (10045) at runtime. All supported
        -- targets are multithreaded; pin the detection result. asio only ever
        -- tests defined(ASIO_HAS_THREADS), and on POSIX the pthread selection
        -- below it still runs, so this is a no-op where detection already works.
        features = {
            ["default"] = { implies = { "standalone" } },
            ["standalone"] = {
                defines = {
                    "ASIO_STANDALONE",
                    "ASIO_HEADER_ONLY",
                    "ASIO_DISABLE_BOOST_CONTEXT_FIBER",
                    "ASIO_HAS_THREADS",
                },
            },
        },
        deps = {},
        -- POSIX threading is detected by Asio from unistd.h feature macros;
        -- retain the portable driver-level thread link contract on Linux.
        linux = {
            ldflags = { "-pthread" },
        },
        -- On the supported desktop MSVC-ABI route, Asio autolinks ws2_32.lib
        -- and mswsock.lib. Do not inject GNU -l flags into native link.exe.
    },
}
