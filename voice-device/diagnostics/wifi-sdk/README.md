# SDK 低功率启动诊断（已实测，射频启动仍失败）

这是独立 ESP-IDF 4.4.7 工程，不修改正常 Arduino 固件的 SDK、声音、动画或接线。2026-10-21 经本机代理完成依赖下载、源码构建及实物对照。10 dBm 下仍在 `esp_wifi_start` 完成前断连，恢复报告上电复位 1；原固件已完整恢复。证据见仓库 `docs/wifi-sdk-low-power-results.json`，Wi-Fi 尚未通过验收。

目标：CPU 80 MHz、关闭 PSRAM、PHY 最大 Wi-Fi 发射功率 10 dBm、启用官方欠压后降低 PHY 功率配置。保持原来的欠压检测等级 7。编译期断言检查生成的 SDK 配置，避免只给应用添加宏、实际仍使用预编译 20 dBm SDK 的错误。

降低功率上限不保证消除完整射频校准时的电流峰值。`REDUCE_TX_POWER` 是欠压后的保护配置，不能据此声称首次启动必然降低全部峰值。最终须以真实设备的阶段日志与复位原因为准。

从仓库根目录执行：

```powershell
.venv/Scripts/python.exe -m pip install -r scripts/requirements-firmware.txt
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_wifi_sdk.ps1
```

启动脚本读取当前 Windows HTTP 代理，只作用于构建子进程，并开启 Python UTF-8、将产物置于 `%LOCALAPPDATA%/DesktopAiRobot/wifi-sdk-build`，避开旧版 objdump 的中文路径编码问题。构建后自动检查 SDK 配置、PHY 源码构建记录和 ELF 中实际链接的 14 项初始化功率值（均为 40，单位 0.25 dBm）。正常固件默认构建环境保持不变。不要使用这个工程的 `upload` 目标：它可能连同启动器和分区表一起写入。

首次独立 USB 驱动版本未输出可用阶段日志，未据此推断射频结果。最终改为 SDK 原生 USB 控制台后才拿到完整的有效测试记录。该次复位原因是 1 而非 9，因此没有强行触发“欠压后降功率”分支或自动重试；不能声称该保护分支已实物触发。

实物对照要求：

1. 停止 Bridge 串口占用；验证当前生产固件备份与设备 flash 一致。此前实测基线为 1.60，现已升级 1.61；后续对照必须恢复新的当前镜像，不可直接复用写死 1.60 的临时脚本。
2. 只覆盖 `0x10000` 开始的诊断应用范围，不写 bootloader、分区表或 NVS；提前保存其按 4096 字节对齐的原固件覆盖范围。
3. 使用 `scripts/read_minimal_wifi_probe.py`，收到 `ready` 才发送一次 `RUN_RADIO`；固件本身不会自动启动或重试射频。不保存任何 Wi-Fi 凭据，不擦除 NVS。
4. 记录生成配置、镜像哈希、最后成功阶段与复位原因。欠压后仍须明确触发下一轮，禁止自动重试循环。
5. 无论成功或失败都恢复原覆盖范围，再对整份原固件做 digest 校验，最后恢复 Bridge 并检查 USB、声音和动画状态。

外设未断开，所以软件停钟/暂停计算不等于移除了背光及外设的静态负载。通过射频启动/被动扫描也不等于已通过无线录音和播音验收。

## 下一轮：LCD 控制器休眠对照（仅构建，未烧录）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_wifi_sdk.ps1 -Environment low-power-lcd-sleep
```

该变体收到同一个显式 RUN_RADIO 命令后，通过当前 CS8/DC9/MOSI11/SCLK12 发送 ST7789 DISPOFF(0x28)、SLPIN(0x10)，等待 150ms，再进入相同的 10 dBm 射频启动流程。阶段名 lcd_sleep_requested 仅表示命令已发送；屏幕没有读回通道，不能声称已测量到休眠或省电。BLK 仍由 3V3 供电，功放和麦克风线仍在，不能称为仅主控测试。

本变体编译和产物检查已通过（616,704 B），尚未烧录。保留当前唤醒测试，未中断设备去做这项对照；后续须先备份并校验当前完整 1.61，再受控测试并恢复。
