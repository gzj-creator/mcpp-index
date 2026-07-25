# 仓库结构、schema、CI 与关键文件

## 仓库布局

```
pkgs/<x>/<name>.lua          描述符。<x> 取完整包名首字母(compat.* → c,nlohmann.json → n,imgui → i)
mcpp.toml                    workspace 清单(members 列表)
tests/examples/<member>/     每库测试工程(workspace 成员;<member> 为包名去前缀,模块包为
  mcpp.toml                  <name>-module)。恰好一条 [indices] <ns> = { path = "../../.." }
                             把所消费命名空间重定向到本 checkout(模块包用 default,
                             mcpp ≥ 0.0.97;单条是硬约束——xlings 多项目级 repo 静默失败,
                             mcpp#238,修复后再做根级集中化)。依赖按平台自门控
                             ([target.'cfg(...)'])
  tests/*.cpp                行为断言(独立 main,退出码非 0 即失败)
tests/check_mirror_urls.lua  lint:GLOBAL+CN 表完整性,以及 CN 指向 mcpp-res
tests/check_package_name.lua lint:身份规则 1+2(FQN 形式;层级在 namespace,short 原子)
tests/check_package_filename.lua lint:身份规则 3(描述符位于其身份的规范路径)
tests/list_cn_urls.lua       抽取 CN url,供 mirror-cn-reachable 使用
README.md                    索引说明与贡献入口
.github/workflows/validate.yml   CI:lint / mirror-cn-reachable / workspace(3 平台矩阵)
.agents/docs/<date>-*.md     设计文档惯例
docs/                        贡献者参考文档(本目录)
tools/gtc                    gitcode CLI,见 cn-mirror.md
tools/compat-ffmpeg/ 等      compat 大包的描述符再生成流水线
.xpkgindex.json              站点配置(标题、链接、install 模板),通常无需改动
```

## 外部仓库与文档

- mcpp 本体:https://github.com/mcpp-community/mcpp(本地通常存在 clone:
  `/home/speak/workspace/github/mcpp-community/mcpp`)。`mcpp --version` 应与 CI 对齐;feature 与 glob 行为以
  `src/manifest.cppm`、`src/modgraph/scanner.cppm`、`src/build/prepare.cppm` 为准。
- xpkg 扩展 schema(权威):
  https://github.com/mcpp-community/mcpp/blob/main/docs/04-schema-xpkg-extension.md(对应本仓 `.xpkgindex.json` 的
  “mcpp ext” 链接)。V1 xpkg spec 见 `d2learn/xim-pkgindex` 的 `docs/V1/xpackage-spec.md`(url-template 约在第 172 行)。
- CN 镜像组织:gitcode `mcpp-res`。

## 描述符 schema 速查(Form B inline)

`package` 必填字段:`spec`、`namespace`、`name`、`description`、`licenses`、`repo`、`type="package"`、`xpm`、`mcpp`。

### 包身份:`(namespace, name)` 的三条规则

包的身份是一个二元组 —— **`namespace` 是带层级的点分路径,`name` 是单一原子段**(mcpp 设计 2026-06-20 §4.2)。三条规则由 `tests/check_package_name.lua` 与 `tests/check_package_filename.lua` 机械强制,CI lint 秒级拦截。

**规则 1 —— `name` 必须写成完全限定名 `<namespace>.<short>`。**

```lua
namespace = "chriskohlhoff",
name      = "chriskohlhoff.asio",   -- ✅
-- name   = "asio",                 -- ❌ split 形式
```

split 形式能通过解析、也能过 mcpp 的身份闸门,但**装不上**:xlings/libxpkg 用 `package.name` 的**字面值**给索引建键(`build_index` → `entries[package.name]`),而 mcpp 按消费端写法重建 `<ns>.<short>` 去要 —— 两者永不相交,`E_NOT_FOUND`。这个缺陷曾让三个平台的 workspace job 各跑满 20~58 分钟才炸(mcpp#278,已于 mcpp 0.0.105 在引擎侧修复)。

**规则 2 —— 层级放在 `namespace` 里,`short` 必须是单一原子段。**

```lua
namespace = "mcpplibs.capi",  name = "mcpplibs.capi.lua",   -- ✅ 身份 = (mcpplibs.capi, lua)
-- namespace = "mcpplibs",    name = "mcpplibs.capi.lua",   -- ❌ short = "capi.lua"
```

两种写法都能被 mcpp 的归一化器接受,因为它按**最后一个点**切分 FQN —— 于是第二种会静默解析成 `(mcpplibs.capi, lua)`,一个描述符从未声明过的命名空间。规则 2 消灭这种自相矛盾:**声明的 namespace 与归一化算出的 namespace 永远是同一个字符串。**

**规则 3 —— 描述符放在其身份对应的规范路径上。**

| 命名空间 | 规范路径 |
|---|---|
| 空 或 `mcpplibs`(默认命名空间) | `pkgs/<short 首字母>/<short>.lua` |
| 其他 | `pkgs/<FQN 首字母>/<FQN>.lua` |

```
(mcpplibs, cmdline)       → pkgs/c/cmdline.lua
(compat,   zlib)          → pkgs/c/compat.zlib.lua
(aimol,    tensorvia-cpu) → pkgs/a/aimol.tensorvia-cpu.lua
(mcpplibs.capi, lua)      → pkgs/m/mcpplibs.capi.lua.lua
```

文件名**不是**身份的一部分(mcpp 身份优先解析,每个命中都要用文件自身的 `package.{namespace,name}` 复核),非规范命名的文件照样能解析。仍然要钉住它,是因为:① mcpp 的**发现**受候选文件名列表约束而非全索引扫描,规范路径让包命中第一个探测项,而不是落到 1.0.0 计划删除的 COMPAT 回退上;② 两个文件可以承载**同一个身份**而无人察觉 —— `pkgs/c/capi.lua.lua` 与 `pkgs/m/mcpplibs.capi.lua.lua` 曾是 `(mcpplibs.capi, lua)` 的字节级重复,目录扫描先到哪个哪个生效,对另一个的编辑是死的。

**零命名空间包是合法的一等形态。** 公开的默认命名空间模块包(`imgui` / `ffmpeg` / `opencv`)显式声明 `namespace = ""`,其**裸名就是 FQN**,消费端照常写 `imgui = "0.0.3"`。规则 2 对它们同样生效:一个带点却不声明命名空间的 `name` 会解析到一个哪儿都没写下来的命名空间。

`xpm.<linux|macosx|windows>.<裸版本>`:

- `url`:字符串,或 `{ GLOBAL=…, CN=… }` 表(本仓统一使用表形式)。
- `sha256`:必填,等于实际下载字节的摘要。

`mcpp`(常用键):

| 键 | 说明 |
|---|---|
| `language` | 通常为 `"c++23"` |
| `import_std` | 多数为 `false` |
| `c_standard` | C 源码:`"c99"` 或 `"c11"` |
| `modules` | module 库:`{ "x.y" }` |
| `include_dirs` | glob 列表,暴露给消费者的头目录 |
| `generated_files` | `{ ["相对路径"]="内容字符串" }`;mcpp ≥ 0.0.85 支持 Lua 长括号 `[==[…]==]` 多行字符串(推荐,可读可 review);转义单行串仍兼容 |
| `scan_overrides` | `{ ["glob"]={ provides={…}, imports={…} } }`;声明式扫描结果,命中文件跳过 M1 文本扫描(适用于带条件 import 守卫的上游模块单元,如 fmt 的 src/fmt.cc);构建期由编译器 P1689 输出自动对账,声明错误响亮失败(mcpp ≥ 0.0.85)|
| `sources` | glob 列表,编入 lib 的源码 |
| `cflags` / `cxxflags` / `ldflags` | 追加至对应规则 |
| `targets` | `{ ["name"]={ kind="lib"/"bin", main=…, soname=… } }` |
| `features` | `{ ["f"]={ sources={…} } }`,仅识别 sources |
| `deps` | `{ ["ns.name"]="ver" }`,扁平或点号式 |

## index 版本契约(index.toml)

仓库根的 `index.toml` 声明 `[index] min_mcpp` —— 能解析本索引全部描述符的最老
mcpp 版本。契约随树旅行:`publish_mcpp_index.sh` 把它打进 artifact,git clone 与
`[indices] path =` 本地索引天然携带。mcpp ≥ 0.0.85 在打开索引树时检查,违反时报
`E0006` + 升级指引(调试逃生口 `MCPP_INDEX_FLOOR=ignore`)。

规则(由 lint 机械强制,非纪律):**floor 先行、新文法在后**——lint 用 CI pin 的
mcpp 跑 `xpkg parse`(strict:未知键即失败),所以需要更新文法/键的描述符在
`MCPP_VERSION` 与 `min_mcpp` 同步提升之前物理上合不进 main。本地复现:
`mcpp xpkg parse pkgs/<x>/<name>.lua`。

## CI 行为(validate.yml)

- 触发条件:PR(改动 `pkgs/**/*.lua`、`tests/**`、`README.md` 或本 workflow)、push 至 main、nightly cron、手动触发。
- `env.MCPP_VERSION` 为全部 job 使用的 mcpp 版本,本地验证应与之对齐。
- `lint`(始终运行):lua 语法 `loadfile(f,'t')`;须含 `spec=`/`name=`/`xpm=`;禁止前导 v 版本;执行
  `check_mirror_urls.lua`;执行 `check_package_name.lua` + `check_package_filename.lua`(身份三规则,见
  上文「包身份」);再用 CI pin 的 mcpp 对每个描述符跑 `mcpp xpkg parse`(strict,未知键即失败)。
  自 `MCPP_VERSION = 0.0.105` 起,`mcpp xpkg parse` **自身**也强制规则 1(INV-NAME,mcpp#278),
  两个 lua lint 因此成为更早、更便宜的冗余闸门,而不再是唯一防线。
- `mirror-cn-reachable`(始终运行):逐个 `curl` CN url,均须返回 200。
- `workspace (linux|macos|windows)`:整个测试面就是一个 mcpp workspace,**唯一的构建/运行通道**——
  没有任何 shell 驱动的例外(公开模块包 imgui/ffmpeg/opencv/tinyhttps 也是普通成员,经成员级
  `[indices] default = { path = "../../.." }` 从 checkout 解析,mcpp ≥ 0.0.97)。
  - 选择性成员测试:PR 时由 `git diff` 将改动文件映射到受影响成员
    (`pkgs/<x>/<lib>.lua` → mcpp.toml 引用 `<lib>` 的成员;`tests/examples/<m>/**` → 成员 `<m>`),
    仅 `mcpp test -p <member>` 这些成员;workflow 本身、workspace 清单非成员部分、`tools/` 等
    全局性改动 → `mcpp test --workspace` 全量。push/nightly/dispatch 恒为全量。
  - `~/.mcpp/registry` 缓存携带工具链与已构建的 compat 包,重复运行增量很快。

## 本地 lint 复现(等价于 CI lint job)

```bash
fail=0
for f in pkgs/*/*.lua; do
  lua5.4 -e "assert(loadfile('$f','t'))" >/dev/null 2>&1 || { echo "SYNTAX $f"; fail=1; }
  for n in 'spec *=' 'name *=' 'xpm *='; do grep -q "$n" "$f" || { echo "MISS $n $f"; fail=1; }; done
  grep -nqE '\["v[0-9]+|\["[^"]+"\][[:space:]]*=[[:space:]]*"v[0-9]+' "$f" && { echo "LEADING-V $f"; fail=1; }
  lua5.4 tests/check_mirror_urls.lua "$f" >/dev/null 2>&1 || { echo "MIRROR $f"; fail=1; }
  lua5.4 tests/check_package_name.lua "$f" || fail=1
  lua5.4 tests/check_package_filename.lua "$f" || fail=1
done
[ $fail -eq 0 ] && echo "ALL LINT PASS"
```

## 合并后

`publish-artifact.yml` 在合并至 `main` 后自动重新发布 mcpp-index artifact 并移动指针,无需发布新的 mcpp 版本。
在线浏览地址:https://mcpplibs.github.io/mcpp-index/

## 案例索引

| 形态 | 描述符 | example | 设计文档 / PR |
|---|---|---|---|
| C 源码 + feature | `pkgs/c/compat.cjson.lua`、`compat.gtest.lua` | `tests/examples/cjson/` | `.agents/docs/2026-06-27-add-cjson-and-nlohmann-json-plan.md` / #48 |
| C++23 module(generated wrapper) | `pkgs/n/nlohmann.json.lua` | `tests/examples/nlohmann.json/` | 同上 / #48 |
| header-only + source-gated feature | `pkgs/c/compat.eigen.lua` | `tests/examples/eigen/` | `.agents/docs/2026-06-28-add-eigen-plan.md` / #50 |
| header-only(纯头) | `pkgs/c/compat.opengl.lua`、`compat.khrplatform.lua` | — | `.agents/docs/2026-06-03-gl-runtime-packages-plan.md` |
