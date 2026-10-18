# ESP32-S3 语音设备端

这个文件夹只放 ESP32 固件和设备侧资源。当前固件为 `voice-device-1.8`：待机、思考各 24 帧，朗读 16 帧，原始帧之间使用双向光流生成 3 张过渡帧，包含循环首尾。过渡画面保持 45 ms，重复传屏 3 次；完整动作仍为待机/思考 1,080 ms、朗读 720 ms。64 张动画画面已预解码到 8 MB PSRAM（7,372,800 字节），播放时不再解压。40 MHz SPI、完整帧缓冲和局部更新。用户已确认“顺滑了，画面正常”。

固定接线：INMP441 SCK/WS/SD 为 GPIO4/5/6；MAX98357A BCLK/LRC/DIN 为 GPIO15/16/17；轻触开关 GPIO1 到 GND；屏幕 CS/DC/RES/SDA/SCL 为 GPIO8/9/10/11/12，BLK 暂不接。

功放最终接线：VIN 单独接主控明确标注的 5V/VBUS，GND 接主控 GND，SD 接 3V3，BCLK/LRC/DIN 分别接 GPIO15/16/17，GAIN 暂不接。喇叭两根线分别夹在绿色端子 `+`、`−`，`−` 不接 GND。麦克风、屏幕 VCC 继续接 3V3，不能把 5V 与它们的 3V3 红轨相连。功放 VIN 原接 3V3 时，较长时间播放曾导致 USB 断开重连；5V 接法下约 25 秒连续测试的 561 个新增音频帧均收到确认，设备持续连接。Bridge 在语音片段之间补静音帧并对片段作淡入淡出，输出音量倍率固定为 0.21；用户确认多句播报无杂音、音量能听清，也没有 USB 断连提示。

当前按键 Toggle：按一次开始上传 16 kHz PCM，再按一次停止；播放语音时按键可打断并开始收音。语音识别、任务选择和远程访问不进入固件。

## 屏幕表情（桌面宠物的回应方式）

### 当前实现（固件 1.8，已通过实物确认）

用户反馈 1.7 有改善但仍卡顿；1.8 将不同画面提高到约 22.2 帧/秒，保留原动作时长。`INTERPOLATION_STEPS=4`，总共 69 张资源（64 张动画帧 + 5 张静帧），2,424,686 字节压缩素材。Flash 2,715,765 / 3,342,336 字节，静态 RAM 32,324 / 327,680 字节；帧缓冲与 PSRAM 缓存为动态分配。

设备实测 64 张缓存全部成功；连续每约 3 秒增加 67 次不同画面更新、200–201 次重复传屏，画面打包约 3.2–3.4 ms、待机局部传屏约 12 ms；uptime 连续增长、CRC 为 0。19 项相关测试通过，包含全部压缩帧解码及循环变化区域校验。用户明确确认“顺滑了，画面正常”，当前保留此版本。

### 历史实现（固件 1.7，过渡帧动画）

`scripts/build_screen_assets.py` 使用 OpenCV 双向 Farneback 光流，在每对原始帧之间插入两张过渡画面（包括循环首尾），采用预乘 alpha 处理透明边缘，并保留变化范围之外的原图像素。开发依赖记录在 `requirements-dev.txt`。预览为 `faces-screen-smooth.gif`，过渡对照为 `faces-interpolation-preview.png`。

素材预先与渐变背景合成并转为大端 RGB565，以 zlib 压缩写进固件，共 53 张画面、1,904,598 字节素材，未扩大 app 分区。运行时解压到 115,200 字节帧缓冲，再打包变化矩形并传屏；解压器的 Huffman 表放在静态内存，避免默认 8 KB loop 栈溢出（1.6 初次试烧发生此问题，1.7 已修正）。保留 20 MHz SPI，源画面间隔 60 ms、重复刷新槽 30 ms；调度保持完整循环时长，遇到延迟跳过过期槽而不积压。

COM9 实测 1.7：每约 3 秒合成 50–51 张不同画面、传屏 100–101 次，解压约 14 ms、待机局部传屏约 22–23 ms，帧号覆盖 0–17，uptime 连续增长、CRC 为 0。19 项相关测试通过，包括对全部压缩画面逐一解压与循环局部变化范围校验。仍待用户目视评价流畅度、重影或变形。

### 历史对照（固件 1.5，重复帧测试）

用户确认 1.4 三次重复后闪烁明显减轻。1.5 再提高为每个源帧重复传送 4 次，刷新槽 45 ms，源帧仍为 180 ms，整组动作时长不变；已编译并烧录。设备报告固件 1.5，连续 3 秒传屏次数增加 67、源帧更新增加 17，设备连接正常，CRC 为 0。等待用户比较四次重复与三次重复的效果。

用户要求提高重复呈现次数并保持动作总时长，1.4 将每个源帧重复传屏 3 次，间隔 60 ms；源帧仍保持 180 ms，待机/思考一轮 1,080 ms，朗读一轮 720 ms。重复传送直接复用已合成的缓存，计时按固定时钟推进；发生长时间阻塞时跳过过期刷新槽，若跳过多个源帧则完整重绘角色区，避免误用相邻帧的局部变化范围。已烧录 COM9 并验证固件 1.4：每 3 秒传屏增加 50 次、源画面合成增加 17 次（边界取样会有 ±1），设备持续连接，CRC 为 0。保持 20 MHz SPI，等待用户目视反馈。18 项相关测试通过。

用户确认 1.1 动画连续但整个背景仍闪；1.2 新增 `FRAME_ANIMATION=0x0D`（一个字节 0 暂停、1 恢复），Bridge 提供登录保护的 `POST /api/device/animation`，请求为 `{"enabled":false}` 或 `{"enabled":true}`。暂停后帧号固定，用户确认静止画面不闪。1.3 保留完整帧缓冲，将面包板接线上的 SPI 时钟从 40 MHz 降至 20 MHz；已烧录、哈希校验通过，设备连接正常，动画开启，传屏实测约 23.8 ms。仍待用户确认降频效果。相关测试 18 项通过。

1.1 将 RLE 解码、背景混合与屏幕传输分成两个阶段：合成时 LCD 保留上一帧，完成后单次 `SPI.writeBytes` 连续发送。缓冲区优先分配内部 RAM，失败时使用 PSRAM。设备状态增加 `screen_buffer`、`compose_us`、`push_us`，Bridge 对应保存 `screen_buffer`、`screen_compose_us`、`screen_push_us`。COM9 实测待机合成约 12.8–12.9 ms、传屏约 12.6–12.9 ms，缓冲区已分配、CRC 为 0；尚待用户确认实物频闪改善情况。编译 Flash 2,214,753 / 3,342,336 字节，静态 RAM 21,004 / 327,680 字节（帧缓冲为动态分配，不计入该静态 RAM 数字）。

屏幕使用本地生成的青蓝至紫色渐变背景。`scripts/create_screen_background.py` 生成 `assets/aurora-gradient.png`，再由 `scripts/build_screen_assets.py` 编译到 `src/screen_assets.h`：240×320 RGB565 背景和透明角色帧。角色仍按 `ROTATE_CCW = 90` 方向显示。待机和思考使用 6 帧、朗读使用 4 帧，其余状态使用静帧。动画周期为 180 ms，屏幕仅重绘相邻帧变化的矩形；切换表情时完整重绘角色区。生成器会拒绝空白帧。

绘制时使用 40 MHz SPI、480 字节逐行缓冲和 `SPI.writeBytes` 批量发送；每帧在角色区域按背景重新合成，透明边缘使用 RGB565 混合。素材都烧进 flash，设备不需要联网。照片作者与 Unsplash License 见 `assets/README.md`。预览 GIF 是开发用效果预览。

**2026-10-15 编译与烧录**：PlatformIO 编译通过，RAM 6.4%（20,988 / 327,680 字节），Flash 66.3%（2,214,513 / 3,342,336 字节）。烧录到 COM9 后 app 镜像回报 `Hash of data verified`。Bridge 状态显示固件 `voice-device-1.0`、设备已连接、CRC 错误为 0、复位原因 0；待机状态下帧号连续采样为 1、3、0、3。实物频闪效果仍需目视确认。

屏幕显示的是 8 张**角色表情**，不是色块。素材取自开源桌面宠物图集 **`f0909172434/deepseek-girl-codex-pet`**（「deepseek 娘」，**MIT**，需署名）：1536×2288 一张图 = **8 列 × 11 行**，单元 192×208。由 `scripts/build_faces.py` 按 (行, 列) 切格、等比缩放进 240×240、合成到黑底、**按 `ROTATE_CCW` 旋转**、转 RGB565 并做游程编码，生成 `src/faces.h`。**数据在 flash 里，断电不丢，运行时不需要网络。**

**屏幕朝向**：`build_faces.py` 顶部的 `ROTATE_CCW = 90` 让角色**逆时针转 90°**（头顶朝屏幕左侧，对应设备的安装方向）；`0` 是正的，`270` 是顺时针。旋转在**生成阶段**用无损的 `transpose()` 做（不是 `rotate()`，不会重采样把画面糊掉），**固件一行都不用改、也不吃运行时间**；改完重新生成 + 编译即可。

图集语义（**读自上游 README，不是猜的**）：列 0–5 是同一动作的连续帧，每一行是一个动作。上游写明「9 種標準狀態動畫」= 行 0–8，加行 9–10 正好 11 行：

| 行 | 动作 | 行 | 动作 |
|---:|---|---:|---|
| 0 | 待機（列 0–5 动画，列 6 中性观看基准） | 6 | 等待使用者 |
| 1 | 向右移動 | 7 | 工作中 |
| 2 | 向左移動 | 8 | 審查中 |
| 3 | 揮手 | 9–10 | 16 個觀看方向 |
| 4 | 跳躍 | | |
| 5 | 失敗 | | |

当前映射（每个状态都对应一个有语义的行）：

| 编号 | 标识 | 含义 | 图集单元 | 行语义 |
|---|---|---|---|---|
| 0 | `FACE_ID_BOOT` | 上电就绪，正在等 Bridge 握手 | r3c0 | 揮手 |
| 1 | `FACE_ID_READY` | 已连接、空闲待命 | r0c0 | 待機 |
| 2 | `FACE_ID_SLEEP` | 等不到心跳，进入等待 | r6c0 | 等待使用者 |
| 3 | `FACE_ID_LISTEN` | 正在收音 | r9c0 | 观看方向·上 |
| 4 | `FACE_ID_THINK` | 语音已收到，识别 / Hermes 处理中 | r7c0 | 工作中 |
| 5 | `FACE_ID_SPEAK` | 正在朗读回复 | r0c5 | 待機动画帧 |
| 6 | `FACE_ID_APPROVE` | Hermes 请求工具审批 | r8c0 | 審查中 |
| 7 | `FACE_ID_ERROR` | 音频驱动 / Hermes / 链路出错 | r5c0 | 失敗 |

设备自己会在按键、播放、断连时立刻换表情；`FRAME_FACE` 让电脑覆盖某个状态（例如 `THINK` 或 `APPROVE`）。8 张表情合计约 **632 KB** 游程数据（每张 70–88 KB；旋转后游程结构变了，比未旋转时略大）。

只有 SPEAK 稍弱：它和 READY 共用行 0（唯一"说话"性质的姿态），只差动画帧；行 4「跳躍」可顶上，但那是我引申的语义，不如其余 7 个硬。改映射只需动 `build_faces.py` 的 `FACES` 表里的一对数字再重新生成。

行 1、2（左右移动）、4（跳跃）当前未使用——app 分区还空 72%，以后要做"设备待久了在屏幕上走动"这类真宠物行为，素材现成。

## 动画资源（固件 0.5 实现前的评估记录）

图集每一行本来就是 **6 帧连续动画**（`揮手` 那行只有 4 帧，6 格里 2 格是空的）。以下是固件 0.5 实现前的资源估算记录：

**瓶颈一 · 闪存**（app 分区 3264 KB，当前已用 935 KB）：

| 方案 | 占用 | 结论 |
|---|---|---|
| 现状 8 张静帧 | 546 KB | 宽松 |
| 8 状态全 6 帧 | 3026 KB | **放不下**（差约 620 KB） |
| 4 状态动 / 4 状态静 | 2014 KB | 放得下，但只剩约 390 KB |

这块板是 **16 MB 闪存**，而现在只给了 app 分区 3.19 MB——换自定义分区表提到 6 MB 就能全动画。

**瓶颈二 · 画法速度（真瓶颈）**：`lcdPut()` 每个像素调 2 次 `SPI.transfer`，一帧 240×240 就是 **115,200 次调用**，而且 SPI 只跑 20 MHz。

- 纯线速下限：115200 B ÷ 20 Mbit/s ≈ **46 ms**（硬下限）
- **估算**实际 100–170 ms/帧 → 6 帧循环不到 1 fps，会像幻灯片
- 靠脏矩形重绘救不了：实测脏矩形占脸 **45–75%**，只能省 1.5–2 倍

固件 1.0 延续行缓冲、批量传输和 40 MHz SPI；动画不先刷黑底，只传相邻帧实际变化的矩形。若仍看到整个屏幕的背光亮度闪烁，应检查背光供电或连线。

**不烧录也能看**：`scripts/create_screen_background.py` 与 `scripts/build_screen_assets.py` 会生成新的屏幕静态预览 `faces-screen-preview.png`。旧图集黑底预览脚本 `scripts/render_faces_animation.py` 输出 `faces-atlas-animation.gif`；静帧表情预览由 `scripts/render_faces_preview.py` 生成。

想先看机器人会显示什么，不用主控也不用烧录：`scripts\render_faces_preview.py` 会把 `faces.h` 解码回 PNG（`faces-preview.png` / `faces-on-screen.png`）。

## 编译与烧录（固件 0.4 历史记录）

在 `voice-device/` 下执行 `pio run`，结果：

| 项 | 值 |
|---|---|
| RAM | 6.1%（20020 / 327680 字节） |
| Flash | **27.6%（921753 / 3342336 字节）** ← app 分区 3.19 MB，其中 619 KB 是表情 |
| `firmware.bin` | 922112 字节（烧录时） |

`.flash.rodata` 实测 674.5 KB；8 个 `FACE_*` 符号在符号表里逐个核对，合计 **633,956 字节**，与 `build_faces.py` 报的 619.1 KB 一致——**表情确实进了镜像**。

**已烧录（2026-10-14）**：`pio run -t upload` 报 `Hash of data verified`，设备端回读校验通过。烧录后 `/api/status` 报：

```
firmware = voice-device-0.4    ← 版本号已升（0.4 = 角色逆时针旋转 90°）
connected = True   port = COM9   uptime_ms = 18000
face = 1 (READY)   device_bad_crc = 0   reset_reason = 0   speaker_ready = True
Flash 28.0% (935129 / 3342336)  RAM 6.1%
```

ELF 符号表核对：8 个 `FACE_*` 合计 **647,336 字节**，与生成器报的 632.2 KB 一致。

**⚠️ 版本号规则**：每次改固件都要同时升 `src/main.cpp` 里 HELLO 载荷的版本号，否则 `/api/status` 分不清板上是哪一版（`face` 索引区分不了，因为 READY 在各版里都是 1）。0.2 = 无色块表情版，0.3 = 女孩子表情 + 行语义映射，0.4 = 逆时针 90°，0.5 = 星云背景 + 状态动画，0.6 = 动画帧间隔调整为 320 ms，0.7 = 蓝青渐变背景 + 朗读静帧，0.8 = 青蓝紫背景 + 全状态静帧诊断，0.9 = 双帧动画 + 局部刷新，1.0 = 全部有效帧 + 180 ms 局部刷新。

### 烧录必须停 Bridge

Bridge 运行时会独占串口，upload 直接报 `Could not open COM9 ... PermissionError(13)`；Bridge **没有**放开串口的接口。流程固定为：按端口找到 Bridge 进程 → `powershell Stop-Process -Force`（**不要用 `taskkill`，MSYS 会吃掉 `//F` 这类参数**）→ 等 8787 释放 → 烧录 → **无论成败都把 Bridge 拉回**：

```
cd D:\Codex工作区\desktop-ai-robot
.\.venv\Scripts\python.exe -m uvicorn bridge.app.main:app --host 127.0.0.1 --port 8787 --no-access-log
```

### 本机工具链的三个坑（都已处理好）

1. **本机没有 `pio` 命令**，`~/.platformio` 原先只有 `platforms/` 没有 `packages/`。已用 `uv tool install platformio` 装 PlatformIO Core 6.2.0 到 `C:\Users\55243\.local\bin\pio.exe`，该目录**不在 PATH 上**，需要时显式调用或 `uv tool update-shell`。
2. **`uv tool` 的隔离环境缺 esptool 的 Python 依赖**，会以 `bootloader.bin` 报 `ModuleNotFoundError: No module named 'intelhex'` 的形式失败（看起来像单片机错误，其实是主机端 Python 问题）。补装到 `C:\Users\55243\AppData\Roaming\uv\tools\platformio\Scripts\python.exe`，命令是 `uv pip install --python "<该解释器>" intelhex ecdsa reedsolo pyyaml pyserial cryptography`。
3. **包的后置安装脚本可能以 `3221225794`（`0xC0000142`，DLL 初始化失败）挂掉**，因为 PlatformIO 跑在 uv 自带的 CPython 3.14 下。重跑一次即可，不必去查单片机。
4. **`scripts/` 下的图像工具需要 Pillow**，原先没声明；已加进 `requirements-dev.txt`。`./.venv/Scripts/python.exe` 是 uv 的 trampoline（会转调底层 Python 并带上 venv 的 site-packages），所以从进程列表里看到 Codex 运行时的路径是正常的。

### 网络不稳时的下载做法

首次装包需要从 GitHub/乐鑫 CDN 拉约 250 MB，这条线**对大文件会被 RST**（`ConnectionResetError 10054`），PlatformIO 自带的下载器一断就从 0 重来，会永久卡住。可行做法是用 curl 断点续传（`-C -`）自己拉，网络一有窗口就前进、进程被掐也不丢进度；实测 86 MB 的工具链在多次失败后靠这种方式收完。相关脚本留在 `%LOCALAPPDATA%\Temp\fetch-toolchain.sh`。链路恢复正常时，直接 `pio run` 即可，无需上述手段。

重新生成表情（只在改素材或改清单时需要，普通编译不需要联网）：

```powershell
.\\.venv\\Scripts\\python.exe scripts\\build_faces.py --background 000000
```

重新生成背景与动画帧资源（需要本地 Pillow；原始素材已保存于项目中）：

```powershell
.\\.venv\\Scripts\\python.exe scripts\\build_screen_assets.py
```

## USB 协议 v1

每帧为 `A5 5A | type:u8 | seq:u16le | len:u16le | payload | crc16:u16le`。CRC-16/CCITT-FALSE 覆盖 type 到 payload，初值 `0xFFFF`，单帧 payload 最多 1024 字节。多字节字段均为小端。

| 类型 | 方向 | 内容 |
|---|---|---|
| `0x09 HELLO` | 设备→电脑 | JSON 协议版本、固件版本，每 2 秒重发直到握手 |
| `0x0A WELCOME` | 电脑→设备 | `{"protocol":1}` |
| `0x05 HEARTBEAT` | 电脑→设备 | 每秒心跳；5 秒未收到则设备停止收音并回到等待状态 |
| `0x01 STATUS` | 设备→电脑 | JSON 收音状态与运行时间 |
| `0x06 BUTTON` | 设备→电脑 | 单字节 `1` 开始或 `0` 结束收音 |
| `0x03 AUDIO_UP` | 设备→电脑 | 16 kHz、单声道、有符号 PCM16LE |
| `0x02 DISPLAY` | 电脑→设备 | 两字节 RGB565 颜色；当前只供调试 |
| `0x04 AUDIO_DOWN` | 电脑→设备 | 16 kHz、单声道、有符号 PCM16LE；设备复制为左右声道送给功放 |
| `0x0B AUDIO_END` | 电脑→设备 | 本轮播放结束，回到就绪表情 |
| `0x0C FACE` | 电脑→设备 | 单字节表情编号，取值见 `faces.h` 的 `FACE_ID_*` |

麦克风 PCM 只经 USB 送到这台电脑，ESP32 不连接 Wi-Fi。
# 显示主题更新（固件 1.11）

保留原角色，新增本地球球渲染。Bridge 顶栏屏幕图标切换主题，选择存入电脑数据库，USB 重连时重新应用。协议新增 `THEME=14`，一个字节：0 原角色、1 球球；设备 STATUS 的 `display_theme` 回报实际主题。

球球 1.11 目标 60 Hz，帧间不清空。所有绘制由核心 0 的独立任务负责，音频与 USB 在 Arduino 核心继续运行；纹理预旋转缓存，逐帧复制连续行并只绘制可见表情。录音时持续动画：睁大眼睛听、抬眼思考并显示小点、随实际 PCM 音量开合嘴巴。动作节奏较 1.10 加快 25%，位置、形状和透明度以约 195 ms 的平滑响应切换，中途切换从当前姿态继续。任务创建失败时回退到单任务绘制，状态切换仍有效。

`scripts/build_qiuqiu.py` 生成纹理，`src/qiuqiu_motion.h` 计算连续动作，`scripts/render_qiuqiu_preview.py` 生成 [当前表情预览](assets/qiuqiu/expressions-preview.png)。原角色资源不变。球球视觉形象仅限非商业用途，见 [LICENSE 与来源](assets/qiuqiu/README.md)。
