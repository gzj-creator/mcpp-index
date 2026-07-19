-- Form A descriptor: the public opencv module package ships its own
-- mcpp.toml. mcpp's default lookup finds <verdir>/*/mcpp.toml inside
-- the GitHub source tarball wrap.
--
-- The package is the thin C++23 module layer (import opencv.cv; and 7
-- per-module interfaces) over OpenCV 5's unchanged C++ API; the OpenCV
-- sources themselves arrive through its compat.opencv dependency (full
-- source build with SIMD dispatch + build.mcpp consumer-side synthesis,
-- plus the compat.ffmpeg videoio backend — see pkgs/c/compat.opencv.lua;
-- the transitional compat.opencv5 alias is retired as of this bump).
-- Linux-only for now: compat.opencv carries a linux-x86_64 config snapshot.
--
package = {
    spec        = "1",
    name        = "opencv",
    namespace   = "",
    description = "C++23 module package for OpenCV 5 (import opencv.cv) — full source build via compat.opencv, C++ API unchanged",
    licenses    = {"MIT"},   -- module layer; upstream via compat.opencv is Apache-2.0
    repo        = "https://github.com/Sunrisepeak/opencv-m",
    type        = "package",

    xpm = {
        linux = {
            ["0.0.3"] = {
                url    = {
                    GLOBAL = "https://github.com/Sunrisepeak/opencv-m/archive/refs/tags/v0.0.3.tar.gz",
                    CN     = "https://gitcode.com/mcpp-res/opencv/releases/download/v0.0.3/opencv-m-0.0.3.tar.gz",
                },
                sha256 = "92ffae8bc4253538143319fba59d4933831a92bb03394126baae2f0a3d4b0e2b",
            },
        },
    },

    -- (no `mcpp` field -- default lookup will find <verdir>/*/mcpp.toml)
}
