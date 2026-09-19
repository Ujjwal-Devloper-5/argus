<div align="center">

<img src="docs/screenshots/argus-banner.jpg" alt="Argus Banner" width="800"/>

# 👁️ Argus

### AI-Powered Smart Security System

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![GPU](https://img.shields.io/badge/CUDA-Accelerated-76B900?style=for-the-badge&logo=nvidia)](https://developer.nvidia.com/cuda-zone)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-black?style=for-the-badge)](https://ollama.ai)

*Named after Argus Panoptes — the all-seeing giant of Greek mythology with 100 eyes.*

[Features](#-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start) • [Configuration](#-configuration) • [Dashboard](#-dashboard) • [Contributing](#-contributing)

</div>

---

## 🌟 Overview

**Argus** is a self-hosted, privacy-first AI security system that transforms any IP camera into an intelligent sentinel. It combines real-time person detection, face recognition, LLM-powered scene understanding, and smart alerting — all running locally on your hardware.

Unlike cloud-based solutions, Argus processes everything on-device. Your footage never leaves your network.

---

## ✨ Features

### 🎯 Smart Detection
- **Person Detection** — YOLOv8-powered, GPU-accelerated, real-time
- **Face Recognition** — InsightFace embeddings with cosine similarity matching
- **Known Face Profiles** — Train on your family/household members
- **Auto-Learning** — Automatically tracks unknown frequent visitors and asks you to approve them

### 🧠 LLM Intelligence
- **Scene Understanding** — Describe what's happening using any Ollama vision model (LLaVA, Moondream, Llama3.2-Vision)
- **Behaviour Analysis** — Context-aware alerts ("Person is checking the door" vs "Person is passing by")
- **Provider Agnostic** — Works with Ollama (local), OpenAI GPT-4V, Anthropic Claude, Google Gemini
- **Smart Summaries** — Daily digest of all events

### 📹 Intelligent Recording
- **Incident-Only Recording** — No 24/7 footage spam; records only when something happens
- **Pre-Event Buffer** — Always captures 5 seconds before the trigger
- **Multi-Stream Support** — Main (1080p) + Sub stream simultaneously
- **Any RTSP Camera** — Tapo, Hikvision, Dahua, Reolink, and more

### 🔔 Flexible Alerting
- **Telegram Bot** — Rich alerts with photo, AI description, inline approve/reject buttons
- **Email** — SMTP support
- **Webhooks** — POST to any endpoint
- **ntfy** — Push notifications
- **Silenced Hours** — Define quiet hours per camera

### ☁️ Storage Backends
- **Local disk**
- **Google Drive** (via rclone)
- **AWS S3 / Cloudflare R2 / Backblaze B2**
- **SFTP / NAS**
- Auto-expiry policies per backend

### 📊 Dashboard
- Live stream viewer (multi-camera grid)
- Event timeline with thumbnails
- Known faces gallery — add, remove, retrain
- Per-camera stats and health
- Mobile-responsive

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     IP Cameras (RTSP)                   │
└──────────────────────┬──────────────────────────────────┘
                       │
          ┌────────────▼────────────┐
          │    Stream Ingestor      │  OpenCV / FFmpeg
          │  (Motion Pre-filter)    │  Skip static frames
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │   YOLOv8 Detector       │  Person / Object
          │   (GPU Accelerated)     │  Detection
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │  InsightFace Recognizer │  512-dim face
          │  + Embedding DB         │  embeddings
          └──────┬──────────┬───────┘
                 │          │
          KNOWN ✅       UNKNOWN ❓
                 │          │
             Log only   ┌───▼──────────┐
                        │ LLM Analyzer │  Ollama / OpenAI
                        │ Scene Intent │  / Claude / Gemini
                        └───┬──────────┘
                            │
               ┌────────────▼────────────┐
               │    Alert Engine         │  Telegram / Email
               │  + Smart Recorder       │  / Webhook / ntfy
               └────────────┬────────────┘
                            │
               ┌────────────▼────────────┐
               │   Storage Manager       │  GDrive / S3
               │   (Incident Clips Only) │  / Local / NAS
               └─────────────────────────┘
```

---

## 🚀 Quick Start

### Option 1 — Docker (Recommended)

```bash
# Clone
git clone https://github.com/yourusername/argus.git
cd argus

# Configure
cp .env.example .env
nano .env  # Add your camera RTSP URL, Telegram token etc.

# Run (CPU)
docker compose up -d

# Run (GPU)
docker compose -f docker-compose.gpu.yml up -d
```

### Option 2 — Bare Metal

```bash
# Clone
git clone https://github.com/yourusername/argus.git
cd argus

# Install
make install        # Sets up virtualenv + dependencies
make install-gpu    # With CUDA support

# Configure
cp .env.example .env
cp config/config.example.yaml config/config.yaml
nano config/config.yaml

# Add known faces
python scripts/enroll_face.py --name "John" --images /path/to/photos/

# Run
make run
```

---

## ⚙️ Configuration

### `.env` — Secrets & Keys
```env
# Camera
CAMERA_RTSP_URL=rtsp://admin:password@192.168.0.100:554/stream1
CAMERA_NAME=Front Door

# LLM Provider (pick one)
LLM_PROVIDER=ollama           # ollama | openai | anthropic | gemini
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llava

# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GOOGLE_API_KEY=...

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Storage
STORAGE_BACKEND=local         # local | gdrive | s3
LOCAL_STORAGE_PATH=./data/clips
# RCLONE_REMOTE=gdrive:Security/Argus

# Dashboard
DASHBOARD_PORT=8501
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=changeme
```

### `config/config.yaml` — Behaviour
```yaml
cameras:
  - name: front_door
    rtsp_url: ${CAMERA_RTSP_URL}
    resolution: [1920, 1080]
    fps: 15
    pre_buffer_seconds: 5
    post_event_seconds: 30

detection:
  model: yolov8n          # yolov8n | yolov8s | yolov8m | yolov8l
  confidence: 0.6
  classes: [person]       # What to detect

recognition:
  similarity_threshold: 0.6
  auto_learn:
    enabled: true
    appearances_before_prompt: 5
    prompt_via: telegram

intelligence:
  enabled: true
  prompt: >
    Describe what this person is doing in one sentence.
    Are they behaving suspiciously? Be concise.

alerts:
  quiet_hours:
    start: "23:00"
    end: "07:00"
  cooldown_seconds: 60    # Min time between alerts per camera
```

---

## 📦 Project Structure

```
argus/
├── argus/                     # Core Python package
│   ├── core/
│   │   ├── stream.py          # RTSP stream handler + motion filter
│   │   ├── detector.py        # YOLOv8 person/object detection
│   │   ├── recognizer.py      # InsightFace face recognition
│   │   └── recorder.py        # Smart pre-buffer recorder
│   ├── intelligence/
│   │   ├── llm.py             # LLM provider abstraction
│   │   ├── learner.py         # Auto-learning face tracker
│   │   └── embeddings.py      # Face embedding DB management
│   ├── alerts/
│   │   ├── telegram.py        # Telegram bot + inline buttons
│   │   ├── email.py           # SMTP alerts
│   │   ├── webhook.py         # Generic webhook
│   │   └── ntfy.py            # ntfy push notifications
│   ├── storage/
│   │   ├── local.py           # Local filesystem
│   │   ├── gdrive.py          # Google Drive via rclone
│   │   └── s3.py              # S3-compatible (AWS/R2/B2)
│   ├── dashboard/             # Streamlit web UI
│   │   ├── app.py
│   │   └── pages/
│   │       ├── live.py        # Live multi-camera view
│   │       ├── events.py      # Event history + playback
│   │       ├── faces.py       # Known faces management
│   │       └── settings.py    # Runtime settings
│   ├── database/
│   │   └── models.py          # SQLAlchemy ORM models
│   └── utils/
│       ├── config.py          # Config loader
│       └── logger.py          # Structured logging
├── docker/
│   ├── Dockerfile             # CPU image
│   └── Dockerfile.gpu         # CUDA image
├── config/
│   ├── config.example.yaml
│   └── known_faces/           # Drop face images here
├── scripts/
│   ├── enroll_face.py         # Add known person
│   ├── test_stream.py         # Verify camera connection
│   └── benchmark.py           # Performance benchmark
├── tests/                     # pytest test suite
├── docs/                      # Documentation
├── docker-compose.yml         # CPU deployment
├── docker-compose.gpu.yml     # GPU deployment
├── Makefile                   # Dev commands
├── pyproject.toml             # Modern Python packaging
└── .env.example               # Environment template
```

---

## 🖥️ Dashboard

Access at `http://localhost:8501`

| Page | Description |
|---|---|
| **Live** | Real-time camera feeds, detection overlays |
| **Events** | Timeline of all incidents with clips + AI descriptions |
| **Faces** | Manage known faces — add photos, review auto-learn suggestions |
| **Settings** | Camera config, alert thresholds, storage settings |

---

## 🤖 Supported LLM Providers

| Provider | Models | Mode |
|---|---|---|
| **Ollama** (default) | LLaVA, Moondream, Llama3.2-Vision | Local 🔒 |
| **OpenAI** | GPT-4V, GPT-4o | Cloud |
| **Anthropic** | Claude 3.5 Sonnet | Cloud |
| **Google** | Gemini 1.5 Pro | Cloud |

---

## 📷 Supported Cameras

Any camera that exposes an RTSP stream:
- TP-Link Tapo (C100, C200, C310, C500...)
- Hikvision
- Dahua
- Reolink
- Amcrest
- Generic ONVIF cameras
- IP Webcam (Android app)

---

## 🛠️ Development

```bash
make dev          # Start in dev mode with hot reload
make test         # Run test suite
make lint         # Ruff + mypy
make docker-build # Build Docker images
make docs         # Serve docs locally
```

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](docs/CONTRIBUTING.md) first.

1. Fork the repo
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'feat: add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 🏗️ Development Progress

Argus is being built according to a rigorous 10-phase engineering blueprint:

- [x] **Phase 0: Foundation** (Config system, Logging, Database Models, Alembic Migrations)
- [x] **Phase 1: Stream Ingestor** (PyAV RTSP ingestor, MOG2 motion pre-filter)
- [ ] **Phase 2: Detection Engine** (YOLOv8 CPU/GPU auto-detect)
- [ ] **Phase 3: Face Recognition** (InsightFace + FAISS + SORT multi-object tracking)
- [ ] **Phase 4: Recording Engine** (Pre-event circular buffer + hardware-accelerated FFmpeg)
- [ ] **Phase 5: LLM Intelligence** (Ollama/OpenAI/Anthropic adapters + Auto-learning system)
- [ ] **Phase 6: Alert Engine** (Telegram with inline actions, rate limiting, quiet hours)
- [ ] **Phase 7: Storage Manager** (Local retention + async rclone to GDrive/S3)
- [ ] **Phase 8: Pipeline Orchestrator** (Tying the async workers together)
- [ ] **Phase 9: Dashboard** (Streamlit UI for live view, events, faces, and settings)
- [ ] **Phase 10: Docker & CI/CD** (Automated builds, GPU containers, deployment scripts)

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
Built with ❤️ for privacy-first home security
<br/>
<b>Argus sees all. Your data stays home.</b>
</div>
