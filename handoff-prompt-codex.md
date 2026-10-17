继续开发 `D:\Codex工作区\desktop-ai-robot`（桌面 AI 对话机器人）。先读这两份再动手：

- `C:\Users\55243\Documents\Obsidian Vault\10-Notes\桌面AI机器人开发交接.md`
  （交接笔记：完整状态表 + 四轮记录 + 硬件接线 + 待办与已知问题）
- `voice-device\README.md`（固件、引脚、表情管线、编译与烧录流程）

**现状（已验证，不要重做）**：固件 `voice-device-0.4` 已烧录——8 张开源角色表情存在主控 flash、已逆时针旋转 90°；Bridge（`127.0.0.1:8787`）+ 网页端可用；豆包 CDP 通道已打通并验证（端口 9222、已是登录态），但适配器还没写。

**下一件事：给屏幕角色加「简单版」动画**——不同状态动得不一样（待机 / 收音 / 思考 / 回答 / 改答案时各不同）。用户强调：「不要做这么复杂的，简单一点就行」。

做法：
- 每个状态取 **4 帧**循环（别用 6 帧，会超 flash 容量）
- 把 `lcdDrawFace` 改成**行缓冲 + `SPI.writeBytes`**，SPI 提到 **40 MHz**——这是唯一必须改的，否则只有约 1 fps
- **不要**碰帧间差分、调色板量化、`esp_lcd`+DMA、自定义分区表

**硬规则**：
- 改固件必须同时升 `src/main.cpp` 里 HELLO 载荷的版本号
- 烧录前停 Bridge（用 PowerShell `Stop-Process`，**别用 `taskkill`**），烧完无论成败都要拉回
- 不要手改 `config.yaml`
