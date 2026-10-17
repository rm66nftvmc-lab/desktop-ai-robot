你是接管 `D:\Codex工作区\desktop-ai-robot`（手工做的桌面 AI 对话机器人）的开发助手。用户说中文，**要求先给结论、再讲理由**，大改动前先确认方案，倾向把大任务拆成小步确认。

## 第一步（必做，不要跳）

按顺序读完这些文件，以它们为唯一事实来源，不要凭猜测开工：

1. `C:\Users\55243\Documents\Obsidian Vault\10-Notes\桌面AI机器人开发交接.md`
   —— 交接笔记：完整状态表、四轮开发记录、硬件接线、待办与已知问题
2. `D:\Codex工作区\desktop-ai-robot\README.md`
3. `D:\Codex工作区\desktop-ai-robot\voice-device\README.md`
   —— 固件、引脚、表情管线、编译与烧录流程

## 当前已验证状态（不要重做）

- 固件 **`voice-device-0.4` 已烧录**：8 张开源角色表情（「deepseek 娘」图集，MIT）经游程编码存进主控 flash，已**逆时针旋转 90°**（`build_faces.py` 的 `ROTATE_CCW = 90`）。Flash 28.0%、RAM 6.1%。
- Bridge（FastAPI，只绑 `127.0.0.1:8787`）+ 网页端 + 本地 faster-whisper STT 已可用；「按键录音 → 转写 → Hermes 回复 → 朗读」闭环已实物验证。
- 豆包：方案①已落地（`start-doubao-edge.cmd`，CDP 端口 **9222**），**已验证可 attach 并读到页面，且该专用目录已是登录态**；适配器尚未写。
- DeepSeek 官方供应商已删除；当前 `provider: ark` + `model.default: deepseek-v4.1-flash`（走 Ark coding 端点）。**DeepSeek 官方与 Ark 是两套不通用的模型名，别混。**

## 第一优先任务：给屏幕角色加「简单版」动画

用户原话：

> 做动画，不要做这么复杂的，只需要简单一点的就行，不同的状态，比如在待机的时候，收听东西的时候，再思考的时候，在回答的时候，在修改问题响应的时候动画都不一样，找你觉着最符合的就可以

已实测的约束（**不要重新测量，直接用**）：

- 只给用户点名的状态做循环、**每状态 4 帧**（**不要 6 帧**）：约 5 个状态 × 4 帧 ≈ **1560 KB**，装得进 2364 KB 余量，**不需要改分区表**。
  （8 状态 × 6 帧 = 3026 KB 才装不下——那是被否掉的复杂方案。）
- 唯一必须动的是写屏速度：`lcdDrawFace` 现在**每像素调用 2 次 `SPI.transfer`**、SPI 仅 20 MHz，一帧 240×240 就是 115,200 次调用，单帧线速下限 46 ms、**估算实际 100–170 ms**，6 帧循环不到 1 fps。
  **最简修法 = 行缓冲（480 字节）+ `SPI.writeBytes` 批量发送，SPI 提到 40 MHz**（约 15 行改动，不动架构）。
- **不要**引入帧间差分、调色板量化、`esp_lcd` + DMA、自定义分区表——用户明确要简单。
- 图集每行本就是 6 帧连续动画；行语义在 `build_faces.py` 的 `ROW_NAMES`。`揮手` 行只有 4 帧。
- 不用烧录就能预览：`scripts\render_faces_animation.py`（复用 `compose()`，逐点一致）。

## 硬性规则（违反会造成真实损害）

- **改固件必须同时升 `voice-device/src/main.cpp` 里 HELLO 载荷的版本号**，否则 `/api/status` 分不清板上是哪一版。
- **烧录前必须停 Bridge**（它独占 COM9），**烧完无论成败都要拉回**：在 `D:\Codex工作区\desktop-ai-robot` 下运行
  `.\.venv\Scripts\python.exe -m uvicorn bridge.app.main:app --host 127.0.0.1 --port 8787 --no-access-log`
  停进程用 PowerShell 的 `Stop-Process`，**别用 `taskkill //F`**（MSYS 会吃掉参数）。
- **不要手改 `config.yaml`**，用 `hermes config set`。
- **绝不索要、接受或显示任何密钥/密码**（API key、access token 等都算）。
- **不要开始手机的远程访问**——用户要求先把设备与网页端调好；Bridge 不得暴露到公网。
- 不要把「网页只保存消息」说成已自动收发。
- 用户说「停止」就立刻停手，不要再执行工具调用。

## 构建环境

- `pio` 在 `C:\Users\55243\.local\bin\pio.exe`（**不在 PATH 上**，需显式调用）
- 工具链 1.9 GB 已装好；平台 `espressif32@6.12.0`、Arduino 框架、ESP32-S3-DevKitC-1、串口 COM9
- 图像脚本用项目 venv：`D:\Codex工作区\desktop-ai-robot\.venv\Scripts\python.exe`（依赖含 Pillow，已装）

## 完成标准

跑 `.\.venv\Scripts\python.exe -m pytest bridge\tests -q`（当前 50 passed），并把进展补写进那篇 Obsidian 交接笔记。
