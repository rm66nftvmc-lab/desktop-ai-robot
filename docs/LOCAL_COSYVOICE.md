# 球球本地声线

用户选择只使用免费本地方案。本功能使用开源 CosyVoice 3，不接入阿里云语音 API，不需要云端 API Key，也没有按字符收取的 API 费用。模型在电脑上运行，ESP32 只负责播放。

## 安装

Windows / Python 3.12 / NVIDIA CUDA GPU：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_cosyvoice_tts.ps1
```

独立环境与模型位于 `%LOCALAPPDATA%\DesktopAiRobot\tts-cosyvoice`，不升级 Bridge 或派蒙环境。使用 CUDA 12.8 的 PyTorch 支持本机 RTX 5070 Laptop。安装脚本复用已有派蒙 PyTorch wheel；模型文件约 5.4 GB，另需 Python/CUDA 依赖空间。国内官方模型镜像的权重必须通过指定 Hugging Face 修订的 SHA-256 和长度校验；重跑可复用已完成的分块。安装标记仅在真实合成测试通过后写入。

## 选择

- **球球 · 本地中英文**：同一模型、同一参考音色朗读普通话、英文及混合句，不切换 Kokoro 英文声线。
- **球球 · 本地广东话**：同一参考音色，使用模型官方广东话指令；需要试听确认方言效果，文本不会自动翻译成粤语口语。
- 保留 **派蒙** 和 **Kokoro 中文女声**，可以随时切回。安装不会自动覆盖原声线选择。
- **安徽话暂未提供**：开源模型的官方已支持方言列表中未找到明确依据。云端龙安欢的方言能力不等同于开源模型能力。

这是免费本地候选音色，**不是云端龙安欢 V3**。试听采用官方仓库随附的 `asset/zero_shot_prompt.wav` 示例参考，原文为“希望你以后能够做的比我还好呦。”，未下载或克隆龙安欢的付费试听音频。音色是否合适及方言自然度以用户试听为准；后续可换成获授权的参考录音。

## 运行与排查

首次选择时启动独立工作进程，冷加载需要时间。工作接口仅绑定 `127.0.0.1:9881`，由 Bridge 随机生成进程密钥；不对 Tailscale/公网开放。推理设置离线模式，合成文本只发往本机工作进程。日志为 `tts-cosyvoice\worker.log`。

安装后的原始试听 WAV 在 `tts-cosyvoice\auditions`。Bridge 将输出经过低通重采样转换为 16 kHz PCM16，并沿用现有音量滑块。停止或替换播放时，已取消的合成结果不得进入设备队列。

网页右上角“语音工具”内可切换声线、选择试听语言、编辑试听文本并播放。普通话与英文共用同一音色；英文试听会先退出广东话模式。播放按钮可以再次点击停止。

球球的 100% 音量上限已校准到用户确认无杂音的测试档位，使用软限幅避免一个瞬时尖峰压低整段人声。球球播报期间自动暂停动画，等待设备实际播放结束后再恢复；用户原本手动暂停的动画不会被强制打开。派蒙、Kokoro 的原有响度基准不变。

## 来源与许可

- [官方代码](https://github.com/QwenAudio/CosyVoice)，Apache-2.0，代码修订 `074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc`。
- [官方模型与模型卡](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512)，Apache-2.0，模型修订 `29e01c4e8d000f4bcd70751be16fa94bf3d85a18`。
- 第三方 Matcha-TTS 保留上游子模块及许可。模型、音频、环境、访问密钥不上传项目 Git。
