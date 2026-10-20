# ESP32-S3 语音设备端

当前排查固件 `voice-device-1.39` 默认使用 [PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet) 蓝发小女仆（主题 2），保留 Emotion Ball（主题 1）供手动选择。1.36 已把动画旋转移到素材生成阶段；访问模式对比指向相关性，但用户反馈闪烁仍未解决，不能认定已修复。60 fps 试验因整帧数据量超过 26.67 MHz SPI 的理论吞吐而回退，普通播放保留 **40 fps、13 段** 基线。

1.37 新增串口 `steady-motion`（模式 14）：固定待机动作 0、40 fps 原时间轴、禁用随机动作及淡化，用于区分持续播放与状态切换。用户确认此模式仍明显闪烁；现正对比新版停止传屏但继续计算的结果。普通动画命令或诊断退出恢复全部正常行为，默认开机功能保留。

1.38 新增 `steady-bands`（模式 15）比较按变化行带传屏；实测像素数据少约四分之一，但用户反馈闪烁基本一样、画面正常。1.39 新增 `steady-30`/`steady-20`（模式 16/17），临时以每秒 30/20 次呈现同一段待机，源动作总时长不变，用来测试更新节奏；30 次档已实测计数，实物结论待反馈，20 次档尚未测试。普通模式默认帧率未改变。

通电后无需 Bridge 或网页指令，先完整播放一次约 10 秒的“女仆屈膝礼仪”（动作 9），再通过原有 220 ms 过渡进入待机。开机期间 USB 就绪/休眠通知不会重启动作；录音、思考、说话或错误状态立即优先接管。开机动作不阻塞串口和音频任务。Bridge 新安装或无效旧主题默认选小女仆；有效的手动主题选择仍会保存。离线 HELLO 包含主题、动画、开机动作和帧计数，方便验证未握手时也在自主播放。

1.25 添加无损稀疏变化缓存，重复播放已缓存帧时跳过 zlib 解压。缓存数据上限 6 MiB，分配前保留至少 512 KiB PSRAM 余量，按最近使用情况回收其他动作末尾的缓存。首次遇到的帧仍正常解压，分配失败也回退到原解码路径。缓存命中、未命中和数据占用可从串口状态查看。该优化减少重复解压，但用户确认闪烁基本不变、仍明显；动画已暂时暂停，接下来需验证供电、地线或背光稳定性，不能宣称已解决。

1.24 改为当前帧直接解码、调色和合成，删除两份交替使用的彩色预解码帧，常用索引和显示影子缓冲优先使用内部 RAM，并为其他功能预留至少 64 KiB 的分配余量。调色表只初始化一次，差分边界跳过相同行。动作时长及 40 fps 源时间轴不变。已实测多个 3 秒区间输出 120 帧，设备图像指纹与电脑独立解码的素材帧一致；实物闪烁改善程度仍待用户确认。

1.23 增加串口诊断 `compute-only`：继续解码和合成动画，但不写 LCD，也不更新实际显示缓冲区。同一静止画面中，用户确认 `hold` 停止计算时不闪，恢复 `compute-only` 后明显闪烁。优先检查负载与供电、地线、背光的关联，但这不等同于电源故障已被证实；该模式也没有正常播放时的 SPI 传输和显示缓冲区复制负载。正常网页行为、音量和屏幕扫描参数保持原样。诊断退出后 Bridge 已恢复，动画暂时暂停。

DSH Pet 的 13 段完整动作编译进 Flash，脱离电脑仍可播放。1.16 将原视频离线光流补帧为每段 402 张、40 fps 的完整画面，循环约 10.05 秒，保留原动作时长（与原片相差不到 9 ms）。主控正常播放不再逐像素实时混合相邻帧，只在状态改变时做 220 ms 过渡；采用最终画面的 8×8 差分刷新，不先清屏。角色绘制区域收紧到 168×168，略微缩小角色，保留全部 13 段动作。渐变暮色背景沿用 gamma 0.85 的提亮版本；这是画面提亮，当前接法没有独立背光调光。实机说话时每约 3 秒呈现 119–120 帧（约 40 fps），320/320 音频帧确认、CRC 为 0；100 秒状态/随机动作测试通过。外观仍需实物确认，不把吞吐数据当作消除闪烁的证明。

八个随机动作只在待机触发，避免连续重复；动作结束后随机等待 8–22 秒再开始下一个（低于 30 秒上限）。录音/思考/回答会立即接管，返回待机时重新计时。Emotion Ball 原来的 60 Hz 动画和安静播放策略不变；DSH Pet 说话时继续动画，音频增益不变。

资源生成：`python scripts/build_dsh_pet.py`，需要 FFmpeg（libvpx）、Pillow、numpy、OpenCV。原视频缓存到本机数据目录，不提交 Git；固定上游提交并逐文件验证 Git blob SHA。生成结果在 `assets/dsh_pet/`，含完整来源清单、许可、预览、背景和压缩动画包。代码 MIT，**动画素材限非商业使用，二次分发必须保留上游链接**，见该目录 NOTICE。

16 MB Flash 使用单个 0xFF0000 应用分区；移除了代码从未使用的 SPIFFS 分区，保留 NVS。固件约 16.42 MB，应用分区还剩约 287 KB；后续增加素材必须重新检查容量。动画按关键帧和 XOR 差分进行 zlib 解压，索引和成帧缓冲位于 PSRAM，约 28 KB 解压输出留在内部 RAM，全部画面不需要常驻内存。显示仍由独立任务单独拥有 SPI，但与 USB/I2S 保持在同一核心，避免跨核心成帧时的音频重启；空闲主循环每毫秒让出处理时间。丢帧时只补解遗漏的差分，不重复从关键帧解压整段。状态遥测含 `pet_action`、`pet_frame`、`pet_random_count`、`pet_decode_errors`。构建/烧录仍用 PlatformIO；不要给只有 8 MB Flash 的板子刷这个镜像。

1.17 的高扫描档虽然减轻闪烁，但亮度严重降低；1.18 中间档恢复亮度却仍明显闪烁，都已停用。1.19 固定同一画面仍高速传屏的对比中，用户依然看到轻闪，不能归因于补帧素材本身。

当前 1.20 恢复默认屏幕扫描参数（FRCTRL2 0x0F），小女仆使用约 26.67 MHz SPI，Emotion Ball 保持 40 MHz。小女仆每帧计算一个最终变化矩形，以一次 RAMWR 连续写入，并用内部缓冲每批打包最多 16 行；取消原来的几十个独立小块，静止区域按原色覆盖，不先清空。没有 TE 同步接线，不能保证完全消除撕裂。实机语音 320/320 帧确认、CRC 0、无重启；说话约 37 帧/秒，待机约 39 帧/秒，素材时间轴仍为 40 fps。20 MHz 曾使说话降到约 32 帧/秒，未采用。当前亮度、闪烁和流畅度仍待实物比较。

静止画面 A/B 排查工具：`scripts/display_ab_test.py --control <本地控制文件> --log <本地日志> --restore-bridge`，需要先停止 Bridge 释放串口。控制文件内容为 `hold`、`repeat`、`compute-only`、`motion-normal`、`motion-slow`、`motion-fast` 或 `stop`；默认十分钟超时，退出会请求恢复动画。固件命令 0x0F 仅用于串口排查，普通网页不启用。状态中 `pixel_writes` 是 RAMWR 次数，`screen_test_hash` 是冻结源图的指纹，不是屏幕回读。此次同一帧在完全停止传屏和约每秒 40 次重复传屏时，用户均确认不闪；正常动画恢复后，用户确认仍然闪烁。1.22 可在不改屏幕扫描的情况下临时请求 20/40 MHz，`lcd_spi_hz` 是请求值而非仪器测量；退出或普通动画命令恢复默认时钟。20 MHz 和 40 MHz 动画均已对比播放并恢复。用户最后说明基本差不多，没有明确改善，因此不能据此判定线路故障。正在通过遮住角色、只看外侧背景，区分整屏明暗波动与角色区域更新问题。

以下旧固件章节保留为历史记录。

固定接线：INMP441 SCK/WS/SD 为 GPIO4/5/6；MAX98357A BCLK/LRC/DIN 为 GPIO15/16/17；轻触开关 GPIO1 到 GND；屏幕 CS/DC/RES/SDA/SCL 为 GPIO8/9/10/11/12。本机已确认 KAC 2.4 英寸 ST7789 模块：BLK 经外接电阻上拉到主控 3V3，保持常亮；用户回忆电阻约 3 kΩ，实际阻值尚未确认。用户反馈上拉后闪烁明显减轻或消失，功放接回后的联合测试已确认 324/324 音频帧，设备持续连接、说话动画运行，用户确认声音正常，但仍有明显闪烁，尚未通过整机验收；正在区分安静待机与说话时的表现。此接法是本机实测记录，不作为所有 ST7789 模块的通用接线规范。

功放最终接线：VIN 单独接主控明确标注的 5V/VBUS，GND 接主控 GND，SD 接 3V3，BCLK/LRC/DIN 分别接 GPIO15/16/17，GAIN 暂不接。喇叭两根线分别夹在绿色端子 `+`、`−`，`−` 不接 GND。麦克风、屏幕 VCC 继续接 3V3，不能把 5V 与它们的 3V3 红轨相连。功放 VIN 原接 3V3 时，较长时间播放曾导致 USB 断开重连；5V 接法下约 25 秒连续测试的 561 个新增音频帧均收到确认，设备持续连接。Bridge 在语音片段之间补静音帧并对片段作淡入淡出，输出音量倍率固定为 0.21；用户确认多句播报无杂音、音量能听清，也没有 USB 断连提示。

当前按键 Toggle：按一次开始上传 16 kHz PCM，再按一次停止；播放语音时按键可打断并开始收音。语音识别、任务选择和远程访问不进入固件。

## 屏幕表情（桌面宠物的回应方式）

### 历史实现（固件 1.8，已通过实物确认）

用户反馈 1.7 有改善但仍卡顿；1.8 将不同画面提高到约 22.2 帧/秒，保留原动作时长。`INTERPOLATION_STEPS=4`，总共 69 张资源（64 张动画帧 + 5 张静帧），2,424,686 字节压缩素材。Flash 2,715,765 / 3,342,336 字节，静态 RAM 32,324 / 327,680 字节；帧缓冲与 PSRAM 缓存为动态分配。

设备实测 64 张缓存全部成功；连续每约 3 秒增加 67 次不同画面更新、200–201 次重复传屏，画面打包约 3.2–3.4 ms、待机局部传屏约 12 ms；uptime 连续增长、CRC 为 0。19 项相关测试通过，包含全部压缩帧解码及循环变化区域校验。用户明确确认“顺滑了，画面正常”，该版本现已由只含球球的 1.13 取代。

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
# 显示主题更新（固件 1.12）

保留原角色，新增本地球球渲染。Bridge 顶栏屏幕图标切换主题，选择存入电脑数据库，USB 重连时重新应用。协议新增 `THEME=14`，一个字节：0 原角色、1 球球；设备 STATUS 的 `display_theme` 回报实际主题。

球球 1.11 目标 60 Hz，帧间不清空。所有绘制由核心 0 的独立任务负责，音频与 USB 在 Arduino 核心继续运行；纹理预旋转缓存，逐帧复制连续行并只绘制可见表情。录音时持续动画：睁大眼睛听、抬眼思考并显示小点、随实际 PCM 音量开合嘴巴。动作节奏较 1.10 加快 25%，位置、形状和透明度以约 195 ms 的平滑响应切换，中途切换从当前姿态继续。任务创建失败时回退到单任务绘制，状态切换仍有效。

`scripts/build_qiuqiu.py` 生成纹理，`src/qiuqiu_motion.h` 计算连续动作，`scripts/render_qiuqiu_preview.py` 生成 [当前表情预览](assets/qiuqiu/expressions-preview.png)。原角色资源不变。球球视觉形象仅限非商业用途，见 [LICENSE 与来源](assets/qiuqiu/README.md)。

1.12 将完成的 RGB565 图像与上一帧按 8×8 小块比较，只传变化块；眼睛、嘴巴移走后露出的底色也会被正确传送，不会先擦屏再画。相同帧不传屏。换主题或颜色测试后会完整重画一次。`ball_bytes`、`dirty_tiles`、`diff_buffer` 分别回报球球像素传送字节数、变化块数和比较缓存是否可用；60 Hz 是动作计算节奏，实际传送次数可能因跳过相同帧而减少。

用户已完成录音、回复实物对照，确认 1.12 差分版不再闪烁；当前以此版作为显示基线。

### 1.40 diagnostic comparison

Serial-only `steady-50` (mode 18) repeats final valid pixels at 50 Hz / 40 MHz while retaining the original 40 fps source timeline and duration. No blank frames or extra unique poses are inserted. Normal playback defaults are unchanged; physical flicker feedback is pending. The 30 Hz trial worsened flicker, and 40 Hz at 40 MHz looked approximately unchanged.

### 1.41 diagnostic comparison

Serial-only `steady-60` (mode 19) adds 60 Hz repeated-frame presentation at 40 MHz, preserving the 40 fps source timeline and clip duration. Device confirms 180 presentations per 3 seconds; visual feedback is pending. Normal playback defaults are unchanged.

### 1.42 normal playback and transitions

Normal pet playback now uses 60 Hz repeated presentation at 40 MHz (40 fps source timing retained), including startup and state changes. Same-clip loops retain timeline remainder and skip a new fade. Equivalent state notifications keep the clip running. Real action changes blend from the displayed image with a 220 ms eased opaque crossfade. Physical confirmation of loop/state white-flash improvement is pending.

### 1.43 bounded maximum-scan diagnostic

Serial mode 20 (`steady-limit`) temporarily requests nominal 119 Hz C6 scanning and a 119 Hz presentation target at 40 MHz. Actual presentation throughput must be measured (initially about 75 Hz); the exact module rating is unknown. Normal scan stays 0x0F and ANIMATION/diagnostic cleanup restores it. Run with `--max-seconds 120 --restore-bridge` for a bounded comparison. User reports 1.42 still flickers; no fix is claimed.

### 1.44 selected 75 Hz configuration

Normal pet presentation targets 75 Hz at 40 MHz SPI; normal screen scanning selects C6=0x09 (nominal 75 Hz). Original 40 fps animation source timing is preserved. Startup and animation restoration retain this setting. Live windows show about 74-75 presentations/second; physical brightness/flicker feedback is pending.

### 1.45 slight image dimming

Pet image channel levels use 90% software scaling, consistently applied to palette/background and transition initialization. The selected 75 Hz scan/presentation configuration and existing BLK wiring stay unchanged. This does not lower backlight current.

### 1.46 SPI transaction audit

Window commands and pixel payload now share one CS assertion / SPI transaction. Every pixel writer validates window geometry and expected RGB565 byte counts; `lcd_tx_errors` reports violations. Live sweeps across both themes and work states stayed at zero errors. Three sampled decoded frame hashes also matched host reconstruction before this change. These checks do not read back LCD RAM or establish electrical bus integrity; physical flicker feedback remains pending.

### 1.47 requested 90 Hz comparison

Normal scan selects C6=0x05 (nominal 90 Hz), with a 90 Hz presentation target. Actual initial delivery is about 80-83 updates/second under current processing/transport load. Image level, bus frequency, source timeline and checked transaction path are unchanged. Visual feedback is pending.

### 1.48 small brightness increase

Software image level rises from 90% to 95% at user request. The selected 90 Hz scan/presentation target, SPI clock and source timing stay unchanged. BLK wiring and backlight current are not controlled by this adjustment.

### 1.49 maximum software image level

`IMAGE_LEVEL=100` restores unattenuated source colors at user request. The selected 90 Hz settings stay unchanged. This does not alter the BLK circuit or establish maximum hardware backlight brightness.

### 1.50 action-crossfade isolation

`ACTION_CROSSFADE=false` disables runtime action crossfades and their source copy. Complete next-action frames are presented directly without a clear/blank frame. Offline interpolation within clips, 90 Hz settings and 100% image level remain unchanged. Direct changes may look more abrupt; switch-flash feedback is pending.

### 1.51 action transitions restored

At user request, `ACTION_CROSSFADE=true` restores the 220 ms eased opaque action blend after the direct-cut trial felt abrupt. The selected 90 Hz settings and 100% image level stay unchanged. Flicker root cause remains unresolved.

### 1.52 raised stage

The DSH Pet stage moves up 20 logical pixels to sit under the character's feet. Removed the LCD bottom text; repository attribution remains in the Bridge panel, LICENSE and NOTICE. Rebuilt all composited clips/background consistently, keeping 13 x 402 frames, source durations, 90 Hz settings, 100% image level, eased transitions and character voice binding.


### 1.58：无线实验与安全回退

保留原有动画和音色；按实际 USB 心跳选择 USB / LAN WebSocket，开机等待 30 秒。无线初始化暂降 CPU 并暂停动画，启动欠压后进入持久化无线安全模式，USB 仍可恢复。最后一次外部供电测试也触发了该保护，因此无线尚未通过实物验收。详见 [无线 Bridge 记录](../docs/WIFI_BRIDGE.md)。
