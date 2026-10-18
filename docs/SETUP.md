# 部署与恢复手册（Windows）

本文覆盖三件事：**新机器从零装好**、**启动/重启 Bridge**、**数据目录或删除插件出问题时怎么恢复**。
架构与协议见 [README.md](../README.md)，硬件接线见 [voice-device/README.md](../voice-device/README.md)。

---

## 1. 新机器一次性安装

### 1.1 代码与 Python

```powershell
git clone <本仓库地址> desktop-ai-robot
cd desktop-ai-robot
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

要求 64 位 Python 3.11+（本机为 3.12.14）。`requirements.txt` 含 FastAPI、pyserial、numpy、PyAV、faster-whisper、kokoro-onnx 等。

### 1.2 安装 Harness 永久删除插件（离线）

Bridge 的"删除会话"依赖 DSH Host 的 `session.delete` / `session.purge` 路由；DSH 原生没有这两个接口。
仓库已在 `plugins/dsh-plugin-session-delete/` 附带 v0.3.4 的构建产物（MIT），不需要 GitHub 或 pnpm 联网：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_dsh_plugin.ps1
```

脚本会：
- 复制插件到 `%USERPROFILE%\.dsh\profiles\web\node_modules\`；
- 把该 profile 的依赖改成指向仓库内的 `file:` 路径；
- 把插件追加进 `dsh.profile.bundles`；
- 修改前备份 `package.json`。

重启 Bridge 后生效。只影响 `web` profile；桌面端自己的 profile 不动。

### 1.3 本地模型

模型不入库，放在数据目录下（默认 `%LOCALAPPDATA%\DesktopAiRobot`）：

```powershell
# 中文 Kokoro（必需，离线 TTS 兜底声线）
.\.venv\Scripts\python.exe scripts\download_kokoro.py
# 英文 Kokoro（中英混读时英文部分）
.\.venv\Scripts\python.exe scripts\download_kokoro_english.py
# Whisper small（按键录音转写；首次下载后运行时 local_files_only）
.\.venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; from pathlib import Path; import os; WhisperModel('small', device='cpu', compute_type='int8', download_root=str(Path(os.environ['LOCALAPPDATA']) / 'DesktopAiRobot' / 'models'))"
# 可选：派蒙 GPT-SoVITS（约 13 GB，独立 venv + CUDA）
powershell -ExecutionPolicy Bypass -File .\scripts\setup_paimon_tts.ps1
```

音频输出设置（音量/静音）、访问密钥、消息库、录音模型都在同一数据目录；**不要**把它们提交到 Git。

### 1.4 首次启动

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_bridge.ps1
```

首次运行会生成六位或随机访问密钥，保存在
`%LOCALAPPDATA%\DesktopAiRobot\access-token.txt`。浏览器打开 `http://127.0.0.1:8787`，用该密钥登录。

---

## 2. 启动、重启与日志

```powershell
# 已运行时只报告，不会重复拉起
powershell -ExecutionPolicy Bypass -File .\scripts\start_bridge.ps1

# 改了代码 / 模型 / 插件后重启（会一并停掉 Paimon 与 Bridge 自启的 Harness Host）
powershell -ExecutionPolicy Bypass -File .\scripts\start_bridge.ps1 -Restart
```

脚本会先把数据目录钉在 `%PROGRAMDATA%\DesktopAiRobot\data-dir.txt` 记录的位置，再启动 uvicorn。
Bridge 运行日志为数据目录内的 `bridge.runtime.log`，达到 2 MiB 自动轮转，保留 `.1` 至 `.3` 三份历史。
`bridge.stdout.log` / `bridge.stderr.log` 捕获启动与第三方标准输出，每次启动前保留最近三份历史；Harness Host 日志 `harness-bridge.log` 独立管理。

手动启动等价于：

```powershell
$env:ROBOT_DATA_DIR = "$env:LOCALAPPDATA\DesktopAiRobot"
.\.venv\Scripts\python.exe -m uvicorn bridge.app.main:app --host 127.0.0.1 --port 8787 --no-access-log
```

开机自启建议用"任务计划程序 → 登录时运行"，操作填
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<仓库>\scripts\start_bridge.ps1"`，
不要安装成系统服务（服务账户的 `LOCALAPPDATA` 与桌面用户不同，会再次出现数据目录分叉）。

---

## 3. 数据目录分叉（密钥突然失效）怎么恢复

Bridge 用 `%PROGRAMDATA%\DesktopAiRobot\data-dir.txt` 锚定唯一数据目录。
从被打包应用（会重定向 `LOCALAPPDATA`）、管理员 shell 或服务账户启动时，解析出的目录可能不同；
此时 Bridge 会**拒绝启动**并报 `DataDirConflict`，而不是悄悄新建空库。这是保护，不是故障。

排查：

```powershell
Get-Content "$env:PROGRAMDATA\DesktopAiRobot\data-dir.txt"   # 锚定目录
Test-Path "$env:LOCALAPPDATA\DesktopAiRobot\access-token.txt"
```

三种处理方式，按优先级：

1. **用锚定目录启动**（推荐）：直接运行 `start_bridge.ps1`，它会读取锚点。
2. **显式指定**：`$env:ROBOT_DATA_DIR = "D:\somewhere\DesktopAiRobot"` 后再启动。
3. **确实要换库**：确认新目录里有真实消息库和模型后，用一次
   `$env:ROBOT_ALLOW_INIT = "1"` 启动以重新锚定；随后移除该变量。

**2026-10-17 本机已做过的迁移**：真实数据原本被 Codex 的 `LOCALAPPDATA` 重定向写到
`...\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\DesktopAiRobot`，
而锚点指向一个只有随机密钥和空库的副本。已把真实目录整体移回
`%LOCALAPPDATA%\DesktopAiRobot`（本机访问密钥（不写入文档或 Git）、0.88 GB 模型、12.8 GB 派蒙、真实历史）。
旧副本保留在 `%LOCALAPPDATA%\DesktopAiRobot.stale-20261017-200318`，确认无用后可删除。

> **不要**在码库根目录放 `data/`、`models/` 或 `access-token.txt`；`.gitignore` 会拦截，但迁移时容易混淆。

---

## 4. 硬件与固件

- 设备：ESP32-S3（16 MB flash / 8 MB PSRAM），原生 USB `303A:1001`。
- 固件：`voice-device-1.8`，`voice-device/` 下用 PlatformIO 编译烧录。
- 接线：见 `voice-device/README.md` 的固定引脚表；功放 VIN 必须单独接 5V/VBUS，共地。
- **烧录前必须停 Bridge**，否则串口被占用：

```powershell
# 先停 Bridge（会一起停 Paimon / Harness Host）
# 再烧录
cd voice-device
pio run -t upload
# 烧完把 Bridge 拉回来
powershell -ExecutionPolicy Bypass -File ..\scripts\start_bridge.ps1
```

改固件时必须同步提升 HELLO 里的 `firmware` 版本号，否则 `/api/status` 分不清板上版本。

---

## 5. 验证清单

```powershell
# 1) 离线测试（不需要硬件）
.\.venv\Scripts\python.exe -m pytest bridge\tests -q     # 当前 116 passed

# 2) 服务健康
Invoke-RestMethod http://127.0.0.1:8787/health

# 3) 自动登录本地 Bridge 并导出脱敏连接诊断（不打印密钥）
.\.venv\Scripts\python.exe scripts\check_bridge.py
```

应看到 `connected=True`、`port=COM9`、`firmware=voice-device-1.8`、`device_bad_crc=0`、
`screen_cached_frames=64`、`face=1`。

**PowerShell 中文提示**：`Invoke-RestMethod -Body '{"text":"你好"}'` 在 Windows PowerShell 5.1 会按
非 UTF-8 编码发送，服务端收到问号，表现为"没有音频"或 500。测试中文接口时必须显式转字节：

```powershell
$json = '{"text":"你好，机器人"}'
Invoke-RestMethod http://127.0.0.1:8787/api/tts/speak -Method Post `
  -ContentType 'application/json; charset=utf-8' `
  -Body ([Text.Encoding]::UTF8.GetBytes($json)) -WebSession $s
```

浏览器端 `fetch` 始终是 UTF-8，不受影响。

**Hermes 会话策略（0.22.1+）**：Hermes 的 API 只允许写入 `api_server` / `bot_room` 来源的会话，桌面端（`desktop`）会话是只读的；写入会返回
`409 permission_denied`。Bridge 已改为默认续接自己的 API 会话，没有就新建，并在目标为桌面会话时提前给出中文提示。网页 Hermes 分组里历史桌面会话仍可查看，
但按键或发送前请选中一个新会话（`+ 新建`）。新建的 API 会话也会出现在 Hermes 桌面端列表里，可继续查看。

---

## 6. 手机访问（Tailscale）与安全边界

Bridge 始终只绑定 `127.0.0.1`。手机不是直连 8787，而是通过 Tailscale Serve 的 HTTPS 反代进入。
当前机器已验证的形态（tailnet only，未开 Funnel）：

```powershell
# 1) 让 Bridge 接受该主机的 Host 头（User 级环境变量，重启 Bridge 生效）
setx ROBOT_TAILNET_HOST "<machine>.<tailnet>.ts.net"
# 2) 发布本机 8787（只需配置一次；--bg 表示后台常驻）
tailscale serve --bg 8787
# 3) 检查：应显示 https://<machine>.<tailnet>.ts.net -> http://127.0.0.1:8787
tailscale serve status
```

手机与电脑需登录同一 tailnet，然后打开 `https://<machine>.<tailnet>.ts.net` 并输入访问密钥。
非本机访问时登录 Cookie 自动带 `Secure` + `HttpOnly` + `SameSite=Strict`。

验证（在电脑上即可完成，不必等手机）：

```powershell
Invoke-WebRequest https://<machine>.<tailnet>.ts.net/ -UseBasicParsing
# 登录后 /api/status 应返回 device.connected=True
```

注意事项：

- **不要**开 `tailscale funnel`，也不要做路由器端口映射。
- `ROBOT_TAILNET_HOST` 由 `main.py` 严格校验为单个 `*.ts.net` 主机名；填错会导致 Bridge 启动失败。
- 六位密钥只适合本机/私人 tailnet；一旦要跨设备长期使用，删掉 `access-token.txt` 重启以换回 32 字节随机密钥。
- 连续 5 次登录失败会按来源锁定 5 分钟。
- Hermes API 密钥、DSH Cookie、模型权重、消息库都不得提交。

---

## 7. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `DataDirConflict` | 锚点与本次解析目录不一致 | 用 `start_bridge.ps1`，或设 `ROBOT_DATA_DIR` |
| 删除会话报"扩展尚未加载（HTTP 404）" | Harness profile 缺插件 | 运行 `scripts\install_dsh_plugin.ps1` 后 `-Restart` |
| 删除会话报"仍被 Harness 占用" | 会话有未完成轮次 | 等回复结束；不要强删 |
| 设备不出现 | USB 线仅供电 / 驱动 / 端口被占 | `Get-PnpDevice -Class Ports`；确认 `303A:1001` |
| 有画面但无声 | 功放 VIN 接错、SD 未接 3V3、静音 | 查接线与 `/api/audio/output`；`speaker_ready` 应为 true |
| 派蒙不可用 | 服务未起或模型缺失 | 看 `tts-paimon\logs\api.log`；可临时切 Kokoro |
| 按键语音报 Hermes 409 `session_busy` | 目标会话正在回复 | 等桌面端/上一轮结束再按，或换一个会话 |
| 按键语音报 Hermes 409 `permission_denied` | 目标会话是 Hermes **桌面端**会话，API 不允许写入 | 在网页 Hermes 分组点“+ 新建”，选中新会话后重新按键或发送 |
| 中文 TTS 测试失败但网页正常 | PowerShell 编码 | 见第 5 节 UTF-8 写法 |


## 6. 日常启动和诊断（2026-10-18）

双击仓库根目录 `start-robot.cmd` 会启动 Bridge 并打开本机网页。已有服务不会重复启动；加载更新使用 `scripts/start_bridge.ps1 -Restart`。不自动安装开机任务。

网页侧栏的“下载连接诊断”会导出设备、AI 服务、音量与最近观察到的任务阶段。它不包含聊天内容、录音、转写、访问密钥、Cookie、会话 ID 或本机路径。也可运行：

```powershell
.\.venv\Scripts\python.exe scripts\check_bridge.py
node --test web-client\tests\ui-state.test.cjs
```

USB 断开后，旧录音与播报失效；已经发送的 AI 消息继续保留在文字会话，重连后不会自动重发。请求超时不能等同于“没有执行”，请先核对会话再手动重试。Harness 已永久删除会话的确认 ID 保存在本机数据库，用于过滤 Host 内存目录的旧条目，不保存聊天副本或归档。


## 7. Bridge 0.2.0 数据与日志维护

正式启动入口仍是 `start-robot.cmd` 或 `scripts/start_bridge.ps1`，内部使用 `python -m bridge.run` 并限制监听回环地址。手动使用旧 uvicorn 命令启动可继续工作，但不会加载新的日志轮转配置。

启动前对现有数据库执行只读 `quick_check`，检查预算约 3 秒。损坏或版本高于当前程序时停止启动，保留原数据库；不会自动重建、覆盖或恢复聊天记录。临时占用或检查超时会标记为 `deferred`，可在诊断里看到，稍后重启复查。启动检查通过只说明当时的完整性，不代表运行中的数据库会被持续扫描。

诊断增加版本、运行时长、数据库检查结果、日志大小与磁盘剩余空间。空间低于 1 GiB 时网页提示；本程序不自动删除聊天、模型或其他文件。聊天记录不做自动备份，继续遵守永久删除规则。

日志轮转只管理 Bridge 自己的运行日志与启动输出；派蒙、Harness 等独立进程的日志不在这个轮转策略内。运行日志可能包含本机路径和异常堆栈，请使用“下载连接诊断”分享故障信息，不要直接上传原始日志或数据目录。

故障测试使用临时数据库和临时数据锚点；不要用真实数据目录执行破坏性的数据库修复实验。
