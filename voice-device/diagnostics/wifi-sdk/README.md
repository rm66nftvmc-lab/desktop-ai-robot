# SDK 低功率启动诊断（未完成实物验证）

这是独立 ESP-IDF 4.4.7 工程，不修改正常 Arduino 固件的 SDK、声音、动画或接线。2026-10-21 首次构建因依赖下载连接失败而中止，尚未生成可烧录镜像。

目标：CPU 80 MHz、关闭 PSRAM、PHY 最大 Wi-Fi 发射功率 10 dBm、启用官方欠压后降低 PHY 功率配置。保持原来的欠压检测等级 7。编译期断言检查生成的 SDK 配置，避免只给应用添加宏、实际仍使用预编译 20 dBm SDK 的错误。

降低功率上限不保证消除完整射频校准时的电流峰值。`REDUCE_TX_POWER` 是欠压后的保护配置，不能据此声称首次启动必然降低全部峰值。最终须以真实设备的阶段日志与复位原因为准。

联网恢复后从仓库根目录执行：

```powershell
.venv/Scripts/python.exe -m platformio run -d voice-device/diagnostics/wifi-sdk
.venv/Scripts/python.exe scripts/verify_wifi_sdk_build.py
```

仅在两步都通过后才安排临时刷写。正常固件默认构建环境保持不变。不要使用这个工程的 `upload` 目标：它可能连同启动器和分区表一起写入。

实物对照要求：

1. 停止 Bridge 串口占用；验证当前完整 1.60 备份与设备 flash 一致。
2. 只覆盖 `0x10000` 开始的诊断应用范围，不写 bootloader、分区表或 NVS；提前保存其按 4096 字节对齐的原固件覆盖范围。
3. 使用 `scripts/read_minimal_wifi_probe.py`，收到 `ready` 才发送一次 `RUN_RADIO`；固件本身不会自动启动或重试射频。不保存任何 Wi-Fi 凭据，不擦除 NVS。
4. 记录生成配置、镜像哈希、最后成功阶段与复位原因。欠压后仍须明确触发下一轮，禁止自动重试循环。
5. 无论成功或失败都恢复原覆盖范围，再对整份原固件做 digest 校验，最后恢复 Bridge 并检查 USB、声音和动画状态。

外设未断开，所以软件停钟/暂停计算不等于移除了背光及外设的静态负载。通过射频启动/被动扫描也不等于已通过无线录音和播音验收。
