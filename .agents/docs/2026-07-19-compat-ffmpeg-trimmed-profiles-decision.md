# compat.ffmpeg 裁剪档(decode-min 等 profile 变体)——设计决策与暂缓依据

日期:2026-07-19 · 结论:**暂缓实现,等 mcpp#242;设计已定型如下。**

## 为什么现在做不了

1. **features 是加法语义**:裁剪档要求"从全量里减",唯一表达 = 基础源集改为
   min、`full` feature 补齐其余。为不破坏已发布消费者(ffmpeg 模块包 0.0.1
   期望全量),包侧需 `default = ["full"]`(Feature System v2 已支持)——但
   **消费端没有 default-features 关闭语法**,min 永远退不回去。已提 mcpp#242
   (含 cargo 式拼写建议)。
2. **config 快照随组件集变化**:config_components.h/.asm 按 profile 不同,
   generated_files 不可 feature 化。方案:包内新增 build.mcpp,内嵌两份
   config 快照,按 MCPP_FEATURE_FULL(或其缺席)落盘对应一份 ——
   compat.opencv 的 build.mcpp 合成模式已验证同类机制可行,这半边不需要
   mcpp 改动。

## 落地顺序(#242 发版后)

1. gen_config.sh 增加 min-profile configure 变体(F0 的 decode-min 配置,
   源列表推导管线复用);gen_descriptor.py 输出双快照 + feature 分段
   (`full` gates 全量源集差集)+ 新增 build.mcpp。
2. `default = ["full"]`:既有消费者零感知;min 消费者
   `ffmpeg = { version, default-features = false }`。
3. 成员测试:min 消费端断言 h264 decoder 存在 + 某 encoder 缺席(负向验证)。

## 与"功能完整性"的关系

ffmpeg-m 本身已是 100% 全功能(2281 TU 全组件),裁剪档是**体积优化**而非
功能补全,不阻塞 R 系列其他项。
