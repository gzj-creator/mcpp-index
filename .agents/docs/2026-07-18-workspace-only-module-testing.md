# workspace-only 模块包测试(mcpp 0.0.97 / R6 落地)

日期:2026-07-18 · PR:feat/mcpp-097-workspace-only-ci

## 背景

公开模块包(namespace = "",即内建 mcpplibs 默认命名空间:imgui/ffmpeg/opencv/
tinyhttps)此前无法像 compat.* 一样经 `[indices] <ns> = { path }` 指回本仓 checkout
——mcpp 没有重定向**默认命名空间**的语法。合并前验证只能走每包一个的 reseeding
smoke shell(临时 MCPP_HOME + 物理拷贝 checkout 覆盖默认索引落盘位置)+ 专属 CI
job,是 zero-shell 立仓哲学下唯一的例外通道。

mcpp 0.0.97 落地了 `[indices] default = { path = ... }`(亦接受 `""` 键;url 形式
显式报错),并且根级 `[indices]` 的相对 path 按 **workspace 根**解析、成员自动继承
(#224)。例外通道的存在理由消失。

## 变更

1. **mcpp pin 0.0.96 → 0.0.97**(env + 3 平台矩阵)。
2. **成员级 default 重定向**(根级集中化被 mcpp#238 挡住,见下"过程发现"):
   每个成员保持/新增恰好一条 `[indices]`;模块包成员用
   `default = { path = "../../.." }`(V0 spike 实证:假版本号 999.0.0 只存在于
   本地副本仍可解析,`""`/`default` 两种键均可)。
3. **4 个模块包 smoke → workspace 成员**:
   - tests/examples/tinyhttps(已有工程,登记成员;三平台描述符,不门控);
   - tests/examples/imgui-module(cfg(linux) 门控——描述符虽三平台,但只有
     linux 被 CI 验证过,按已验证面转换;老 smoke 的 llvm@20.1.7 钉不再携带:
     它早于 gcc16 模块支持,imgui-m 上游 CI 现以 gcc@16.1.0 构建模块层);
   - tests/examples/ffmpeg-module、tests/examples/opencv-module(包本身 linux-only,
     cfg(linux) 门控 + 非 linux no-op main)。
   测试源码逐行移植自对应 smoke 的消费工程(断言不变)。
4. **删除**:tests/smoke_{tinyhttps,imgui,ffmpeg,opencv}_module.sh、validate.yml 的
   imgui-module/ffmpeg-module/opencv-module 三个 job 与 workspace job 里的 tinyhttps
   smoke 步骤、`mcpp index update` 前置步骤(#232 已修,V0 冷环境实证:无 PATH/apt
   nasm 时从沙箱同步解析)。
5. **文档**:README 贡献段、docs/repository-and-schema.md(布局 + CI 行为两节,
   顺带清掉两代前的 detect/smoke-examples 残留描述)、add-mcpp-index-package skill
   (成员化流程、`mcpp test -p` 本地验证)。

## 过程发现:xlings 多项目级 repo 静默失败(mcpp#238)

首版实现走的是 #224 根级集中化(根一次声明 5 个命名空间、删全部 per-member
块)。本地验证发现:成员沙箱 .xlings.json 一旦注册 ≥2 个项目级 index repo,
`xlings interface install_packages` 对任意包静默 exit 1(无 error 事件)——与
repo 名、URL 无关,纯数量触发。既有成员从未暴露(每成员恰好 1 条);根级继承让
每个成员变成 5 条,全部未缓存安装即挂。已提 mcpp#238(含最小复现矩阵);本 PR
退回单条声明形态,修复后再集中化。连带影响:模块成员的传递 compat 依赖
(opencv → compat.opencv5)从**已发布**的全局 compat 索引解析,而非本 checkout
(compat 描述符的合并前验证由其专属成员覆盖,见成员注释)。

## 语义差异(接受)

smoke 曾额外覆盖"物理重播默认索引"这一机制本身;成员形态覆盖的是我们真正关心的
**合并前描述符正确性**,消费的仍是真实已发布 tarball(Form A 下载源不变)。
选择性成员测试机制对新成员零配置生效(pkgs/<x>/<lib>.lua → grep 引用成员)。

## 效果

- CI job 数 8 → 5(lint、mirror-cn-reachable、workspace×3);模块包验证并入
  `mcpp test --workspace`,新模块包只需加成员目录,不再复制 shell。
- 后续 compat.opencv 合一(B0)、opencv 0.0.3 升版等改动的回归 = 改一行 + CI。
