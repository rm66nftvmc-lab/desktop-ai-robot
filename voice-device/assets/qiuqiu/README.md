# 球球显示主题

视觉参考：[sam70361/aora-bot 的球球](https://github.com/sam70361/aora-bot/blob/main/emotion-ball/assets/screenshots/qiuqiu.png)。原作者：sam70361，Copyright (c) 2026。

这是为 ESP32 编写的轻量适配：脚本生成暖色球体纹理，固件在完整 RGB565 缓冲区中绘制连续视线、眨眼及状态动作，再一次传送到屏幕。没有移植原网页的全部 32 种表情、彩带或浏览器引擎。原角色的素材和缓存完整保留。

运行 `python scripts/build_qiuqiu.py` 可重新生成 `texture.png` 和 `voice-device/src/qiuqiu_assets.h`。生成结果及球球形象衍生内容遵循附带的 [LICENSE](LICENSE) 和 [NOTICE.md](NOTICE.md)：仅供个人非商业技术学习、研究和交流，球形角色视觉形象禁止商业使用。两份声明原样保留；该限制不应被仓库其他许可覆盖。
