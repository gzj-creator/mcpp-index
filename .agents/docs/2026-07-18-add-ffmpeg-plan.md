# 收录 compat.ffmpeg 8.1.2 — 全源码直编形态(新形态首例)

> 日期: 2026-07-18
> 来源: mcpplibs/ffmpeg-m 项目派生(该仓调研+POC 文档为完整背景:
> `ffmpeg-m/.agents/docs/2026-07-18-ffmpeg-m-{research-and-plan,implementation}.md`)

## 形态判定:第五种形态——"全源码直编"(config 快照 + 源列表)

FFmpeg 属第三方上游 (a),但不落入既有四形态:它**不用 install() 跑外部构建系统**
(openblas/opencv 形态),而是把上游 `./configure` 的产物一次性冻结进描述符,由
mcpp 直接编译全部源码:

- `generated_files`:15 个 configure 产物(config.h、config_components.{h,asm}、
  config.asm、avconfig.h、ffversion.h、9 个 `*_list.c`)≈ 240KB 内联 —— 对冻结的
  (target, profile) 是确定性纯文本;
- `sources`:2281 条精确清单(2124 `.c` + **157 NASM `.asm`**),`make -n` 推导
  (ground truth,含 `_select` 闭包);
- `flags`(mcpp 0.0.95 per-glob):每库 `BUILDING_<lib>` define + `.asm` 的
  `-Pconfig.asm`;NASM 的 `-I` 由 mcpp 自动从 include_dirs 馈送;
- 消费者构建期**零 configure/make/cmake**;nasm 按 PATH → sandbox → xlings 惰性
  解析(xim 已收录)。

描述符由 `ffmpeg-m/tools/gen_descriptor.py` 自动生成(329KB,勿手改);升级
FFmpeg = 重跑生成器 + review diff。

## 配置档位

`--disable-autodetect --disable-programs --disable-doc`,其余全默认:全部内部组件
(600+ decoders / 272 encoders / 358 demuxers / muxers / filters / 7 库全build),
**LGPL-2.1+**(无 gpl/version3/nonfree),零宿主库探测(hermetic)。

## 平台

**linux(x86_64)only**(先例:compat.x11)。config 快照与源列表是 target 相关的
(x86 编 NASM,aarch64 编 GAS `.S`);macOS/Windows 待各自快照生成后追加
(ffmpeg-m 的 macOS CI job 已在产 gen/macos-aarch64 artifact)。

## 镜像

- GLOBAL: `https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.gz`(官方发行物,
  sha256 `32faba5e…8bf22`,两次计算一致)
- CN: `https://gitcode.com/mcpp-res/ffmpeg/releases/download/8.1.2/ffmpeg-8.1.2.tar.gz`
  (gtc 建仓+发布,已验证 200 + 字节一致)

## feature 评估

v1 无 feature。组件裁剪(slim 档)需要**成套**的 config 快照 + 源列表(features
仅门控 sources,无法切换 generated_files),属"档位=独立版本/包"问题,与
compat.opencv 的结论一致;待需求出现再议。

## 验证(mcpp 0.0.95,与本 PR bump 后的 CI pin 一致)

- `tests/examples/ffmpeg` 构建 16.3s(32 核),运行输出
  `ffmpeg 60.26: decoders+demuxers(358) ok`;
- 断言:三库 major 版本(60/62/62)、h264/hevc/av1/aac 解码器存在、demuxer>300;
- .asm 验证:157 个 `.asm.o` 全部产出,最终二进制含 3260 个 ssse3/avx2 符号;
- 本地 lint 五项全过(语法/必填/无前导v/镜像表/`mcpp xpkg parse`)。

## 注意事项

- **本 PR 将 `MCPP_VERSION` 0.0.94 → 0.0.95**:描述符的 per-glob `flags` 键是
  0.0.95(#223)语法,0.0.94 的 resolver grammar lint 会拒绝(这正是"floor first,
  new grammar after"规则的预期行为)。
- 上游源列表与 git tag n8.1.2 逐字节一致(已比对);ffversion.h 冻结为 "8.1.2"。
- 相关 mcpp issue(ffmpeg-m 项目产出):#226(-iquote 相对路径)、#227(flags
  数组表)、#228(glob 花括号)、#229(依赖包 cfg 条件 sources——macOS 支持前置)。
