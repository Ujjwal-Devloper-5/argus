<div align="center">

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║        ████████╗ ██████╗   ██████╗ ██╗   ██╗███████╗                         ║
║       ██╔══██╗██╔════╝ ██╔════╝ ██║   ██║██╔════╝                           ║
║       ████████║██║  ███╗██║  ███╗██║   ██║███████╗                           ║
║       ██╔══██║██║   ██║██║   ██║██║   ██║╚════██║                           ║
║       ██║  ██║╚██████╔╝╚██████╔╝╚██████╔╝███████║                           ║
║       ╚═╝  ╚═╝ ╚═════╝  ╚═════╝  ╚═════╝ ╚══════╝                          ║
║                                                                               ║
║          AI-Powered Security System  ·  v0.6.0  ·  Phase 6 Active            ║
║               Telegram · Discord · Vision · AutoLearn                         ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

*Named after Argus Panoptes — the all-seeing giant of Greek mythology with 100 eyes.*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)
[![CUDA](https://img.shields.io/badge/CUDA-Accelerated-76B900?style=for-the-badge&logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-zone)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![Tests](https://img.shields.io/badge/Tests-617%20passing-22c55e?style=for-the-badge&logo=pytest&logoColor=white)](#testing)
[![Coverage](https://img.shields.io/badge/Coverage-81%25-22c55e?style=for-the-badge)](#testing)
[![Ruff](https://img.shields.io/badge/Linting-Ruff-D7FF64?style=for-the-badge)](https://docs.astral.sh/ruff/)

**[Features](#-features) · [Architecture](#-architecture) · [Quick Start](#-quick-start) · [Configuration](#-configuration) · [Roadmap](#-roadmap) · [Contributing](#-contributing)**

</div>

---

## Overview

**Argus** is a self-hosted, privacy-first AI security system that transforms any RTSP IP camera into an intelligent, thinking sentinel. It does not just record video — it *understands* what is happening.

Argus combines a two-brain AI decision pipeline (a fast 421M local gate model + a configurable vision LLM), real-time face recognition, and a unified alert engine that delivers rich, interactive notifications to Telegram and Discord with a single button click to identify unknown visitors.

**Everything runs on your own hardware. Your footage never leaves your network.**

---

## Features

### Vision Pipeline

| Capability | Technology | Detail |
|---|---|---|
| **Person Detection** | YOLOv8 (ultralytics) | GPU-accelerated, configurable confidence threshold, async process isolation |
| **Motion Pre-filter** | MOG2 Background Subtractor | Skips 60% of frames with no motion before touching the GPU |
| **Face Recognition** | InsightFace + ArcFace | 512-dimension embeddings, cosine similarity, sub-millisecond FAISS search |
| **Multi-Face Tracking** | SORT Tracker | Stable `track_id` across frames — no duplicate alerts for the same person |
| **Pre-Event Buffer** | Circular `deque` + FFmpeg | Captures 5 seconds *before* the trigger — never miss what caused the alert |
| **Hardware Recording** | FFmpeg with NVENC/VAAPI | H.264 hardware encoding, async subprocess — pipeline never blocks |
| **Multi-Camera** | Async `StreamWorker` per camera | Unlimited cameras via `asyncio` fan-out, each fully isolated |

### Two-Brain AI Intelligence

Argus uses a **dual-model decision system** inspired by cognitive science:

```
┌─────────────────────────────────────────────────────────────────┐
│                    TWO-BRAIN PIPELINE                           │
│                                                                 │
│  Frame In ──► [System 1: Laya 421M] ──► Fast decision (ms)    │
│                      │                                          │
│               Suspicious?                                       │
│                      │ Yes                                      │
│                      ▼                                          │
│              [System 2: Vision LLM] ──► Deep analysis (s)     │
│              Ollama / OpenAI / Anthropic / Gemini               │
│                      │                                          │
│                      ▼                                          │
│                 SceneAnalysis → Alert                           │
└─────────────────────────────────────────────────────────────────┘
```

**System 1 — Laya Decision Gate (Fast)**
- Model: [`convaiinnovations/laya-typed-decisions`](https://huggingface.co/convaiinnovations/laya-typed-decisions) (421M, self-hosted)
- Role: Instantly scores detections for suspicion and urgency — replaces heuristic rule engines
- On-device, zero latency, zero API cost
- Falls back gracefully to heuristics if the model isn't loaded

**System 2 — Vision LLM (Deep)**
- Only invoked when Laya flags a scene as worth analysing
- Provider-agnostic: swap models in `config.yaml` without touching code

| Provider | Models | Mode |
|---|---|---|
| **Ollama** (default) | LLaVA, Moondream, Llama3.2-Vision | 🔒 Local |
| **OpenAI** | GPT-4o, GPT-4V | ☁️ Cloud |
| **Anthropic** | Claude 3.5 Sonnet | ☁️ Cloud |
| **Google** | Gemini 1.5 Pro | ☁️ Cloud |
| **Disabled** | — | Silent passthrough |

### AutoLearner — Argus Gets Smarter Over Time

When Argus sees an unrecognised face enough times, it automatically:
1. Scores the face crop quality (Laplacian variance sharpness metric)
2. Saves the sharpest sample seen
3. Analyses temporal patterns — flags 3am repeat visitors as suspicious
4. Sends an interactive Telegram/Discord message: **"Do you know this person?"**
5. One button click adds them to the known-faces index forever

### Unified Alert Engine

A production-grade async alert pipeline with priority queueing and two-way interactivity:

```
Alert Event ──► AlertQueue (Priority: CRITICAL=0, WARNING=1, INFO=2)
                      │
              TokenBucket RateLimiter (30 msg/s default)
                      │
              QuietHoursGate (configurable window, hold or drop)
                      │
              ┌───────┴────────┐
              ▼                ▼
        TelegramClient   DiscordClient
        (polling)        (background task)
              │                │
        InlineKeyboard   discord.ui.View
        callback         ActionRow callback
              └───────┬────────┘
                      ▼
              AutoLearner Callback Handler
```

| Feature | Telegram | Discord |
|---|---|---|
| Rich text | HTML formatting | Embedded fields |
| Image attachments | `send_photo()` | `discord.File` |
| Interactive buttons | `InlineKeyboardMarkup` | `discord.ui.View` |
| Two-way listeners | Long polling | Background task |
| Button callback | Immediate ACK + edit | Interaction response |
| Alert routing | `config.yaml` | `config.yaml` |

**Alert routing** is fully configurable — send to `telegram`, `discord`, or `both` per environment.

### Storage & Retention

| Backend | Method | Use Case |
|---|---|---|
| **Local disk** | Direct copy | NAS / external drive |
| **Google Drive** | `rclone` async subprocess | Personal cloud |
| **AWS S3 / R2 / B2** | `rclone` async subprocess | Object storage |
| **SFTP / NAS** | `rclone` async subprocess | Network storage |

All uploads are fire-and-forget via an internal `asyncio.Queue` — the vision pipeline never waits on network I/O.

### Dashboard

Streamlit-powered web UI at `http://localhost:8501`:

| Page | Capability |
|---|---|
| **Live** | Real-time multi-camera grid with detection overlays |
| **Events** | Paginated timeline — click to play clip + view LLM analysis |
| **Faces** | Known faces gallery, enroll new person by dropping photos |
| **Settings** | Runtime config editor — cameras, thresholds, alert routing |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ARGUS PIPELINE                              │
│                                                                     │
│  ┌──────────────┐   frames   ┌──────────────┐  persons             │
│  │ StreamWorker │────Queue──►│ DetectWorker │──────────┐           │
│  │  (PyAV/TCP)  │            │  (YOLOv8)    │          │           │
│  │  per camera  │            │  GPU/CPU     │          ▼           │
│  └──────────────┘            └──────────────┘  ┌──────────────┐   │
│       ▲                                         │  FaceWorker  │   │
│  MOG2 Motion Gate                               │ (InsightFace)│   │
│  (skips 60% frames)                             │   + SORT     │   │
│                                                 └──────┬───────┘   │
│                                                        │           │
│                          ┌─────────────────────────────┘           │
│                          ▼                                          │
│                 ┌─────────────────┐  ┌──────────────────┐         │
│                 │  Laya 421M Gate │  │   AutoLearner    │         │
│                 │  (System 1 AI)  │  │  track_unknown() │         │
│                 └────────┬────────┘  └────────┬─────────┘         │
│                          │ suspicious?         │ threshold?         │
│                          ▼                     ▼                   │
│                 ┌─────────────────┐   ┌─────────────────┐         │
│                 │  Vision LLM     │   │  AlertManager   │         │
│                 │  (System 2 AI)  │   │  Learn Prompt   │         │
│                 └────────┬────────┘   └────────┬────────┘         │
│                          │                      │                   │
│          ┌───────────────┼──────────────────────┘                  │
│          ▼               ▼                  ▼                      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐              │
│  │AlertManager  │ │ Recorder     │ │StorageManager│              │
│  │Telegram+     │ │ Pre-buffer   │ │ rclone async │              │
│  │Discord       │ │ FFmpeg clip  │ │ upload queue │              │
│  └──────────────┘ └──────────────┘ └──────────────┘              │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                     SHARED LAYER                            │   │
│  │  SQLite / PostgreSQL  │  FAISS EmbeddingDB  │  Config       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │             STREAMLIT DASHBOARD  :8501                      │   │
│  │  Live View  │  Events + Clips  │  Faces Gallery  │ Settings │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- CUDA-capable GPU recommended (runs on CPU, but slower)
- At least one RTSP-capable IP camera
- `ffmpeg` installed (`sudo pacman -S ffmpeg` / `sudo apt install ffmpeg`)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/argus.git
cd argus

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install dependencies (CPU)
pip install -e ".[dev]"

# 4. Install with GPU support (NVIDIA)
pip install -e ".[dev,gpu]"

# 5. Copy and edit config
cp .env.example .env
cp config/config.example.yaml config/config.yaml
$EDITOR config/config.yaml

# 6. Run database migrations
alembic upgrade head

# 7. Enroll a known face (optional)
python scripts/enroll_face.py --name "Your Name" --images path/to/photos/

# 8. Start Argus
python -m argus
```

### Docker (Recommended for Production)

```bash
# CPU stack
docker compose up -d

# GPU stack (NVIDIA)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

---

## Configuration

Argus uses two config files: `.env` for secrets and `config/config.yaml` for behaviour. Secrets are **never** stored in YAML.

### `.env` — Secrets

```env
# Database
DATABASE_URL=sqlite+aiosqlite:///./data/argus.db

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
    motion_threshold: 0.005     # 0.5% of pixels changed = motion

detection:
  model: yolov8n                # yolov8n | yolov8s | yolov8m | yolov8l | yolov8x
  confidence: 0.60
  device: auto                  # auto | cuda | cpu | mps
  classes: [0]                  # COCO class IDs: 0 = person

recognition:
  similarity_threshold: 0.60
  auto_learn:
    enabled: true
    appearances_before_prompt: 5
    prompt_via: both            # telegram | discord | both

llm:
  provider: ollama              # ollama | openai | anthropic | gemini | disabled
  ollama:
    host: http://localhost:11434
    model: llava
    timeout_seconds: 30
  laya:
    enabled: true
    model_id: convaiinnovations/laya-typed-decisions
    suspicion_threshold: 0.60
    urgency_threshold: 6.0

alerts:
  routing: both                 # telegram | discord | both
  max_rate_per_second: 30.0
  cooldown_seconds: 60
  quiet_hours:
    enabled: true
    start: "23:00"
    end: "07:00"
    override_on_suspicious: true
    action: hold                # hold | drop
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

Any camera that exposes an RTSP stream over TCP:

| Brand | Models | Protocol |
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
├── argus/                          # Main Python package
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
│   │   ├── learner.py              # AutoLearner — quality scoring, temporal analysis
│   │   └── embeddings.py           # FAISS IndexFlatIP embedding database
│   ├── alerts/
│   │   ├── models.py               # Alert, AlertKind, AlertSeverity, InteractiveButton
│   │   ├── queue.py                # Priority queue + TokenBucket + QuietHoursGate
│   │   ├── telegram_client.py      # Telegram bot dispatcher + callback polling
│   │   ├── discord_client.py       # Discord bot dispatcher + ui.View listeners
│   │   └── manager.py              # AlertManager — routing hub, worker, held-release
│   ├── storage/
│   │   ├── base.py                 # StorageBackend ABC
│   │   ├── local.py                # Local filesystem + retention policy
│   │   ├── rclone.py               # rclone wrapper (GDrive, S3, B2, SFTP)
│   │   └── manager.py              # Async upload queue + background worker
│   ├── database/
│   │   ├── engine.py               # SQLAlchemy async engine + session factory
│   │   ├── models.py               # ORM: Camera, FaceProfile, Event, Clip, UnknownFaceTracker
│   │   └── repository.py           # Repository pattern — clean CRUD, no raw SQL in logic
│   ├── pipeline/
│   │   └── orchestrator.py         # EventOrchestrator — wires all modules together
│   ├── dashboard/
│   │   ├── app.py                  # Streamlit entrypoint
│   │   └── pages/                  # Live · Events · Faces · Settings
│   └── utils/
│       └── banner.py               # Professional ASCII terminal banner
├── alembic/                        # Database migrations
├── tests/                          # 617 tests, 81% coverage
│   ├── core/
│   ├── intelligence/
│   ├── alerts/                     # Full mock suite for Telegram + Discord
│   ├── config/
│   └── database/
├── config/
│   └── config.example.yaml
├── docker/
│   ├── Dockerfile                  # CPU production image
│   └── Dockerfile.gpu              # CUDA 12.3 production image
├── scripts/
│   ├── enroll_face.py              # Enroll a known person from image files
│   ├── test_stream.py              # Verify camera RTSP URL and show live frame
│   └── benchmark.py               # FPS benchmark on your hardware
├── docker-compose.yml
├── docker-compose.gpu.yml
├── Makefile
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Development

```bash
make dev          # Start in dev mode with hot reload
make test         # Run full test suite with coverage
make lint         # Ruff check + mypy type-check
make fmt          # Ruff format (auto-fix)
make docker-build # Build CPU + GPU Docker images
make migrate      # Run alembic upgrade head
make benchmark    # FPS benchmark on your hardware
```

### Testing

```bash
# Run full suite
.venv/bin/python -m pytest

# Run specific module
.venv/bin/python -m pytest tests/alerts/ -v

# With coverage report
.venv/bin/python -m pytest --cov=argus --cov-report=html
```

Current test statistics:
- **617 tests** across all modules
- **81.79% coverage**
- **0 ruff / mypy issues**
- All Telegram and Discord API calls are **fully mocked** — CI requires no real credentials

---

## Roadmap

Argus is built phase-by-phase. Each phase ships working, tested, committed code before the next begins.

| Phase | Status | Description |
|---|---|---|
| **0 — Foundation** | ✅ Done | Config system, logging, database models, Alembic migrations |
| **1 — Stream Ingestor** | ✅ Done | PyAV RTSP ingestor with MOG2 motion pre-filter |
| **2 — Detection Engine** | ✅ Done | YOLOv8 GPU detection with async process isolation |
| **3 — Face Recognition** | ✅ Done | InsightFace + ArcFace + FAISS + SORT tracker |
| **4 — Recording Engine** | ✅ Done | Pre-event circular buffer + FFmpeg hardware encoding |
| **5 — LLM Intelligence** | ✅ Done | Laya 421M gate + multi-provider vision LLM + AutoLearner |
| **6 — Alert Engine** | ✅ Done | Telegram + Discord with priority queue, rate limiting, interactive buttons |
| **7 — Storage Manager** | 🔜 Next | Async rclone upload to GDrive / S3 / B2 / SFTP |
| **8 — Pipeline Orchestrator** | ⏳ Planned | Wires all workers into the live running system |
| **9 — Dashboard** | ⏳ Planned | Streamlit UI: live view, event timeline, face gallery, settings |
| **10 — Docker + CI/CD** | ⏳ Planned | GPU containers, GitHub Actions, automated publishing |

---

## Contributing

Contributions are warmly welcome! Argus follows conventional open-source contribution guidelines.

### Before You Start

1. **Check existing issues** — your idea may already be tracked
2. **Open an issue first** for large features — get alignment before writing code
3. **Small fixes** (typos, doc improvements) — PRs welcome directly

### Development Setup

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/argus.git
cd argus

# Install in editable mode with all dev deps
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install pre-commit hooks (runs ruff + mypy on every commit)
pre-commit install

# Run the test suite to confirm everything works
make test
```

### Workflow

```bash
# 1. Create a descriptive branch
git checkout -b feat/add-ntfy-alert-channel
#   or
git checkout -b fix/telegram-callback-timeout

# 2. Make your changes. Write tests for new behaviour.
#    Coverage must not drop below 80%.

# 3. Verify everything passes locally
make lint    # Must be clean
make test    # Must all pass

# 4. Commit using Conventional Commits format
git commit -m "feat(alerts): add ntfy.sh push notification channel"
git commit -m "fix(telegram): handle callback timeout gracefully"
git commit -m "docs(readme): add ntfy configuration example"

# 5. Push and open a Pull Request
git push origin feat/add-ntfy-alert-channel
```

### Commit Message Convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

Types: feat | fix | docs | test | refactor | perf | chore | ci
Scope: core | intelligence | alerts | storage | dashboard | database | config | pipeline
```

### Pull Request Checklist

Before submitting your PR, confirm:

- [ ] All existing tests pass (`make test`)
- [ ] New behaviour has tests (coverage ≥ 80%)
- [ ] Linting is clean (`make lint`)
- [ ] Commit messages follow Conventional Commits
- [ ] PR description explains **what** changed and **why**
- [ ] External API calls (Telegram, Discord, OpenAI) are mocked in tests

### Code Standards

- **Type hints everywhere** — all function signatures must be fully annotated
- **Structured logging** — use `structlog` with key-value context, never `print()`
- **Async safety** — CPU/GPU-bound work runs in `run_in_executor`, never blocks the event loop
- **Dependency injection** — pass dependencies in `__init__`, never use global singletons
- **Pydantic for data** — all inter-module data structures use Pydantic models, never raw dicts
- **Errors never silently swallow** — log with context, return safe fallback or re-raise

### Project Areas Needing Help

| Area | Skills Needed | Difficulty |
|---|---|---|
| Dashboard pages | Python, Streamlit | 🟡 Intermediate |
| Storage backends | Python, rclone | 🟢 Beginner |
| Camera ONVIF discovery | Python, networking | 🟡 Intermediate |
| Multi-GPU support | Python, CUDA | 🔴 Advanced |
| ARM / Apple Silicon builds | Python, Docker | 🟡 Intermediate |
| Documentation & tutorials | Writing | 🟢 Beginner |

### Reporting Bugs

Open a [GitHub Issue](https://github.com/yourusername/argus/issues/new) with:
- Your OS and Python version
- Argus version (`python -m argus --version`)
- Steps to reproduce
- Expected vs actual behaviour
- Relevant log output (redact any tokens or API keys)

---

## Acknowledgements

Argus is built on the shoulders of excellent open-source work:

- [ultralytics](https://github.com/ultralytics/ultralytics) — YOLOv8 object detection
- [InsightFace](https://github.com/deepinsight/insightface) — ArcFace face recognition
- [faiss](https://github.com/facebookresearch/faiss) — Vector similarity search
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) — Telegram async SDK
- [discord.py](https://github.com/Rapptz/discord.py) — Discord async SDK
- [pydantic](https://github.com/pydantic/pydantic) — Data validation
- [structlog](https://github.com/hynek/structlog) — Structured logging
- [PyAV](https://github.com/PyAV-Org/PyAV) — Python bindings for FFmpeg

---

## License

MIT License — see [LICENSE](LICENSE) for full text.

---

<div align="center">

Built with precision for privacy-first home security.

**Argus sees all. Your data stays home.**

*If this project helps you, consider starring it ⭐*

</div>
