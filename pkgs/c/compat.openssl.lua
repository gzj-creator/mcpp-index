-- compat.openssl — OpenSSL 3.5.1 built from source as a portable, static
-- library that provides TLS/crypto for consumers (e.g. chriskohlhoff.asio's
-- `ssl` feature, which wraps asio::ssl::context / asio::ssl::stream).
--
-- OpenSSL builds through its own Perl Configure + GNU Make system, which does
-- not fit mcpp's "list the .c files" model. The xpkg install() hook runs that
-- build (build-dep `xim:make@latest`) and lays the lib + headers under the
-- install dir.
--
-- HOST REQUIREMENT — perl. `./config` IS a Perl script, and there is no
-- `xim:perl` to declare as a build dep, so this is the one thing the package
-- cannot bring itself. CI runners and every mainstream distro ship it; a
-- stripped container may not. install() probes for it up front and fails with
-- that sentence rather than letting `./config` die with a shell error nobody
-- can read. (This is also why mbun's OpenSSL package chose a vendored prebuilt
-- over a source build; here a source build is the only option that covers both
-- linux and macOS.)
--
-- Platforms:
--   * linux/macosx — build a fully static libcrypto.a + libssl.a from source
--     via install() hook (anchor-triggered build, same pattern as compat.openblas).
--   * windows — deferred (requires prebuilt MSVC libs uploaded to xlings-res).
package = {
    spec        = "1",
    namespace   = "compat",
    name        = "openssl",
    description = "OpenSSL — TLS/crypto library (static, install()-driven build)",
    licenses    = {"Apache-2.0"},
    repo        = "https://github.com/openssl/openssl",
    type        = "package",

    xpm = {
        linux = {
            deps = { "xim:make@latest" },
            ["3.5.1"] = {
                url = {
                    GLOBAL = "https://github.com/openssl/openssl/releases/download/openssl-3.5.1/openssl-3.5.1.tar.gz",
                    CN     = "https://gitcode.com/mcpp-res/openssl/releases/download/3.5.1/openssl-3.5.1.tar.gz",
                },
                sha256 = "529043b15cffa5f36077a4d0af83f3de399807181d607441d734196d889b641f",
            },
        },
        macosx = {
            -- xim:make is declared here for the same reason as linux, and NOT
            -- left to PATH: macOS does ship a /usr/bin/make, but it is GNU Make
            -- 3.81 (the last GPLv2 release, frozen in 2006), and OpenSSL 3.x's
            -- generated Makefile does not build with it. compat.openblas
            -- declares the same dep on macosx.
            deps = { "xim:make@latest" },
            ["3.5.1"] = {
                url = {
                    GLOBAL = "https://github.com/openssl/openssl/releases/download/openssl-3.5.1/openssl-3.5.1.tar.gz",
                    CN     = "https://gitcode.com/mcpp-res/openssl/releases/download/3.5.1/openssl-3.5.1.tar.gz",
                },
                sha256 = "529043b15cffa5f36077a4d0af83f3de399807181d607441d734196d889b641f",
            },
        },
        -- windows deferred (prebuilt zip not yet prepared)
    },

    mcpp = {
        language     = "c++23",
        import_std   = false,
        c_standard   = "c11",
        -- Anchor TU is NOT a generated_files entry on linux/macosx: it is emitted
        -- by install() so mcpp must run install() (which also builds the lib)
        -- before it can compile this source. include/ + lib/ are produced by
        -- `make install_sw`.
        sources      = { "mcpp_openssl_anchor.c" },
        targets      = { ["openssl"] = { kind = "lib" } },
        include_dirs = { "include" },
        deps         = { },

        linux = {
            ldflags = {
                "-Llib",
                -- `-l:<archive>` names the file and goes straight to ld, so the
                -- static archive is what gets linked no matter what else is on
                -- the search path. Plain `-lssl` asks the driver to *resolve* a
                -- name, and a resolver prefers a shared object — one stray -L
                -- ahead of ours (a toolchain sysroot, a distro multiarch dir)
                -- and the link silently picks up the host libssl.so.3, giving
                -- the consumer a runtime dependency this package exists to
                -- avoid. ssl precedes crypto: libssl depends on libcrypto.
                "-l:libssl.a",
                "-l:libcrypto.a",
                -- Static libcrypto's own system deps. Configured `no-dso
                -- no-engine` (so no dlopen) and glibc >= 2.34 folds both into
                -- libc, which is why CI links without them — but musl and
                -- older glibc still need them spelled out.
                "-ldl",
                "-lpthread",
            },
        },
        -- macOS: ld64 has no `-l:` spelling. lib/ holds only the .a archives
        -- this package built, so name resolution has nothing else to find, and
        -- libSystem already carries dl/pthread.
        macosx = { ldflags = { "-Llib", "-lssl", "-lcrypto" } },
    },
}

import("xim.libxpkg.pkginfo")
import("xim.libxpkg.log")

local function sh_quote(value)
    return "'" .. tostring(value):gsub("'", "'\\''") .. "'"
end

local function resolve_make()
    local mk = pkginfo.build_dep("xim:make") or pkginfo.build_dep("make")
    if mk and mk.bin then
        local cand = path.join(mk.bin, "make")
        if os.isfile(cand) then return cand end
    end
    return "make"
end

local function have(tool)
    return pcall(function()
        os.exec(string.format("bash -c %s",
                              sh_quote("command -v " .. tool .. " >/dev/null 2>&1")))
    end)
end

-- Last `n` lines of the build log, or nil if it cannot be read.
local function tail_lines(file, n)
    local ok, content = pcall(io.readfile, file)
    if not ok or not content then return nil end
    local lines = {}
    for line in (tostring(content) .. "\n"):gmatch("(.-)\n") do
        lines[#lines + 1] = line
    end
    if #lines == 0 then return nil end
    return table.concat(lines, "\n", math.max(1, #lines - n + 1), #lines)
end

-- Run one build step, and on failure print the tail of the log with it.
--
-- Everything the build says goes to an on-disk log (xim's interface mode
-- swallows subprocess stdout), and xlings surfaces a failed install() as a
-- bare `E_INTERNAL: [openssl] failed:` — so without this the only signal a CI
-- run gives is that something, somewhere, went wrong. The message is passed as
-- a single pre-formatted argument: log output contains `%` often enough that
-- handing it to a format string is its own failure mode.
local function run(step, logf, cmd)
    local ok, err = pcall(os.exec, string.format("bash -c %s", sh_quote(cmd)))
    if ok then return true end
    local tail = tail_lines(logf, 40) or "<log unreadable at " .. tostring(logf) .. ">"
    log.error("%s", "compat.openssl: " .. step .. " failed (" .. tostring(err)
                 .. ")\n--- last 40 lines of " .. tostring(logf) .. " ---\n" .. tail)
    return false
end

local function _install_impl()
    if not have("perl") then
        log.error("compat.openssl: `perl` not found on PATH. OpenSSL's "
               .. "./config is a Perl script and there is no xim:perl build "
               .. "dep to fall back on — install perl and retry.")
        return false
    end

    -- The fetched tarball unpacks to openssl-<ver>/ beside the archive. Every
    -- command below cd's into srcroot itself, so the process cwd is left alone
    -- (an os.cd here would break the relative-path fallback on the next line).
    local ifile   = pkginfo.install_file()
    local srcroot = ifile and tostring(ifile):replace(".tar.gz", "")
                            or ("openssl-" .. pkginfo.version())
    if not os.isdir(srcroot) then
        srcroot = "openssl-" .. pkginfo.version()
    end

    -- Build in the extracted source directory with --prefix pointing at a
    -- clean install directory. Building in-place (prefix == srcroot) makes
    -- `make install_sw` fail with "cp: source and dest are identical".
    --
    -- The prefix is emptied HERE, before the build, so the build log can live
    -- inside it: a log that a later os.tryrm would delete, or one left in the
    -- transient srcroot, is gone exactly when a failed build needs reading.
    -- xim's interface mode swallows subprocess stdout, so this file is the
    -- only record of what the compiler said.
    local prefix = pkginfo.install_dir()
    os.tryrm(prefix)
    os.mkdir(prefix)
    local logf = path.join(prefix, "mcpp_openssl_build.log")

    -- Static-only build: no shared libs, no DSO, no tests, no apps, no engine.
    -- `./config` auto-detects the target (equivalent to `perl Configure
    -- <detected-target>`).
    --
    -- --libdir=lib is NOT cosmetic. Left unset, OpenSSL derives the install
    -- libdir as "lib$target{multilib}" (Configurations/unix-Makefile.tmpl),
    -- and Configurations/10-main.conf gives linux-x86_64 `multilib => "64"`.
    -- So on the single most common target the archives land in $prefix/lib64
    -- while `-Llib` and the check below look at $prefix/lib. linux-aarch64 and
    -- both darwin64 targets declare no multilib and resolve to plain "lib" —
    -- which is how a source build can pass on an arm64 Mac and still be broken
    -- for everyone on x86_64 Linux.
    local make  = resolve_make()
    local jobs  = (os.default_njob and os.default_njob()) or 4
    local flags = "no-shared no-dso no-tests no-apps no-engine"

    -- Record which make is in play: "3.81 vs 4.x" is the difference between a
    -- build and a wall of Makefile syntax errors, and it is invisible after
    -- the fact otherwise.
    run("make --version", logf, string.format(
        "%s --version >> %s 2>&1 || true", make, sh_quote(logf)))

    if not run("./config", logf, string.format(
        "cd %s && ./config --prefix=%s --libdir=lib %s >> %s 2>&1",
        sh_quote(srcroot), sh_quote(prefix), flags, sh_quote(logf))) then
        return false
    end
    if not run("make", logf, string.format(
        "cd %s && %s -j%d >> %s 2>&1",
        sh_quote(srcroot), make, jobs, sh_quote(logf))) then
        return false
    end

    -- macOS only: `make install_dev` runs `$(RANLIB) -c`, and the toolchain
    -- puts llvm-ranlib (which rejects -c) ahead of the system one on PATH.
    -- Pinning an absolute /usr/bin/ranlib is itself a host assumption, so it
    -- is confined to the platform that needs it — a Linux container without
    -- /usr/bin/ranlib would otherwise fail install_sw for no reason.
    local ranlib = (os.host() == "macosx") and "RANLIB=/usr/bin/ranlib " or ""
    if not run("make install_sw", logf, string.format(
        "cd %s && %s%s install_sw >> %s 2>&1",
        sh_quote(srcroot), ranlib, make, sh_quote(logf))) then
        return false
    end

    -- Verify the build produced the expected archives.
    local libdir   = path.join(prefix, "lib")
    local crypto_a = path.join(libdir, "libcrypto.a")
    local ssl_a    = path.join(libdir, "libssl.a")
    if not os.isfile(crypto_a) or not os.isfile(ssl_a) then
        log.error("compat.openssl: build produced no libcrypto.a / libssl.a "
               .. "under %s (see %s)", libdir, logf)
        return false
    end

    -- Emit the anchor TU mcpp compiles. Its absence after extraction is what
    -- makes mcpp run this install() before the build (same trigger as
    -- compat.openblas / compat.xcb).
    io.writefile(path.join(prefix, "mcpp_openssl_anchor.c"),
                 "int mcpp_compat_openssl_anchor(void) { return 0; }\n")
    return true
end

function install()
    -- Windows is deferred: there is no windows xpm block, so version
    -- resolution already fails before this point. Kept as a named error in
    -- case a windows entry is added before this hook learns to build there.
    if os.host() == "windows" then
        log.error("compat.openssl: windows is not yet supported")
        return false
    end
    local ok, result = pcall(_install_impl)
    if not ok then
        log.error("compat.openssl install() failed: %s", tostring(result))
        return false
    end
    if not result then
        log.error("compat.openssl install() returned false")
        return false
    end
    return true
end
