# 同一局域网无线 Bridge

固件 1.58 增加设备主动连接电脑的 WebSocket 客户端。电脑上的 Bridge、Hermes/Harness 和本地声音服务仍需运行；机器人可以通过 USB 充电头或充电宝供电。

## 通信与兼容

- 主控连接 2.4 GHz Wi-Fi；电脑可连接同一路由器的 5 GHz 网络或网线。访客网络/AP 隔离可能阻断设备互访。
- 原 v1 CRC 二进制协议原样放入 WebSocket 二进制消息，音频仍为 16 kHz、16 bit 单声道。Bridge 继续使用原按键路由、录音识别、音色绑定和播放回执逻辑。
- 收到有效 USB 协议帧和 Bridge 心跳时优先使用 USB；拔离电脑改用充电头后自动选择 Wi-Fi。插回电脑后恢复 USB。并非同时向两个链路复制录音。
- 网络断开丢弃当前录音和播放，恢复后等待下一次操作，不自动重投旧问题。
- 网页仍只监听本机 8787，现有 Tailscale 页面继续可用。另一个监听器只提供 `/device`，默认端口 8788，仅绑定配置的电脑局域网 IP。
- 设备使用独立的随机令牌鉴权，浏览器 Origin 请求拒绝。此首版是可信局域网内的 **ws 明文传输**，不应转发到公网；它不是加密的 WSS，也不走手机 Tailscale 网址。

## 配置

1. 保留经过验证的旧固件，编译并通过 USB 烧录 1.55。
2. 停止 Bridge，释放 USB 串口。在项目根目录执行：

   ```powershell
   .venv\Scripts\python.exe scripts/configure_device_wifi.py --host <电脑局域网IPv4地址>
   ```

   交互输入 SSID 和密码；密码不显示、不作为命令行参数。工具写入主控 NVS，收到设备确认后写入电脑私有数据目录中的 `device-network.json`。该电脑文件只保存监听 IP、端口和设备令牌，不保存 Wi-Fi 密码。设置后主控重启。
3. 重新启动 Bridge。Windows 防火墙如阻止，在管理员 PowerShell 运行 `scripts/enable_device_wifi_firewall.ps1 -HostAddress <电脑局域网IPv4地址>`，仅为设备端口、对应程序、局域网接口及本地子网添加规则。不要关闭整个防火墙。
4. 将机器人 USB 从电脑移到充电头。网页应显示“设备已连接 · Wi-Fi”。
5. 电脑 DHCP 地址改变后需要重新配置，建议在路由器为电脑保留固定地址。

开发诊断命令：USB 协议类型 16 为配置 JSON、17 为配置结果；18 请求受限无线诊断（profile 0/1）、19 返回阶段和结果。配置和扫描仅在 USB 下且非录音/播放时接受。Wi-Fi 密码及设备令牌不进入仓库。

## 资源与回退

所有 13 个 DSH 动作、5,226 个动画帧、原动作时长、背景、Emotion Ball 和音色均保留。对现有动画包逐帧选择更短的标准 zlib 编码，包从 15,838,813 字节减到 14,788,881 字节。重打包逐帧验证解压结果完全相等；无需重做光流或调色。

`scripts/repack_dsh_pet.py` 可无损优化现有包；原素材构建脚本也使用同一压缩函数。网络凭据保存于 NVS，重新烧应用通常不会清除；转让设备前应单独清除凭据。

首版验收必须区分软件模拟与实物：鉴权、二进制收发和 USB 兼容测试通过，并不代表已经确认无线音质、重连、录音和动画并行正常。最终须使用充电头供电，按键发给当前选中的 AI/会话、听到完整回答，并验证拔网恢复和 USB 回退。

Wi-Fi 发射功率暂设为 8.5 dBm，扫描时短暂暂停动画计算并使用被动扫描。1.53 初次扫描触发过复位原因 9（欠压），降低负载后的实际结果应单独记录，不能仅凭编译成功判断供电问题已解决。

1.55 将无线初始化放在 USB 连接判定之后，开机留 8 秒 USB 接管窗口。配网后 USB 已确认恢复，监听器已启动；1.54 被动低功率扫描仍出现 reset_reason=9。下一步需要充电头供电实测，尚未确认无线连接或音质成功。


## 后续实物测试与限制（1.58）

- Windows 防火墙规则已由用户成功配置；局域网监听端口本机连通，电脑扫描确认目标网络存在且为 2.4 GHz。
- 1.55 在充电头供电下画面正常但未无线连接。1.56 改为实际 USB 帧/心跳选择链路，充电头供电下用户观察到反复重启。
- 1.57 暂停动画计算、将 CPU 暂降为 80 MHz，再启用低功率 Wi-Fi，电脑侧仍实际读到 reset_reason=9；保护按预期启用，USB 可正常恢复。
- 1.58 延长开机 USB 接管窗口为 30 秒。Wi-Fi 得到 IP 后稳定 10 秒恢复 CPU 240 MHz；与 Bridge 通信稳定后清除启动标记。如果启动期间欠压，后续开机自动进入无线安全模式，不再自动尝试 Wi-Fi。重新运行 USB 配网工具可清除安全模式并重试。
- 独立网络诊断包类型 20（与原 STATUS 分开，避免超出 1024 字节）：wifi_configured、wifi_selected、wifi_status、wifi_disconnect_reason、wifi_safe_mode 和内部空闲内存，不含密码/令牌。
- 用户报告 1.58 充电头下画面正常，没有观察到重启，但 Bridge 尚未收到无线连接。仍需读取安全模式，不能把稳定画面视为无线连接成功。
- 最新后端测试 155 项通过。无线音频、识别闭环和断网恢复尚未实物验收；USB 备用目前可连接。不要对外把这一版本描述为已完成无线语音功能。


### 本轮最终实物结果

1.58 最后一轮充电头测试后，USB 回读确认 `wifi_safe_mode=true`，而测试前该值明确为 false。该位仅由无线启动标记与欠压复位共同触发自动设置。因此本轮仍发生过无线启动欠压，保护随后停止尝试，用户观察到稳定画面。当前保留 USB 正常使用，**无线功能仍未实物验收通过**，不应为此关闭欠压检测。电脑充电口/外部充电头均出现过相关证据，尚不能确定是主控稳压、接线压降、局部去耦还是其他供电环节造成。

重新配网会重新允许无线尝试；在供电问题未处理前，不必反复解除安全模式。后续需要供电测量或合理的硬件改善，再重新验收语音和动画并行。


## 不拔线的软件负载对比（1.60）

用户明确要求不拔任何外设线，本轮未改变接线；两组测试均由电脑 USB 供电。

| 配置 | 已完成的阶段 | 无线初始化结果 | 恢复后的复位记录 |
| --- | --- | --- | --- |
| profile 0：正常待机，CPU 240 MHz、I2S 保留、动画正常 | starting → before_radio_init | 没有收到 mode_ready，USB 断开 | 9：ESP_RST_BROWNOUT |
| profile 1：暂停动画，卸载麦克风/扬声器 I2S 驱动，数字时钟/数据引脚拉低，CPU 80 MHz | starting → i2s_stopped → cpu_low_ready → before_radio_init | 没有收到 mode_ready，USB 断开 | 1：ESP_RST_POWERON |

低负载在 1.59 和补充阶段标记后的 1.60 均出现上电复位记录 1；不能把这个记录直接改写为欠压复位 9。1.60 的阶段标记已确认低负载配置步骤本身完成，故障发生在随后无线模式启动完成之前。本轮没有成功扫描或建立 Wi-Fi 连接，因此没有测试到 WebSocket 握手、无线音频或智能体路由。

该对比只能说明软件降低运行负载尚不能避免重启。屏幕背光、功放、麦克风仍接电，不等于仅主控测试；不能排除外设静态负载、主控供电瞬态、稳压/去耦、USB 路径或其他硬件因素，也不能仅凭复位记录确定具体故障元件。保持欠压保护，不再自动反复尝试。

诊断入口：固件本地 USB 类型 18，payload 单字节 0/1；类型 19 返回阶段与结果。成功时报告扫描数、目标是否可见、关联状态、内部内存及 I2S 恢复状态，不输出 Wi-Fi 密码或令牌。命令限定 USB 且非录音/播放；Bridge 必须先停止以释放串口。

```powershell
.venv\Scripts\python.exe scripts/probe_device_wifi.py --profile 0
.venv\Scripts\python.exe scripts/probe_device_wifi.py --profile 1
```

CLI 会在断开后尝试重新握手，并读取 STATUS / NETWORK_STATUS；成功输出 JSON 报告表示诊断结束，**不代表无线验收通过**。正常结束会关掉无线探测并恢复原 CPU、动画、I2S；若复位，则重启恢复默认外设与 USB，同时保留无线安全模式。

恢复检查：USB 固件 1.60 正常连接，原 DSH 动画帧号/传屏计数持续增加，测试语音 127 帧全部回执、CRC 与动画解码错误均为 0。


## 最小固件分阶段验证：定位到 esp_wifi_start（接线不动）

在相同 ESP-IDF 4.4.7 / Arduino-ESP32 2.0.17 下，临时刷入约 643 KB 的独立诊断应用。它不加载动画素材、不创建屏幕任务、不安装 I2S、不调用 Hermes/Bridge 协议、不读取 Wi-Fi 密码。保持屏幕/功放/麦克风物理连线与供电，数字时钟静止。只有 USB 明确发送 RUN_RADIO 才启动一次探测，复位后不会自动重试。

| 配置 | 初始化结果 | 启动射频前的内存 | 最后阶段 / 恢复记录 |
| --- | --- | --- | --- |
| wifi-probe，psramFound=true，CPU 80 MHz | NVS、netif、事件循环、esp_wifi_init、RAM 存储、STA 模式均 ESP_OK | 内部空闲 283,896 B，最大连续块 270,324 B | before_wifi_start 后 USB 断开，恢复 reset_reason=9 |
| wifi-probe-no-psram，psramFound=false，CPU 80 MHz | 同上，均 ESP_OK | 同上 | before_wifi_start 后 USB 断开，恢复 reset_reason=9 |

这进一步说明本轮故障不需要动画、音频或 PSRAM 参与，且不是常规驱动初始化返回 ESP_ERR_NO_MEM。实际卡在 esp_wifi_start() 完成之前，未成功扫描、关联或进入 WebSocket。它仍不是外设断电/仅主控测试，不能断言是哪一处硬件故障，也没有验证换 SDK 后的结果。

随后只读调用 esp_phy_load_cal_data_from_nvs：NVS 初始化 ESP_OK，校准读取返回 4354 / ESP_ERR_NVS_NOT_FOUND。该次只读检查没有启动射频，没有擦除、伪造或覆盖校准数据及用户凭据。[官方 RF 校准说明](https://docs.espressif.com/projects/esp-idf/en/v4.4/esp32s3/api-guides/RF_calibration.html)指出校准缓存缺失时会使用完整校准。缓存缺失与 esp_wifi_start 欠压相符，但尚未测量电流，也未证明是校准过程中的哪一步造成。

之前应用中的 8.5 dBm 设置位于 WiFi.mode()/esp_wifi_start 之后，在本次启动失败前未执行到，不能将其视为已限制启动阶段功率。当前预编译 SDK 的 CONFIG_ESP_PHY_MAX_WIFI_TX_POWER=20，CONFIG_ESP_PHY_REDUCE_TX_POWER 未启用。下一步可考虑**单独构建 SDK 级低功率初始化对照**：按官方允许范围降低构建期 PHY 功率，并评估欠压后的 PHY 降功率选项；保持欠压保护，不跳过必要校准。此项尚未实现/实测，不能只加应用层 -D 就声称改变了预编译 SDK。参数与限制见 [官方 Kconfig](https://docs.espressif.com/projects/esp-idf/en/v4.4.8/esp32s3/api-reference/kconfig.html)。

新增构建环境 wifi-probe / wifi-probe-no-psram 和 scripts/read_minimal_wifi_probe.py（可加 --calibration-only）。default_envs 明确保持 esp32-s3-devkitc-1，普通构建/上传不选择诊断应用；正常环境只编译 main.cpp，诊断源单独选择。两种最小环境及默认生产环境均编译通过。

临时覆盖前先对真实 1.60 镜像做完整 digest 校验并保留私有备份，只覆盖应用起始 647,168 字节。射频两组对照作为一批、校准只读检查作为另一批；每批结束恢复原前缀，再对整份 15,922,960 字节应用做 digest 验证，两批恢复均成功，未改分区表或擦除 NVS。最终 Bridge 确认固件 1.60、USB COM9、扬声器就绪、原 DSH 动画持续增加、音频 CRC 与动画解码错误均为 0。完整非敏感阶段数据见 [结构化结果](wifi-minimal-results.json)。
