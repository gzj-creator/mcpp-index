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
                url = "https://github.com/chriskohlhoff/asio/archive/refs/tags/asio-1-38-1.tar.gz",
                sha256 = "2827b229972be80cdb14e5497962fa393d1adf036b5869e2b9c99f644daadacc",
            },
        },
        macosx = {
            ["1.38.1"] = {
                url = "https://github.com/chriskohlhoff/asio/archive/refs/tags/asio-1-38-1.tar.gz",
                sha256 = "2827b229972be80cdb14e5497962fa393d1adf036b5869e2b9c99f644daadacc",
            },
        },
        windows = {
            ["1.38.1"] = {
                -- The tag tarball contains two POSIX symlinks. xlings cannot
                -- materialize them on the Windows runner, so use GitHub's ZIP
                -- encoding of the same tagged commit on this platform.
                url = "https://github.com/chriskohlhoff/asio/archive/refs/tags/asio-1-38-1.zip",
                sha256 = "c4557a5a07ff8aa9c37bd141b7d1a6ba2b1bad5557d97762ad27aaf0091c665b",
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
        features = {
            ["default"] = { implies = { "standalone" } },
            ["standalone"] = {
                defines = {
                    "ASIO_STANDALONE",
                    "ASIO_HEADER_ONLY",
                    "ASIO_DISABLE_BOOST_CONTEXT_FIBER",
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
