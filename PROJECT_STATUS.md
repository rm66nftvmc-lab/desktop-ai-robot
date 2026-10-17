# Desktop AI Robot project status

Last updated: 2026-10-17

## Purpose and layout

This project connects an ESP32-S3 voice device to a Windows Bridge service and a shared desktop/mobile web interface. Speech recognition and speech synthesis run locally on the computer. The web client sends text only.

- `bridge/`: authenticated local API, device protocol, local storage, voice pipeline, and Hermes / DeepSeek Harness adapters.
- `web-client/`: responsive chat UI, agent conversation lists, speaker controls, and mobile-friendly navigation.
- `voice-device/`: ESP32-S3 PlatformIO firmware, screen assets, microphone, button, and speaker transport.
- `scripts/`: asset generation, model setup, and development utilities.

## Working features

- ESP32-S3 connects to Bridge over USB CDC, reports button and audio state, uploads microphone PCM, and receives acknowledged speaker audio and screen frames.
- A button recording follows the currently selected AI and conversation. It transcribes locally, sends the result to that conversation, and queues the response for robot playback. Selecting mute keeps answers in chat without speech output.
- The web UI supports Hermes and DeepSeek Harness conversations, switching, creation, single deletion, and selection-based bulk deletion. Doubao PPT is not an active conversation target.
- Hermes uses the local Gateway integration and can continue a desktop session. DeepSeek Harness uses its local desktop web runtime and continues its current session.
- Paimon is the selected Chinese voice; English passages use the Kokoro English voice. The user preferred this mixed-language arrangement after testing. Volume and mute settings are controlled in the UI.
- The ST7789 display runs cached/interpolated face animation. The user confirmed the latest cache optimization looked smooth and normal.
- The Bridge can be reached from the dedicated Android phone through the user's private Tailscale network. Do not expose it with a public router port or Tailscale Funnel.

## Latest verified state

- Bridge and ESP32-S3 were connected during the latest hardware tests.
- Hermes and DeepSeek Harness routing were exercised. The user confirmed a Hermes button-recording reply played through the robot speaker.
- Harness permanent deletion is implemented through a locally installed `dsh-plugin-session-delete` v0.3.4 in the Bridge-specific `.dsh/profiles/web` profile. The plugin is an external local dependency and is not included in this repository. The API path and failure recovery have been tested; a real user session was not deleted as a destructive test.
- Last recorded full Bridge test run: **87 passed**. Rerun before relying on this checkout because the machine may have changed since that run.
- The selected voice setup and third-party model files live under `%LOCALAPPDATA%\DesktopAiRobot`; they are intentionally outside the repository.

## Known follow-up work

1. Recheck Bridge startup and the authenticated remote page from the dedicated Android phone after a fresh restart; prior remote access hit an `Invalid host header` issue before the Tailscale Serve/host configuration was corrected.
2. Verify bulk deletion against multiple disposable Harness sessions and confirm errors remain visible long enough to read. Avoid using real conversations for destructive tests.
3. Keep the mobile sidebar gestures and desktop layout usable at narrow widths; the web UI is shared across devices.
4. Document a clean-machine installation path for the optional Paimon/Kokoro/Whisper models and the Harness delete plugin, without copying model weights or credentials into Git.
5. Consider a small Windows service/startup setup only after confirming the desired restart and privacy behavior.

## Local setup and safety

Install Python dependencies with `python -m pip install -r requirements.txt`. Run the Bridge from the repository root with `python -m uvicorn bridge.app.main:app --host 127.0.0.1 --port 8787`. Install PlatformIO and use `voice-device/platformio.ini` for firmware builds. See the root `README.md` and `voice-device/README.md` for detailed setup and pin mappings.

Runtime data, access keys, API keys, local databases, logs, virtual environments, model weights, and PlatformIO build output must stay out of version control. Keep the GitHub repository private while the project's security and deployment model is still evolving. Rotate any credential that has ever been pasted into a public location.
