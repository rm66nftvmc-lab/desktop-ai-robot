# Desktop AI Robot project status

Last updated: 2026-10-31

## Offline light speech cleanup (2026-10-31)

- Button and wake recordings now pass through local OpenCC 1.4.2 (`t2s`) and conservative cleanup before the existing authorized voice route. Default is light cleanup; an authenticated, persisted setting also offers simplified-only mode in the display/voice popover. Typed messages are unchanged. No extra model/API call or firmware update.
- Only a small allowlist of repeated request starters and explicit day/same-unit quantity corrections is rewritten. Negation, questions, ambiguous repairs, emphasis and repeated numbers are retained. Quotes, code, URLs and Windows paths are preserved verbatim; utterances containing these literals receive no rule-based rewriting. This is not free-form semantic rewriting or guaranteed ASR error correction.
- Recent original/cleaned comparison stays in process memory (last 20 transcript records); it is protected by existing access-key sessions, excluded from diagnostics, and never added to logs by cleanup. Normal submitted chat text retains existing conversation storage behavior. Missing conversion dependency falls back to original text with a visible warning; rule failure falls back to simplified text.
- Validation: 244 backend and 23 frontend tests passed, including generation-preserving recognition callback, negative/number/literal cases, settings persistence/auth/origin and failed UI saves. 2,000 warm local short-text runs: median 0.006 ms, p95 0.007 ms, max 0.439 ms; this measures cleanup only, not recognition or agent response time. Restarted Bridge serves the new controls; COM9 / firmware 1.65 connected, recognition model ready, light mode active. Live human recording acceptance remains to be checked.

## Start a stopped Bridge with the physical button (2026-10-31)

- Firmware 1.65 sends the 3-second hold event even before a Bridge handshake. Short presses still require a connected Bridge and retain manual recording behavior.
- Added a separate Windows login standby listener. While Bridge is down it reads only USB frames, verifies robot HELLO and CRC, and never sends WELCOME, microphone commands or AI requests. It closes USB before starting the existing anchored-store launcher, waits for health readiness, then opens Edge. While Bridge is running it relinquishes USB and the existing Bridge long-press handler opens the page.
- Installed per-user startup is reversible with `scripts/install_button_launcher.ps1 -Uninstall`. A Windows named mutex prevents duplicate listeners. Logs rotate at 1 MB with two backups. The listener bypasses proxies only for loopback health probes; the user's network proxy is unchanged.
- This works with the robot connected to this awake, signed-in Windows computer over native USB. It cannot start an off/sleeping computer, does not implement wireless discovery, and does not grant access-key/voice authorization. Existing Wi-Fi safe mode and all audio/display settings retained.
- Validation: 213 backend tests passed (one initial transient Windows temp-file replacement denial passed on isolated and full reruns). Firmware 1.65 built and the full 15,923,872-byte application digest matched after 868,352 bytes of differential writes. Per-user login startup installed; independent listener process/log confirmed with Bridge stopped, and a second launch exited without starting a duplicate listener. Physical long press was received at 11:57:45; Bridge became ready and Edge launch was issued at 11:58:08 (~23 seconds). Live status confirmed COM9/1.65 connected, not recording, CRC errors 0. User initially reported no page before startup completed, then confirmed the Bridge page opened in Edge.

## Physical button opens Bridge in Edge (2026-10-29)

- Firmware 1.64 distinguishes a debounced short release from a 3-second hold (increased from 1.2 seconds at the user’s request). Short press retains start/stop recording; holding sends one OPEN_BRIDGE event, and releasing after a hold never starts a recording. Existing capture-control acknowledgements are unchanged.
- Bridge handles the event only after a device handshake, launches Microsoft Edge explicitly and suppresses repeated opens within three seconds. Opening the page never grants agent/voice authorization. Bridge must already be running on the computer; powering the robot alone cannot launch a stopped PC-side service.
- Validation: firmware build successful; 208 backend and 21 frontend tests passed for 1.63. Backed up full 16 MB flash privately, wrote 868,352 changed bytes, and verified the full 15,923,888-byte application digest. Bridge restored: COM9, firmware 1.63, connected, CRC errors 0, DSH Pet retained. User confirmed the 1.63 hold did not trigger recording. The requested 3-second adjustment in 1.64 compiled successfully, wrote 16,384 changed bytes, passed the full application digest verification and all three browser-action regression tests. Physical 3-second timing acceptance remains pending.

## Visible logout control (2026-10-21)

- Moved logout from the collapsed sidebar to an always-visible top-right “退出” button, with a 44px minimum touch target. Successful logout clears the input/drafts/key and returns to the access-key screen. Expired sessions also return to login; network/server errors retain the workspace and show a retry error instead of claiming authorization was revoked.
- Logout revokes the current browser session. Hardware voice stops when no other authorized browser sessions remain; this is not an all-devices logout.
- Validation: 21 frontend tests and 9 voice-access backend tests passed; JavaScript syntax and diff checks passed. Live HTTP confirmed the single logout control is inside the header and updated asset versions are served.

## Connection notice and voice authorization (2026-10-21)

- User requests the exact spoken notice “连接不上，没有大白饭吃，工作不了哟” for connection problems and explicitly requires that agents cannot be invoked without the access key. Existing web routes already required authenticated sessions; the separate hardware voice route previously did not require a web authorization grant. That gap is now closed.
- Successful authenticated selection/sync of the web AI target grants hardware voice access. Ordinary diagnostic login/status requests do not grant microphone access. Grants are memory-only, expire with the associated browser sessions and are lost on Bridge restart. All voice-authorized browsers must be logged out/expired to revoke shared hardware access; just closing a tab is not logout.
- Microphone input is checked before ASR/approval/submission; queued text requests bind to their own browser session, queued voice to their original grant. Workers recheck immediately before model dispatch; logout/expiry cancels pending/running work and CLI checks every 0.5 seconds. Local stop/cleanup requests can continue for already-sent runs; remote instantaneous cancellation is not guaranteed. New login cannot revive a revoked old voice request.
- Wake connection gate checks authorization before probing agents. Missing authorization/target or unavailable selected local API plays the cached notice, returns to armed and never starts capture or prompts an agent. Both cues retain current voice/mute. Paimon notice generated locally, ~6.495 seconds; this fixed audio is private, no user background audio stored.
- Bounded Harness read-only health uses an independent cookie jar, 0.4-second login/read timeouts and 2-second cache; never starts a Host or sends prompts. Existing Hermes authenticated capabilities health retained. Model-provider internet failures after local preflight remain possible.
- Validation: 205 backend tests passed. Live unauthenticated Hermes and Harness POSTs returned 401; authorized disposable Hermes text test completed and only its own session was removed. Diagnostic login still left voice_authorized=false. Both local API health checks succeeded. Bridge restarted with cached normal/failure cues ready; user confirmed the unauthenticated wake/notice behavior works correctly.
- Fully stopped Bridge/PC or disconnected robot cannot detect the wake phrase with the present PC-hosted recognizer. MCU offline wake remains unimplemented; no new firmware, wiring or display changes in this task.

## Wake cue rhythm replacement (2026-10-21)

- User reports “在呢” sounds unnatural with an internal pause. Inspection found the v2 cached Paimon clip lasts ~1.329 seconds with a pronounced inter-syllable energy dip. The cue was already one continuous WAV; the transport was not proven to be the cause of that perceived pause.
- Generated punctuation variants locally and selected an intact “在呢！” take lasting ~0.614 seconds with no internal low-energy gap at the check threshold. Installed it in the private v3 voice cache. Audio is not sped up or spliced between characters. New uncached generation retries up to three times when a cue is long or internally paused, preferring a shorter lower-gap take; this heuristic is not a guarantee of naturalness.
- Old cache remains private but is no longer selected. Background prewarm, voice binding, mute and input routing remain unchanged. During the first audition the host sent all 20 cue packets but stale device_playing telemetry rejected the following capture; fixed capture admission to accept the current acknowledged stream-completion generation. A busy capture now returns to armed after a short cooldown instead of remaining stuck in error.
- Validation: 194 backend tests passed, including internally paused cue retry, silent warmup/cache reuse, stale speaker status capture admission and transient-busy rearming. Bridge restarted with the replacement and capture fix; physical listening acceptance pending. User then requested a conditional spoken “bridge” when disconnected; clarification is pending because fully offline wake recognition is not implemented on the MCU.

## Faster wake and reply preparation (2026-10-21)

- User reports slow initial acknowledgement and unclear “我在呢”, requests “在呢” and faster responses. Cue changed to “在呢。” with punctuation for synthesis; trim excessive silence, retain phoneme edges, prewarm on startup/theme switch and persist only this fixed cue per voice in private cache. Cache is not user microphone audio. Active Paimon cue measured 1.329 seconds; initial local generation ~0.602 seconds and a fresh-process cache load ~8 ms.
- Complete plain Vosk partial hypothesis may trigger after ~300 ms stability; final-result confidence checks remain. Word-aligned partials withheld the last word and did not improve the initial experiment, so ordinary partial text is used. Synthetic positive fired at 1.9 seconds of input vs 2.6 seconds for final-only; three non-wake sentences rejected. This does not establish real-world false-wake rates.
- Automatic endpoint silence shortened 1.4→1.0 seconds with VAD; button recording remains manual. Whisper preloads the local model before the first recording. Long Ball voice replies synthesize a smaller complete first clause, preserving short English/mixed utterances and existing voice/volume.
- Added host stream-completion generation after all audio ACKs and AUDIO_END; the wake cue's 300 ms echo guard can use it instead of waiting up to 3 seconds for stale device_playing telemetry. No firmware, animation, microphone wiring or AI model settings changed. AI provider generation time remains outside these local optimizations.
- Validation: 191 backend tests passed before deployment, including persisted silent warmup, stale-STATUS handling, partial phrase stability, short-pause preservation and long-clause segmentation. Physical clarity and reaction-time acceptance remains pending user retest.

## Dual INMP441 enhancement first version (2026-10-21)

- User mounted two INMP441s front-to-back, 5 cm apart, both pickup holes up. Rear/original microphone L/R is GND; front/new microphone L/R is 3V3. Firmware 1.62 advertises stereo_protocol=1, negotiates mode 3, uploads synchronized PCM16 slots in frame types 24/25. Fixed mono channels and old firmware remain compatible.
- Bridge applies bounded delay-and-sum, conservative coherence filtering and low-frequency attenuation on PC, with single-channel fallback. Captures still route to the selected AI/session. Streamed local Silero VAD v6 replaces the automatic recording's loudness-only endpoint test. No new downloaded model, paid API or background audio storage. This is not voice identification, AEC or proven front-only rejection; coherent TV/other speech remains a limitation. Raw slot-to-physical mapping can be checked with close-talk tests.
- Tests: 186 backend and 19 Node passed; firmware builds successfully. Synthetic DSP checks preserve aligned signal and reduce independent noise by >3dB, process at ~0.096 ms per 8 ms block. Local generated speech and silence validate the installed VAD. These are not room-noise acceptance results.
- Firmware 1.62 application 15,923,760 B; verified old 1.61 backup, changed 974,848 B, verified full new flash digest. Live USB connected, stereo mode 3, both slots active, ~16k samples/s, CRC 0. Observed a real wake→acknowledgement→recording→AI→speech-send sequence; user has been asked about heard reply, automatic stop, missing words and loudness. Physical noise comparison remains pending.
- Display, bound voices, speaker controls, typed-input silence and Wi-Fi safe mode preserved. See docs/VOICE_WAKE.md for algorithms and scope.

## Spoken wake acknowledgement (2026-10-21)

- Wake-word recognition now says the fixed local phrase “我在呢” using the current bound voice, then starts automatic capture only after device playback is finished and a 0.3-second quiet tail. First synthesis may take longer; subsequent wakes reuse one in-memory voice-specific clip cache. No AI request is created for the acknowledgement.
- Acknowledgement microphone packets are discarded. Disable/disconnect/manual recording invalidate the pending wake; synthesis/playback failures return to armed with an actionable error instead of opening capture. Global mute skips the cue while retaining capture. Button recording, typed-reply policy, firmware and wiring are unchanged.
- Validation: 180 backend tests passed, including ordering, own-audio discard, disconnect/manual/disable cancellation, failed acknowledgement, mute and voice-cache switching. Physical wake/acknowledgement/recording timing remains pending user confirmation.

## Reply playback follows original input (2026-10-21)

- User requests automatic robot playback for both button and wake-word microphone questions; mobile typed questions receive text replies only. Both microphone paths already share the voice input route, and web submissions retain the text route on both mobile and desktop.
- Hardened final reply playback against a typed request becoming the active voice turn through spoken approval: the original stored input method and agent must qualify before automatic synthesis. Text approval prompts also remain silent. Manual message playback, global mute, volume, voices and firmware remain unchanged.
- Validation: 173 backend tests passed, including mobile text interleaved with a voice turn for Hermes and Harness, plus spoken approval preserving text/voice playback policy. No live AI messages or unsolicited speaker playback needed for this change; physical automatic playback acceptance remains with the user.

## Wake test: Hermes API recovery (2026-10-21)

- User confirms the existing INMP441 L/R is tied to GND. Second microphone remains unconnected; its future L/R selection is 3V3, opposite the first. No wiring or firmware changes in this repair.
- Live wake count reached 1 and recognition completed, but Hermes delivery failed because the local Gateway was not listening on 127.0.0.1:8642. Existing API configuration/key matched; no secret rewrite was required. Gateway was restored hidden, with authenticated capabilities and an actual short model reply verified. The disposable test session was permanently removed; the failed user recording was not replayed.
- Bridge now reports cached authenticated API health instead of assuming an installed client is connected. Connection refusal and timeout receive distinct actionable errors. Launcher reuses an existing listener or starts an already configured Gateway without replacing processes, changing keys or approving hooks. Missing optional configuration leaves other agents usable.
- Validation: 169 backend tests and 19 Node tests passed. Startup helper reused the running Gateway; Bridge restarted and reports API available, USB device connected and wake armed. Full spoken wake-to-answer acceptance remains pending user retry. Wi-Fi diagnostic state remains unchanged.

## Hermes reply recovery and read-only session visibility (2026-10-20)

- User reports no replies. Live state showed successful recording recognition but Hermes worker rejected the selected desktop-origin conversation: Runs API permits writes only to `api_server` / `bot_room` sessions. Device, firmware 1.52 and Paimon were healthy.
- Also found Gateway not listening on 127.0.0.1:8642. The current Hermes profile lacked its local API environment configuration; inherited process environment did not reach the multiplexed profile secret scope. Backed up the local Hermes .env privately and restored only API_SERVER_KEY (existing Bridge secret), API_SERVER_HOST=127.0.0.1 and API_SERVER_PORT=8642. Restarted the foreground Gateway hidden with the supported --replace option, without hook auto-approval or public listening. Private configuration/backup/logs are outside Git.
- Authenticated capabilities check succeeded. A new API session test completed and returned the requested short reply. This test did not play audio or retry any failed user request. Existing desktop history is untouched.
- Catalog marks desktop-origin sessions read-only in API mode. UI labels them, keeps history browsable, blocks text submission and exposes a one-click new writable Bridge conversation action. Backend checks writability before enqueueing text and before voice delivery. User must select/create a writable session to continue, preserving the old conversation instead of silently changing its history/context.
- Validation: **150 Bridge tests and 19 Node interaction tests passed**, including desktop history access, writable/new-draft resolution and pre-send UI blocking. Bridge restarted, latest app 30 / CSS 23 assets served. Gateway API restored; no firmware change.

## Raised DSH Pet stage and LCD text removal (2026-10-20)

- User requests a higher background stage so the character appears to stand on it, and removal of the bottom text line. Generator raises both stage ellipses by 20 logical pixels (top 208 -> 188), removes the LCD text draw, and keeps the source attribution in Bridge's theme panel, LICENSE and NOTICE.
- Regenerated every composited frame/background consistently: 13 clips x 402 frames, 168-square region, 40 fps source timeline and all original durations/action bindings retained. Manifest records the new background layout, attribution location and pack hash. Contact-sheet preview is shown in logical orientation.
- Firmware **1.52** changes only the embedded art and version. Selected 90 Hz settings, 100% image level, eased transitions, paired voices and Emotion Ball are retained. Build fits Flash (16,371,237 / 16,711,680 bytes); three asset/theme tests passed. Exact decoded preview shows feet aligned with the raised stage, no bottom text. All four bounded upload chunks passed their hashes, followed by a full 16,371,600-byte application flash digest match. Updated the private verified-flash baseline only after that full verification; Bridge restored and reconnected on 1.52, DSH Pet/Paimon binding retained, animation counters advance with decode errors/USB CRC 0. Physical stage-position feedback is optional; preview was visually checked.

## Character-bound voices and unified audition panel (2026-10-20)

- User requests DSH Pet -> Paimon, Emotion Ball -> local Ball Mandarin/English, removal of Ball Cantonese, and all voice audition controls moved into the display selector panel. Backend theme selection now sets/persists the matching voice under a lock, stops previous playback and queues the theme only after voice selection succeeds. App construction restores the binding without starting models; lifespan starts the selected engine. Legacy independent voice API rejects choices inconsistent with the selected theme.
- Removed the `cosyvoice-yue` product voice and its Cantonese synthesis mode routing. Shared CosyVoice weights remain because the Mandarin/English voice needs them. Paimon's existing English handling is unchanged. Missing model errors leave the previous display selection and voice config intact.
- Display panel now contains the bound voice label, Mandarin/English/mixed test presets, custom text and playback/error controls. Removed the independent voice icon/panel and free voice selector. Audition waits while a theme change is pending; changing audition language does not change the bound voice. The panel scrolls within mobile viewport height. Asset versions are app 29 / CSS 22.
- Validation: **149 backend tests and 18 Node interaction tests passed**, including persisted binding/restart, rejection of detached voices, missing-model preservation and HTML control ownership. Live authenticated API switching verified Ball/cosyvoice and Pet/paimon with device connected; restored the prior DSH Pet selection. Updated page assets are served. Bridge restarted; firmware 1.51 unchanged. No unsolicited audio playback or shared model-file deletion was performed. Browser pixel-level visual validation was not performed.

## Bridge draft and background-tab maintenance (2026-10-20)

- User accepts the current display configuration and asks to continue optimizing Bridge. Firmware stays at 1.51; the acceptance fixes the desired configuration and does not establish a flicker root-cause fix.
- Browser drafts are isolated by AI/session in tab-scoped sessionStorage, survive a page reload, and fall back to in-memory storage when browser persistence is unavailable. Only confirmed deleted sessions lose their drafts; explicit logout clears all Bridge drafts. Drafts are not sent to the server or AI until submission.
- Submission pins its AI/session before posting, rejects context changes while an unresolved session lookup is pending, prevents duplicate in-flight submission, and scopes success/error/focus handling to the originating context. Late confirmations preserve newly typed text and identical input in a different session. Uncertain write outcomes are not retried automatically.
- Hidden tabs suspend the existing periodic status/history/session/task reads; visibility return immediately refreshes all four and resynchronizes the hardware voice target. Browser asset cache versions advance to app 28 / ui-state 2; backend APIs and firmware are unchanged by this maintenance.
- Validation: **18 Node interaction tests and 146 Bridge tests passed**, JavaScript syntax and whitespace checks passed. Live authenticated HTTP checks confirm the latest HTML/JS assets are served and the robot remains connected on 1.51. No paid model calls, real chat deletion or robot firmware reflash was needed for the Bridge changes. Browser visual testing was not performed in this turn; the layout is unchanged.

## Eased action transitions restored (2026-10-20)

- User reports the no-crossfade trial looks like abrupt cuts and requests transitions back; no definitive flash verdict was provided for that trial. Firmware **1.51** restores `ACTION_CROSSFADE=true` and its existing 220 ms eased opaque blend. Normal source interpolation, selected 90 Hz settings and 100% software image level are retained.
- Build and incremental flash verification passed. Restoration is a user preference, not evidence that crossfades are cleared as a possible contributor to flicker.

## Action crossfade disabled for isolation (2026-10-20)

- User confirms pronounced flashes specifically on action switching. Firmware **1.50** sets `ACTION_CROSSFADE=false`: no 220 ms RGB frame mixing or transition-source copy on action changes. Complete next-action frames go through the existing checked dirty-rectangle writer; there is no clear or blank image inserted. Source interpolation inside each clip is retained, as are nominal 90 Hz scan, presentation target, 100% software image level and 40 MHz SPI.
- Build and incremental flash verification passed. This is an isolation change, not a claim that crossfade is proven to cause the flashes. Direct pose changes may be more abrupt; physical switch-flash feedback is pending.

## Maximum software image brightness (2026-10-20)

- At user request, firmware **1.49** sets `IMAGE_LEVEL=100`, restoring unattenuated source RGB565 colors for both palette and background. Selected nominal 90 Hz scan, presentation target, SPI clock and source timing stay unchanged. This is maximum software image level, not a claim of maximum hardware backlight output.
- Build and incremental flash verification passed; physical brightness/flicker feedback is pending.

## Slight brightness increase at 90 Hz (2026-10-20)

- At user request, firmware **1.48** raises software RGB565 image level from 90% to 95%, retaining nominal 90 Hz scan, 90 Hz presentation target, 40 MHz SPI and original source timing. This changes palette/background channel values, not the BLK circuit or backlight current.
- Build and incremental flash verification passed; physical brightness/flicker feedback is pending.

## Requested 90 Hz comparison (2026-10-20)

- User requests 90 Hz after the 1.46 audit trial, without a definitive visual verdict for 1.46. Firmware **1.47** selects nominal C6=0x05 (90 Hz scan) and an 11,111 us normal presentation target, retaining 40 MHz SPI, 90% software image level, checked single-transaction writes and the original source timeline.
- Build and incremental flash hashes passed. Bridge reconnected to 1.47 with animation enabled, USB CRC 0. Initial live windows show 248 and 239 presentations per 3 seconds (~80-83 Hz), so 90 is the configured target, not a claim of 90 actual delivered images/second or optically measured panel rate. Physical brightness/flicker feedback is pending.

## Pixel and SPI code audit (2026-10-20)

- User sees clean desktop replay of the exact embedded source frames and asks to audit transport code. This lowers suspicion of the asset but does not prove electrical SPI corruption.
- Three live frozen-frame checks on 1.45 matched host reconstruction of the exact RGB565 bytes (including 90% software dimming): idle frames 168 / 380 / 98 had FNV-1a hashes 3760828583 / 2329059366 / 3817219337 respectively, identical on host and device. This validates sampled decoded/shadow image contents, not LCD RAM readback.
- Audited buffer layout: the 168-square RGB frame plus 16-row transfer scratch fits inside the 192-square shared buffer; delta-cache scratch is overwritten by complete composition before output; only the display task owns composition/SPI after setup. Arduino 2.0.17 `SPI.writeBytes` is synchronous and its ESP32-S3 HAL polls 64-byte chunks. No confirmed asynchronous source-buffer reuse or out-of-bounds strip was found.
- Firmware **1.46** stages the rectangle and sends CASET/RASET/RAMWR plus pixels under one SPI transaction/CS assertion. All pet, background, fill and Emotion Ball pixel writes use a checked writer: validate window bounds, even RGB565 byte counts, no overrun, and exact expected byte count at end. Added `lcd_tx_errors` telemetry; this is software length/geometry validation, not electrical CRC/ACK from the screen.
- Build and incremental flash hashes passed, three existing asset/theme/audio-policy tests passed. A 32-second live serial sweep exercised both themes and recording/thinking/speaking/idle states; `lcd_tx_errors`, decode errors and USB CRC stayed zero, no restart. Normal pet delivery was approximately 74-75 Hz once warm. The original 75 Hz scan setting, 90% image level and source clip duration are retained. Bridge restored. Physical flicker feedback is pending.
- Remaining risks: the 8-pin display exposes no TE synchronization or MISO readback in the current wiring, so correct transmitted pixels can still tear during panel scan, and no screen-side integrity check exists. 40 MHz is a tested configuration, not a verified KAC module electrical rating. A DMA/scan-synchronization experiment would be a further change, not a claimed fix already made.

## Slight image dimming (2026-10-20)

- At user request, firmware **1.45** keeps the selected nominal 75 Hz scan / 75 Hz presentation target and 40 MHz SPI, while reducing RGB565 image channel values to 90% (rounded). This is software image dimming, not PWM or a change to BLK/backlight supply.
- Palette colors and the full background / initial transition source use the same mapping. Original assets are preserved; per-frame palette conversion gains no new per-pixel dimming pass. Build and changed-sector flash verification passed, Bridge restored and connected to 1.45. Physical brightness/flicker feedback is pending.

## Selected 75 Hz configuration (2026-10-20)

- User requested 75 Hz. Firmware **1.44** selects nominal ST7789 FRCTRL2 C6=0x09 scanning and a 13,333 us normal presentation deadline (~75 updates/second), while retaining 40 MHz SPI and the original 40 fps source timeline / clip duration. Both power-on initialization and normal theme/animation restoration use the selected scan setting. Diagnostic maximum-scan mode remains temporary, and other diagnostic comparisons retain explicit scan choices.
- Build and incremental flash verification passed. Bridge reconnected to 1.44 with animation enabled, CRC 0. Live telemetry: presents 526 -> 751 over 3000 ms and 751 -> 973 over 3001 ms, approximately 74-75 delivered presentations/second during those windows. This verifies transport cadence, not measured optical panel refresh. Physical brightness/flicker feedback is pending.

## Maximum scan / presentation diagnostic (2026-10-20)

- User reports 1.42 now flickers continuously, rejecting any claim that the normal-mode transition revision fixed it. Previous positive feedback applied to isolated mode 19, not every production workload.
- Checked ST7789V controller datasheet: C6 RTNA=0 requests nominal 119 Hz, RTNA=0x0F nominal 60 Hz. Exact KAC module rated maximum remains unverified. Scan frequency and pixel transport frequency are distinct; 240x320 RGB565 at 40 MHz has a theoretical full-screen ceiling of 32.55 images/second before protocol/software overhead. Controller serial timing and module wiring must not be inferred from ESP32 SPI capability.
- Firmware **1.43** adds temporary serial mode 20 (`steady-limit`): same idle clip, no fades/random actions, target 119 presentations/second and nominal highest C6 scan setting, SPI kept at 40 MHz. Normal scan setting remains 0x0F. Diagnostic cleanup/ANIMATION restores that scan setting. Earlier highest-scan trials became dim, so this is a 120-second bounded comparison, not a new permanent scan default.
- Build and changed-sector write hashes passed. Initial actual throughput is **225-226 presentations per 3 seconds (~75 Hz)**, not 119 delivered images/second; decode/transfer costs limit cadence. Source timeline stays 40 fps. User reports the image is too dark; actions are very smooth but flicker remains. This maximum-scan setting is rejected. The bounded test ended, cleanup requested C6=0x0F and normal animation, and Bridge reconnected to firmware 1.43. Reference: https://newhavendisplay.com/content/datasheets/ST7789V.pdf (FRCTRL2).

## Normal 60 Hz playback and transition revision (2026-10-20)

- User clarified the residual white flash occurs at both clip loops and state/action transitions; ordinary playback looks essentially normal at 60 Hz.
- Firmware **1.42** promotes 60 Hz repeated presentation / 40 MHz SPI to normal pet playback, including autonomous startup, animation commands and real state changes. Source assets remain 40 fps and original duration. Serial diagnostic modes retain their explicit comparison rates/clocks.
- Same-action loop rollover now carries elapsed time remainder and decodes the new cycle without restarting its fade. Host states mapping to the same action no longer restart the clip. Real action changes preserve the displayed image and use a smoothstep 220 ms opaque crossfade; no clear/white intermediate frame is introduced.
- Build, incremental flash hashes, three existing asset/theme/audio-policy tests, Python syntax and whitespace checks passed. A normal-mode visual state demo exercised recording/thinking/speaking/idle, with 40 MHz, approximately 180 presentations per 3 seconds, no decode/CRC errors or restart. Physical loop/transition verdict is pending; do not report the remaining white flash as fixed.

## 60 Hz repeated-frame comparison (2026-10-20)

- User requested 60 Hz after the 50 Hz trial, without a comparative visual verdict for 50 Hz. Firmware **1.41**, serial-only mode 19 (`steady-60`), retains the 40 fps source timeline and original clip duration; repeats resend final valid pixels in the last dirty rectangle. SPI remains 40 MHz. No new interpolated poses or blank frames are added; normal playback defaults are unchanged.
- Build and incremental flash hashes passed. Live device confirms mode 19, action 0, 40 MHz, **180 presentations and pixel writes per 3000 ms**, source frame advances 120, CRC 0. User reports **almost no continuous flicker, but occasional sudden white flashes**. Keep this distinction: 60 Hz improves the reported continuous flicker but is not a complete fix. The test continues pending classification of whole-screen versus character-area/loop-boundary flashes. This does not measure the panel's internal scan rate.
- Investigation so far: device uptime remains continuous, CRC and pet decode errors remain 0, action stays 0 without random switching/fades. The 402 decoded source frames have no full-white image: near-white pixels peak at 2.073%; mean relative luminance ranges 0.384-0.395, maximum adjacent/loop mean step 0.00214. These are host asset checks, not proof of correct electrical LCD writes or backlight stability. No clear command is issued in the steady animation path.

## 50 Hz repeated-frame comparison (2026-10-20)

- User reports steady 40 fps with SPI raised from 26.67 MHz to 40 MHz looks approximately the same. No flicker fix is claimed.
- Firmware **1.40** adds serial-only mode 18 (`steady-50`): 50 presentations/second at 40 MHz, action 0 without random switching or fades. The original 40 fps source timeline and clip duration remain unchanged. Duplicate source frames resend the last valid dirty rectangle, without clearing or blank frames. This is repeated-frame playback, not 50 distinct animation frames.
- Normal production playback remains unchanged. Build and changed-sector flash hashes passed. Device confirms mode 18, action 0, 40 MHz, **150 presentations and pixel writes per 3000 ms**, with source frame advancing 120 and CRC 0. Physical feedback is pending.

## Presentation cadence comparison (2026-10-20)

- User reports 1.38 changed-row-band mode has **approximately the same flicker, normal imagery**. It reduced transport volume but did not produce a visual improvement in this comparison. Mode 15 remains optional diagnostics; ordinary playback is still the single-rectangle renderer.
- Firmware **1.39** adds serial-only `steady-30` (mode 16) and `steady-20` (mode 17), using a microsecond presentation deadline. These keep the 40 fps source timeline and clip duration, sampling fewer displayed frames and decoding skipped deltas correctly. They hold action 0 without random actions or fades, use the original single-rectangle output, and preserve SPI/scan/brightness/wiring. Normal mode 0 remains 40 fps and full normal behavior. This is a cadence comparison, not a promise of scan synchronization or a permanent frame-rate downgrade.
- Build, Python syntax and whitespace checks passed; changed-sector flash hashes verified against the known 1.38 baseline. The 1.39 mode-16 comparison measured presents advance **90 per 3000 ms**, source frame advances **120 per 3000 ms**, CRC 0. User reports the 30 Hz comparison made flicker worse; it was rejected and 40 Hz restored. Mode 17 is available but **not tested yet**. The diagnostic will restore animation/Bridge on cleanup.

## Changed-row-band transport comparison (2026-10-20)

- The completed 1.37 sequence reports: steady animation **obvious flicker**; compute-only frozen image **markedly reduced but slight flicker**; repeated identical LCD transfers without animation computation **slight flicker**; same frozen image with both computation and transfers stopped **no flicker**. This points to multiple workload/update contributions under current conditions but does not identify an electrical cause. The diagnostic was then stopped and Bridge restored.
- Firmware **1.38** adds serial-only mode 15, `steady-bands`, paired with mode 14 `steady-motion`. Both keep action 0, 40 fps, source duration and no fades/random actions. Mode 15 plans top-to-bottom dirty 8-row bands, skips unchanged regions, and falls back to one rectangle when estimated window overhead outweighs saved pixels. It streams final pixels directly, never clears first. **Ordinary mode 0 remains the previous single-rectangle renderer** pending physical acceptance.
- Offline analysis across all frame pairs estimates pixel savings of about 25.8% idle, 25.4% listening, 30.5% thinking and 27.6% speaking. This predicts transport reduction, not visual benefit. Runtime adds cumulative pet pixel-byte and window counts for measurement; these counts do not measure SPI electrical integrity.
- Fixed the diagnostic frozen-hash lifecycle: modes 14/15 no longer capture a moving pose, so a following frozen phase captures the actual last displayed buffer afresh. Earlier 1.37 stale hashes remain documented rather than rewritten as fresh measurements.
- Build and changed-sector write hashes passed against the fully verified 1.37 private baseline. Direct telemetry confirms firmware 1.38, 40.0 presents/s in both modes, CRC/decode errors 0. Measured samples: **31,159 bytes/present over 18 s** in mode 14 versus **23,155 bytes/present over 51 s** in mode 15; scene phase/sample durations differ. Windows increased from 1.0 to 14.63 per present; example push times decreased from about 12 ms to 9.5 ms. User reports **same flicker, normal imagery**. The diagnostic was stopped and Bridge restored before the cadence test.

## Steady-motion isolation (2026-10-20)

- Device API confirmed connected firmware 1.36, theme 2, animation enabled, no audio playing and CRC 0. User reports flicker in both ongoing movement/transitions or cannot distinguish them. No change to wiring, brightness, scan profile or source FPS is made for this comparison.
- Source asset analysis found idle action 0's six-pixel outer border unchanged throughout all 402 frames; viewport-average adjacent-frame luminance change peaks around 0.461 on a 0–255 scale. This does not establish what the panel electrically displays, but gives no evidence of baked-in whole-background alternating brightness in idle imagery.
- Firmware 1.37 adds serial-only `steady-motion` mode 14: force action 0, keep 40 fps and source duration, disable random actions and fades, and omit the unused crossfade-source copy. It keeps LCD output active. The normal renderer and default autonomous startup remain available; ordinary ANIMATION or diagnostic cleanup clears the mode. This isolates uninterrupted playback from state/clip fades, not a claimed fix.
- Build, Python syntax and whitespace checks passed, plus all 3 asset/theme tests including a new RGB565 idle-border invariant. The pre-rotated pack remains unchanged. Full application flashing was interrupted near its end and a complete digest check correctly failed. The uncertain tail was rewritten from absolute address 0xD00000, then **all 16,295,392 application bytes passed full flash digest verification**. Testing began only after successful verification; the private flash baseline was refreshed then.
- Direct serial telemetry confirms **1.37, mode 14, action 0, animation enabled, approximately 120 presents/3 seconds, CRC 0**. User reports **obvious flicker, approximately unchanged**, so state transitions and fades are not required to trigger the current symptom.
- The same session then switched to ordinary `compute-only` on the new sequential-palette firmware. Pixel-write count remained **3465**, presents **3475**, while source updates advanced **3482 to 3602** over 3 seconds. User reports **marked improvement, but a little flicker remains**. This phase may change source action, so it is not a perfectly matched workload comparison. The frozen hash was captured earlier in mode 14 and is stale across this particular phase switch; do not use it to identify the newly frozen pose. Zero further LCD pixel writes is supported by the write counter.
- Next phase repeats the same frozen viewport without animation computation: mode 2, source updates fixed **6811**, source frame fixed **127**, writes/presents increase **120/3001 ms**, CRC 0. User reports **only slight flicker**. This compares fixed-content LCD transfers against animated content and compute-only; it is not an electrical waveform measurement.
- The same frozen image was then held with writes fixed **8459**, presents **8469**, source updates **6811**, frame **127**, CRC 0. User confirmed **no flicker**. No voltage/scan/wiring change was involved. This completed the phase sequence, after which normal animation and Bridge were restored before the 1.38 transport test.
- Diagnostic exclusively owns COM9 while Bridge is temporarily stopped; the tool has a 600-second bound and restores normal animation/Bridge on cleanup. No brightness, wiring or scan change has been made. Do not report the steady-playback trial as a flicker fix.

## Independent Wi-Fi feasibility review (2026-10-20)

- Fetched origin/main and reviewed `870758d` (firmware 1.36, pre-rotated animation pack, serial diagnostics). User reports the latest DeepSeek optimization still has little effect; retain the distinction between access-pattern correlation and a confirmed complete flicker fix.
- Rebuilt the existing source without flashing: Flash usage **16,294,925 / 16,711,680 bytes**, about **416,755 bytes remaining**. Bridge tests **146 passed**. A public weather request using example coordinates succeeded from the Windows host (HTTP 200, 436-byte JSON); this is not device Wi-Fi validation.
- Added [independent Wi-Fi feasibility report](docs/INDEPENDENT_WIFI_FEASIBILITY.md), checked against official ESP32-S3/ESP-IDF, ESP-SR, Open-Meteo, DeepSeek search/Responses, and XiaoZhi documentation. Current firmware has no Wi-Fi transport or weather client. Recommended progression: budget resources, prototype device-direct weather, then autonomous online ASR/LLM/tools/TTS through an optional cloud gateway. A Wi-Fi link to the current PC alone does not satisfy computer-off operation.
- This is research only: no new Wi-Fi firmware, credentials, paid API call or cloud deployment; no running-device reset, flash, theme or audio change. Full conversation remains a service architecture task, not on-device execution of the existing desktop Whisper/CosyVoice/Hermes processes.

## Runtime transpose isolation and 40 fps baseline (2026-10-20)

- Controlled frozen-image diagnostics on the 40 fps pack isolated the remaining steady flicker to the runtime 90-degree transpose in `colors()`. A sequential 28 KB read did not flicker; the same buffer read with the 168-byte column stride flickered; a sequential 56 KB write did not. The runtime transpose was removed by storing the animation pack pre-rotated in display orientation.
- Firmware **1.36** keeps 13 DSH Pet clips at 40 fps, 220 ms transitions, and a 6 MiB decoded-delta cache. Palette conversion is now a sequential read. The transition fade is fused into that pass and skips pixels that are identical to the previous frame; the crossfade source prefers internal RAM.
- A true 60 fps build was generated and tested with 8 clips x 602 frames (11.18 MB) and then rejected. At 168x168 RGB565 the panel needs 56 KB/frame; 60 fps requires about 3.4 MB/s while 26.67 MHz SPI provides about 3.33 MB/s, so even single-clip playback flickered. The 60 fps assets and 8-clip firmware were reverted; 40 fps is the retained baseline.
- Serial-only diagnostic modes 4-13 remain in `dsh_pet.h`/`display_ab_test.py` for CPU, PSRAM, internal-RAM, flash, decode-only, colors-only, combined, sequential-write, transposed-read and sequential-read comparisons. They never write the LCD and are not exposed to the web UI.
- Validation after the revert: **146 Bridge tests and 11 web interaction tests passed**; the pre-rotated pack is checked frame by frame by `test_dsh_pet.py`. Physical steady/transition flicker feedback for 1.36 is still being collected; no claim of a complete flicker fix is made.

## Handoff snapshot and standalone USB-supply test (2026-10-19)

- User has no multimeter or capacitors and requested further no-instrument methods plus a GitHub checkpoint. They confirmed a compatible household USB charger was available and were instructed to move the existing controller USB cable from the computer to that charger, without changing screen or other wiring. Firmware 1.26 supports autonomous opening/idle playback without Bridge.
- User reports **the household USB supply still does not solve the flicker**. They did not quantify the difference, so do not claim severity was exactly equal. This test also removes the computer USB data connection; it does not prove every power/ground/backlight path is healthy or identify a specific fault. Bridge cannot communicate with the device while its USB cable is on the charger; that is expected, not a software regression.
- Added [docs/SCREEN_FLICKER_NO_TOOLS.md](docs/SCREEN_FLICKER_NO_TOOLS.md) with the evidence ledger, limitations, and proposed internal-workload/PSRAM-workload diagnostics, layout and video comparisons. Newly proposed workload diagnostics are **not implemented in 1.26**. No further firmware or wiring change was made for this handoff. Autonomous startup remains accepted; flicker remains unresolved.
- Latest validated source/firmware baseline remains 1.26: 146 Bridge tests and 11 web tests, successful build/flash verification, offline opening-to-idle verification and work-state priority verification. Preserve DSH Pet default and automatic animation; Emotion Ball remains selectable. No audio changes in this checkpoint.

## Autonomous power-on pet greeting (2026-10-19)

- User confirms screen power/ground already connect directly to the controller and requested another visual test, automatic animation at power-on, an opening animation, and Emotion Ball disabled as the default (not deleted).
- Firmware **1.26** starts directly in DSH Pet with animation enabled and the existing approximately 26.67 MHz pet bus clock. It reuses the attributed upstream **maid curtsy, action 9** as a complete once-only opening greeting, followed by the original crossfade into idle. No new animation asset or storage expansion was needed. Ordinary USB ready/sleep notifications preserve the greeting; listening/thinking/speaking/error interrupt it. Task ownership and non-blocking serial/audio servicing are preserved.
- Bridge constructor and missing/invalid stored-theme fallback now use DSH Pet. The web selector lists it first and its unknown-state fallback agrees. Explicit valid Emotion Ball selection and persistence still work; its quiet-playback policy is retained. Existing migration and reconnect tests were updated to verify the new default while preserving a manual Ball selection.
- Build and changed-sector flash hash verification passed, **146 Bridge tests and 11 web tests passed**, plus JavaScript syntax and whitespace checks. Offline boot was verified with Bridge stopped and no host WELCOME/animation command: action 9 advanced through frames 0/81/161/241/322, then the greeting flag cleared and action 0 was selected, with increasing uptime and presents. This is autonomous startup, not host-triggered playback.
- A separate reset test sent WELCOME/READY during the greeting: at uptime 6.3 seconds the device still displayed action 9/frame 122. Sending LISTEN then produced action 2/frame 118 by the next status, CRC 0, proving work-state priority without blocking the host. The diagnostic sent READY and released serial ownership, then restored Bridge. Authenticated API confirmed **1.26, connected, requested/actual theme 2, animation enabled and no audio playing**; the current stored selection was explicitly set to DSH Pet. Physical cold-start appearance and flicker feedback remain pending; flicker is not claimed fixed by this startup change.
- Physical cold-start result: after unplugging/reconnecting USB, user confirmed **automatic opening playback works normally, but flicker remains**. Autonomous startup is accepted; the flicker investigation remains unresolved. Retain enabled animation and DSH Pet startup per the latest user request, rather than automatically pausing it again. No additional timing/brightness or wiring changes were made after this report.

## Sparse decoded-delta cache (2026-10-19)

- User confirmed 1.24 renders correctly and is smooth, but **flicker persists**, and requested further algorithm optimization. A later question asks whether low voltage causes it. The unchanged-image computation A/B supports a workload-linked symptom, but no supply waveform, ground or BLK measurement has established the electrical cause. Do not describe it as proven undervoltage or conclude that hardware is ruled out.
- Firmware **1.25** adds an optional PSRAM cache for already-inflated frame deltas: a bit mask plus nonzero XOR bytes, with dense/absolute frames stored raw. Cached playback preserves the same indexed frame values, palette, orientation and timing. First encounters still inflate and populate the cache; cache allocation failures retain ordinary decoding.
- An initial 4 MiB / whole-clip eviction run preserved 40 fps and zero decoder/CRC errors but thrashed between clips, so it was superseded before physical acceptance. Final policy caps cached payloads at **6 MiB**, also checks for **512 KiB PSRAM free** before allocating, and reclaims small tail batches from the least-recently-used inactive clip, retaining action prefixes for transitions. Pointer metadata and allocator overhead are additional to the payload cap. Active-clip entries are not evicted while being decoded.
- Build and changed-sector flash hash verification passed. Runtime exposes `pet_cache_bytes`, `pet_cache_hits` and `pet_cache_misses` for validation. Motion duration, source FPS, display scanning/clock, wiring, audio gain and retained Emotion Ball are unchanged. Physical flicker comparison is pending; do not claim a cure or assume caching eliminates all workload.
- Final hardware run retained about 120 presentations per three seconds, with cache payload peaking at 6,288,262 bytes (below 6 MiB), zero decoder errors/CRC errors and continuous uptime. Warm-frame decode samples were approximately 0.3–0.4 ms; uncached samples still require several milliseconds and include cache population. A separate warm capture verified action 0/frame 59 against independent Python asset decoding: all 28,224 pixels matched hash **903764412**; the capture interval added 22 hits and zero misses. A cold action-11/frame-55 capture also matched hash **1506414137**.
- Physical comparison result: user reports **approximately unchanged, still obvious flicker** on 1.25. Reduced warm decode cost is therefore not a flicker cure. Animation was paused again through Bridge while retaining the image; no panel voltage, scan register, SPI or wiring change was made. Further frame-count/cache tuning has no demonstrated visual benefit. Next investigation needs evidence about screen power/ground/backlight or interference; no voltage waveform has been measured. User has previously confirmed no multimeter and no capacitors on hand.
- The diagnostic originally retained a frozen-image baseline across intentional normal-motion phases and rejected the subsequent different pose; its cleanup restored Bridge correctly. Baseline now resets when motion is intentionally resumed, preserving same-pose validation only across hold/repeat/compute-only phases. Final short capture diagnostic exited normally and restored Bridge; normal animation was re-enabled through the API. Audio behavior has not yet been exercised on 1.25; visual comparison remains the current physical check.

## DSH Pet direct-frame algorithm (2026-10-19)

- After changing computer USB ports, the user requested an algorithm change instead of another hardware test. No comparative improvement/worsening result for the port substitution was supplied; do not record it as a failed or successful power test.
- Firmware **1.24** removes the two alternating RGB lookahead buffers. Decoder indices now represent the current source frame; required XOR deltas advance sequentially, and the current frame is palette-converted directly into the final composition buffer. The palette is initialized once, delta XOR works a word at a time, and dirty bounds skip identical rows and scan only the changed row endpoints. Crossfades, 40 fps source timing, 8 random actions, other theme, brightness, SPI and audio gain remain unchanged.
- Hot indexed state prefers internal RAM. The last-displayed shadow also prefers internal RAM only when at least 64 KiB remains for other work; PSRAM fallback is retained. The removed RGB buffers offset this allocation. Palette conversion uses separate decoder scratch, so writing the final frame cannot overwrite its indexed input. The existing `pet_internal_frames` flag now indicates both indexed state and displayed shadow were allocated internally, rather than referring to the removed RGB lookahead allocation.
- Build and sector patch hash verification passed. Direct serial run measured **120 presents / 3000 ms** in multiple normal-motion intervals, CRC 0, decode errors 0 and internal hot-buffer flag 1. Independent Python zlib/XOR/palette/rotation decoding of action 0, frame 288 matched the device's frozen displayed-shadow hash **1714418413** across all **28,224 pixels**. This verifies pixel generation and frame state for that capture, not the panel's electrical output.
- Sample median composition cost was approximately 3.7 ms in the new run versus 6.8 ms in a small prior normal-motion sample; scenes and sample counts differ, so this is indicative rather than a controlled performance ratio. The new run retained source duration and full 40 fps motion.
- Diagnostic released COM9 and restored Bridge. Authenticated status confirmed connected firmware 1.24, theme 2, animation enabled and no audio playback. User confirmed normal imagery and smooth motion but **flicker persists**. No audio test was initiated during the visual comparison.

## Animation computation isolation (2026-10-19)

- Firmware **1.23** adds serial-only `compute-only` (SCREEN_TEST mode 3): decode and compose changing animation while leaving the LCD and its last-displayed shadow unchanged. It preserves normal themes, panel registers, audio gain and default SPI rates. Build and sector patch hash verification passed.
- Hardware telemetry verified `pixel_writes=65` and `presents=58` remained fixed, while `source_updates` advanced about 120 per three seconds; CRC remained zero. User reported **obvious flicker even with the displayed image frozen**. This warrants checking computation/memory workload and shared supply/backlight effects, but does not establish an electrical root cause.
- The control file was briefly empty during a phase change and the diagnostic safely exited/restarted Bridge. The script now tolerates an empty file while a writer updates it. A new `hold` run verified pixel writes, presents and source updates all stopped; the user confirmed **no flicker or discomfort**. Because normal animation ran briefly between these runs, that first comparison was not an uninterrupted same-pose A/B.
- In the same second run, `hold` was then changed directly to `compute-only`: `pixel_writes=1227` and `presents=1226` stayed fixed, while source updates advanced 120 per three seconds. User confirmed **obvious flicker returned on the unchanged displayed pose**. The frozen-image computation on/off comparison therefore reproduced the symptom without LCD pixel writes.
- Diagnostic serial ownership was released and Bridge restarted normally. Authenticated status confirmed firmware 1.23, theme 2, connected, no audio playing and animation disabled. The freeze is temporary mitigation while checking power/backlight stability, not a completed flicker fix. Asked whether the user has capacitors and their markings; no new wiring instruction or unverified capacitor connection was given.
- Source review found no firmware BLK/PWM control. Decompression, palette conversion and frame memory accesses remain active in compute-only. Shared supply/ground/backlight coupling is a hypothesis, not a measured fault; lack of SPI writes does not exclude electromagnetic coupling or a module-specific issue. Do not continue blind panel scan/analogue-register trials as if a scan fault were established.
- Compute-only omits SPI writes and the normal last-frame buffer copy, so it does not reproduce the complete normal rendering workload. No screen readback or voltage measurement was performed.

## USB cable substitution (2026-10-19)

- User reports the controller connects directly to the computer and has a spare data cable. To change one variable, they were instructed to replace the cable while retaining the same computer USB port, screen/BLK resistor and restored amplifier connections. User confirmed the swap was done.
- Bridge confirmed data connection and no audio playback, then resumed theme-2 animation on firmware 1.22. No firmware, SPI, panel scan, gain or screen wiring changes were made. User reported flicker was **approximately unchanged** with the replacement cable on the same computer port. Cable substitution did not improve the symptom; this does not rule out other power or connection issues.

## BLK limited pull-up comparison (2026-10-19)

- User confirmed screen VCC/GND each directly connect to controller 3V3/GND, bypassing breadboard supply rails. Screen rear photo positively identifies **KAC-2.4 TFT RGB (240x320), 4-SPI, ST7789**, panel flex **T240B7-C10-25**. Q1 and resistor network are visible; exact KAC adapter schematic and BLK polarity were not established from the photo or searches.
- A bounded comparison was proposed: USB removed, controller 3V3 through a 1k–4.7k ohm resistor to BLK, maintaining amplifier isolation. This was proposed as a limited pull-up test, not a verified manufacturer wiring specification. User said it was connected and requested the test; exact resistor value and wiring have not been independently verified.
- Bridge resumed animation on firmware 1.22, theme 2, with host/device playback false. Live presents increased **118 over 3001 ms** (~39.3/s), device connected and reported CRC 0. No firmware, panel scan, SPI clock or gain changes were made for this comparison. After amplifier restoration, the combined CosyVoice/animation test completed with **324/324 audio frames acknowledged**, CRC unchanged at zero, continuous connection, and observed speaking action 4 with animation enabled. User confirmed sound was normal but **obvious flicker remained during the combined test** with amplifier restored. The initial BLK improvement is therefore not full-system acceptance. User subsequently confirmed obvious flicker also persists in silent idle after speech finishes. It is not exclusively speech-triggered. Animation was paused again before checking USB cable/connection topology; no new firmware or panel-register changes were made. User reports **flicker significantly reduced or disappeared** after the BLK limited pull-up. Retain this wiring as an effective mitigation; the report does not establish the sole electrical root cause. User recalls the external resistor is approximately **3 kΩ**, but is not certain; record as approximate/unverified, not an exact measured value. Animation was paused before USB-off amplifier reconnection. User then confirmed the amplifier was restored and controller/screen lit normally; combined animation/speech testing was started with BLK pull-up retained.

## Outer-background brightness observation and load isolation (2026-10-19)

- With normal animation restored, the user covered the central character and reported that the corners/outermost background also became brighter/dimmer. These pixels are outside the pet viewport and ordinary dirty-rectangle writes. This raises priority of panel-wide power/backlight/drive effects over a purely local animation artifact; it does not establish a specific electrical fault without measurement.
- Bridge animation was paused, connected device confirmed `animation_enabled=false`, with both host/device playback false. No new panel timing, gamma, analogue drive, or audio gain changes were made.
- Next controlled hardware step requested: unplug main USB, disconnect all six MAX98357-to-controller wires (VIN/GND/SD/BCLK/LRC/DIN), leave speaker-to-amplifier leads and screen/microphone wiring in place, then reconnect USB. Full amplifier interface isolation avoids leaving signal connections as an alternate path. Await user confirmation before restarting screen animation; do not send audio with the amplifier isolated.
- User confirmed all six amplifier-to-controller wires were disconnected with USB removed; main controller and screen lit normally after reconnecting. Bridge then resumed animation with no audio playback. User reported flicker was approximately unchanged with all six amplifier connections removed. This does not support the connected amplifier as the dominant trigger under this idle animation test; it does not rule out screen supply or grounding effects. Animation was then paused again, with amplifier still isolated, while requesting the screen VCC/GND supply path before any rewiring. Current live firmware is 1.22; normal SPI default is approximately 26.67 MHz, FRCTRL2 default 0x0F. The temporary animation pause is intentional for wiring/testing.

## Runtime SPI clock isolation (2026-10-19)

- Firmware **1.22** extends serial SCREEN_TEST with optional clock selector byte: 0 restores theme default, 1 requests 20 MHz, 2 requests 40 MHz. The display owner applies pending settings; theme changes and ordinary ANIMATION commands restore theme defaults. `lcd_spi_hz` reports the configured request, not an oscilloscope measurement.
- `scripts/display_ab_test.py` also supports `motion-normal`, `motion-slow`, and `motion-fast`. Cleanup restores the default clock and ordinary animation before reconnecting Bridge. Slow-clock comparison is diagnostic, not a final playback choice; rendering throughput and naturally changing idle actions can differ, so visual improvement alone would not prove a wiring fault.
- Built/flashed with hash verification; live low-speed phase reports 20,000,000 Hz requested, normal animation, CRC 0, and approximately 117–118 presents per three seconds while idle. Approximately 150 seconds of low-clock animation were played, then the test was stopped and normal clock/animation and Bridge were restored. User initially reported the 20 MHz interval was more obvious. A subsequent 40 MHz comparison also showed no clear improvement; their latest clarification was understood as approximately the same. Treat the clock comparison as inconclusive for root cause, not proof of a wiring fault. Both tests ended with Bridge/default settings restored. Panel FRCTRL2, palette and audio gain were not changed.

## Controlled static-screen A/B diagnostic (2026-10-19)

- User authorized a controlled comparison before changing wiring. Firmware **1.21** adds local serial-only `SCREEN_TEST` command 0x0F: 0 returns to animation, 1 freezes the last displayed image without writes, 2 repeatedly writes that same frozen viewport at the normal 40-Hz scheduling target. No scan, SPI clock, palette, background or audio gain change was made from 1.20. Normal ANIMATION commands clear the diagnostic; face changes cancel it.
- New telemetry reports `screen_test`, `screen_test_hash` (captured FNV-1a of frozen source pixels, not LCD readback) and `pixel_writes` (all RAMWR starts). `scripts/display_ab_test.py` owns the serial port, keeps heartbeat active, switches via a control file, validates unchanged image hash and write-count behavior, aborts on button input, and requests normal animation in cleanup. With `--restore-bridge`, it restores Bridge after releasing the port; default timeout is ten minutes. Logs/control files stay outside Git.
- Live test used physical theme 2, the same frozen source frame **60**, fingerprint **1607504220**. Hold phase: `pixel_writes` stayed at **67** over multiple three-second status intervals. User: **no flicker or discomfort**. Repeat phase: fingerprint/frame unchanged, writes increased by **120 per three seconds** (~40/s), CRC 0 and uninterrupted uptime. User: **still no flicker or discomfort**.
- Both conditions were stable in this controlled comparison, unlike the earlier subjective 1.19 repeat report. It does not prove that power or signal integrity is fault-free, and it does not establish that animation assets are responsible. Repeated identical writes alone did not reproduce the complaint under the current settings. Next check is whether ordinary changing animation reproduces it before proceeding to clock/wiring isolation.
- Test ended and Bridge was restored. Device reports **voice-device-1.21**, connected, theme 2, animation enabled and changing frame numbers. After restoring ordinary animation, the user again observed flicker. Thus repeated identical writes were stable, while changing imagery reproduced the complaint under current settings; scan/transfer interaction and temporal content remain possible. Prior 1.20 throughput/transport results remain historical; this revision has not been claimed as a flicker cure.

## DSH Pet continuous rectangle transport (2026-10-19)

- User confirmed 1.16 stutter gone but uncomfortable flicker remained. 1.17 high scan reduced flicker but made the panel nearly unreadable; 1.18 intermediate scan restored brightness but retained obvious flicker. Both scan experiments are superseded.
- Private diagnostic **1.19** restored FRCTRL2 0x0F and held one identical pose while retransmitting it 40 times/s. Telemetry confirmed fixed frame 206 while presents increased 120 per 3 seconds. User still observed slight flicker. This rules out changing animation content as the sole cause, but does not identify whether bus integrity, panel scan/write interaction or power is responsible.
- Current **1.20** restores normal pause semantics (paused means no ongoing redraw), uses default FRCTRL2 0x0F for both themes, and lowers only DSH Pet SPI from 40 to approximately **26.67 MHz**. Emotion Ball retains 40 MHz.
- DSH Pet now finds the final changed bounding rectangle and streams it with one RAMWR/CS transaction, packing up to 16 rows per internal-memory transfer. It does not clear the region. Static pixels within the rectangle are copied unchanged. This replaces dozens of independently addressed tile runs and should reduce fragmented old/new scanout; no TE synchronization is available, so no guarantee of tear-free output is made.
- An initial 20 MHz rectangle trial acknowledged 320/320 audio frames but fell to approximately 32 presentations/s during speech, so it was not retained. The final approximately 26.67 MHz build acknowledged **320/320 audio frames**, CRC 0, continuous uptime and animated speaking. It measured approximately **37 presentations/s during speech and 39/s afterward**. The source motion remains 40 fps and original duration; small frame skips remain possible. Do not claim 40 sustained during speech for this build.
- Build and sector patch hash verification passed. Bridge reconnected on **voice-device-1.20**, actual theme 2, animation restored. The temporary fixed-pose repeat diagnostic is removed. Physical comparison of brightness, flicker and smoothness remains pending.

## DSH Pet scan/brightness compromise (2026-10-19)

- Live firmware **1.18** replaces the rejected high-scan 0x00 profile with FRCTRL2 **0x08** for DSH Pet (datasheet nominal 78 Hz at default porches); Emotion Ball still requests 0x0F. This is an empirical intermediate setting, not a measured scan frequency. Motion is unchanged at 40 fps.
- Built and sector-flashed with verified hashes. Bridge reconnected on 1.18, actual theme 2, animation enabled, measured 40 fps, CRC/decode errors zero. Physical feedback: brightness recovered but flicker remained obvious; this compromise was rejected. If still too dim, restore default 0x0F before further transfer-path changes; do not increase analogue panel drive voltages to compensate.

## DSH Pet panel-scan experiment (2026-10-19)

- Firmware **1.17** changes only the theme-specific ST7789V FRCTRL2 register: DSH Pet requests 0x00, Emotion Ball restores the default 0x0F. Dot-inversion bits stay unchanged. Source artwork, 40-fps playback, SPI clock, gamma, state transitions and audio gain remain unchanged to isolate the comparison.
- Datasheet: https://newhavendisplay.com/content/datasheets/ST7789V.pdf, section 9.2.16. With default porches, the documented nominal scan rates for these codes are 119/60 Hz. These are controller requests, not measured physical panel rates; no TE synchronization signal or readback is wired. The change may reduce scan/presentation beat visibility but is not proof of a flicker cure.
- Built and sector-patched with hash verification. Audio playback passed with 320/320 acknowledgements, speaking animation active, continuous uptime and CRC 0. Bridge reconnected on 1.17; theme switching measured 60 fps for Emotion Ball and 40 fps for DSH Pet with zero decode errors. Physical feedback rejected 1.17: flicker reduced, but the panel became almost unreadably dim. The 0x00 setting must not remain the final profile. Keep 1.16 as the accepted smooth-playback baseline if the panel experiment worsens appearance. A local 1.16 binary backup is outside Git.

## DSH Pet precomputed motion playback (2026-10-19)

- User rejected 1.15: residual stutter/flicker remained. Firmware **1.16** replaces normal per-pixel temporal blending with precomputed bidirectional optical-flow frames: **13 × 402 = 5,226 frames at 40 fps**, approximately 10.05 seconds per clip (less than 9 ms difference from the full 241/24-fps source). State changes retain a 220 ms crossfade from the last displayed frame. No clear/blank intermediate frame is sent.
- The drawing viewport is 168×168 at physical (36,76), with a tighter source crop and a slightly smaller character. Gamma 0.85 remains. All 13 clips and the 8–22 second post-action idle interval remain; Emotion Ball and audio gain are unchanged.
- The 48-fps trial exceeded Flash capacity and was not flashed. The final 40-fps pack is approximately 15.16 MiB. Firmware is **16,424,381 / 16,711,680 bytes** (98.3%). The unused SPIFFS partition was removed to enlarge the factory app to 0xFF0000; NVS is retained. There is only approximately 287 KB app headroom, so future asset additions must check the build size. No OTA slot is provided.
- Built and flashed with hash verification. Full pack validation and regression tests: **146 Python + 11 Node passed**. During actual audio playback, **320/320 audio frames** were acknowledged with animation and speaking action 4 active, CRC 0 and continuous uptime. Presentation deltas were **120/119/120 over roughly three-second intervals** (~39.6–39.9 fps), compared with ~32 fps in 1.15. Normal frame copying replaced the previous approximately 9 ms blend work; stage counters remain asynchronous diagnostics.
- The 100-second state/random run passed: LISTEN/THINK/SPEAK mapped to actions 2/3/4, three idle random actions occurred, continuous uptime and zero decode/CRC errors. Sampled end-to-next-start random gaps were approximately 17.36 and 13.60 seconds. Bridge reconnected on 1.16 with desired/actual theme 2. Theme 1 measured 180 presentations per 3 seconds; switching back to theme 2 measured 120 per 3 seconds. A real CosyVoice sentence queued successfully and played with animated speaking action 4, with no connection loss. Physical feedback: user confirmed stuttering disappeared, but noticeable flicker remains. They cannot distinguish whole-background pulsing from character tearing; it feels uncomfortable to watch. Do not treat 1.16 as a flicker fix.

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

## Supply-voltage and background questions (2026-10-20)

- Keep the KAC screen on 3V3. ST7789V chip supply specifications do not establish the module VCC rating; no module schematic or verified 5 V regulator has been found. The photographed Q1 alone is not evidence of a regulator. Do not test 5 V merely because the high-scan diagnostic is dim.
- User asks whether background causes flicker. Current idle asset border is constant and no full-white source frame was found, but content-dependent panel behavior / perceived contrast remains possible. A uniform-background comparison with identical motion, scan and presentation rate is a useful next test; it has not yet been performed.


## 2026-10-20：局域网无线 Bridge 开发中（固件 1.54）

- 用户授权实现同一 Wi-Fi 连接 Bridge，保留 USB、当前声音和全部动画，实物验收后同步 GitHub。
- 新增独立设备 WebSocket 监听器、独立随机令牌、USB/网络统一帧处理。网页仍保持原 loopback/Tailscale 访问方式；无线端口只处理设备二进制协议，不提供网页或智能体 API。
- 固件保存配网到 NVS；USB 主机存在时走 USB，离开电脑 USB 后主动连接配置的局域网 Bridge；断线清空旧录音与播放，重连不重投旧问题。
- `scripts/configure_device_wifi.py` 本地隐藏输入密码；`scripts/enable_device_wifi_firewall.ps1` 限定程序、局域网接口、本地地址和 LocalSubnet，需管理员运行。
- 动画包无损重压缩从 15,838,813 减至 14,788,881 字节；5,226 帧逐帧验证解压字节一致，13 动作、显示尺寸、原播放时间和音色均保留。1.54 编译 Flash 15,918,497 / 16,711,680 字节。
- 软件检查：154 项后端测试与 19 项网页状态测试通过；包含真实本机 WebSocket 鉴权、拒绝浏览器 Origin、录音上传/回调、播放下发与 ACK。
- 1.53 完整刷写并全镜像 digest 校验成功；初次主动 Wi-Fi 扫描发生复位，随后 STATUS reset_reason=9（欠压）。因此 1.54 降为 8.5 dBm、被动扫描、扫描时暂时停止动画计算，Wi-Fi 初始化尽量先于可选显示缓存。
- 当前阻碍：电脑侧仅扫描到 5 GHz 网络；主控 2.4 GHz 扫描、无线音质/按键路由、重连、USB 回退仍需实测。防火墙添加返回“拒绝访问”，须用户管理员执行准备好的脚本。无线验收前不标记完成。
- Wi-Fi 密码及设备令牌只在私有配置/NVS，禁止提交公开仓库。当前首版 ws 在可信局域网明文通信，无公网转发。

- 后续实测：1.54 被动低功率扫描仍触发欠压复位。1.55 延后无线初始化，开机保留 8 秒 USB 接管窗口，避免配置网络后破坏 USB 恢复。1.55 已补丁烧录并核对全部修改区 hash，已通过 USB 配网确认；Bridge 已重启，连接 COM9、主题 DSH、解码错误 0，无线监听 configured/listening 均 true。正在等待用户执行管理员防火墙脚本并改用充电头供电；无线验收尚未完成。


### 无线实测续记：1.56–1.58（待验收）

用户已管理员执行防火墙脚本，规则有效；电脑确认目标 2.4 GHz 网络存在。原 1.55 充电头供电画面稳定但未连上。1.56 使用有效 USB 协议帧/心跳判定链路，用户报告充电头下反复重启。1.57 将无线启动 CPU 降为 80 MHz、暂时停止动画计算；电脑侧仍读到欠压复位 9，新增的无线安全模式成功阻止重试并保留 USB。1.58 开机留 30 秒 USB 接管窗口，已烧录并验证修改区 hash，USB 配网重置安全模式，状态为 firmware=1.58、connected=true、wifi_configured=true、wifi_safe_mode=false、reset_reason=3 后，交给用户换充电头。用户说画面正常无重启，但 Bridge 仍无无线会话；正在等待用户接回 USB 核对安全模式。音频无线验收尚未开始；不能认定无线功能完成。155 后端测试通过，19 网页状态测试此前通过。


### 无线本轮结论（1.58，实物未通过）

用户完成最后一次充电头供电测试后接回 USB：Bridge 已确认 COM9 连接固件 1.58，wifi_configured=true、wifi_safe_mode=true、wifi_selected=false。换充电头前已确认 wifi_safe_mode=false；本版本仅在启动标记存在且 esp_reset_reason()==ESP_RST_BROWNOUT 时自动置安全模式。说明本次外部供电过程中也发生过无线启动欠压，随后保护生效而画面稳定。用户说“没重启”的视觉判断不足以否定这个持久化保护记录。

因此软件降低负载（启动时 CPU 80 MHz、暂停动画计算、8.5 dBm 发射功率）仍未使当前硬件无线启动稳定。保持欠压保护，不继续提高供电电压或关闭保护；USB 备用已恢复，声音/动画绑定保留。当前只同步实现和故障证据，不把无线录音、播音或网络重连标记为成功。后续须先检查主控 3V3 供电瞬态、稳压器余量和背光负载/接线；现有记录不能确定供电路径中具体哪个元件有问题。

USB 回归播音已实测 341 音频帧下发/回执全部一致，设备持续连接，device_bad_crc=0、pet_decode_errors=0；该结果是传输和设备回执确认，不替代用户听感确认。155 后端测试、19 网页测试通过。


### 用户要求不拔线：1.59 / 1.60 软件负载对比

未改变接线。新增受限 USB 诊断类型 18（profile 0/1）与 `scripts/probe_device_wifi.py`，单轮有超时、阶段记录和重启恢复读取，不泄露凭据。1.60 补齐 I2S 停止、CPU 低频就绪、进入无线初始化前的串口阶段标记，并 flush 后才继续。

- 正常待机 profile 0：starting → before_radio_init → USB 断开；恢复后 reset_reason=9、wifi_safe_mode=true。
- 低负载 profile 1：暂停动画、卸载 I2S、数字时钟/数据线拉低、CPU 80 MHz；已收到 i2s_stopped → cpu_low_ready → before_radio_init，随后 USB 断开；恢复后 reset_reason=1、wifi_safe_mode=true。上电复位 1 不应误报为欠压 9。
- 两组都未收到 mode_ready。故障局限到开启无线模式完成之前，尚未进入网络扫描和 Bridge 握手，不能声称无线功能成功或明确具体硬件元件故障。仍存在外设持续供电影响，本轮不是仅主控测试。
- 固件 1.60 已烧录并通过所有修改区 hash 校验。Bridge 已重启恢复，后续检查 USB、动画、语音；当前保留无线安全模式，用户无需再改线。

本轮恢复检查：USB COM9 已连接固件 1.60，speaker_ready=true、animation_enabled=true、主题 DSH，presents 持续增加；回归播音 127 帧发送/回执一致，device_bad_crc=0、pet_decode_errors=0。协议与动画资源测试 5 项通过，诊断 CLI 编译检查通过。


### 不改线续查：最小应用 / PSRAM / 射频校准

新增两个隔离诊断环境（约 643 KB），正常构建默认仍是完整 esp32-s3-devkitc-1；不改任何接线。两种最小固件分别确认 psramFound=true / false，均 CPU 80 MHz，不加载动画、音频、Bridge 或凭据。两组 esp_wifi_init、设置存储/模式等均 ESP_OK，射频启动前内部空闲 283,896 B、最大连续块 270,324 B；均在 before_wifi_start 后 USB 断开，恢复原因 9。因此比之前 WiFi.mode 黑盒更精确地定位到 esp_wifi_start 完成前，尚未联网，不能归咎于动画代码或常规堆不足。

只读 RF 校准缓存检查返回 ESP_ERR_NVS_NOT_FOUND（4354）；NVS 初始化正常。官方说明该情况会触发完整校准，与启动负载较高这一假设相符，但没有测量证明具体电流波形。当前应用 8.5 dBm 设置在射频启动之后，来不及影响本次失败；下一有价值的软件实验是 SDK 构建级 PHY 限功率/官方欠压后降功率配置，而非继续改帧率。该 SDK 配置实验尚未实施，仍保持欠压保护与 USB 正常使用。

首次临时覆盖前验证整份原 1.60 镜像 digest；射频对照批次和校准只读批次结束后分别恢复起始 647,168 B，再完整校验整镜像；无分区擦除或凭据修改。原声音/动画已恢复，USB、扬声器与动画计数正常，CRC/解码错误 0。详见 docs/WIFI_BRIDGE.md、docs/wifi-minimal-results.json。默认完整固件及两种最小环境均编译成功；未把新构建的生产镜像覆盖已验证的旧运行镜像，运行中仍为恢复校验的 1.60。

### 2026-10-21：SDK 低功率诊断工程（构建受网络阻塞，尚未烧录）

新增独立 `voice-device/diagnostics/wifi-sdk`：目标 ESP-IDF 4.4.7、CPU 80 MHz、无 PSRAM、SDK PHY 最大功率 10 dBm、官方欠压后降功率配置；保留欠压检测及原等级 7。编译期断言与构建产物检查脚本用于确认 SDK 配置和 PHY 源码构建，不能把应用宏或启动后的 API 限功率当作底层配置已生效。

依赖下载时 PlatformIO、GitHub 与 Espressif 文档连接失败，本机没有 ESP-IDF 源码缓存；已停止未完成的依赖安装。工程尚未编译、没有可烧录镜像，也没有新实物结果；机器人接线与运行中的完整 1.60 均未改动。联网恢复后先构建并验证，再按诊断 README 的备份、仅覆盖应用和完整恢复流程测试。降低功率上限不保证消除校准电流峰值，Wi-Fi 功能仍未通过验收。

修复诊断读取器对“每条阶段日志都携带 idf_version”的兼容性，避免把 ready/complete 误当成独立版本日志丢弃。3 项针对性测试通过：旧版/SDK 日志均只触发一次并完成；USB 丢失保留最后 RF 阶段、不自动重试。

本轮收尾：默认完整固件重新编译成功，诊断读取器/协议/动画资源合计 6 项测试通过。Bridge 已启动，COM9 固件 1.60、扬声器就绪、动画运行、CRC/解码错误 0，无线安全模式保持开启。GitHub fetch 同样返回 Connection was reset；本轮更改先提交本地，联网恢复后再同步，不能认定云端已更新。

### 2026-10-21：代理重试与 SDK 10 dBm 实测（未解决无线复位）

用户说明电脑需保持代理。显式使用 Windows 当前 HTTP 代理后 GitHub fetch 与依赖下载成功；新增构建启动器自动继承当前代理，不修改系统代理或 Bridge 网络配置。锁定 ESP-IDF 4.4.7 包 3.40407.240606，补齐旧版构建适配器需要的 setuptools，开启 Python UTF-8 并使用本地英文缓存路径，解决中文路径的配置/链接编码问题。

最终测试镜像 616,528 字节，SDK 源码构建通过；检查生成配置与 ELF 实际 PHY 初始化表，14 项功率值均为 40（0.25 dBm 单位，即 10 dBm）。CPU 80 MHz，无 PSRAM、动画或 I2S，仍保留原欠压保护等级 7，全部实物接线不动。最初独立 USB 驱动版没有就绪日志，未计为射频结果；切换 SDK USB 控制台后取得有效阶段记录。

有效实测：nvs_init/netif_init/event_loop/wifi_init/storage_ram/set_mode 全部 ESP_OK；进入 before_wifi_start 时空闲内部内存 307,124 B，随后 USB 断连，恢复 ready 报告 reset_reason=1（上电复位，不能写成欠压 9）。未收到 wifi_start 成功，未扫描/连接路由器或 Bridge。恢复并未报告 9，故没有强行触发欠压分支或自动重试；官方降功率保护虽已编入，不能声称实物触发过。本次已证实 SDK 10 dBm 限制不足以修复当前启动问题，不能认定根因是动画、一般堆不足，也不能直接指定某个硬件元件故障。

只覆盖应用前 618,496 B，结束后恢复该范围，并对原 1.60 整份 15,922,960 B 镜像 digest 校验成功；启动器、分区表、接线及用户凭据未改动。Bridge 已恢复 COM9、声音就绪、动画运行、CRC/解码错误 0，无线安全模式仍开启。公开证据 `docs/wifi-sdk-low-power-results.json`；诊断读取器/协议/动画资源共 6 项测试通过。

### 2026-10-21：语音唤醒首版 1.61（真人与双麦验收待完成）

用户指定“你好，大肥鱼”，确认第二只也是 INMP441。已安装本地 Vosk 中文模型；增加待机 PCM、受控录音及回执协议，在显示/语音面板加入唤醒开关和声道选项。唤醒后自动录音，静音约 1.4 秒提交当前 AI 会话，无语音 6 秒取消、最长 20 秒；按键仍手动结束。播音/识别/等待回复时抑制唤醒，背景音频仅在有界内存队列，不保存或上传。双麦改为整段选择一个声道，取消逐采样取最大值，接线未改，L/R 尚待用户确认。

1.61 编译、烧录及整镜像 digest 校验通过（15,923,648 B，差分 974,848 B）；原 1.60 保留备份。Bridge 已恢复 COM9、speaker_ready/animation_enabled=true，CRC/动画解码错误 0；已启用唤醒，设备回执 true，连续待机音频到达本地识别器，状态 armed。166 后端、19 网页测试通过，Windows 合成唤醒短句触发而普通问句不触发；不能据此声称真人唤醒或双麦已验收。等待用户喊唤醒词、看到录音表情再提问的实测反馈。见 docs/VOICE_WAKE.md。

Wi-Fi 本轮保持安全模式，没有重新强启射频；上一轮 SDK 10 dBm 下启动复位仍未解决。语音唤醒当前依赖电脑 USB，不是主控离线 WakeNet，也未实现语音打断或声学回声消除。

后续准备：独立 SDK 增加 low-power-lcd-sleep 变体，接线不动，通过现有 SPI 请求 ST7789 DISPOFF/SLPIN 后再尝试射频。背光仍供电，无写后读回，不能声称已关闭所有屏幕负载或确认功耗下降。该变体 616,704 B，构建/ELF 功率表检查通过；普通 SDK 对照也重新构建通过。两者本轮均未烧录，以免打断正在等待用户反馈的 1.61 唤醒测试。后续临时诊断须先备份并最终恢复当前 1.61，不能再直接运行写死 1.60 基线的旧临时脚本。
