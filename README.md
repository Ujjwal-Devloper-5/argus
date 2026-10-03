<div align="center">

<img src="docs/screenshots/argus-banner.jpg" alt="Argus AI Security System" width="100%"/>

# ARGUS

### AI-Powered Self-Hosted Security System

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![CUDA](https://img.shields.io/badge/CUDA-Accelerated-76B900?style=for-the-badge&logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-zone)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![Kafka](https://img.shields.io/badge/Kafka-Event_Streaming-231F20?style=for-the-badge&logo=apachekafka&logoColor=white)](https://kafka.apache.org)
[![Laya AI](https://img.shields.io/badge/Laya_421M-Decision_Gate-8B5CF6?style=for-the-badge&logo=huggingface&logoColor=white)](https://huggingface.co/convaiinnovations/laya-typed-decisions)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-000000?style=for-the-badge&logo=ollama&logoColor=white)](https://ollama.ai)
[![Telegram](https://img.shields.io/badge/Telegram-Alerts-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![Discord](https://img.shields.io/badge/Discord-Alerts-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/developers)
[![Tests](https://img.shields.io/badge/Tests-661_Passing-22c55e?style=for-the-badge&logo=pytest&logoColor=white)](#testing)
[![Coverage](https://img.shields.io/badge/Coverage-78%25-22c55e?style=for-the-badge&logoColor=white)](#testing)
[![License](https://img.shields.io/badge/License-MIT-f59e0b?style=for-the-badge)](LICENSE)

*Named after Argus Panoptes — the all-seeing giant of Greek mythology with 100 eyes.*

**[Features](#-features) · [Architecture](#-architecture) · [Quick Start](#-quick-start) · [Configuration](#-configuration) · [Roadmap](#-roadmap) · [Contributing](#-contributing)**

</div>

---

## Overview

**Argus** is a self-hosted, privacy-first AI security system that transforms any RTSP IP camera into an intelligent, thinking sentinel. It does not just record video — it *understands* what is happening.

Argus combines a **two-brain AI decision pipeline** (a fast 421M on-device gate model + a configurable vision LLM), real-time face recognition, **Apache Kafka** for high-throughput event streaming, and a unified alert engine that delivers rich, interactive notifications to both Telegram and Discord with one-click face enrollment.

**Everything runs on your own hardware. Your footage never leaves your network.**

---

## Features

### Vision Pipeline

| Capability | Technology | Detail |
|---|---|---|
| **Live Orchestration** | `EventOrchestrator` | Per-camera async pipeline — all stages wired, running, production-grade |
| **Person Detection** | YOLOv8 (ultralytics) | GPU-accelerated, configurable confidence threshold, executor-isolated |
| **Motion Pre-filter** | MOG2 Background Subtractor | Eliminates ~90% of static frames before hitting the GPU |
| **Face Recognition** | InsightFace + ArcFace | 512-dim embeddings, cosine similarity, sub-millisecond FAISS search |
| **Multi-Face Tracking** | SORT Tracker | Kalman filter + Hungarian algorithm — stable `track_id` across frames |
| **Pre-Event Buffer** | Circular `VideoBuffer` + FFmpeg | Captures N seconds *before* the trigger — never miss what caused the alert |
| **Hardware Recording** | FFmpeg NVENC (RTX) / libx264 | H.264 async subprocess — event loop never blocked during encoding |
| **Multi-Camera** | Async `StreamWorker` per camera | Unlimited cameras via asyncio tasks, each fully isolated with backoff reconnect |
| **Graceful Degradation** | `contextlib.suppress` at every stage | Any subsystem failure is logged and skipped — the pipeline never crashes |

### Two-Brain AI Intelligence

Argus uses a **dual-model decision system** inspired by cognitive science's System 1 / System 2 framework:

```
Frame In ──► [ System 1: Laya 421M Gate ] ──► Fast decision (milliseconds)
                          │
                    Suspicious?
                          │ Yes
                          ▼
             [ System 2: Vision LLM ] ──► Deep scene analysis (seconds)
             Ollama / OpenAI / Anthropic / Gemini
                          │
                          ▼
                  SceneAnalysis ──► AlertManager
```

**System 1 — Laya Decision Gate**
- Model: [`convaiinnovations/laya-typed-decisions`](https://huggingface.co/convaiinnovations/laya-typed-decisions) (421M, fully self-hosted)
- Instantly scores suspicion and urgency — replaces brittle rule-based heuristics
- Zero latency, zero API cost, zero data leaving your machine
- Graceful fallback to heuristics if model is not loaded

**System 2 — Vision LLM (configurable)**
- Only invoked when Laya flags a scene as worth deep analysis
- Swap providers in `config.yaml` with zero code changes

| Provider | Models | Mode |
|---|---|---|
| **Ollama** (default) | LLaVA, Moondream, Llama3.2-Vision | 🔒 Local |
| **OpenAI** | GPT-4o, GPT-4V | ☁️ Cloud |
| **Anthropic** | Claude 3.5 Sonnet | ☁️ Cloud |
| **Google** | Gemini 1.5 Pro | ☁️ Cloud |
| **Disabled** | — | Silent passthrough |

### AutoLearner — Gets Smarter Over Time

When Argus sees an unrecognised face enough times, it automatically:

1. Scores every face crop for sharpness (Laplacian variance metric)
2. Saves the best quality sample captured so far
3. Analyses temporal patterns — 3am repeat visitors are flagged suspicious automatically
4. Sends an interactive Telegram / Discord prompt: **"Do you know this person?"**
5. One button click adds them to the known-faces FAISS index permanently

### Apache Kafka — Event Streaming Backbone

Kafka decouples the pipeline's I/O-heavy operations from the real-time vision loop:

| Kafka Topic | Producer | Consumer | Status | Purpose |
|---|---|---|---|---|
| `argus.events` | `EventOrchestrator` | `AlertManager`, dashboard | ✅ Live | Security event fan-out |
| `argus.uploads` | `StorageManager` | rclone worker | ✅ Live | Crash-safe async clip upload queue |
| `argus.learn` | `AutoLearner` | `AlertManager` | ✅ Live | Face learn prompts |
| `argus.dlq` | `ArgusConsumer` | Ops monitoring | ✅ Live | Dead letter queue — failed messages after 3 retries |
| `argus.frames` | `StreamWorker` | GPU worker pool | ⏳ Phase 9+ | Horizontal frame distribution |

**Resilience guarantees:**
- Kafka offsets are committed **only after handler succeeds** — no data loss on crash
- 3-retry exponential backoff (1s → 5s → 15s) before DLQ
- Idempotent producer with `acks=all` + LZ4 compression
- KRaft mode (no Zookeeper) in the included `docker-compose.yml`


### Unified Alert Engine

A production-grade async alert pipeline with priority queueing and full two-way interactivity:

```
Alert Event
    │
    ▼
AlertQueue  (Priority: CRITICAL=0  WARNING=1  INFO=2)
    │
TokenBucketRateLimiter  (30 msg/sec default)
    │
QuietHoursGate  (configurable window — hold or drop)
    │
    ├──────────────────┐
    ▼                  ▼
TelegramClient    DiscordClient
(long polling)    (background task)
    │                  │
InlineKeyboard    discord.ui.View
callback          ActionRow callback
    └──────────┬───────┘
               ▼
    AutoLearner callback handler
```

| Feature | Telegram | Discord |
|---|---|---|
| Rich text | HTML formatting | Embed fields |
| Image attachments | `send_photo()` | `discord.File` |
| Interactive buttons | `InlineKeyboardMarkup` | `discord.ui.View` |
| Two-way listeners | Long polling | Background event task |
| Button callback | Immediate ACK + message edit | Interaction response |
| Alert routing | Per-env `config.yaml` | Per-env `config.yaml` |

### Storage & Cloud Sync

| Backend | Method | Use Case |
|---|---|---|
| **Local disk** | Direct copy | NAS / external drive |
| **Google Drive** | `rclone` async subprocess | Personal cloud |
| **AWS S3 / Cloudflare R2 / Backblaze B2** | `rclone` async subprocess | Object storage |
| **SFTP / NAS** | `rclone` async subprocess | Network storage |

All uploads are fire-and-forget via a Kafka-backed async queue — the vision pipeline never waits on network I/O.

### Unified Dashboard (React + FastAPI)

Argus features a built-in enterprise-grade dashboard served automatically at `http://localhost:8501`.

| Page / Feature | Capability |
|---|---|
| **Setup Wizard** | Guided first-run wizard to configure cameras, LLMs, DB, and alerts |
| **Live View** | Real-time multi-camera grid with detection bounding box overlays |
| **Event Timeline** | Live WebSocket-fed event stream — play clips, read LLM analysis, view faces |
| **Face Gallery** | Manage known faces and auto-learned strangers — enroll via UI |
| **System Health** | Live CPU/GPU/RAM metrics + Kafka and pipeline status |
| **Settings** | Full runtime configuration editor — write back to `config.yaml` |

---

## Architecture

### Per-Camera Pipeline (live as of Phase 8)

```
RTSP Camera
    │
    ▼
StreamWorker (PyAV / TCP, async reconnect with exp. backoff)
    │  asyncio.Queue
    ▼
MotionFilter (MOG2) ──── no motion? ──► skip frame
    │ motion detected
    ▼
DetectorWorker (YOLOv8, CUDA) ──── no persons? ──► skip frame
    │ person detections
    ▼
SortTracker (Kalman + Hungarian) ──► stable track_id per person
    │ tracked detections
    ▼
FaceRecognizer (InsightFace + FAISS)
    │
    ├── is_known=True ──► update DB last_seen (no alert)
    │
    └── is_known=False ──► EventOrchestrator._handle_unknown_face()
                                │
                    asyncio.gather (CONCURRENT):
                    ├── Laya 421M gate (fast, ~33ms, self-hosted)
                    ├── Vision LLM analysis (Ollama / OpenAI / etc.)
                    └── EventRecorder.start_recording (FFmpeg NVENC)
                                │
                    ┌───────────┴────────────┐
                    ▼                        ▼
              DB: Event + Clip       Kafka: argus.events
              (SQLAlchemy async)     (fan-out to subscribers)
                    │
                    ├──► AlertManager ──► Telegram / Discord
                    ├──► AutoLearner  ──► face quality cache + learn prompt
                    └──► StorageManager ──► Kafka: argus.uploads ──► rclone
```

### Application Startup Sequence

```
python -m argus
    │
    ├─ 1. Load Settings (Pydantic-Settings, .env + config.yaml)
    ├─ 2. Configure structured logging (structlog JSON / pretty)
    ├─ 3. Print banner
    ├─ 4. Alembic DB migrations (run_in_executor, non-blocking)
    ├─ 5. Setup DB engine (SQLAlchemy async)
    ├─ 6. Start Kafka producer (ArgusProducer, idempotent)
    ├─ 7. Start AlertManager (Telegram + Discord bots)
    ├─ 8. Start StorageManager (rclone / local backend + Kafka consumer)
    ├─ 9. For each active camera → build EventOrchestrator → start pipeline task
    ├─ 10. Wait for SIGTERM / SIGINT
    └─ Graceful shutdown (reverse order — storage → alerts → kafka → db)
```

### Shared Layer

```
┌─────────────────────────────────────────────────────────────────┐
│  PostgreSQL / SQLite  │  FAISS EmbeddingDB  │  Pydantic-Settings│
│  (SQLAlchemy async)   │  (face vectors)     │  (.env + YAML)    │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│            Apache Kafka (KRaft, no Zookeeper)                   │
│  argus.events │ argus.uploads │ argus.learn │ argus.dlq         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- CUDA GPU recommended (CPU mode fully supported)
- `ffmpeg` installed (`sudo pacman -S ffmpeg` / `sudo apt install ffmpeg`)
- Docker + Docker Compose (for Kafka and PostgreSQL)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/argus.git
cd argus

# 2. Create virtual environment
python -m venv .venv && source .venv/bin/activate

# 3. Install dependencies
pip install -e ".[dev]"          # CPU
pip install -e ".[dev,gpu]"      # NVIDIA GPU (CUDA)

# 4. Copy config templates
cp .env.example .env
cp config/config.example.yaml config/config.yaml
$EDITOR config/config.yaml      # add your camera RTSP URL + bot tokens

# 5. Start infrastructure (Kafka KRaft + PostgreSQL — no Zookeeper needed)
docker compose up -d argus-kafka argus-db

# 6. Run database migrations
alembic upgrade head

# 7. (Optional) Enroll known faces
python scripts/enroll_face.py --name "Your Name" --images path/to/photos/

# 8. Launch Argus — fully live end-to-end
python -m argus
```

> **Status:** As of Phase 8, `python -m argus` runs the complete pipeline. Point it at any
> RTSP camera and Argus will detect persons, recognise faces, record clips, and fire
> Telegram/Discord alerts in real time.


### Docker (Recommended)

```bash
# Full CPU stack
docker compose up -d

# GPU stack (NVIDIA)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

---

## Configuration

Argus uses two files: `.env` for secrets (never committed), `config/config.yaml` for behaviour.

### `.env` — Secrets

```env
# Database
DATABASE_URL=sqlite+aiosqlite:///./data/argus.db

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# LLM Provider
LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llava

# OpenAI (optional)
# OPENAI_API_KEY=sk-...

# Anthropic (optional)
# ANTHROPIC_API_KEY=sk-ant-...

# Google (optional)
# GOOGLE_API_KEY=...

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Discord Bot
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=your_channel_id
DISCORD_GUILD_ID=your_guild_id

# Storage
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=./data/clips
# RCLONE_REMOTE=gdrive:Security/Argus
```

### `config/config.yaml` — Behaviour

```yaml
cameras:
  - name: front_door
    rtsp_url: rtsp://admin:password@192.168.0.200:554/stream1
    fps: 15
    pre_buffer_seconds: 5
    post_event_seconds: 30
    motion_threshold: 0.005   # 0.5% pixel change = motion

detection:
  model: yolov8n              # yolov8n | yolov8s | yolov8m | yolov8l | yolov8x
  confidence: 0.60
  device: auto                # auto | cuda | cpu | mps
  classes: [0]                # COCO class IDs (0 = person)

recognition:
  similarity_threshold: 0.60
  auto_learn:
    enabled: true
    appearances_before_prompt: 5
    prompt_via: both          # telegram | discord | both

llm:
  provider: ollama            # ollama | openai | anthropic | gemini | disabled
  ollama:
    host: http://localhost:11434
    model: llava
    timeout_seconds: 30
  laya:
    enabled: true
    model_id: convaiinnovations/laya-typed-decisions
    suspicion_threshold: 0.60
    urgency_threshold: 6.0

kafka:
  bootstrap_servers: localhost:9092
  topics:
    frames: argus.frames
    detections: argus.detections
    events: argus.events
    uploads: argus.uploads
    learn: argus.learn

alerts:
  routing: both               # telegram | discord | both
  max_rate_per_second: 30.0
  cooldown_seconds: 60
  quiet_hours:
    enabled: true
    start: "23:00"
    end: "07:00"
    override_on_suspicious: true
    action: hold              # hold | drop
  telegram:
    enabled: true
    bot_token: ${TELEGRAM_BOT_TOKEN}
    chat_id: ${TELEGRAM_CHAT_ID}
  discord:
    enabled: true
    bot_token: ${DISCORD_BOT_TOKEN}
    channel_id: ${DISCORD_CHANNEL_ID}
    guild_id: ${DISCORD_GUILD_ID}
```

---

## Supported Cameras

Any camera that exposes an RTSP stream:

| Brand | Tested Models | Protocol |
|---|---|---|
| TP-Link Tapo | C100, C200, C310, C500, C520WS | RTSP |
| Hikvision | DS-2CD series | RTSP / ONVIF |
| Dahua | IPC-HDW series | RTSP / ONVIF |
| Reolink | RLC-810A, E1 Pro | RTSP |
| Amcrest | IP8M series | RTSP / ONVIF |
| Generic | Any ONVIF-compliant device | RTSP |
| Mobile | IP Webcam (Android) | RTSP |

---

## Project Structure

```
argus/
├── argus/
│   ├── cli.py                      # Typer CLI (start, enroll, benchmark)
│   ├── config/
│   │   ├── settings.py             # Pydantic-Settings — single source of truth
│   │   └── logging.py              # structlog (JSON prod / pretty dev)
│   ├── core/
│   │   ├── stream.py               # PyAV RTSP ingestor + exponential reconnect
│   │   ├── motion.py               # MOG2 motion pre-filter
│   │   ├── detector.py             # YOLOv8 GPU detection worker
│   │   ├── recognizer.py           # InsightFace + ArcFace face recognition
│   │   ├── tracker.py              # SORT multi-object face tracker
│   │   └── recorder.py             # Circular pre-buffer + FFmpeg HW encoding
│   ├── intelligence/
│   │   ├── base.py                 # LLMProvider ABC + SceneAnalysis model
│   │   ├── laya.py                 # Laya 421M fast decision gate (System 1)
│   │   ├── ollama.py               # Ollama vision provider
│   │   ├── openai_provider.py      # OpenAI GPT-4o provider
│   │   ├── anthropic_provider.py   # Anthropic Claude provider
│   │   ├── gemini_provider.py      # Google Gemini provider
│   │   ├── factory.py              # Provider factory (config-driven)
│   │   ├── learner.py              # AutoLearner — quality scoring + temporal analysis
│   │   └── embeddings.py           # FAISS IndexFlatIP embedding database
│   ├── alerts/
│   │   ├── models.py               # Alert, AlertKind, AlertSeverity, InteractiveButton
│   │   ├── queue.py                # Priority queue + TokenBucket + QuietHoursGate
│   │   ├── telegram_client.py      # Telegram bot + callback polling
│   │   ├── discord_client.py       # Discord bot + ui.View listeners
│   │   └── manager.py              # AlertManager — routing hub + held-release worker
│   ├── storage/
│   │   ├── base.py                 # StorageBackend ABC
│   │   ├── local.py                # Local filesystem + retention policy
│   │   ├── rclone.py               # rclone wrapper (GDrive, S3, B2, SFTP)
│   │   └── manager.py              # Kafka-backed async upload queue + worker
│   ├── database/
│   │   ├── engine.py               # SQLAlchemy async engine + session factory
│   │   ├── models.py               # ORM: Camera, FaceProfile, Event, Clip, UnknownFaceTracker
│   │   └── repository.py           # Repository pattern — no raw SQL in business logic
│   ├── pipeline/
│   │   └── orchestrator.py         # EventOrchestrator — wires all modules together
│   ├── dashboard/
│   │   ├── app.py                  # Streamlit entrypoint
│   │   └── pages/                  # Live · Events · Faces · Settings
│   └── utils/
│       └── banner.py               # Professional ASCII terminal banner
├── alembic/                        # Database migrations
├── tests/                          # 617 tests · 81% coverage · 0 lint issues
│   ├── core/
│   ├── intelligence/
│   ├── alerts/                     # Full mock suite — Telegram + Discord
│   ├── config/
│   └── database/
├── config/
│   └── config.example.yaml
├── docker/
│   ├── Dockerfile                  # CPU production image
│   └── Dockerfile.gpu              # CUDA 12.3 production image
├── scripts/
│   ├── enroll_face.py
│   ├── test_stream.py
│   └── benchmark.py
├── docker-compose.yml              # Includes Kafka + Zookeeper + PostgreSQL
├── docker-compose.gpu.yml
├── Makefile
├── pyproject.toml
└── .env.example
```

---

## Development

```bash
make dev          # Start in dev mode with hot reload
make test         # Run full test suite with coverage report
make lint         # Ruff check + mypy type check
make fmt          # Ruff format (auto-fix)
make docker-build # Build CPU + GPU Docker images
make migrate      # Run alembic upgrade head
make benchmark    # FPS benchmark on your hardware
```

### Testing

```bash
# Full suite
.venv/bin/python -m pytest

# Specific module
.venv/bin/python -m pytest tests/alerts/ -v

# Coverage report
.venv/bin/python -m pytest --cov=argus --cov-report=html
```

Current statistics: **661 tests · 77.98% coverage · 0 ruff/mypy issues**
All Telegram, Discord, and LLM API calls are fully mocked — CI requires no real credentials.

---

## Roadmap

| Phase | Status | Description |
|---|---|---|
| **0 — Foundation** | ✅ Done | Config, logging, SQLAlchemy models, Alembic migrations |
| **1 — Stream Ingestor** | ✅ Done | PyAV RTSP ingestor with MOG2 motion pre-filter |
| **2 — Detection Engine** | ✅ Done | YOLOv8 GPU detection with async process isolation |
| **3 — Face Recognition** | ✅ Done | InsightFace + ArcFace + FAISS + SORT tracker |
| **4 — Recording Engine** | ✅ Done | Pre-event circular buffer + FFmpeg hardware encoding |
| **5 — LLM Intelligence** | ✅ Done | Laya 421M gate + multi-provider vision LLM + AutoLearner |
| **6 — Alert Engine** | ✅ Done | Telegram + Discord with priority queue, rate limiting, interactive buttons |
| **7 — Storage Manager** | ✅ Done | Kafka-backed async upload to GDrive / S3 / B2 / SFTP via rclone |
| **8 — Pipeline Orchestrator** | ✅ Done | Kafka-wired EventOrchestrator — live camera → detect → LLM → alert |
| **9 — Dashboard** | ✅ Done | React/FastAPI: setup wizard, live view, timeline, face gallery, WebSockets |
| **10 — Docker + CI/CD** | ⏳ Planned | GPU containers, GitHub Actions, automated publishing |

---

## Contributing

Contributions are warmly welcome! See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for the full guide including:

- Development environment setup
- Branch and commit naming conventions
- Testing requirements (coverage ≥ 80%, all APIs mocked)
- Pull request checklist and code standards

### Quick workflow

```bash
# Fork, clone, setup
git clone https://github.com/YOUR_USERNAME/argus.git
cd argus && pip install -e ".[dev]" && pre-commit install

# Branch → Code → Test → Commit → PR
git checkout -b feat/your-feature
make lint && make test
git commit -m "feat(scope): description"
```

### Areas Needing Help

| Area | Skills | Difficulty |
|---|---|---|
| Streamlit dashboard pages | Python, Streamlit | 🟡 Intermediate |
| Storage backends | Python, rclone | 🟢 Beginner |
| Kafka consumer tuning | Python, Kafka | 🟡 Intermediate |
| ARM / Apple Silicon builds | Docker, Python | 🟡 Intermediate |
| Multi-GPU scaling | Python, CUDA | 🔴 Advanced |
| Documentation and tutorials | Writing | 🟢 Beginner |

---

## Acknowledgements

| Project | Role in Argus |
|---|---|
| [ultralytics](https://github.com/ultralytics/ultralytics) | YOLOv8 object detection |
| [InsightFace](https://github.com/deepinsight/insightface) | ArcFace face recognition |
| [FAISS](https://github.com/facebookresearch/faiss) | Vector similarity search |
| [Laya 421M](https://huggingface.co/convaiinnovations/laya-typed-decisions) | Fast AI decision gate |
| [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) | Telegram async SDK |
| [discord.py](https://github.com/Rapptz/discord.py) | Discord async SDK |
| [Apache Kafka](https://kafka.apache.org) | Event streaming backbone |
| [pydantic](https://github.com/pydantic/pydantic) | Data validation |
| [structlog](https://github.com/hynek/structlog) | Structured logging |
| [PyAV](https://github.com/PyAV-Org/PyAV) | FFmpeg Python bindings |

---

## License

MIT License — see [LICENSE](LICENSE) for full text.

---

<div align="center">

Built with precision for privacy-first home security.

**Argus sees all. Your data stays home.**

*If this project helps you, consider giving it a star ⭐*

</div>
