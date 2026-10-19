# Desktop AI Robot project status

Last updated: 2026-10-19

## DSH Pet precomputed motion playback (2026-10-19)

- User rejected 1.15: residual stutter/flicker remained. Firmware **1.16** replaces normal per-pixel temporal blending with precomputed bidirectional optical-flow frames: **13 × 402 = 5,226 frames at 40 fps**, approximately 10.05 seconds per clip (less than 9 ms difference from the full 241/24-fps source). State changes retain a 220 ms crossfade from the last displayed frame. No clear/blank intermediate frame is sent.
- The drawing viewport is 168×168 at physical (36,76), with a tighter source crop and a slightly smaller character. Gamma 0.85 remains. All 13 clips and the 8–22 second post-action idle interval remain; Emotion Ball and audio gain are unchanged.
- The 48-fps trial exceeded Flash capacity and was not flashed. The final 40-fps pack is approximately 15.16 MiB. Firmware is **16,424,381 / 16,711,680 bytes** (98.3%). The unused SPIFFS partition was removed to enlarge the factory app to 0xFF0000; NVS is retained. There is only approximately 287 KB app headroom, so future asset additions must check the build size. No OTA slot is provided.
- Built and flashed with hash verification. Full pack validation and regression tests: **146 Python + 11 Node passed**. During actual audio playback, **320/320 audio frames** were acknowledged with animation and speaking action 4 active, CRC 0 and continuous uptime. Presentation deltas were **120/119/120 over roughly three-second intervals** (~39.6–39.9 fps), compared with ~32 fps in 1.15. Normal frame copying replaced the previous approximately 9 ms blend work; stage counters remain asynchronous diagnostics.
- The 100-second state/random run passed: LISTEN/THINK/SPEAK mapped to actions 2/3/4, three idle random actions occurred, continuous uptime and zero decode/CRC errors. Sampled end-to-next-start random gaps were approximately 17.36 and 13.60 seconds. Bridge reconnected on 1.16 with desired/actual theme 2. Theme 1 measured 180 presentations per 3 seconds; switching back to theme 2 measured 120 per 3 seconds. A real CosyVoice sentence queued successfully and played with animated speaking action 4, with no connection loss. Physical visual acceptance is pending; throughput measurements do not establish that residual flicker is resolved.

## DSH Pet smoothness and brightness follow-up (2026-10-19)

- User accepted removal of whole-background flashing, but then reported low smoothness, slightly low brightness and residual flicker. Firmware **1.15** raises picture luminance (palette gamma 0.85; measured background luminance +18.4%, physical backlight wiring unchanged).
- Packed-channel RGB565 interpolation replaces separate channel arithmetic, with exact same-color/endpoints and 32 interpolation levels. The packed result was checked against independent per-channel averaging for 20,000 random cases. Stable frames skip the old transition snapshot read; the current/lookahead buffers swap pointers instead of copying 73,728 bytes each source step. One full-frame cache now fits internal RAM, with a PSRAM fallback.
- Actual 1.15 hardware playback: **320/320** audio frames acknowledged, speaking clip 4 active, animation enabled, CRC 0, no restart. Presents increased by 95/97/96 over approximately three seconds during speech (~32 fps), and by 112 over three seconds after speech (~37 fps). Original clip duration and 8–22 second random gaps are unchanged. These are measured rates, not the 50 Hz scheduling target.
- Added device stage timing counters (`pet_decode_us`, `pet_color_us`, `pet_blend_us`) and `pet_internal_frames` for future profiling. Stage counters are best-effort asynchronous telemetry; cumulative presentation/uptime deltas are used for measured rate.
- 1.15 is flashed and Bridge reconnected, theme 2 restored, internal frame allocated. User rejected the physical 1.15 recheck: playback still stutters or flickers. This is not a validated visual fix.

## DSH Pet animation theme (2026-10-19)

- Firmware 1.14 adds theme 2, `dsh_pet`, from pinned PC2005-cloud/dsh-pet sources; Emotion Ball remains theme 1. The removed old whale-girl atlas remains absent.
- Thirteen full 241-frame source clips (24 fps) fit a 10.36 MiB compressed indexed-color pack. A fixed dusk background, on-device intermediate RGB565 blending, 220 ms state crossfades and final-only changed-tile output avoid empty frames. No per-frame transfers from the computer.
- LISTEN → note-taking, THINK/APPROVE → thought bubbles, SPEAK → talking. Eight additional fun clips are selected randomly only while idle, without immediate repeats. Next trigger waits 8–22 seconds after the previous fun action ends; busy states interrupt and reset the idle schedule.
- Bridge display menu switches/persists both themes and restores selection after USB reconnect. DSH Pet keeps animation during CosyVoice playback; Emotion Ball retains its tested quiet-screen playback policy. Audio gain is unchanged.
- Full binary/delta validation and theme reconnect/audio-policy tests added: 146 Python + 11 Node tests pass. Build succeeds at approximately 11.42 MB / 15,663,104 bytes; 16 MB physical Flash is required. Material restrictions/attribution are in the asset NOTICE and README; original videos stay outside Git.
- Hardware 100-second state/idle test passed: LISTEN/THINK/SPEAK map to clips 2/3/4, three random actions occurred, uptime increased continuously, CRC and decode errors stayed zero. Actual presentation is approximately 27 fps idle / 22 fps during speech with current full-body art; 50 Hz is a scheduling target, not a claimed measured rate. Rendering copies PSRAM rows into internal buffers before blending; contiguous row transposition and internal inflate output reduce external-memory work. Missed source frames advance through only the missing deltas, avoiding a keyframe-replay slowdown.
- User observed whole-background flashing. Reproduction found a separate Bridge reset loop: opening a port with default DTR/RTS and lowering them afterward resets USB-UART ESP32-S3; a heartbeat write during boot times out, reopens and resets again. Control lines now configure before open, with a three-second first-heartbeat grace while reading HELLO. Two regression tests cover line ordering and cold-boot write suppression. Live Bridge subsequently connected with both themes set to 2 and stable uptime. User then confirmed **background no longer flashes**.
- Audio concurrency regression was reproduced with low-amplitude PCM: the cross-core display path reset during USB/I2S playback, while Emotion Ball succeeded. Pinning the single-owner display task to the USB/I2S core and yielding idle polling time fixed reproduction. Two subsequent approximately ten-second runs each acknowledged **320/320** audio frames with speaking clip 4 and animation enabled, CRC 0 and continuous uptime. A final real CosyVoice sentence through Bridge acknowledged **122/122** frames with animated speaking and no connection loss.
- Following the requested physical test, the user reported playback smoothness/brightness/residual flicker; see 1.15 follow-up above. The earlier whole-background reset-loop confirmation is distinct from residual motion flicker.

## Emotion Ball only firmware (2026-10-19)

- User requested removal of the first downloaded whale-girl character from firmware. `voice-device-1.13` removes its compiled bitmap/compressed-frame header, decoder, background renderer and 7,372,800-byte pose cache. `faces.h` now contains only the eight stable state protocol IDs; Emotion Ball texture, continuous motion, transitions and changed-tile rendering remain.
- Boot renders Emotion Ball directly. Theme telemetry is always 1; old wire commands 0/1 both retain the sphere. Bridge migrates any `original` preference to `qiuqiu`, rejects the removed API choice and exposes only Emotion Ball in the display menu. Original-character media/generators outside the firmware remain historical artifacts and are not built into the device.
- Firmware flash usage dropped from approximately 2.80 MB to **371,181 bytes** (11.1% of the application slot); binary image is 371,552 bytes. Pixel composition buffer is now 73,728 bytes, with no legacy frame cache or decompressor allocation.
- Compiled and flashed to COM9 successfully. Live device reports `voice-device-1.13`, actual/desired theme 1, cached frames 0, changed-tile buffer present, animation enabled, CRC 0 and **180 presentations in 3 seconds**. Physical appearance is not inferred from telemetry. Regression suite: **141 Python tests + 11 Node interaction tests passed**; retired bitmap tests were replaced with Emotion Ball texture/transport validation, and legacy preference migration is covered.

## Free local Qiuqiu voice and UI (2026-10-18)

- User chose **free local only**. CosyVoice 3 runs in its own computer-side environment; no cloud voice account or paid synthesis call is configured. This is an alternative voice, not cloud Long Anhuan V3. Paimon and Kokoro remain available.
- Voice tools offer Qiuqiu Mandarin/English and Qiuqiu Cantonese, plus Mandarin, English, mixed-language and Cantonese audition presets. Voice switching finishes before audition begins. Short English/mixed utterances remain intact instead of using the legacy 18-character first chunk. Separate cached Cantonese instruction conditioning prevents reuse of the generic Mandarin prompt.
- Actual offline synthesis succeeded for all four audition types. Earlier robot tests confirmed complete audio acknowledgement with CRC 0, but the user reported continuous noise and insufficient loudness. A whole-clip peak cap was reducing average loudness; Qiuqiu now uses bounded soft limiting. The user confirmed **no noise / normal sound** for the subsequent 60%-volume, paused-animation test. That exact amplitude is now Qiuqiu's 100% slider ceiling, without changing other voices.
- Qiuqiu playback automatically pauses animation while host audio or device audio remains active and restores the user's requested animation state afterward. This applies to message readout, test speech and automatic AI replies. The combined quiet configuration is validated; which individual change removed the noise has not been isolated.
- UI integration verification: **142 Python tests and 11 Node interaction tests passed**. A real Bridge audition at the new 100% ceiling completed **108/108** audio acknowledgements, CRC 0, no disconnect. Telemetry confirmed animation paused during speech and resumed after playback. The bilingual local Qiuqiu voice is selected on this computer.
- Installation and license/source details: [LOCAL_COSYVOICE.md](docs/LOCAL_COSYVOICE.md). Anhui speech is not offered because explicit support in this open model has not been established. Source/model revisions are pinned; downloaded weights are checksum-verified and excluded from Git. The private worker binds loopback and uses a per-process secret.

## Changed-pixel display update (2026-10-18)

- User observation: 60 Hz still flickered during recording/playback; pausing animation removed the flicker during those operations. This links the visible issue to continuous display updates; it does not establish a specific panel timing/electrical cause.
- Firmware `voice-device-1.12` caches the preceding face region (23,940 bytes) and compares the completed RGB565 output in 8×8 tiles. Only neighboring changed tiles are merged and transmitted; clean tiles are never bridged. Old feature locations are restored in the composed frame and included in the comparison, avoiding trails without a base-only erase pass on screen. Identical quantized frames perform no SPI write.
- Theme changes, solid-color tests and first entry invalidate the comparison cache and repaint completely once. Allocation failure falls back to the previous region transfer. All SPI activity remains on its single rendering task, with the 60 Hz motion clock retained.
- New device diagnostics report actual ball pixel bytes sent, changed-tile count and comparison-buffer availability. Backend regression suite: **134 tests passed**. Hardware: ~60 motion updates/s, 86.5–87.3% fewer pixel bytes in recording-expression/thinking previews and 89.5–90.3% fewer during actual speech; 387/387 audio acknowledgements, CRC 0, comparison buffer available, no disconnect. **User confirmed the physical recording/reply test no longer flickers.** Keep this changed-tile version as the verified display baseline.

## Faster Qiuqiu rendering and expression gallery (2026-10-18)

- Firmware `voice-device-1.11` moves all SPI drawing to one FreeRTOS task on core 0; the Arduino core continues USB, microphone and I2S output. Atomic pending commands and status fields prevent cross-core mutation of the pixel buffer. If task creation fails, the original single-core service remains available.
- Qiuqiu targets 60 Hz with a microsecond clock. A rotated RGB565 base texture is cached once in PSRAM (73,728 bytes); per-frame texture restoration uses contiguous row copies. Tighter capsule bounds, one rotation normalization per eye and skipped invisible features reduce composition work. Full theme entry and steady-state opaque region transfers preserve the background without clearing between poses.
- Motion timing is 1.25x faster, attentive eyes have a small visible gaze movement, and shape transitions reach ~95% in 195 ms. The original character, SPI clock, speech voices and volume settings are retained.
- Previous firmware measured ~30 fps during real speech; this was not evidence of a speech-specific frame collapse. This revision raises update cadence; the user still needs to judge residual flicker on the physical panel.
- Hardware verification: idle, recording-expression preview, thinking, approval, error and sleep measured **60 fps**; real audio playback measured **59.84–60.17 fps**, with **301/301 acknowledgements**, CRC 0 and no disconnect. Genuine button-recording throughput and visible flicker remain physical checks. Theme-switch and pause/resume are checked separately through Bridge.
- `scripts/render_qiuqiu_preview.py` generates the current expression gallery: idle, recording, thinking, speaking, sleep, approval (shares thinking), and error. It is a schematic of implemented poses, not the upstream project's full expression set.

## Qiuqiu state expressions (2026-10-18)

- Firmware `voice-device-1.10`: recording uses wide symmetric attentive eyes; thinking uses an upward gaze, asymmetric squint and three animated dots; speaking uses softened eyes and an opening mouth driven by the outgoing PCM energy. Silent audio and playback completion close the mouth. The original character is retained unchanged.
- All eye position, shape, tilt, dot opacity and mouth changes retarget from the currently displayed pose using time-based smoothing (~270 ms to 95% of a change). Interrupting a transition does not jump to a fixed starting frame.
- Sphere entry draws a complete frame; normal updates rebuild only the fixed face region from its original texture before a single opaque SPI transfer. Recording remains animated. USB audio processing yields between frames so a continuous playback queue cannot starve display updates or the button.
- Recording stop enters THINK directly. Accepted voice approval resumes THINK; denied approval and empty transcriptions return READY. Stale host face commands cannot override the recording expression.
- Backend regression verification: **133 Python tests passed**, including approval and empty-transcription screen states. Firmware built and uploaded successfully. Hardware expression previews reported LISTEN/THINK at ~30.3 fps, CRC 0, ~5.6 ms region transfers. The spoken test completed with 187/187 audio acknowledgements and no disconnect. Physical expression/transition confirmation is a user check.

## Qiuqiu display and incremental answers (2026-10-18)

- Firmware `voice-device-1.9` preserves the original character and all 64 cached poses, and adds an independently rendered Qiuqiu sphere theme. Continuous eye movement and blinking render at measured **30.3 new frames/second** (91 frames per ~3 seconds); a whole opaque buffer is sent without clearing between frames. Texture generation is reproducible with `scripts/build_qiuqiu.py`. Recording freezes the display to protect microphone capture; speaking keeps animation enabled.
- The screen icon beside the device badge opens an Original / Qiuqiu selector. The authenticated, same-origin `/api/device/theme` endpoint persists the choice in the existing settings database and replays it on USB handshake. Actual switch back to Original and back to Qiuqiu succeeded with 64 cached poses retained and CRC errors 0. Qiuqiu is selected on this computer.
- Character reference: [sam70361/aora-bot](https://github.com/sam70361/aora-bot). This is a lightweight hardware adaptation, not the entire browser emotion engine. Ball visuals are **non-commercial only**; original LICENSE and NOTICE are retained under `voice-device/assets/qiuqiu/`.
- Hermes official SSE and Harness authenticated session-follow WebSocket deliver public text incrementally. Reasoning and tool arguments are excluded. Web polling is scoped to the selected agent/conversation and ignores late results after switching. Final native history replaces live text.
- “停止回答” cancels the selected queued/running request. Harness queued requests are removed from its inbox; active requests wait for their own turn-end. A remote acknowledgement alone is not treated as a confirmed stop. Failed confirmation stays visible. Accepted cancellation suppresses late automatic speech; it cannot undo already executed tool actions.
- Verification: **131 Python tests and 10 Node interaction tests passed**; firmware built and uploaded successfully. Live disposable-session tests passed for **both agents**: multiple partial updates before completion, stop during output, confirmed interruption, and permanent removal of test conversations. Browser visual and physical appearance checks remain user observations.


## Message playback toggle (2026-10-18)

- Assistant-message speech actions now use a compact play icon that becomes a stop icon immediately, including while speech is being generated. Clicking again stops the same request; switching messages moves the active state to the new message. Touch hit areas are larger than the visible icon.
- Added authenticated same-origin `POST /api/tts/stop` and optional `playback_id` on `/api/tts/speak`. Retired IDs prevent cancelled requests from starting late. Generation-aware stops cannot stop a newer recording or playback. Polling and message rerenders preserve the active icon until audio drains or is interrupted.
- Verification: **121 Python tests and 8 Node tests passed**, including concurrent stop during synthesis, cancellation before arrival, delayed stops, rapid message switching and message rerendering. Physical listening/visual confirmation is still a user check.

## Bridge maintenance release 0.2.0 (2026-10-18)

- Database startup now runs a time-bounded, read-only integrity check. Corrupt databases and schemas from a newer Bridge are refused without replacement or downgrade. A temporarily busy check is reported as deferred. Schema version 1 preserves existing messages.
- Production startup uses `python -m bridge.run`. Bridge runtime logs rotate at 2 MiB with three retained archives (four files total); startup stdout/stderr retain three previous runs. AI model and Harness logs are separate. Existing-listener detection verifies the process and health endpoint before declaring Bridge ready.
- Authenticated status/diagnostics include Bridge version, uptime, startup database-check result, database/log sizes and free disk space. A low-space warning appears below 1 GiB; no automatic data deletion or chat backups are introduced.
- Pytest import-time application creation is now isolated from the real data store and the installed Harness executable.
- Verification: **116 Python tests and 6 Node tests passed**. Live launch, device handshake, version/diagnostic checks and repeated-start detection passed. No speech or firmware settings were changed.

## Latest update (2026-10-18)

- Added shared task status: recording, local transcription, waiting for AI, approval, generating speech, playback, completion, failure, and interruption.
- Short/empty recordings and model errors now terminate the task with an actionable message. USB disconnects discard old capture/playback buffers; reconnects cannot replay stale speech or resend messages. Missing device heartbeats and speaker acknowledgements fail visibly.
- Harness recovers its expired authentication cookie once after an explicit 401 and can restart its owned host. Ambiguous failed writes are never automatically retried.
- Bulk deletion processes five sessions at a time, displays progress, retains failed selections and errors across automatic conversation switching, and filters host catalog entries only after permanent purge is confirmed. Two fresh native Harness sessions were permanently deleted through the running Bridge and did not reappear in its catalog.
- Mobile keyboard height follows the visual viewport. Sidebar gestures require a clear horizontal swipe, distinguish pointer IDs, and do not treat diagonal scrolling as a swipe. Keyboard focus stays inside the open sidebar. Approval polling no longer repeatedly steals focus.
- Added authenticated content-free diagnostics (`/api/diagnostics`), web download, local `scripts/check_bridge.py`, and `start-robot.cmd` for one-click startup. Voice settings and firmware remain unchanged.
- Automated verification: **108 Python tests + 6 Node interaction tests passed**. Live Bridge restart, ESP32 handshake, diagnostic export, and native Harness batch deletion passed. The in-app browser's saved access policy blocked opening the local page, so this update has no real mobile visual/keyboard verification and no new physical speech/button test.
- Unpublished status documents contained the local access key. It has been removed from the publication snapshot and its unpublished commit ancestry is kept only in a local backup branch, not pushed.

## Purpose and layout

This project connects an ESP32-S3 voice device to a Windows Bridge service and a shared desktop/mobile web interface. Speech recognition and speech synthesis run locally on the computer. The web client sends text only.

- `bridge/`: authenticated local API, device protocol, local storage, voice pipeline, and Hermes / DeepSeek Harness adapters.
- `web-client/`: responsive chat UI, agent conversation lists, speaker controls, and mobile-friendly navigation.
- `voice-device/`: ESP32-S3 PlatformIO firmware, screen assets, microphone, button, and speaker transport.
- `plugins/`: vendored DSH plugins needed by the Bridge's Harness host (currently `dsh-plugin-session-delete` 0.3.4, MIT).
- `scripts/`: asset generation, model setup, offline plugin install, and the pinned-store Bridge launcher.
- `docs/`: setup/recovery manual, wiring, protocol and verification notes.

## Working features

- ESP32-S3 connects to Bridge over USB CDC, reports button and audio state, uploads microphone PCM, and receives acknowledged speaker audio and screen frames.
- A button recording follows the currently selected AI and conversation. It transcribes locally, sends the result to that conversation, and queues the response for robot playback. Selecting mute keeps answers in chat without speech output.
- The web UI supports Hermes and DeepSeek Harness conversations, switching, creation, single deletion, and selection-based bulk deletion. Doubao PPT is not an active conversation target.
- Hermes uses the local Gateway integration. **Hermes 0.22.1 refuses API writes into desktop sessions** (409 `permission_denied`), so Bridge routes to an API-created session and creates one when needed; desktop sessions remain readable in the catalog. DeepSeek Harness uses its local desktop web runtime and continues its current session.
- Paimon is the selected Chinese voice; English passages use the Kokoro English voice. Volume and mute settings are controlled in the UI.
- The ST7789 display runs cached/interpolated face animation from 64 PSRAM-cached poses. The user confirmed the animation looked smooth and normal.
- The Bridge can be reached from the dedicated Android phone through the user's private Tailscale network. Do not expose it with a public router port or Tailscale Funnel.

## Latest verified state (2026-10-17 evening)

- **Hardware is connected and was exercised end-to-end.** `COM9` (`303A:1001`), firmware `voice-device-1.8`, `device_bad_crc=0`, `screen_cached_frames=64`, face `READY`, speaker `audio_down_ack` matching `audio_down_sent` (122/122 and 326/323 samples during test sentences).
- **Runtime data store was consolidated.** The real store had been created under the Codex package's redirected `LOCALAPPDATA` while the machine anchor pointed at an empty duplicate (random key, no models). The real store (local access key (not stored in Git), 0.88 GB Whisper/Kokoro models, 12.83 GB Paimon install, real history) was moved to `%LOCALAPPDATA%\DesktopAiRobot`; the old duplicate is preserved as `DesktopAiRobot.stale-20261017-200318`. The anchor is consistent again.
- **Bridge startup is now one command** through `scripts/start_bridge.ps1`, which pins `ROBOT_DATA_DIR` from the anchor, verifies models/plugin, starts uvicorn detached, and supports `-Restart`.
- **Harness session lifecycle was verified with a disposable session**: a Bridge-created Harness draft answered `bridge-ok`, then was permanently deleted (`native_session_deleted=true`) and disappeared from the catalog. The delete route was re-probed after a Bridge restart and returns `session-not-found` for an invalid ID instead of a missing-route 404.
- **The missing DSH plugin is now vendored in-repo** at `plugins/dsh-plugin-session-delete` with an idempotent offline installer (`scripts/install_dsh_plugin.ps1`). The `web` profile dependency now uses the local `file:` path.
- **Paimon and Kokoro both played through the robot speaker** in this session (Paimon via `/api/tts/speak`, English via Kokoro earlier). No synthesis or CRC errors.
- **Local STT was verified with a round trip**: Paimon synthesized `今天天气不错，我们测试一下语音识别。`, and `faster-whisper small` recognized it correctly (punctuation dropped). This exercises the model cache after the store move.
- **The physical button captured speech during this session**: presses produced 55,680 and 52,352 PCM samples, and Whisper transcribed `這樣就說好了`, `1加1等于1`, and `dbs你现在用的是什么模型`. The first two returned 409 `session_busy`; the last returned 409 `permission_denied`. Source inspection confirmed Hermes 0.22.1's `admit_api_steps` refuses any target whose session source is not `api_server`/`bot_room`, so a desktop session can never receive an API turn.
- **Hermes routing was corrected for that policy**: Bridge now prefers API-created sessions, creates one when none exists, and refuses a desktop target with an actionable Chinese message *before* sending. A dedicated conversation (`桌面机器人专用会话`) was created and exercised twice (`机器人已就绪`, `链路正常`); the persisted voice target now points at it. A fresh disposable Hermes conversation also answered and was deleted.
- **Remote access through Tailscale Serve was verified from the host**: `https://<host>.<tailnet>.ts.net/` served the page and the authenticated API, login returned a `Secure` + `HttpOnly` cookie, and `/api/status` reported the device. Serve is tailnet-only (no Funnel). `ROBOT_TAILNET_HOST` is set at User scope, so a scheduled task inherits it.
- **Bulk deletion was exercised with two disposable local drafts**: `deleted=2, failed=0`, and no catalog residue remained. Native multi-session deletion still needs a disposable-session run.
- Last full Bridge test run: **108 passed** (`python -m pytest bridge/tests -q`), including 9 vendored-plugin tests, 2 Hermes error-detail tests, and 3 Hermes source-routing tests.

## Known follow-up work

1. Run one clean **button → reply → speech** loop on the new API-backed session. Capture, STT, Hermes API continuation and TTS are each verified; this one combined press is the remaining physical check.
2. Confirm the remote page **from the physical Android phone** (`redmi-note-11t-pro` is online in the tailnet). Serve, TLS, host header and the secure cookie are verified from this machine; the phone still needs to open the URL and enter the access key.
3. Native Harness batch deletion and persistent failure selection are verified; continue regression testing with disposable sessions only.
3. Keep the mobile sidebar gestures and desktop layout usable at narrow widths; the web UI is shared across devices.
4. Optional: move Bridge startup into a per-user scheduled task after confirming the desired restart/privacy behavior. Do not install it as a system service (different `LOCALAPPDATA` would fork the store).
5. The 404 diagnostic now points at `scripts/install_dsh_plugin.ps1`; keep that message aligned if the plugin layout changes.

## Local setup and safety

See [docs/SETUP.md](docs/SETUP.md) for a clean-machine install, store recovery and verification checklist. Short version:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File .\scripts\install_dsh_plugin.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start_bridge.ps1
```

Install PlatformIO and use `voice-device/platformio.ini` for firmware builds; stop the Bridge before flashing because it owns the serial port.

Runtime data, access keys, API keys, local databases, logs, virtual environments, model weights, and PlatformIO build output must stay out of version control. The GitHub repository is public; publish source and sanitized status only. Rotate any credential that has ever been pasted into a public location.
