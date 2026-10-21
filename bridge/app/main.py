"""Loopback-only Bridge API and separate web client."""

import logging
import os
import re
import subprocess
import sqlite3
import threading
from pathlib import Path
from urllib.parse import urlparse
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .device import DeviceLink
from .network_device import NetworkDevices
from .audio_output import AudioOutput
from .hermes import HermesWorker
from .harness import HarnessWorker
from .conversations import Conversations
from .hermes_api import HermesRunsClient
from .security import (SESSION_SECONDS, Sessions, anchor_path, load_or_create_token,
                       record_or_verify_data_dir, resolve_data_dir)
from .speech import SpeechWorker
from .wake import WakeWorker
from .wake_ack import WakeAcknowledgement, WakeConnectionGate, CONNECTION_NOTICE
from .message_access import MessageAccess
from .microphone import SpeechActivity
from .storage import add_message, initialize, list_messages, set_delivery, get_setting, set_setting
from .tts import (SynthesisCancelled, selected_voice, set_selected_voice, remember_voice, synthesize_chunks,
                  start_voice_service, stop_voice_services, voice_status,
                  warm_voice)
from .voice import VoiceConversation
from .runtime import RuntimeStatus
from .maintenance import BRIDGE_VERSION, MaintenanceStatus, check_database
from .playback import PlaybackControl

SOURCES = ("hermes", "deepseek_harness", "doubao_web")
THEME_VOICES = {"dsh_pet": "paimon", "qiuqiu": "cosyvoice"}
WEB_DIR = Path(__file__).resolve().parents[2] / "web-client"

logger = logging.getLogger("bridge.datadir")


class LoginBody(BaseModel):
    token: str = Field(min_length=6, max_length=256)


class MessageBody(BaseModel):
    source: str
    text: str = Field(min_length=1, max_length=4000)
    new_session: bool = False
    session_id: str | None = Field(default=None, min_length=1, max_length=256)


class StopAnswerBody(BaseModel):
    source: str
    session_id: str | None = Field(default=None, min_length=1, max_length=256)
    message_id: int = Field(gt=0, strict=True)


class ConversationBody(BaseModel):
    source: str


class DeleteConversationsBody(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    session_ids: list[str] = Field(min_length=1, max_length=200)


class VoiceTargetBody(BaseModel):
    source: str
    session_id: str | None = Field(default=None, min_length=1, max_length=256)


class SpeakBody(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    playback_id: str | None = Field(default=None, min_length=1, max_length=96)


class StopSpeechBody(BaseModel):
    playback_id: str | None = Field(default=None, min_length=1, max_length=96)


class VoiceBody(BaseModel):
    voice: str


class WakeBody(BaseModel):
    enabled: bool = Field(strict=True)
    mic_channel: str = Field(default='auto', pattern='^(auto|left|right)$')


class AnimationBody(BaseModel):
    enabled: bool


class DisplayThemeBody(BaseModel):
    theme: str


class AudioOutputBody(BaseModel):
    volume: int | None = Field(default=None, ge=0, le=100, strict=True)
    muted: bool | None = Field(default=None, strict=True)


class ApprovalBody(BaseModel):
    request_id: str = Field(min_length=1, max_length=256)
    choice: str


def create_app(data_dir: Path | None = None, token: str | None = None,
               hermes_worker: HermesWorker | None = None, harness_worker=None) -> FastAPI:
    if data_dir is None:
        data_dir, data_dir_source = resolve_data_dir()
        data_dir_record = record_or_verify_data_dir(data_dir, data_dir_source, anchor_path())
    else:
        data_dir_source = "explicit"
        data_dir_record = {"path": str(data_dir), "source": data_dir_source, "consistent": True}
    data_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Bridge store: %s (source=%s, anchor=%s, anchored=%s)",
                data_dir_record["path"], data_dir_source,
                data_dir_record.get("anchor", "-"), data_dir_record.get("anchored", "-"))
    database = data_dir / "messages.sqlite3"
    database_check = check_database(database)
    initialize(database)
    if database_check["state"] == "new":
        database_check["state"] = "ok"
    maintenance = MaintenanceStatus(data_dir, database_check)
    sessions = Sessions(token or load_or_create_token(data_dir))
    message_access = MessageAccess(sessions)
    speech = SpeechWorker(data_dir / "models")
    api_key_file = data_dir / "hermes-api-key.txt"
    api_client = HermesRunsClient(api_key_file) if api_key_file.is_file() else None
    hermes = hermes_worker or HermesWorker(database, api_client=api_client)
    harness = harness_worker or HarnessWorker(database, data_dir)
    conversations = Conversations(database, hermes, harness)
    audio_output = AudioOutput(data_dir)
    network = NetworkDevices(data_dir)
    def submit_recording(wav, generation):
        if voice.capture_authorized(generation):
            speech.enqueue(wav, generation)
        else:
            voice.on_speech_error('请先输入访问密钥登录 Bridge 并选择会话', generation)

    device = DeviceLink(submit_recording, lambda generation: voice.on_listen_start(generation),
                        audio_output=audio_output,
                        on_disconnect=lambda: (voice.on_device_disconnect(), wake.disconnected()), network=network,
                        on_mic_audio=lambda pcm, capture, generation: wake.feed(pcm, capture, generation),
                        on_capture_state=lambda listening, generation: wake.capture_changed(listening, generation),
                        on_cancel=lambda generation: voice.on_capture_cancelled(generation))
    theme = get_setting(database, 'display_theme')
    if theme not in ('qiuqiu', 'dsh_pet'):
        theme = 'dsh_pet'
        set_setting(database, 'display_theme', theme)
    device.set_theme(2 if theme == 'dsh_pet' else 1)
    remember_voice(data_dir, THEME_VOICES[theme])
    device.set_quiet_playback(selected_voice(data_dir).startswith('cosyvoice'))
    theme_voice_lock = threading.Lock()
    voice = VoiceConversation(database, data_dir, device, hermes, audio_output=audio_output,
                              workers={"hermes": hermes, "deepseek_harness": harness},
                              validate_target=conversations.resolve_writable,
                              access_grant=sessions.voice_grant, bind_access=message_access.voice)
    for worker in (hermes, harness):
        worker.authorize_job = message_access.allowed
        worker.release_authorization = message_access.release
    speech.on_transcript = voice.on_transcript
    speech.on_error = voice.on_speech_error
    def wake_connection_error():
        # Authorization comes first: an unpaired robot must not query an agent.
        if not sessions.voice_grant():
            return '请先输入访问密钥登录 Bridge 并选择会话'
        target = voice.snapshot()['target']
        worker = {'hermes': hermes, 'deepseek_harness': harness}.get(target['source'])
        if worker is None or not target['session_id']:
            return '请先在 Bridge 选择智能体和会话'
        client = getattr(worker, 'api_client', None) if target['source'] == 'hermes' else getattr(worker, 'client', None)
        probe = getattr(client, 'health_snapshot', None)
        if client is None and not getattr(worker, 'executable', None):
            return '当前智能体未安装或未连接'
        if callable(probe) and probe().get('available') is not True:
            return '当前智能体的本地 API 未连接'
        return None

    wake_ack = WakeConnectionGate(WakeAcknowledgement(data_dir, device, audio_output),
        WakeAcknowledgement(data_dir, device, audio_output, text=CONNECTION_NOTICE), wake_connection_error)
    wake = WakeWorker(database, data_dir, device, voice_busy=lambda:
                      speech.snapshot()['state'] in ('queued', 'transcribing') or voice.snapshot()['state'] in (
                          'listening', 'listening_for_approval', 'sending', 'waiting_for_hermes', 'waiting_for_agent',
                          'queued_to_speak', 'speaking', 'approval_prompt', 'approval_pending'),
                      acknowledge=wake_ack,
                      speech_activity=SpeechActivity())
    runtime = RuntimeStatus()
    playback = PlaybackControl(device)
    hermes.on_reply = voice.on_reply
    hermes.on_error = voice.on_hermes_error
    hermes.on_approval = voice.on_approval
    harness.on_reply = lambda message_id, answer: voice.on_reply(message_id, answer, source="deepseek_harness")
    harness.on_error = lambda message_id, error: voice.on_agent_error(message_id, error, source="deepseek_harness")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            start_voice_service(data_dir)
        except (OSError, RuntimeError):
            logger.exception("Could not start optional local TTS; keeping the current voice")
        warm_voice(data_dir)
        wake_ack.warm()
        try:
            harness.client.start()
        except (OSError, ValueError):
            logger.exception("Could not start optional Harness service")
        speech.start()
        network.start()
        device.start()
        hermes.start()
        harness.start()
        voice.start()
        wake.start()
        try:
            yield
        finally:
            wake.stop()
            wake_ack.stop()
            network.stop()
            device.stop()
            speech.stop()
            hermes.stop()
            harness.stop()
            harness.client.stop()
            voice.stop()
            stop_voice_services()

    app = FastAPI(title="Desktop AI Robot Bridge", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.device = device
    app.state.speech = speech
    app.state.hermes = hermes
    app.state.harness = harness
    app.state.voice = voice
    app.state.audio_output = audio_output
    app.state.wake = wake
    app.state.sessions = sessions
    app.state.message_access = message_access
    allowed_hosts = ["127.0.0.1", "localhost"]
    tailnet_host = os.environ.get("ROBOT_TAILNET_HOST", "").strip().lower()
    if tailnet_host:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.ts\.net", tailnet_host):
            raise ValueError("ROBOT_TAILNET_HOST must be one exact *.ts.net hostname")
        allowed_hosts.append(tailnet_host)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self'; frame-ancestors 'none'"
        )
        # This local app changes frequently during development. Both Edge and
        # the embedded browser must revalidate the HTML, JS and CSS together.
        response.headers["Cache-Control"] = "no-store"
        return response

    def check_origin(request: Request) -> None:
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            raise HTTPException(status_code=403, detail="Origin mismatch")

    def require_session(request: Request) -> None:
        if not sessions.valid(request.cookies.get("robot_session")):
            raise HTTPException(status_code=401, detail="Login required")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "version": BRIDGE_VERSION}

    @app.post("/api/login")
    def login(body: LoginBody, request: Request, response: Response) -> dict:
        check_origin(request)
        session = sessions.login(body.token, request.client.host if request.client else "unknown")
        if not session:
            raise HTTPException(status_code=401, detail="Invalid access key")
        local_host = request.url.hostname in ("127.0.0.1", "localhost")
        response.set_cookie(
            "robot_session", session, max_age=SESSION_SECONDS,
            httponly=True, samesite="strict", secure=not local_host,
        )
        return {"ok": True}

    @app.post("/api/logout", dependencies=[Depends(require_session)])
    def logout(request: Request, response: Response) -> dict:
        check_origin(request)
        sessions.logout(request.cookies.get("robot_session"))
        for message_id in message_access.revoked():
            for worker in (hermes, harness):
                cancel = getattr(worker, 'cancel', None)
                if callable(cancel):
                    cancel(message_id)
        if not sessions.voice_grant():
            voice.on_authorization_lost()
            device.stop_playback()
        response.delete_cookie("robot_session", samesite="strict")
        return {"ok": True}

    @app.get("/api/status", dependencies=[Depends(require_session)])
    def status() -> dict:
        result = {
            "bridge": "ready",
            "maintenance": maintenance.snapshot(),
            "playback": playback.snapshot(),
            "device": device.snapshot(),
            "device_network": network.snapshot(),
            "speech": speech.snapshot(),
            "wake": wake.snapshot(),
            "voice": voice.snapshot(),
            "audio_output": audio_output.snapshot(),
            "tts": voice_status(data_dir),
            "hermes": hermes.snapshot(),
            "deepseek_harness": harness.snapshot(),
            "sources": SOURCES,
            "store": {"path": data_dir_record["path"], "source": data_dir_source,
                      "consistent": data_dir_record.get("consistent", True)},
            "delivery": {"hermes": "connected" if hermes.executable or hermes.api_client else "unavailable",
                         "doubao_web": "not_configured"},
        }
        result["delivery"]["hermes"] = "connected" if result["hermes"]["available"] else "unavailable"
        result["task"] = runtime.snapshot(result["device"], result["speech"], result["voice"],
                                          [result["hermes"], result["deepseek_harness"]])
        return result

    @app.get("/api/diagnostics", dependencies=[Depends(require_session)])
    def diagnostics() -> dict:
        return runtime.diagnostics(status())

    @app.post("/api/voice/target", dependencies=[Depends(require_session)])
    def select_voice_target(body: VoiceTargetBody, request: Request) -> dict:
        check_origin(request)
        if body.source not in SOURCES:
            raise HTTPException(status_code=400, detail="Unknown source")
        if body.session_id:
            try:
                conversations.resolve(body.source, body.session_id)
            except ValueError as exc:
                voice.set_target(body.source, None)
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except (OSError, RuntimeError) as exc:
                voice.set_target(body.source, None)
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        result = voice.set_target(body.source, body.session_id)
        sessions.authorize_voice(request.cookies.get('robot_session'))
        return result

    @app.post('/api/voice/wake', dependencies=[Depends(require_session)])
    def configure_wake(body: WakeBody, request: Request) -> dict:
        check_origin(request)
        try:
            return wake.update(body.enabled, body.mic_channel)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/audio/output", dependencies=[Depends(require_session)])
    def set_audio_output(body: AudioOutputBody, request: Request) -> dict:
        check_origin(request)
        settings = audio_output.update(volume=body.volume, muted=body.muted)
        if not settings["enabled"]:
            voice.on_output_muted()
            device.stop_playback()
        return settings

    @app.post('/api/device/theme', dependencies=[Depends(require_session)])
    def set_display_theme(body: DisplayThemeBody, request: Request) -> dict:
        check_origin(request)
        if body.theme not in ('qiuqiu', 'dsh_pet'):
            raise HTTPException(status_code=422, detail='Unknown display theme')
        with theme_voice_lock:
            try:
                playback.stop(None)
                set_selected_voice(data_dir, THEME_VOICES[body.theme])
            except RuntimeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            set_setting(database, 'display_theme', body.theme)
            device.set_quiet_playback(body.theme == 'qiuqiu')
            device.set_theme(2 if body.theme == 'dsh_pet' else 1)
        wake_ack.warm()
        return {'theme': body.theme, 'voice': THEME_VOICES[body.theme], 'queued': True}

    @app.post("/api/device/animation", dependencies=[Depends(require_session)])
    def set_animation(body: AnimationBody, request: Request) -> dict:
        check_origin(request)
        if not device.snapshot()["connected"]:
            raise HTTPException(status_code=503, detail="Voice device disconnected")
        device.set_animation(body.enabled)
        return {"queued": True, "enabled": body.enabled}

    @app.get("/api/recording/last.wav", dependencies=[Depends(require_session)])
    def last_recording() -> Response:
        audio = device.last_capture_wav()
        if audio is None:
            raise HTTPException(status_code=404, detail="No completed recording")
        return Response(audio, media_type="audio/wav")

    @app.get("/api/transcripts", dependencies=[Depends(require_session)])
    def transcripts() -> dict:
        return {"items": speech.transcripts()}

    @app.post("/api/tts/stop", dependencies=[Depends(require_session)])
    def stop_speech(body: StopSpeechBody, request: Request) -> dict:
        check_origin(request)
        return {"stopped": playback.stop(body.playback_id)}

    @app.post("/api/tts/speak", dependencies=[Depends(require_session)])
    def speak(body: SpeakBody, request: Request) -> dict:
        check_origin(request)
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Empty speech")
        if not audio_output.enabled:
            return {"queued": False, "muted": True}
        if not device.snapshot()["connected"]:
            raise HTTPException(status_code=503, detail="Voice device disconnected")
        identity, generation, cancelled = playback.claim(body.playback_id)
        if cancelled:
            return {"queued": False, "superseded": True}
        if generation is None:
            raise HTTPException(status_code=409, detail="Voice device busy")
        try:
            started = False
            for wav in synthesize_chunks(
                text, data_dir,
                cancelled=lambda: not audio_output.enabled or not device.is_current_generation(generation),
            ):
                if not device.is_current_generation(generation):
                    return {"queued": False, "superseded": True}
                if not device.append_wav(wav, generation=generation):
                    raise HTTPException(status_code=409, detail="Voice device busy")
                started = True
        except SynthesisCancelled:
            return {"queued": False, "superseded": True}
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        finally:
            device.finish_playback(generation)
            playback.finished(identity)
        if not device.is_current_generation(generation):
            return {"queued": False, "superseded": True}
        return {"queued": started}

    @app.post("/api/tts/voice", dependencies=[Depends(require_session)])
    def select_voice(body: VoiceBody, request: Request) -> dict:
        check_origin(request)
        try:
            with theme_voice_lock:
                bound_voice = THEME_VOICES[get_setting(database, 'display_theme')]
                if body.voice != bound_voice:
                    raise ValueError("声线随显示动画切换，请在显示动画面板选择角色")
                set_selected_voice(data_dir, body.voice)
                device.set_quiet_playback(body.voice.startswith('cosyvoice'))
                wake_ack.warm()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return voice_status(data_dir)

    @app.get("/api/sessions", dependencies=[Depends(require_session)])
    def session_catalog(source: str) -> dict:
        try:
            return conversations.catalog(source)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (OSError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/sessions", dependencies=[Depends(require_session)])
    def new_conversation(body: ConversationBody, request: Request) -> dict:
        check_origin(request)
        try:
            return {"item": conversations.create(body.source)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/sessions/batch", dependencies=[Depends(require_session)])
    def delete_conversations_batch(body: DeleteConversationsBody, request: Request) -> dict:
        check_origin(request)
        try:
            conversations.check_source(body.source)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        deleted = []
        failed = []
        seen = set()
        target = voice.snapshot().get('target') or {}
        for session_id in body.session_ids:
            if session_id in seen:
                continue
            seen.add(session_id)
            try:
                result = conversations.delete(body.source, session_id)
            except ValueError as exc:
                failed.append({"session_id": session_id, "error": str(exc)})
                continue
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                failed.append({"session_id": session_id,
                               "error": str(exc) or '删除会话失败，请稍后重试'})
                continue
            deleted.append(result)
            if (target.get('source') == body.source and target.get('session_id') in {
                    session_id, result.get('native_session_id')} and target.get('session_id')):
                voice.set_target(body.source, None)
                target = {}
        return {"deleted": deleted, "failed": failed}

    @app.delete("/api/sessions", dependencies=[Depends(require_session)])
    def delete_conversation(source: str, session_id: str, request: Request) -> dict:
        check_origin(request)
        try:
            result = conversations.delete(source, session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            detail = str(exc) or '删除会话失败，请稍后重试'
            raise HTTPException(status_code=503, detail=detail) from exc
        target = voice.snapshot().get('target') or {}
        if target.get('source') == source and target.get('session_id') in {
                session_id, result.get('native_session_id')} and target.get('session_id'):
            voice.set_target(source, None)
        return result

    @app.get("/api/tasks", dependencies=[Depends(require_session)])
    def answer_tasks(source: str, session_id: str | None = None) -> dict:
        if source not in SOURCES:
            raise HTTPException(status_code=400, detail="Unknown source")
        worker = {"hermes": hermes, "deepseek_harness": harness}.get(source)
        return {"items": worker.progress_snapshot(session_id) if worker and hasattr(worker, 'progress_snapshot') else []}

    @app.post("/api/messages/stop", dependencies=[Depends(require_session)])
    def stop_answer(body: StopAnswerBody, request: Request) -> dict:
        check_origin(request)
        worker = {"hermes": hermes, "deepseek_harness": harness}.get(body.source)
        if not worker:
            raise HTTPException(status_code=400, detail="此智能体不支持停止回答")
        with sqlite3.connect(database) as db:
            row = db.execute('SELECT source,conversation_id,role FROM messages WHERE id=?', (body.message_id,)).fetchone()
        if not row or tuple(row) != (body.source, body.session_id, 'user'):
            raise HTTPException(status_code=404, detail="当前会话中找不到这条请求")
        accepted = worker.cancel(body.message_id)
        if accepted:
            voice.on_answer_cancelled(body.message_id, body.source)
        return {"accepted": bool(accepted), "message_id": body.message_id}

    @app.get("/api/messages", dependencies=[Depends(require_session)])
    def messages(source: str, session_id: str | None = None) -> dict:
        if source not in SOURCES:
            raise HTTPException(status_code=400, detail="Unknown source")
        if session_id:
            try:
                return {"items": conversations.history(source, session_id)}
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except (OSError, RuntimeError) as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"items": list_messages(database, source)}

    @app.post("/api/hermes/approval", dependencies=[Depends(require_session)])
    def resolve_approval(body: ApprovalBody, request: Request) -> dict:
        check_origin(request)
        if body.choice not in {"once", "deny"}:
            raise HTTPException(status_code=400, detail="Only once or deny is supported")
        try:
            accepted = hermes.approve(body.request_id, body.choice)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if not accepted:
            raise HTTPException(status_code=409, detail="Approval is no longer pending")
        return {"ok": True, "choice": body.choice}

    @app.post("/api/messages", dependencies=[Depends(require_session)])
    def submit(body: MessageBody, request: Request) -> dict:
        check_origin(request)
        if body.source not in SOURCES:
            raise HTTPException(status_code=400, detail="Unknown source")
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Empty message")
        if body.session_id:
            if body.new_session:
                raise HTTPException(status_code=400, detail="请选择已有会话或新建会话")
            try:
                conversations.resolve_writable(body.source, body.session_id)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except (OSError, RuntimeError) as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        if body.source == "hermes":
            item = add_message(database, body.source, text, delivery="queued", conversation_id=body.session_id)
            message_access.browser(item['id'], request.cookies.get('robot_session'))
            if hermes.enqueue(item["id"], text, new_session=body.new_session):
                return {"item": item, "delivery": "queued"}
            set_delivery(database, item["id"], "failed")
            message_access.release(item['id'])
            item["delivery"] = "failed"
            return {"item": item, "delivery": "failed"}
        if body.source == "deepseek_harness":
            item = add_message(database, body.source, text, delivery="queued", conversation_id=body.session_id)
            message_access.browser(item['id'], request.cookies.get('robot_session'))
            if harness.enqueue(item["id"], text, new_session=body.new_session):
                return {"item": item, "delivery": "queued"}
            set_delivery(database, item["id"], "failed")
            message_access.release(item['id'])
            item["delivery"] = "failed"
            return {"item": item, "delivery": "failed"}
        item = add_message(database, body.source, text)
        return {"item": item, "delivery": "not_configured"}

    return app


app = create_app()
