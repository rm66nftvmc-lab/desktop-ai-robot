# 桌面 AI 机器人：软件层

## 当前维护状态（2026-10-20）

显示角色与回复声线绑定：DSH Pet 使用派蒙，Emotion Ball 使用球球普通话／英文。选择动画会同步保存声线，重启保持绑定；中英文试听、自定义测试文本和播放按钮统一放在“显示动画”图标面板中。独立语音工具入口及球球广东话选项已移除；派蒙英文仍沿用现有英文片段处理方式。目标语音模型未安装时会明确报错，保留原显示选择。

Bridge 的输入草稿按 AI 和会话分别保存于当前浏览器标签页，切换会话或刷新后可恢复；主动退出登录会清除草稿，删除会话只清除已确认删除项的草稿。草稿不发送给 AI，浏览器禁用存储时仍可在当前页面内保存。发送期间切换会话或继续输入，不会被旧请求的返回结果误清；未确认发送结果的请求不会自动重发。手机切到后台时暂停网页轮询，回到前台立即更新状态和消息。

显示参数沿用用户选择的 1.51 配置（当前固件 1.52 更新舞台素材）：标称 90 Hz 扫描档、90 次/秒画面更新目标、100% 软件画面亮度与约 220 毫秒动作过渡。实际传图速度受场景和处理耗时限制，闪烁根因仍未确认；后续 Bridge 维护不改动该设置。

## 当前显示主题

Emotion Ball 保留，可切换蓝发小女仆动画：录音、思考、说话分别对应不同动作，另有八个待机随机动作，动作结束后等待 8–22 秒。完整素材在主控 Flash 内离线播放，168×168 角色区域与暮色背景预合成，打包素材为 40 fps，保持原动作时长，主控重复显示补足画面更新次数并使用局部刷新。详情见 [设备说明](voice-device/README.md)。

固件 1.52 将 DSH Pet 舞台上移 20 像素，让角色脚底贴近台面，并去掉屏幕底部文字；Bridge 动画面板和素材声明中的来源署名保留。

素材来自 [PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)，固定提交 `c6f96350d9307bd6c23bc6ea31974e76a719a8b6`。上游代码 MIT；动画素材许可另行限制为非商业使用并要求来源署名，见 [素材声明](voice-device/assets/dsh_pet/NOTICE.md)。


当前工作状态与后续事项见 [PROJECT_STATUS.md](PROJECT_STATUS.md)；新机器部署、数据目录恢复和排错见 [docs/SETUP.md](docs/SETUP.md)。屏幕闪烁的已测结果与无仪表排查方案见 [docs/SCREEN_FLICKER_NO_TOOLS.md](docs/SCREEN_FLICKER_NO_TOOLS.md)。

**2026-10-19 · 固件 1.13 / Bridge 0.3.0**：固件只保留 Emotion Ball（球球），已移除鲸鱼娘的位图、解压器和动画帧缓存；设备开机直接显示球球，保持 60 Hz 动作与差分刷新。旧主题选择自动迁移到球球，网页移除“原角色”选项。球球视觉参考 sam70361/aora-bot，仅供个人非商业学习使用，详见 [素材许可说明](voice-device/assets/qiuqiu/README.md)。

**2026-10-17 晚 · 硬件实测 + 完整性修复**：设备 `COM9` / `voice-device-1.8` / CRC 0 / 64 帧 PSRAM 缓存已在线确认；派蒙与 Kokoro 均经机器喇叭实际播放并收到全部下行回执。Bridge 真实数据目录此前被 Codex 的 `LOCALAPPDATA` 重定向分叉（锚点指向空库），已整体迁回 `%LOCALAPPDATA%\DesktopAiRobot` 并保持六位密钥 `<本机访问密钥>` 不变。缺失的 Harness 永久删除插件已按 MIT 附带进 `plugins/dsh-plugin-session-delete`，新增离线安装脚本 `scripts/install_dsh_plugin.ps1`；用一个一次性 Harness 会话验证了"建会话 → 回答 `bridge-ok` → 永久删除"闭环。新增 `scripts/start_bridge.ps1` 固定数据目录启动/重启。测试 **98 passed**。本轮还从主机端验证了 Tailscale Serve 的 HTTPS 登录与安全 Cookie、中文 TTS→Whisper 转写回环、两个本地草稿的批量删除，以及设备物理按键录音被 Whisper 正确转写；那次 Hermes 因目标会话正忙返回 409（新建临时 Hermes 会话问答与删除均成功），现在 409 会显示 Gateway 的错误码与说明。仍需用户实测：会话空闲时完整走一遍"按键→回复→朗读"、手机实体页面、多个原生会话的批量删除。

三个目录各司其职：

| 目录 | 职责 |
|---|---|
| `voice-device/` | ESP32-S3 固件：按键、I2S、屏幕和 USB CDC 传输 |
| `bridge/` | 电脑常驻进程：认证、设备连接、会话、语音和适配器 |
| `web-client/` | 手机/电脑共用的纯文字网页对话框，没有麦克风入口 |
| `plugins/` | Bridge 的 Harness Host 所需的随仓库插件（离线可装） |

## 历史实现与验证记录（当前状态以 PROJECT_STATUS.md 为准）

**2026-10-15 按键语音跟随网页会话**：网页选择 AI/会话后，通过认证同源 `POST /api/voice/target` 同步并持久化按键目标。按下录音时冻结该目标，录音期间切换网页只影响下一次录音；本轮转写带 `conversation_id` 进入选中的 Hermes / DeepSeek Harness 会话，两者回复均自动排队朗读。下一轮按键取消原智能体的旧语音任务，丢弃过期转写/回复。静音继续仅显示文字。无会话、会话失效或豆包 PPT 不会回退发送 Hermes；审批口令只作用于同一 AI/会话的待审批请求。后台标签页轮询不抢路由，最近主动选择或获得焦点的网页控制单个机器人。76项测试通过；在线验证两个目标的会话路由同步成功，设备连接正常，派蒙/音量设置保持。新版本物理按键全流程仍需用户在刷新网页后实测。

**2026-10-15 会话侧栏上线**：侧栏“会话”可折叠，按 Hermes / DeepSeek Harness 分组展示原有会话、切换历史和新建；豆包 PPT 无会话管理。输入框里的新建勾选项已移除。声线选择与测试语音改为设备连接状态旁的图标浮层，不常驻占用侧栏。`GET/POST /api/sessions` 管理列表与本地空会话，`/api/messages` 用 `session_id` 显式路由。空会话首次发送才创建原生会话，随后绑定，连续排队消息不会重复新建；会话选择保存在浏览器当前会话存储。历史只显示用户/助手文字，不显示系统指令、工具参数或推理。新模块 `bridge/app/conversations.py`，Bridge 数据库新增 `conversations` 表和 `messages.conversation_id`，不直接修改 AI 原生数据库。70 项测试通过；在线已验证 Hermes 12 个会话 / 当前历史151条、Harness 32个会话 / 当前历史125条读取正常。页面视觉仍受内置浏览器观察权限限制，需用户刷新查看。

**2026-10-15 最新：DeepSeek Harness 文字会话已接入**。网页“对话目标”新增 DeepSeek Harness，经本机官方 Web Runtime 接口续接最近的顶层桌面会话，消息独立保存，只有勾选新建才主动另开会话。实测 Bridge 消息 19/20 完成问答，回答 `bridge-ok`；65 项测试通过。适配器在 `bridge/app/harness.py`，默认程序 `D:\deepseek harness桌面端\DeepSeek Harness.exe`，可用 `ROBOT_HARNESS_EXE` 覆盖。后台只监听 `127.0.0.1:3081`，使用官方登录 Cookie，不对公网开放；从桌面 patch 只读取默认模型与现有 provider 配置，不修改原配置。原会话被桌面端持有时需先退出桌面端，不能同时写入，也不会自动新建绕过。当前接入文字发送、续接、完整回答和消息下的手动朗读；机器人按键语音及网页工具审批仍接 Hermes，尚未扩展至 Harness。

**2026-10-17 Harness 会话永久删除**：DSH 原生 `session/delete` 不存在，Bridge 旧删除操作因此返回 404。已将固定版本 `dsh-plugin-session-delete` v0.3.4 安装到 Bridge 专用的 `.dsh/profiles/web`，不改桌面 profile；`bridge/app/harness.py` 调用宿主认证的删除、立即 purge 接口，只有 Host 确认 purge 成功后才清理 Bridge 本地记录。插件的短暂 staging 会在同一请求中立即 purge，不会保留归档副本；purge 失败会请求恢复会话并报错。Harness 专用删除接口已通过无效 ID 的无副作用探测（HTTP 400），Bridge 状态、Harness 连接和设备连接均正常。Bridge 删除流程有测试覆盖；没有用真实用户会话做破坏性测试。全量测试 87 项通过。

**派蒙中英混读修正**：旧逻辑遇到任一英文字母就将整段回复切成 Kokoro，已改为按文字片段路由：中文派蒙、仅英文 Kokoro。用户实测纯派蒙英文难以听懂，明确选择此方案；派蒙服务不可用时报错，不再静默整段切换声线。音量上限仍 0.12，音量/静音设置不变。网络已找到 Dolyfin 英文派蒙 RVC 候选（约5.28 GB），它是语音转语音模型，需英文 TTS 后另做变声；目前未下载、安装或试听，不能当成已接入声线。

**2026-10-17 音量微调**：网页侧栏音量滑块与静音按钮仍保留；100% 对应当前最高输出，滑块可降低。按用户试听反馈将派蒙和 Kokoro 的目标响度从 0.015 RMS 提高到 0.0225 RMS，保留峰值限制以控制削波；等待实物试听确认。静音立即取消播放和排队播报，后续仅显示文字；设置保存在本机 `audio-output.json`，重启保留。

Hermes Gateway 只监听 `127.0.0.1:8642`，使用独立的随机长密钥，存放在 `%LOCALAPPDATA%\DesktopAiRobot\hermes-api-key.txt`；它与网页六位访问密钥分开。Hermes 等待工具审批时，网页会显示命令与说明。语音提示只朗读简短说明，批准前请在网页核对命令全文；语音识别结果只有严格匹配“同意审批”或“拒绝审批”才会提交决定。Gateway 接口不可用时，移除该密钥文件并重启 Bridge 可退回原命令行问答，但命令行模式不能处理中途审批。

Bridge 已能在本机接收网页文字、按 Hermes / 豆包 PPT 网页分别保存消息，并显示 ESP32 是否握手连接。**Hermes 0.22.1 起，Runs API 只允许写入 `api_server` / `bot_room` 来源的会话；桌面端（`desktop`）会话是只读的，强行写入会返回 409 `permission_denied`。** 因此 Bridge 现在默认续接自己创建的 API 会话（没有就新建一个），不再把消息送进桌面会话；网页 Hermes 分组里的桌面会话仍可查看历史，但按键/文字发送前请选择 API 会话或点“+ 新建”。2026-10-17 已用专用会话“桌面机器人专用会话”实测两轮问答（`机器人已就绪`、`链路正常`），无 409。豆包 PPT 网页仍只保存消息。固件 `voice-device-1.8` 已烧录：待机/思考 24 帧、朗读 16 帧，光流补帧后预缓存到 PSRAM；保留原动作时长，实际不同画面约 22 帧/秒，用户确认“顺滑了，画面正常”。设备通过带 CRC 的 USB 帧与 Bridge 握手、发送心跳和按键事件，并在按键启动收音时上传 16 kHz 单声道 PCM。按键结束收音后，Bridge 用本地 `faster-whisper small` 将语音转成文字，自动作为 Hermes 消息保存并发送；Hermes 回复自动进入本地 Kokoro 语音合成，经 USB 由机器人朗读。2026-10-14 已用实物确认“按键录音 → 本地转写 → Hermes 回复 → 自动朗读”闭环可用。屏幕显示 8 张**角色表情**作为桌面宠物的回应方式，素材是 MIT 授权的开源桌面宠物图集「deepseek 娘」（`f0909172434/deepseek-girl-codex-pet`）：`scripts/build_faces.py` 按 (行, 列) 从 8×11 图集切格、游程编码后编译进 flash，断电不丢、运行时不联网，设备在按键/播放/断连时自动换脸，电脑可用 `0x0C FACE` 帧覆盖 THINK / APPROVE / ERROR。映射已按上游 README 的行语义逐一对齐（BOOT=揮手、THINK=工作中、APPROVE=審查中、ERROR=失敗）。**固件 0.4 历史记录**：角色按 `build_faces.py` 的 `ROTATE_CCW = 90` **逆时针旋转 90°** 显示（生成阶段无损旋转，固件零改动）；当时 Flash 28.0%、632 KB 表情经符号表确认在镜像内。当前固件与动画背景实现见 `voice-device/README.md`。细节见 `voice-device/README.md`。新一轮按键会中止上一轮朗读，并取消尚未完成的上一轮语音 Hermes 请求；旧回复若迟到，不会再朗读。网页会标出语音消息，并可试听最近一次录音。识别模型运行时只从本地缓存加载。音频下行使用主控回执控制发送量，USB 接收队列设为 8 KB。播放过程中曾出现 USB 断连，功放 VIN 当时接主控 3V3；最终接法为功放 VIN 单独接 5V/VBUS，共地，SD 接 3V3。历史 Kokoro 测试时音量倍率为 0.21（当前上限已降至 0.12，见上方更新）；约 25 秒多句播报的 561 个音频帧均收到回执，设备保持连接，用户确认整段无杂音、音量能听清，也没有 USB 断连提示。

网页使用聊天布局：用户消息显示在右侧蓝色气泡，Hermes 回复显示在左侧，并标出发送与回复状态。设备工具收在侧栏。网页和静态资源均返回 `Cache-Control: no-store`，避免 Edge 与内置浏览器分别显示过期版本；两个浏览器的登录 Cookie 仍各自独立。

保留的原有声线为离线 Kokoro `zf_001` 女声，中文与常见英文词由本地发音词典处理。安装依赖后运行 `.\.venv\Scripts\python.exe scripts\download_kokoro.py`，会从 [kokoro-onnx 模型发布页](https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.1) 下载量化模型与女声包，并从 [原模型仓库](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh) 读取配置，保存在 `%LOCALAPPDATA%\DesktopAiRobot\models\tts`。下载可续传；文件完整就绪后 Bridge 自动使用女声，缺文件时仍用 Windows 本地中文语音。模型在 Bridge 启动时预加载，长回复分段合成并尽早开始播放。语音合成只在电脑运行，网页状态会显示当前声线。

可选试听声线：用户选择试用 `cbw364/deepseek-dafeiyu` 项目所用的 GPT-SoVITS 派蒙模型。该公开项目没有附带模型文件；当前可下载版本由第三方转存，分享页说明分享者不是原作者，原作者仓库标注“严禁商用”。因此仅作为本机个人试听，不用于商业或公开发布。派蒙和 GPT-SoVITS 都安装在 `%LOCALAPPDATA%\DesktopAiRobot\tts-paimon`，使用独立 Python 环境；Bridge 仅访问绑定 `127.0.0.1:9880` 的本地服务，并强制模型库离线。首次安装可运行 `powershell -ExecutionPolicy Bypass -File .\scripts\setup_paimon_tts.ps1`，需下载 CUDA 运行时和若干 GB 的模型。安装完成后重启 Bridge，在“设备与语音工具”选择派蒙即可试听；随时切回 Kokoro。派蒙声线当前仅用于中文，含英文的文本会继续使用 Kokoro。派蒙服务异常时接口报错、不会静默改声线，可在“设备与语音工具”手动切回 Kokoro；切换不会改动或覆盖原有 Kokoro 模型。

**2026-10-15 派蒙安装与实物试听完成**：默认中文声线已选为派蒙，用户确认“清晰，音量合适，保留派蒙”。本地生成的测试语音经机器人播放，132 个新增下行帧全部收到确认，设备持续连接、CRC 为 0。Kokoro 原模型与网页切换入口保留；选择备份为 `%LOCALAPPDATA%\DesktopAiRobot\tts-voice.before-paimon.json`。中文前端明确使用 `all_zh`，避免自动语言识别触发联网下载；含英文仍走 Kokoro。RTX 5070 Laptop 的 PyTorch 2.7.1+cu128 运算已通过实测。安装脚本使用 `scripts/requirements-paimon.txt` 的独立中文推理依赖，并由 `scripts/prepare_paimon_runtime.py` 修复旧版代码的 jieba、Torch checkpoint 与 librosa 参数兼容问题；HuBERT、RoBERTa、G2PW 与声线文件均校验下载，未使用不必要的 v4 底模。Bridge 全量测试 **56 passed**。

网页连续点击不同消息的“让机器人朗读”时，新请求先取消当前播放；若前一条仍在合成，新请求会让它失效。设备端会先收到上一轮的 `AUDIO_END`，再收到新音频，避免两段音频帧交叉。

服务只监听 `127.0.0.1:8787`，目前不对局域网或公网开放。访问密钥首次启动时随机生成，保存在当前 Windows 用户的 `%LOCALAPPDATA%\DesktopAiRobot\access-token.txt`；本机密钥已按用户要求改为六位数字，连续 5 次登录失败会锁定该来源 5 分钟。聊天记录保存在同目录的 `messages.sqlite3`。这台电脑上的数据目录已限制为当前 Windows 用户与 SYSTEM 可读写。不要把访问密钥发给其他人或提交到仓库。将来启用手机远程访问前，应换回高强度随机密钥，且只通过加密私有网络开放。

安装依赖（已有项目虚拟环境时跳过第一行）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 离线安装 Harness 永久删除插件（仓库已附带，不访问 GitHub）
powershell -ExecutionPolicy Bypass -File .\scripts\install_dsh_plugin.ps1
```

从仓库根目录启动（推荐；会自动固定真实数据目录、检查模型并等待健康检查）：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_bridge.ps1
# 改代码/模型/插件后
powershell -ExecutionPolicy Bypass -File .\scripts\start_bridge.ps1 -Restart
```

等价的手动命令是：

```powershell
.\.venv\Scripts\python.exe -m uvicorn bridge.app.main:app --host 127.0.0.1 --port 8787 --no-access-log
```

电脑浏览器打开 `http://127.0.0.1:8787`，从上述本机文件复制访问密钥登录。当前没有手机远程入口，也未启用 Windows 开机自启；等认证、适配器与设备链路完成后，再通过加密私有网络接入，绝不直接映射路由器公网端口。

Bridge 为以后私有网络访问预留了 `ROBOT_TAILNET_HOST` 环境变量，只接受一个明确的 `*.ts.net` 主机名；未设置时仍只接受 `localhost` 和 `127.0.0.1`。这**不会**启用外网访问，服务始终绑定 `127.0.0.1`。真正的远程入口须在确定手机与现有 VPN 的兼容方式后单独配置 Tailscale Serve；不要启用 Funnel 或路由器端口转发。

已下载的离线模型缓存位于 `%LOCALAPPDATA%\DesktopAiRobot\models`。若在另一台电脑部署，首次下载模型可运行：

```powershell
.\.venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; from pathlib import Path; import os; WhisperModel('small', device='cpu', compute_type='int8', download_root=str(Path(os.environ['LOCALAPPDATA']) / 'DesktopAiRobot' / 'models'))"
```

识别工作线程使用 `local_files_only=True`，不会在处理语音时尝试联网。最后一次录音仅在 Bridge 进程内存保留，登录后可从 `/api/recording/last.wav` 获取供调试；进程退出即清除。最近 20 条转写也只在内存中。用户说话内容不会上传给模型提供方。

## 按用户确认的实施顺序

1. **Bridge + 文字网页基础**：本机登录、消息入库、设备发现、每个来源单独历史。当前已完成。
2. **ESP32 与 Bridge 的真实链路**：版本化 USB CDC 帧、校验、心跳和自动重连；按键按一次收音、再按一次停止，麦克风 PCM 只传到本机。按键和音频上传已实测。
3. **本地语音链路**：本地 STT、TTS 与喇叭下行已接入。按键录音、中文识别、自动发送 Hermes、自动朗读回复已在实物上连贯测试；扬声器播报已由用户确认清晰且音量合适。播放期间不上传麦克风音频，按键可打断播放并开始收音。唤醒词暂缓，词句由用户以后确定；不使用云语音服务。VAD 尚未接入。
4. **执行适配器**：Hermes 文字问答已通过本机 Gateway Runs API 接入。Hermes 0.22.1 不允许 API 写入桌面端会话，所以默认续接 Bridge 自己创建的 API 会话（没有就新建），网页上也可显式新建；桌面会话只读查看。中途工具审批可在网页选择仅同意本次或拒绝，也可通过设备按键说“同意审批”或“拒绝审批”。豆包 PPT 网页（入口 `https://www.doubao.com/office/ppt`）标签页复用仍待实现；**网页版 DeepSeek 已按用户要求移除**。
5. **手机安全访问**：网页只有文字输入；使用加密私有网络和 Bridge 鉴权，无公网开放端口。之后加文件投递、进度和开机自启。

本项目按后续对话修正了 Obsidian 原稿中的 `edge-tts` 云语音、手机语音输入、PTT 长按及唤醒词默认值；以用户最新确认的需求为准。





局域网无线 Bridge 正在开发验证，当前实物在 Wi-Fi 启动时触发欠压保护，USB 备用可用；尚未完成无线语音验收。实现、配置和故障证据见 [无线 Bridge 记录](docs/WIFI_BRIDGE.md)。
