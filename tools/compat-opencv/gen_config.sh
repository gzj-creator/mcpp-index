#!/bin/sh
# gen_config.sh — maintainer-time descriptor pipeline for compat.opencv.
#
# Fetches the pinned OFFICIAL OpenCV tarball (fetch_upstream.sh alongside),
# builds a local static FFmpeg prefix for CMake discovery (the videoio
# FFmpeg backend — consumers get the same libraries from the compat.ffmpeg
# dependency instead), runs CMake ONCE with the frozen hermetic profile,
# runs the reference ninja build so the build-time generators (cl2cpp,
# blob2hdr, dispatch stubs) materialize, dumps the full compile-command list
# (`ninja -t commands` — state-independent, unlike `ninja -n`), and emits
# the mcpp-index descriptor via gen_descriptor.py alongside. Consumers never
# run this: OpenCV reaches them as the compat.opencv package (frozen config
# + real-path sources + build.mcpp synthesis).
#
# Usage: tools/compat-opencv/gen_config.sh [target] [out.lua]
#   target  default: autodetected <os>-<arch>   (only linux-x86_64 supported yet)
#   out.lua default: <this repo>/pkgs/c/compat.opencv.lua
# Env:
#   FFMPEG_PREFIX   pre-built static FFmpeg install prefix (with lib/pkgconfig).
#                   When unset, the script builds one from FFMPEG_SRC (a
#                   fetched FFmpeg source tree matching compat.ffmpeg's pin).
#   FFMPEG_SRC      FFmpeg source dir (required if FFMPEG_PREFIX unset)
#   OPENCV_CFG_DIR  reuse a build dir (default: fresh mktemp)
#
# NOTE: use a real host gcc via CC/CXX if the default `cc` is shimmed to a
# cross toolchain (xlings subos). Host gcc 13 ICEs on two AVX2 bfloat TUs —
# harmless here (ninja -k skips them; only the generators' outputs matter).
# The FFmpeg prefix itself needs a non-ICEing gcc (gcc 13 ICEs on
# libswscale/output.o too — use the xlings gcc16 via FFMPEG_CC).
set -eu

target="${1:-$(uname -s | tr 'A-Z' 'a-z' | sed s/darwin/macos/)-$(uname -m | sed s/arm64/aarch64/)}"
here="$(cd "$(dirname "$0")" && pwd)"
index_root="$(cd "$here/../.." && pwd)"
version="${OPENCV_VERSION:-5.0.0}"
sha256="${OPENCV_SHA256:-b0528f5a1d379d59d4701cb28c36e22214cc51cf64594e5b56f2d3e6c0233095}"
out="${2:-$index_root/pkgs/c/compat.opencv.lua}"

src="$(sh "$here/fetch_upstream.sh")"
bld="${OPENCV_CFG_DIR:-$(mktemp -d /tmp/opencv-cfg.XXXXXX)}"

# ── FFmpeg prefix (videoio backend reference; consumers use compat.ffmpeg) ──
if [ -z "${FFMPEG_PREFIX:-}" ]; then
    : "${FFMPEG_SRC:?set FFMPEG_PREFIX or FFMPEG_SRC}"
    FFMPEG_PREFIX="$bld/ffmpeg-prefix"
    ffbld="$bld/ffmpeg-build"
    mkdir -p "$ffbld"
    ( cd "$ffbld" && "$FFMPEG_SRC/configure" \
        ${FFMPEG_CC:+--cc=$FFMPEG_CC} ${FFMPEG_CXX:+--cxx=$FFMPEG_CXX} \
        --prefix="$FFMPEG_PREFIX" --disable-shared --enable-static \
        --disable-programs --disable-doc --enable-pic \
      && make -j"$(nproc)" && make install )
fi
export FFMPEG_PREFIX

# Frozen hermetic profile: five requested modules (flann and geometry join
# as dependency closure), every external probe OFF except FFmpeg (static
# prefix above, discovered via pkg-config), all needed 3rdparty built from
# the vendored tree (zlib, libpng, libjpeg-turbo incl. NASM SIMD), headless
# highgui, V4L2 + FFmpeg videoio. WITH_UNIFONT stays OFF: it is a
# configure-time EXTRA download (13 MB CJK font) which would break the
# single-pinned-source model — future `unifont` feature.
PKG_CONFIG_LIBDIR="$FFMPEG_PREFIX/lib/pkgconfig" \
cmake -G Ninja -S "$src" -B "$bld" \
  -DCMAKE_BUILD_TYPE=Release \
  ${CC:+-DCMAKE_C_COMPILER=$CC} ${CXX:+-DCMAKE_CXX_COMPILER=$CXX} \
  -DBUILD_LIST=core,imgproc,imgcodecs,highgui,videoio \
  -DBUILD_SHARED_LIBS=OFF \
  -DBUILD_ZLIB=ON -DBUILD_PNG=ON -DBUILD_JPEG=ON \
  -DWITH_TIFF=OFF -DWITH_WEBP=OFF -DWITH_OPENJPEG=OFF -DWITH_JASPER=OFF \
  -DWITH_OPENEXR=OFF -DWITH_AVIF=OFF -DWITH_JPEGXL=OFF -DWITH_IMGCODEC_GIF=OFF \
  -DWITH_OPENCL=OFF -DWITH_IPP=OFF -DWITH_LAPACK=OFF -DWITH_EIGEN=OFF -DWITH_ITT=OFF \
  -DWITH_GTK=OFF -DWITH_QT=OFF -DWITH_WAYLAND=OFF -DWITH_OPENGL=OFF \
  -DWITH_FFMPEG=ON -DWITH_GSTREAMER=OFF -DWITH_V4L=ON -DWITH_OBSENSOR=OFF \
  -DWITH_PROTOBUF=OFF -DWITH_CAROTENE=OFF -DWITH_FLATBUFFERS=OFF \
  -DWITH_UNIFONT=OFF \
  -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_opencv_apps=OFF

grep -q '#define HAVE_FFMPEG' "$bld/cvconfig.h" || {
    echo "FATAL: HAVE_FFMPEG missing from cvconfig.h — FFmpeg probe failed" >&2
    exit 1
}

# Reference build: -k because two AVX2 bfloat TUs ICE on host gcc 13 — the
# object files are irrelevant, only generator outputs are harvested. The
# cap_ffmpeg TUs however must COMPILE (API-compat window OpenCV5 x FFmpeg8):
# a real error there means the profile is broken, so check explicitly.
ninja -C "$bld" -k 9999 > "$bld/ninja-build.log" 2>&1 || true
for o in cap_ffmpeg_impl cap_ffmpeg; do
    ninja -C "$bld" -t targets all 2>/dev/null | grep -q "$o" || continue
done
if grep -E "cap_ffmpeg[^ ]*\.(cpp|hpp).*(error|Error)" "$bld/ninja-build.log" >/dev/null; then
    echo "FATAL: cap_ffmpeg failed to compile — OpenCV$version x FFmpeg API mismatch?" >&2
    grep -E "cap_ffmpeg" "$bld/ninja-build.log" | head -20 >&2
    exit 1
fi
ninja -C "$bld" -t commands > "$bld/ninja-cmds.log"

python3 "$here/gen_descriptor.py" "$src" "$bld" "$version" "$sha256" "$out"
echo "descriptor written: $out (configured on: $target)"
