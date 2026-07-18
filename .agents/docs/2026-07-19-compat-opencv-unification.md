# compat.opencv 合一 + v2 de-stub + FFmpeg videoio 后端 + compat.ffmpeg 瘦身

日期:2026-07-19 · 分支 feat/compat-opencv-unification(基于 workspace-only PR)

## 决策背景(用户拍板)

1. compat.opencv 只保留一份:老 install()-CMake 4.13 形态删除,`compat.opencv`
   直接采用源码直编形态(原 compat.opencv5 的演进版);compat.opencv5 过渡期保留,
   opencv 模块包切换依赖后删除。
2. compat.ffmpeg / compat.opencv 简洁性优化都做。
3. F2(videoio↔ffmpeg)并入本次 regen——只跑一次参考构建。

## compat.opencv v2(源码直编形态的 0.0.97 演进)

- **de-stub**:mcpp 0.0.97 修了 #233(对象路径消歧)+ #234(空格 defines 引号),
  v1 的 457-TU 全量转发 stub 层撤销。sources = 真实 tarball 路径,385 个文件按
  目录 glob/花括号交替(#228)压到 **19 条**;快照 dispatch stub 以
  `mcpp_generated/**` 直接进 sources;flags 改真实路径 glob
  (`**/modules/<mod>/**` 同时覆盖 tarball 与快照两侧)。
- **仍走 build.mcpp 的**:字体 blob2hdr、OpenCL kernel 嵌入(cl2cpp)、
  libjpeg-turbo BITS_IN_JSAMPLE=12/16 重复编译 stub(43 个,同一 .c 三次编译
  是构建语义,普通 sources 表达不了;stub 文件名加组前缀保证唯一 basename,
  规避 mcpp#239 的绝对路径对象逃逸)。
- **FFmpeg videoio 后端**:参考构建 WITH_FFMPEG=ON(本地静态 FFmpeg prefix +
  pkg-config 探测;gen_config.sh 自动构建该 prefix);cap_ffmpeg 进 videoio 组
  (组 defines 带 HAVE_FFMPEG/HAVE_FFMPEG_LIBAVDEVICE);描述符
  `deps = { ["compat.ffmpeg"] = "8.1.2" }` —— **compat 依赖 compat 首例**
  (V0 spike 玩具实证 + 本描述符实测:传递解析、头传播、链接闭包全通)。
  注意描述符键是 `deps` 不是 `dependencies`(误写会被 build 静默忽略,
  `xpkg parse`/lint 会拦,mcpp#237)。
- 版本键仍 5.0.0(内容修订);111KB → 100KB。
- 参考坑:HAVE_FFMPEG 不落 cvconfig.h,按 TU `-D` 传递(校验要看
  ninja-cmds.log 里的 cap_ffmpeg);gcc13 在 libswscale/output.o 也 ICE
  (FFmpeg prefix 用 xlings gcc16 构建,FFMPEG_CC)。

## compat.ffmpeg 瘦身(B4)

- gen_descriptor.py 加目录 glob/花括号压缩(与 opencv 同法,FFMPEG_SRC 树上
  验证"整目录编译才发目录 glob"):2281 条显式 sources → **28 条 glob**;
  展开集与原列表逐文件相等(脚本断言);其余段 byte 级一致。337KB → 267KB。

## 测试

- tests/examples/opencv 成员重写:compat.opencv 5.0.0(cfg(linux) 门控),断言
  imgproc/imgcodecs + **真实 mp4 编→解码回环**(CAP_FFMPEG 双向,10 帧)——
  这同时是 R3 视频主线在 compat 层的验收;本地 `mcpp test -p opencv` 通过。
- tests/examples/opencv5 成员与 pkgs/c/compat.opencv5.lua 过渡期保留
  (已发布 opencv 0.0.2 模块 tarball 依赖它),opencv-m v0.0.3 切换后删除。

## R4:unifont feature(随本 PR)

- `pkgs/c/compat.opencv-unifont.lua`:数据资产包 —— 上游 opencv_3rdparty 原始
  `WenQuanYiMicroHei.ttf.gz`(GLOBAL 直取 raw.githubusercontent,CN 镜像
  mcpp-res/opencv@unifont-1.0.0,sha256 钉,MD5 与上游 CMake pin 一致)。
  裸 .gz 不是归档:安装器把它字节保真地放到 store 共享 `data/runtimedir/`
  (实测),verdir 只有元数据 → 描述符带 asio 式 anchor-TU 空壳 mcpp 段。
- `compat.opencv` 新 feature `unifont`(0.0.97 features 已支持 deps/defines
  门控):`deps = { ["compat.opencv-unifont"] = "1.0.0" }` +
  `defines = { "HAVE_UNIFONT" }`;build.mcpp 见 `MCPP_FEATURE_UNIFONT=1` 时按
  `MCPP_MANIFEST_DIR/../../../runtimedir/<fname>`(fallback:verdir 扫描)找到
  字体并 blob2hdr 成 `builtin_font_uni.h`(符号 OcvBuiltinFontUni,与 cmake
  ocv_blob2hdr 逐字节同构)。无 MCPP_DEP_<NAME>_DIR 契约变量是已知空洞
  (待提 mcpp 增强)。
- 成员 tests/examples/opencv-unifont:长式依赖
  `opencv = { version = "5.0.0", features = ["unifont"] }`,断言
  `FontFace("uni")` 可用(该内建字体面只在 HAVE_UNIFONT 下存在——本身即
  feature 探针)且 CJK putText 出墨;默认成员回归不受影响。

## 合并门槛(先决条件)

**mcpp#240**:#233 消歧后可执行目标的链接输入未跟随改名——依赖包与消费者源文件
同 basename(OpenCV 带 modules/{imgproc,geometry}/src/main.cpp,消费者入口几乎
都叫 src/main.cpp)即 `'obj/main.o' missing and no known rule`。成员测试文件名
不撞可以绿,但**发布后真实用户必踩**——本 PR 必须等 mcpp 修复发版 + CI pin 升级
后再合并。(2 文件最小复现已附在 issue。)

## 后续

- opencv-m v0.0.3(R1+R2)切依赖 `compat.opencv = "5.0.0"` → index 升 opencv
  0.0.3 → 删 compat.opencv5.lua + opencv5 成员 + README 过渡注记。
- R4 unifont / R5 dnn 以 feature 挂在本包(gen_config 的 profile 分支)。
