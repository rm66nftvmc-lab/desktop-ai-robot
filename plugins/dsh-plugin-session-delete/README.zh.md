---
description: "在 Web 侧边栏永久删除一个对话，并批量清理从未使用过的空会话。"
kind: "package-reference"
---

# dsh-plugin-session-delete

[English](README.md) | 中文

一个 [DSH](https://github.com/deepseek-ai/deepseek-harness) 插件:**真正从磁盘删除一个对话**,
外加批量清理空会话。

## 安装

```sh
# 从 GitHub 安装 —— 用 https 形式(原因见下方提示)
dsh plugin --profile <profile> add https://github.com/SereinHK/dsh-plugin-session-delete.git

# 或者用挂在 Release 上的打包文件:装的那台机器不需要 git
dsh plugin --profile <profile> add https://github.com/SereinHK/dsh-plugin-session-delete/releases/download/v0.1.2/dsh-plugin-session-delete-0.1.2.tgz
```

或者把同一个 spec 粘进侧边栏的 **Plugins** 页。包自带 bundle 补丁(`dsh.bundle.patch`),
那一行插件行会被自动插入,不需要手改 profile 的 `cordis.patch.yml`。
装完刷新窗口(或那个实例)即可;`lib/` 随仓库提供,安装时不编译任何东西。

> **两种分发形式,同一个包。** git 地址是项目自己用的方式,跟随分支;Release 上的 tarball
> 是同一份字节的冻结快照,而且**装的那台机器不需要装 `git`** —— pnpm 只是照常拉一个 https 地址。
> 两者装出来的东西完全一样:tarball 里同样带 `lib/`、`cordis.patch.yml` 和声明 bundle 补丁的清单。
>
> **没有发布到 npm。** 仓库就是分发渠道,所以直接写包名的 registry 形式
> (`dsh plugin --profile <profile> add dsh-plugin-session-delete`)解析不到 —— 请用上面那个
> `https://…` 地址。
>
> **请用 `https://…` 地址,不要用 `github:owner/repo` 简写。** pnpm 会把简写规范化成
> SSH 地址(`git+ssh://git@github.com/…`),在任何没配 GitHub SSH key 的机器上直接失败。
> 两种写法指向同一个提交,但 https 只需要一个公开仓库。
>
> 桌面应用自带包管理器,所以从 Plugins 页安装不需要 `pnpm` 在 `PATH` 上;
> 直接用 `dsh plugin` 命令则需要。

**版本要求:DSH 0.2.x。** 本插件注册的会话行菜单槽位
(`sidebar.workspaces.session.menu.item`)在 0.1.x 那条线上**不存在** ——
在那个构建上只可能出现侧边栏的清理入口。实测环境:`@deepseek-ai/dsh-desktop-runtime` 0.2.0-rc.2。

**卸载**:在 Plugins 页移除,或 `dsh plugin --profile <profile> remove dsh-plugin-session-delete`;
从源码目录装卸用 `node install.mjs --uninstall`。

## 概要

补上 DSH **刻意没有**提供的那一个破坏性动作:**真正从磁盘删除一个对话**。

- `sidebar.workspaces.session.menu.item` —— 每个会话 `...` 菜单里的红色
  **「删除对话」**，排在自带的 pin/rename/fork/archive 之后。
- `sidebar.footer.action` —— 设置旁的 **「清理空会话」**：一次删掉所有
  `blank: true`（从未开始过任何一轮对话）的空会话。
- `shell.overlay` —— 两个确认框，都会先列出「到底要删什么」。
- Node 面在 Connection 的 `/api` 认证围栏内注册**五条**路由：`POST /api/session.delete`（把对话移入回收站）、
  `POST /api/session.unused` 报告每个会话的**持久事实**（日志是否从未使用过、最后一次提问时间）、
  `POST /api/session.trash`（回收站列表，回答前先清掉过期项）、`POST /api/session.restore`、
  `POST /api/session.purge`（彻底删除一个或全部）。
  两个入口都走这一条路由。

删除不可恢复：会话根目录下该会话的整个目录（含全部格式世代）与它的投影缓存记录
一并删除。已导出的文件、附件与工作区文件不受影响。

## 使用

会话行的 `...` 菜单多出一行：

```
置顶 / 重命名 / 派生 / 归档
─────────────────────────────
删除对话                     ← 本包，order 900，danger
```

对话框先说明是哪个对话、删什么范围，然后才提供「永久删除」。删除成功后 Host 发
`api-session/removed`（列表行立刻消失），浏览器再拉一次权威列表。

清理入口会先列出发现的空会话（工作区路径 + 闲置时长），再给出带数量的确认按钮；
执行时逐个删除，结束后报告 `已删除 / 失败 / 跳过`。

### 什么会被跳过，为什么

| 情况 | 行为 | 原因 |
|---|---|---|
| 对话正被某个窗口打开 | Host 返回 `409 session-live` | 它的写句柄会把日志写回来或写坏 |
| 空会话最近一小时内还有活动 | 客户端计划里跳过 | 「新建会话」也是空会话，别的窗口可能正停在上面 |
| 空会话的 Agent 正在运行 | 客户端计划里跳过 | 那不是被遗弃的草稿 |
| id 不是会话 id 形状 | Host 返回 `400 invalid-session-id` | id 会变成一个路径段，任何路径操作之前先校验 |
| 目标不是 `<root>/<项目>/<编码 id>` | Host 返回 `500 unsafe-target` | 递归删除前最后一道闸 |
| 附件（`<DSH_HOME>/attachments`） | 绝不触碰 | 内容寻址、跨会话共享、没有引用计数 |

### 失败

路由返回 `{ ok: false, error: { code, message } }`；对话框用当前语言翻译它自己拥有的
错误码（`session-live`、`session-not-found`、`unsafe-target`），下面再附 Host 原始诊断。

## 实现要点

`SessionPersistence` 只有 `create`/`open`/`flush`/`stat`/`list`，`/clear` 只清选中，
归档只隐藏行 —— 所以「删除」必须由插件自己完成。本包按 JSONL 后端的真实布局寻址：

```
<root>/<projectKey(header.cwd)>/<encodeSegment(sessionId)>/session[.vN].jsonl[.zstd]
<root>                                        → dshHomePath('sessions')
```

`projectKey` 与 `encodeSegment` 是逐字复刻（后端没有导出），并由测试套件**对着真实会话
根目录**做断言。根目录下的目录扫描作为兜底，因此布局变化只会退化成
`session-not-found`，不会删错地方；`containmentRefusal` 还会再确认目标正好在根目录下一层、
且以编码后的 id 命名。

整个交互只用一个路由而不是 Typert Remote：插件的浏览器面在没有仓库内生成器的情况下
无法产出 `./remote` 贡献，而 `ctx.connection.fetch.register` 正是「插件自有端点」的官方缝，
并且天然继承 Host/Origin + 浏览器令牌围栏。

## 对着哪个版本写的

| 项目 | 值 |
|---|---|
| 运行时 | `@deepseek-ai/dsh-desktop-runtime` 0.2.0-rc.2（cordis 4.0.4） |
| 槽位 | `sidebar.workspaces.session.menu.item`、`sidebar.footer.action`、`shell.overlay` |
| Host 服务 | `connection`、`sessionPersistence`、`sessions` |
| 浏览器种子模块 | `react`、`@deepseek-ai/dsh-client-ui-primitives` |
| 存储 | JSONL 会话后端 `dshHomePath('sessions')`；投影缓存 `dshHomePath('storages')/session_projcache` |

## 已知边界

- **活会话删不掉**，这是契约里有意的另一半：先切走再删才是被支持的路径。
  如果核心提供 `SessionPersistence.remove` 加一个 session-controller 端点，Host 就能先停止并
  释放该会话；提案见本工作区的 `docs/upstream-issue-session-persistence-location.md`。
- **删父会话会留下孤儿子会话**：子会话日志各自独立（`parentSession` 只是 lineage 元数据），
  `sessionQuery.traceSession` 会退化成「第一个解析不到的父级」而不是报错。
- **没有回收站、不能撤销**：删除就是对会话目录 `rm -rf`；重要的对话请先用 `/export` 导出。
- **故意不做版本门禁**：app-boot 会把 `@deepseek-ai/dsh-*` peer 和运行时版本比对，
  所以 `^0.2.0` 会拒绝正在运行的 `0.2.0-rc.2`。本包按稳定的服务/槽位形状编程，
  宁可使用时明确报错，也不肯拒绝挂载。
- 这里没有手写 README.i18n.yaml：那些分节哈希由仓库工具生成
  （`pnpm run verify-translation-pairing --write …`）。

## 开发说明

仓库用 `pnpm run bundle`（tsdown）构建。本工作区没有工具链，所以同一份 `lib/` 由
`tools/build.mjs` 从这些源码生成（用 Node 自带的类型剥离），并把 `src/client/*` 模块图
拼成 Host 原样提供的 `window.__ModuleLoader__.load({ id, factory })` 脚本。
两份产物随后由 `tools/verify-artifact.mjs`（对构建产物跑 87 项路由断言）、`tools/verify-browser.mjs`
（69 项渲染与交互断言，含拒绝路径）和
`tools/verify-boot.mjs`（读取运行中应用的浏览器插件图）验证。

```sh
node --test "tests/*.test.ts"   # 21 个测试：Host 路由、清理计划、词典对齐
```
