# Master Dashboard Architecture & Remediation Plan (Argus AI Security System)

**Document Version**: 1.0.0  
**Target Path**: `/home/ujjwal/homelab/argus/argus/dashboard/master_dashboard_plan.md`  
**Classification**: Enterprise Security & Production Architecture Blueprint  
**System**: Argus NVR & Vision Intelligence Command Center (FastAPI + React)  
**Author**: Master Plan Architect  

---

## Table of Contents
1. [Executive Summary & Dashboard Architecture Assessment](#1-executive-summary--dashboard-architecture-assessment)
2. [Security Flaws & Vulnerabilities](#2-security-flaws--vulnerabilities)
   - [2.1 WebSocket Vulnerabilities](#21-websocket-vulnerabilities)
   - [2.2 Authentication & Authorization Gaps](#22-authentication--authorization-gaps)
   - [2.3 Severe Security Attack Vectors](#23-severe-security-attack-vectors)
3. [UI/UX Flaws & Frontend Deficiencies](#3-uiux-flaws--frontend-deficiencies)
   - [3.1 Complete Mock & Dummy Data Catalog (17 States)](#31-complete-mock--dummy-data-catalog-17-states)
   - [3.2 White Screen Crashes & Missing Error Boundaries](#32-white-screen-crashes--missing-error-boundaries)
   - [3.3 Dark/Light Mode FOUC & Theme Engine](#33-darklight-mode-fouc--theme-engine)
   - [3.4 Missing Loading Skeletons & Empty States](#34-missing-loading-skeletons--empty-states)
   - [3.5 Mobile & Tablet Responsive Layout Breakdowns](#35-mobile--tablet-responsive-layout-breakdowns)
   - [3.6 Video Streaming UX & Player Limitations](#36-video-streaming-ux--player-limitations)
4. [Bugs & Runtime Failures](#4-bugs--runtime-failures)
   - [4.1 Fatal Startup Crashes](#41-fatal-startup-crashes)
   - [4.2 Fatal Login Lockout](#42-fatal-login-lockout)
   - [4.3 Frontend Fatal Crash in Events Page](#43-frontend-fatal-crash-in-events-page)
   - [4.4 Infinite 401 Redirect Loop & Orphaned Route](#44-infinite-401-redirect-loop--orphaned-route)
   - [4.5 WebSocket Memory Leaks & Schema Desynchronization](#45-websocket-memory-leaks--schema-desynchronization)
   - [4.6 Synchronous Event Loop Blocking Traps](#46-synchronous-event-loop-blocking-traps)
   - [4.7 Broken Stubs & Missing Media Endpoints](#47-broken-stubs--missing-media-endpoints)
5. [Missing Configurations & Feature Gaps](#5-missing-configurations--feature-gaps)
   - [5.1 Camera Management & RTSP Controls](#51-camera-management--rtsp-controls)
   - [5.2 Storage, Video Recording & RAM Memory Buffering](#52-storage-video-recording--ram-memory-buffering)
   - [5.3 AI Vision & LLM Intelligence Controls](#53-ai-vision--llm-intelligence-controls)
   - [5.4 Alerts, Bot Integrations & Two-Way Callbacks](#54-alerts-bot-integrations--two-way-callbacks)
   - [5.5 Configuration Persistence, Cache & Zero-Downtime Hot-Reload](#55-configuration-persistence-cache--zero-downtime-hot-reload)
6. [Concrete Premium-Grade Architectural Solutions & Phased Implementation Roadmap](#6-concrete-premium-grade-architectural-solutions--phased-implementation-roadmap)
   - [6.1 Strictly Typed Configuration Schemas & Safe Secret Handling](#61-strictly-typed-configuration-schemas--safe-secret-handling)
   - [6.2 In-Memory Pub/Sub Event Bus (`DashboardEventBus`)](#62-in-memory-pubsub-event-bus-dashboardeventbus)
   - [6.3 Hardened Authentication, Single-Use Nonces & Bounded Sockets](#63-hardened-authentication-single-use-nonces--bounded-sockets)
   - [6.4 High-Performance Live Video Streaming & Canvas Bounding Box Engine](#64-high-performance-live-video-streaming--canvas-bounding-box-engine)
   - [6.5 End-to-End Face Enrollment & FAISS Vector Index Synchronization](#65-end-to-end-face-enrollment--faiss-vector-index-synchronization)
   - [6.6 AutoLearner Candidate Management Interface](#66-autolearner-candidate-management-interface)
   - [6.7 Phased Implementation Roadmap](#67-phased-implementation-roadmap)

---

## 1. Executive Summary & Dashboard Architecture Assessment

The Argus Security System is an edge-first AI surveillance platform combining RTSP stream ingestion (PyAV), motion pre-filtering (OpenCV MOG2), object detection (Ultralytics YOLOv8), facial recognition (InsightFace + FAISS), circular RAM pre-buffering, local hardware-accelerated video recording (FFmpeg NVENC), and two-way alert dispatch (Telegram and Discord).

The Argus Dashboard comprises a **FastAPI backend** and a **React 19 (TypeScript + Vite + Tailwind CSS) single-page application (SPA)**. An exhaustive, multi-vector audit of the dashboard codebase reveals that while the aesthetic design tokens and conceptual capabilities are robust, the implementation remains in an unstable prototype stage characterized by:
1. **Critical Boot Blockers**: The FastAPI server cannot boot due to missing module imports (`secrets`) and parameter signature mismatches across four primary API routers.
2. **Fatal Authentication Lockouts**: The initial setup wizard writes password hashes under an incompatible cryptographic schema than what the authentication module expects, locking administrators out immediately upon initialization.
3. **Severe Security Vulnerabilities**: Unauthenticated WebSocket telemetry, arbitrary local file disclosure (path traversal) in SPA serving allowing unauthenticated `/etc/passwd` exfiltration, unauthenticated SSRF in connection testing, plaintext credential exposure in camera URLs, and destructive configuration overwriting of masked secrets.
4. **Widespread Prototype Mock States**: 17 individual user-facing components contain hardcoded dummy metrics, fake SVG graphs, non-functional buttons, and un-routed detail views.
5. **Decoupled Real-Time Pipeline**: In standard standalone deployments without an external Kafka cluster, the backend defaults to an empty 30-second heartbeat loop, severing the live surveillance pipeline from the frontend interface.
6. **Synchronous Concurrency Traps**: The single-threaded asyncio event loop is blocked by synchronous directory scanning (`glob.glob`) in MJPEG streaming, synchronous subprocess executions (`nvidia-smi`), and blocking synchronous disk I/O.

This Master Plan provides a comprehensive, production-grade architectural specification to remediate every discovered defect, close all security vulnerabilities, eliminate all mock data, and establish a resilient, hardened surveillance operations center.

```
                      CURRENT HYBRID PROTOTYPE STATE
┌────────────────┐     HTTP REST      ┌──────────────────┐
│  React 19 SPA  │ ◄────────────────► │  FastAPI Server  │ ──► Boot Crashes & Broken Auth
│ (17 Mock Views)│     /ws/stats      │  (Blocking I/O)  │
└────────────────┘ (Zero-Auth Leak)   └─────────┬────────┘
                                                │ (Decoupled in Non-Kafka Deployments)
                                                ▼
                                      ┌──────────────────┐
                                      │  Argus Pipeline  │
                                      │ (SQLite Storage) │
                                      └──────────────────┘

                    TARGET PRODUCTION-GRADE ARCHITECTURE
┌────────────────────────────────────────────────────────────────────────┐
│                        React 19 Operations Center                      │
│  - React Error Boundaries        - Canvas Bounding Box Overlays        │
│  - ThemeProvider (FOUC-Free)     - Low-Latency Bounded WebSocket Hooks │
│  - Responsive Drawer & Grid      - Dedicated Event Detail & ClipPlayer │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Secure Nonce WS & Authenticated REST
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        Hardened FastAPI Backend                        │
│  - Unified PBKDF2 Constant-Time Auth    - Canonical Path-Checked SPA   │
│  - Safe Secret Preservation Engine      - Single-Use Nonce Cache       │
│  - Non-Blocking ThreadPool I/O          - StreamWorker Frame Bridge    │
└───────────────────▲───────────────────────────────▲────────────────────┘
                    │                               │
                    ▼ Config Updates                ▼ Pub/Sub Events
┌────────────────────────────────────┐    ┌──────────────────────────────┐
│           ConfigEventBus           │    │       DashboardEventBus      │
│  - Hot-reloads Camera Ingestors    │    │  - Real-time Alert Dispatch  │
│  - Dynamic YOLO Confidence Tuning  │    │  - Bounded Client WS Queues  │
│  - Zero-Downtime Worker Sync       │    │  - Works with/without Kafka  │
└────────────────────────────────────┘    └──────────────────────────────┘
```

---

## 2. Security Flaws & Vulnerabilities

### 2.1 WebSocket Vulnerabilities

#### 2.1.1 Zero-Authentication Access on `/ws/stats`
* **File & Lines**: `argus/dashboard/backend/websocket/stats_ws.py:9-10, 72-75`
* **Vulnerability Description**: While `verify_ws_ticket` is imported at the top of the file, the endpoint function defines `token: str | None = None` and immediately calls `await stats_manager.connect(websocket)` without validating the ticket or session token.
* **Threat Model & Attack Vector**: Any unauthenticated client on the local network (or public internet if reverse-proxied without edge authentication) can connect to `ws://<host>:8000/ws/stats`. Every 5 seconds, the server broadcasts full host metrics, CPU/RAM utilization, active camera lists, storage path allocations, and raw database connection strings.
* **Severity**: **HIGH (CVSS: 7.5)** — CWE-306: Missing Authentication for Critical Function.
* **Remediation Blueprint**:
  Enforce ticket verification during connection establishment:
  ```python
  @router.websocket("")
  async def websocket_endpoint(
      websocket: WebSocket,
      ticket: Annotated[str | None, Query()] = None,
  ):
      if not ticket or not verify_ws_ticket(ticket):
          await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
          return
      await stats_manager.connect(websocket)
      try:
          while True:
              await websocket.receive_text()
      except (WebSocketDisconnect, ConnectionResetError):
          stats_manager.disconnect(websocket)
      finally:
          stats_manager.disconnect(websocket)
  ```

#### 2.1.2 Reusable WebSocket Tickets & Query Parameter Exposure
* **File & Lines**: `argus/dashboard/backend/auth.py:80-87, 103-110`
* **Vulnerability Description**: WebSocket tickets are signed JWTs with a 60-second expiration (`"exp": time.time() + 60`), but they are entirely stateless. They are not one-time tokens (nonces). Once issued, a ticket can be reused multiple times by any client within the 60-second window. Furthermore, tickets are passed as URL query parameters (`/ws/events?ticket=...`), exposing them to browser histories, proxy access logs, and HTTP server referer headers.
* **Threat Model & Attack Vector**: An eavesdropper or intermediate proxy logging query strings can capture an active ticket and establish an unauthorized WebSocket connection before the 60-second window elapses.
* **Severity**: **MEDIUM (CVSS: 5.3)** — CWE-287: Improper Authentication.
* **Remediation Blueprint**:
  Implement single-use nonces stored in an in-memory TTL dictionary with constant-time verification. When a ticket is verified, it is immediately popped and invalidated:
  ```python
  import secrets
  from typing import Dict, Tuple

  _TICKET_STORE: Dict[str, Tuple[str, float]] = {}  # nonce -> (username, expiry_timestamp)

  def create_ws_ticket(username: str) -> str:
      _purge_expired_tickets()
      nonce = secrets.token_urlsafe(32)
      _TICKET_STORE[nonce] = (username, time.time() + 30.0)  # 30-second window
      return nonce

  def verify_ws_ticket(ticket: str) -> bool:
      _purge_expired_tickets()
      if not ticket or ticket not in _TICKET_STORE:
          return False
      username, expiry = _TICKET_STORE.pop(ticket)  # Single-use pop!
      return time.time() <= expiry
  ```

#### 2.1.3 Cross-Site WebSocket Hijacking (CSWSH) & Missing Origin Validation
* **File & Lines**: `argus/dashboard/backend/websocket/events_ws.py:82-99` and `stats_ws.py:72-80`
* **Vulnerability Description**: WebSocket handshakes do not validate the `Origin` or `Sec-WebSocket-Origin` header against permitted dashboard hostnames.
* **Threat Model & Attack Vector**: If a user is logged into the Argus dashboard and visits a malicious website in another browser tab, malicious JavaScript on that site can initiate a WebSocket connection to `ws://argus.local:8000/ws/events`. If ticket generation or session cookies are accessible, the attacker can hijack the real-time event feed.
* **Severity**: **MEDIUM (CVSS: 6.5)** — CWE-346: Origin Validation Error.
* **Remediation Blueprint**:
  Validate the request Origin header against configured `dashboard.allowed_origins` before calling `await websocket.accept()`.

#### 2.1.4 Head-of-Line Blocking & Denial of Service in WebSocket Broadcasts
* **File & Lines**: `argus/dashboard/backend/websocket/events_ws.py:34-44` and `stats_ws.py:30-40`
* **Vulnerability Description**:
  `ConnectionManager.broadcast()` iterates sequentially over `self.active_connections.copy()`, awaiting `connection.send_text(message)` on each socket. If a single client has network latency, buffer backlog, or is deliberately slow to read, the `await connection.send_text(message)` call blocks, stalling the broadcast to all other active dashboard operators.
  Additionally, unhandled network exceptions exit the handler without calling `disconnect(websocket)`, permanently leaking socket descriptors.
* **Severity**: **MEDIUM (CVSS: 5.9)** — CWE-400: Uncontrolled Resource Consumption.
* **Remediation Blueprint**:
  Decouple broadcasts using per-client bounded `asyncio.Queue(maxsize=100)` workers. Broadcast simply executes `queue.put_nowait(message)`. If a slow client's queue fills, the oldest non-critical frame is dropped or the slow client is disconnected.

---

### 2.2 Authentication & Authorization Gaps

#### 2.2.1 Cryptographic Hash & Iteration Schema Incompatibility
* **File & Lines**: `argus/dashboard/backend/routes/setup.py:63-66, 278-284` vs `argus/dashboard/backend/auth.py:33-36`
* **Vulnerability Description**:
  `setup.py` generates passwords using PBKDF2-HMAC-SHA256 with 260,000 iterations and writes a single formatted string:
  ```python
  # setup.py
  def _hash_password(password: str) -> str:
      salt = secrets.token_hex(16)
      dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
      return f"pbkdf2:sha256:260000:{salt}:{dk.hex()}"
  ```
  Conversely, `auth.py` attempts to access distinct dictionary keys `stored["salt"]` and `stored["hash"]` with 100,000 iterations:
  ```python
  # auth.py
  stored = users[username]
  salt = bytes.fromhex(stored["salt"])
  key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
  return key.hex() == stored["hash"]
  ```
* **Impact**: Accessing `stored["salt"]` raises an unhandled `KeyError: 'salt'`, causing `POST /api/auth/login` to return HTTP 500. Every user completing the setup wizard is permanently locked out.
* **Severity**: **CRITICAL (CVSS: 9.1)** — Complete authentication denial of service.
* **Remediation Blueprint**:
  Standardize on PBKDF2-HMAC-SHA256 with 260,000 iterations using a standardized JSON user schema:
  `{"salt": salt_hex, "hash": hash_hex, "iterations": 260000, "role": "admin"}`.

#### 2.2.2 Missing `import secrets` NameError Crash
* **File & Lines**: `argus/dashboard/backend/auth.py:4-15, 17-19`
* **Vulnerability Description**:
  ```python
  JWT_SECRET = os.environ.get("ARGUS_JWT_SECRET", secrets.token_hex(32))
  ```
  `secrets` is never imported in `auth.py`. When `ARGUS_JWT_SECRET` is unset, Python raises `NameError: name 'secrets' is not defined` during module import, crashing the backend at startup.
* **Severity**: **HIGH (CVSS: 7.5)** — Fatal boot failure.
* **Remediation Blueprint**:
  Add `import secrets` to `auth.py` and persist the generated JWT secret to `data/.jwt_secret` so user sessions remain valid across process restarts.

#### 2.2.3 Pydantic `SecretStr` Equality Comparison Defect
* **File & Lines**: `argus/dashboard/backend/auth.py:40`
* **Vulnerability Description**:
  ```python
  return username == settings.dashboard.username and password == settings.dashboard.password
  ```
  In `argus/config/settings.py`, `DashboardConfig.password` is typed as `SecretStr`. In Pydantic, comparing a raw `str` to a `SecretStr` via `==` always evaluates to `False`. Authentication via `config.yaml` fallback credentials always fails.
* **Severity**: **HIGH (CVSS: 7.5)** — Authentication failure.
* **Remediation Blueprint**:
  Extract the secret value using `settings.dashboard.password.get_secret_value()` and use `secrets.compare_digest`.

#### 2.2.4 Timing Side-Channel Vulnerabilities in Password Verification
* **File & Lines**: `argus/dashboard/backend/auth.py:36, 40`
* **Vulnerability Description**: Hashes and plaintext passwords are evaluated using Python's standard `==` operator, which short-circuits on the first mismatched byte, exposing the verification routine to timing attacks.
* **Severity**: **LOW/MEDIUM (CVSS: 3.7)** — CWE-208: Observable Timing Discrepancy.
* **Remediation Blueprint**:
  Use `secrets.compare_digest(key.hex(), stored["hash"])`.

#### 2.2.5 Absence of Role-Based Access Control (RBAC)
* **File & Lines**: `argus/dashboard/backend/auth.py:48-70`
* **Vulnerability Description**: The auth dependency checks only whether a valid token exists (`"sub": username`). There are no permission scopes (e.g., `viewer`, `operator`, `admin`). A viewing client has unrestricted access to delete face profiles, wipe audit events, and alter camera RTSP URLs.
* **Severity**: **MEDIUM (CVSS: 6.5)** — CWE-285: Improper Authorization.
* **Remediation Blueprint**:
  Embed `"role": "admin" | "operator" | "viewer"` in the JWT payload and enforce `require_role(["admin"])` on destructive endpoints (`PUT /api/settings`, `DELETE /api/cameras/{name}`, `DELETE /api/faces/{id}`).

#### 2.2.6 Hardcoded Localhost CORS Origins
* **File & Lines**: `argus/dashboard/backend/app.py:61-67`
* **Vulnerability Description**:
  `allow_origins` is hardcoded to `["http://localhost:5173", "http://localhost:3000"]`. Accessing the dashboard over LAN IPs (`192.168.1.x`), VPNs (WireGuard/Tailscale), or homelab domains results in CORS rejections.
* **Severity**: **LOW/MEDIUM (CVSS: 4.0)** — Functional network blocking.
* **Remediation Blueprint**:
  Populate `allow_origins` dynamically from `settings.dashboard.allowed_origins`, defaulting to localhost while allowing subnet wildcards or user-configured hostnames.

---

### 2.3 Severe Security Attack Vectors

#### 2.3.1 Arbitrary Local File Disclosure / Path Traversal in SPA Serving
* **File & Lines**: `argus/dashboard/backend/app.py:90-95`
* **Vulnerability Description**:
  ```python
  @app.get("/{full_path:path}", include_in_schema=False)
  async def serve_spa(full_path: str):
      path = os.path.join(STATIC_DIR, full_path)
      if os.path.isfile(path):
          return FileResponse(path)
      return FileResponse(os.path.join(STATIC_DIR, "index.html"))
  ```
  1. `os.path.join(STATIC_DIR, full_path)` does not sanitize relative directory traversal (`../`).
  2. If `full_path` has a leading slash (e.g. `/etc/passwd`), Python's `os.path.join` discards `STATIC_DIR` and evaluates to `/etc/passwd`.
  3. No validation verifies that `os.path.abspath(path)` begins with `STATIC_DIR`.
* **Threat Model & Attack Vector**: An unauthenticated attacker sends an HTTP GET request for `//etc/passwd`, `//etc/shadow`, or `//home/ujjwal/homelab/argus/config/config.yaml`. The server returns the sensitive host file directly as a static file response.
* **Severity**: **CRITICAL (CVSS: 9.8)** — CWE-22: Improper Limitation of a Pathname to a Restricted Directory.
* **Remediation Blueprint**:
  ```python
  @app.get("/{full_path:path}", include_in_schema=False)
  async def serve_spa(full_path: str):
      # Strip leading slashes to prevent root discard
      safe_subpath = full_path.lstrip("/\\")
      target_path = os.path.abspath(os.path.join(STATIC_DIR, safe_subpath))
      
      # Strict containment check
      static_root = os.path.abspath(STATIC_DIR)
      if target_path.startswith(static_root) and os.path.isfile(target_path):
          return FileResponse(target_path)
          
      index_file = os.path.join(static_root, "index.html")
      if os.path.isfile(index_file):
          return FileResponse(index_file)
      raise HTTPException(status_code=404, detail="Dashboard UI not built")
  ```

#### 2.3.2 Path Traversal in Face Photo Upload
* **File & Lines**: `argus/dashboard/backend/routes/faces.py:81-86`
* **Vulnerability Description**:
  ```python
  file_path = os.path.join(temp_dir, img.filename or f"{name}_{len(saved_files)}.jpg")
  with open(file_path, "wb") as f:
      shutil.copyfileobj(img.file, f)
  ```
  The user-controlled `img.filename` from the `multipart/form-data` request header is passed directly to `os.path.join`. An attacker supplying a filename like `../../../../tmp/malicious.sh` writes arbitrary files outside `temp_dir`.
* **Severity**: **HIGH (CVSS: 8.6)** — CWE-22: Path Traversal.
* **Remediation Blueprint**:
  Sanitize uploaded filenames using `os.path.basename(img.filename)` or generate random UUID filenames: `f"{uuid.uuid4().hex}.jpg"`.

#### 2.3.3 Unauthenticated Server-Side Request Forgery (SSRF) in `/api/setup/test`
* **File & Lines**: `argus/dashboard/backend/routes/setup.py:334-391`
* **Vulnerability Description**:
  The `/api/setup/test` endpoint is unauthenticated and accepts arbitrary URLs and hostnames:
  - For `kind == "ollama"`: executes `urllib.request.urlopen(f"{host}/api/tags")`
  - For `kind == "database"`: executes `create_async_engine(url)`
  - For `kind == "kafka"`: executes `AIOKafkaAdminClient(bootstrap_servers=servers)`
* **Threat Model & Attack Vector**: An external attacker sends requests to probe internal private subnets (`192.168.1.0/24`), query cloud metadata services (`http://169.254.169.254/latest/meta-data`), or interact with internal redis/database ports.
* **Severity**: **HIGH (CVSS: 8.2)** — CWE-918: Server-Side Request Forgery.
* **Remediation Blueprint**:
  Restrict `/api/setup/test` to authenticated sessions or localhost requests during initial setup; validate hostnames against an internal IP blocklist (preventing `169.254.169.254` and loopbacks unless explicitly enabled in dev mode).

#### 2.3.4 Unprotected Setup Wizard Hijacking
* **File & Lines**: `argus/dashboard/backend/routes/setup.py:183-191, 304-312`
* **Vulnerability Description**: On initial boot prior to running the setup wizard, `/api/setup/complete` and `/api/setup/users` are publicly exposed without an initial installation token. Any party scanning the network can submit admin credentials and establish control of the system.
* **Severity**: **HIGH (CVSS: 8.1)** — CWE-306: Missing Authentication.
* **Remediation Blueprint**: Require an ephemeral bootstrap token generated and printed to the terminal console at first startup (`argus-bootstrap-token`).

#### 2.3.5 Plaintext Camera Password Leakage in RTSP URLs
* **File & Lines**: `argus/dashboard/backend/routes/cameras.py:31-38`
* **Vulnerability Description**:
  `CameraStatus.rtsp_url` returns the raw stored RTSP connection string (`rtsp://admin:CameraPassword@192.168.1.100:554/stream`). Camera hardware credentials are leaked to all dashboard users.
* **Severity**: **MEDIUM (CVSS: 6.5)** — CWE-200: Exposure of Sensitive Information.
* **Remediation Blueprint**:
  Redact camera credentials before returning API responses: `rtsp://***:***@192.168.1.100:554/stream`.

#### 2.3.6 Destructive Secret Overwrite Bug in `PUT /api/settings`
* **File & Lines**: `argus/dashboard/backend/routes/settings.py:16-43, 46-66`
* **Vulnerability Description**:
  1. `GET /api/settings` masks sensitive fields by replacing values with literal `"********"`.
  2. When the user modifies settings on the frontend and clicks "Save Changes", the frontend sends the complete settings object back, including the `"********"` strings.
  3. `PUT /api/settings` blindly dumps the dictionary into `config/config.yaml`.
  4. Real API tokens, bot tokens, and database passwords are permanently overwritten with literal `"********"` strings, corrupting system configuration and breaking external integrations.
* **Severity**: **HIGH (CVSS: 7.5)** — Data integrity loss and denial of service.
* **Remediation Blueprint**:
  Implement the Safe Secret Preservation pattern: if an incoming secret value is `None`, empty, or matches `"********"`, retain the currently configured secret without overwriting.

---

## 3. UI/UX Flaws & Frontend Deficiencies

### 3.1 Complete Mock & Dummy Data Catalog (17 States)

The frontend audit identified 17 distinct mock, dummy, or hardcoded prototype states across the React application:

| # | Component / File | Line(s) | Observed Mock Implementation | Impact & Required Production Fix |
|---|---|---|---|---|
| 1 | `src/components/pages/EventDetail.tsx` | 18, 23-26, 31-36, 40, 42-44 | 100% hardcoded dummy data: `🚨 CRITICAL`, dummy thumbnail, `<ClipPlayer src={null} />`, fake intruder description (`"Unknown individual lingering..."`), fake confidence (`94%`), dummy buttons without click handlers. | Replace with `useEventDetail(id)` hook fetching `/api/events/{id}`, dynamically rendering real camera, real LLM analysis, playable MP4 clip, and functional "Enroll Face" / "False Positive" actions. |
| 2 | `src/components/shell/Sidebar.tsx` | 10 | Hardcoded badge: `badge: 3`. | Connect badge count to real-time unread/suspicious event count via `useLiveEvents` or `/api/events/stats`. |
| 3 | `src/components/shell/Sidebar.tsx` | 47-49 | Hardcoded status indicator: `bg-success pulse-online` and `"LIVE"`. | Derive status dynamically from WebSocket connection state (`connected ? 'LIVE' : 'DISCONNECTED'`). |
| 4 | `src/components/shell/Sidebar.tsx` | 85-88 | "Lock Dashboard" button has no `onClick` handler. | Wire button to trigger `/api/auth/logout`, clear session tokens, and redirect to `/login`. |
| 5 | `src/components/shell/Header.tsx` | 25-27 | Hardcoded threat level: `[●●●●○] ELEVATED`. | Calculate threat level dynamically based on rolling 1-hour critical alerts count (LOW, ELEVATED, HIGH, CRITICAL). |
| 6 | `src/components/shell/Header.tsx` | 31 | Notification bell permanently displays red pulsing dot with no drawer or dropdown. | Implement an interactive Notification Drawer listing recent critical events with a "Clear All" action. |
| 7 | `src/components/shell/Header.tsx` | 34-36 | Theme toggle button (`<Moon />`) has no `onClick` handler. | Implement a responsive `ThemeProvider` context and toggle between dark and light themes with localStorage persistence. |
| 8 | `src/components/shell/Header.tsx` | 38-40 | Hardcoded user avatar initials: `"AD"`. | Fetch current user session from `/api/auth/me` and display real username initials and role badge. |
| 9 | `src/components/shell/CommandPalette.tsx` | 38-41 | Mock search results: non-clickable text `"Navigate to Settings"`, `"Search events for {query}"`. | Index routes, cameras, face profiles, and events in an interactive `cmdk` palette supporting keyboard navigation and instant route execution. |
| 10 | `src/components/pages/Overview.tsx` | 30-34 | Fake CSS severity bars with static heights (`60%`, `30%`, `10%`). | Fetch real rolling 24-hour event aggregation from `/api/events/stats` and render dynamic SVG/CSS severity distributions. |
| 11 | `src/components/pages/SystemHealth.tsx` | 38-51 | Hardcoded Kafka telemetry: `CONNECTED`, `12 msg/s`, `0 msgs lag`. | Connect to real telemetry from `/api/system/stats`; if Kafka is disabled, display a clean "Internal EventBus Mode (Kafka Inactive)" badge. |
| 12 | `src/components/pages/SettingsPage.tsx` | 163-167 | Detection and Kafka tabs render stub message: `"Configure in config.yaml directly"`. | Implement complete UI configuration panels for YOLOv8 (model, conf, classes, device) and Kafka/EventBus parameters. |
| 13 | `src/components/pages/Faces.tsx` | 35 | "Enroll New Face" button has no `onClick` handler. | Implement an enrollment dialog modal allowing user to name a profile, upload multiple images, and preview face detections. |
| 14 | `src/components/pages/Faces.tsx` | 61-66 | "Unknown Regulars" dropzone has no drop handlers or file inputs. | Wire dropzone to AutoLearner candidate review API (`/api/faces/unknown`) allowing users to review and approve detected strangers. |
| 15 | `src/components/ui/AlertFeed.tsx` | 14 | Hardcoded timestamp: `"Just now"` on every alert. | Parse `ev.created_at` or `ev.triggered_at` and render real dynamic relative times (`date-fns` or `Intl.RelativeTimeFormat`). |
| 16 | `src/hooks/useWebSocket.ts` | 1-3 | 3-line dummy stub: `return { connected: true, reconnectCount: 0 };`. | Replace with a production hook featuring exponential backoff reconnection, heartbeat monitoring, ticket renewal, and clean unmount. |
| 17 | `src/api/*.ts` (`cameras`, `events`, `faces`, `system`) | 1 | All primary API helper modules are empty dummy stubs: `export function useCameras() {}`. | Implement fully typed, React-friendly API client functions wrapping `apiFetch`. |

---

### 3.2 White Screen Crashes & Missing Error Boundaries
* **Deficiency**: The React application lacks React Error Boundaries. Any unhandled runtime error—such as `TypeError: Cannot read properties of undefined` in `Events.tsx` or a malformed WebSocket payload—unmounts the entire React component tree, presenting the user with an unrecoverable blank white screen.
* **Remediation Blueprint**:
  Implement a root-level and per-module `ErrorBoundary` component styled with Argus security design tokens:
  ```tsx
  import React, { Component, ErrorInfo, ReactNode } from 'react';
  import { AlertTriangle, RefreshCw } from 'lucide-react';

  interface Props { children: ReactNode; fallbackTitle?: string; }
  interface State { hasError: boolean; error: Error | null; }

  export class ErrorBoundary extends Component<Props, State> {
    public state: State = { hasError: false, error: null };

    public static getDerivedStateFromError(error: Error): State {
      return { hasError: true, error };
    }

    public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
      console.error("Dashboard Module Crash:", error, errorInfo);
    }

    public render() {
      if (this.state.hasError) {
        return (
          <div className="flex flex-col items-center justify-center min-h-[400px] p-8 bg-card rounded-xl border border-destructive/30 text-center">
            <AlertTriangle className="w-12 h-12 text-destructive mb-4 animate-pulse" />
            <h3 className="text-lg font-bold text-foreground">Module Rendering Interrupted</h3>
            <p className="text-sm text-muted-foreground mt-1 max-w-md">
              {this.state.error?.message || "An unexpected UI error occurred while rendering this module."}
            </p>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="mt-6 flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 text-sm font-medium transition-colors"
            >
              <RefreshCw className="w-4 h-4" /> Reset Module
            </button>
          </div>
        );
      }
      return this.props.children;
    }
  }
  ```

---

### 3.3 Dark/Light Mode FOUC & Theme Engine
* **Deficiency**:
  1. `index.html` line 2 declares `<html lang="en">` without `class="dark"`.
  2. `App.tsx` line 82 runs `useEffect(() => { document.documentElement.classList.add('dark'); }, []);`, which executes only after JavaScript bundles load, parse, and initialize.
  3. On systems with dark theme preferences, users experience a blinding white Flash of Unstyled Content (FOUC).
  4. The `<Moon>` icon in `Header.tsx` line 34 is inert.
* **Remediation Blueprint**:
  1. Add `class="dark"` immediately to `<html lang="en" class="dark">` in `index.html`.
  2. Inject an inline pre-render script in `<head>` to detect stored theme preferences or `prefers-color-scheme`:
     ```html
     <script>
       (function() {
         const theme = localStorage.getItem('argus_theme') || 
           (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
         document.documentElement.classList.toggle('dark', theme === 'dark');
       })();
     </script>
     ```
  3. Implement a reactive `ThemeProvider` and hook it to the Header toggle button.

---

### 3.4 Missing Loading Skeletons & Empty States
* **Deficiencies**:
  1. `src/components/ui/LoadingSkeleton.tsx` exists in the repository but has **0 usages**.
  2. Pages render raw, unstyled text: `<div className="p-6">Loading...</div>` (`Overview.tsx:12`, `SystemHealth.tsx:23`, `SettingsPage.tsx:47`).
  3. `LiveView.tsx` has no loading state: while cameras are loading, the empty array triggers `"No cameras configured"` for 300ms, causing an abrupt layout jump.
  4. `AlertFeed.tsx` collapses to a 0px invisible div when empty.
* **Remediation Blueprint**:
  Implement domain-specific skeleton loaders (`CameraGridSkeleton`, `StatCardSkeleton`, `TableSkeleton`) and rich security empty states (e.g., "Shield Check: All systems nominal. No incidents detected in the last 24 hours.").

---

### 3.5 Mobile & Tablet Responsive Layout Breakdowns
* **Deficiencies**:
  1. **Fixed Sidebar**: `Sidebar.tsx:37` specifies `w-[260px] h-full ... shrink-0`. On mobile screens (<768px), the sidebar takes up 70–80% of the screen width and cannot be collapsed.
  2. **Unused Mobile Icons**: `Header.tsx` imports `Menu` and `X` from `lucide-react`, but no mobile hamburger toggle exists.
  3. **Settings Squeezing**: `SettingsPage.tsx:65` uses a fixed `w-48` left navigation, reducing the settings form to ~150px on smartphones.
  4. **Tablet Camera Grid Collapse**: `LiveView.tsx:27` defines `grid-cols-1 lg:grid-cols-2 xl:grid-cols-3`. On tablet screens (768px–1023px), the layout collapses to a single column, preventing security operators from viewing multiple cameras simultaneously.
  5. **Viewport Scrolling Breakdown**: `App.tsx:50` applies `w-screen h-screen overflow-hidden`, breaking touch scrolling and virtual keyboards on iOS and Android devices.
* **Remediation Blueprint**:
  - Implement a responsive sidebar drawer using `Sheet` or an off-canvas drawer controlled by `isOpen` state.
  - Enable 2-column camera layouts on tablets (`md:grid-cols-2`).
  - Convert Settings tab navigation to a horizontal scrollable tab bar on screens `<768px`.

---

### 3.6 Video Streaming UX & Player Limitations
* **Deficiencies**:
  1. **Bandwidth Inefficiency**: `LiveView.tsx` displays video via `<img>` tags pointing to an MJPEG stream that reads static JPEG files from disk at up to 10 FPS.
  2. **Chromium Memory Leaks**: Long-running multipart MJPEG streams in `<img>` tags leak memory in Blink/Chromium renderers over extended multi-hour sessions.
  3. **Absence of Operator Controls**: No digital zoom, no pan, no per-camera fullscreen toggle, no manual snapshot capture, no aspect ratio toggle (16:9, 4:3, Fill), and no stream bitrate/FPS diagnostics.
  4. **Fragile Stream Error Recovery**: On error, `LiveView.tsx` hides the `<img>` permanently (`display = 'none'`) with no retry timer or error badge.
  5. **Missing Bounding Box Overlay**: Real-time YOLO detections and track IDs cannot be overlaid on live feeds.
* **Remediation Blueprint**:
  Replace raw `<img>` streams with a specialized `CameraMonitor` component featuring an overlay `<canvas>` for YOLO bounding box rendering, digital zoom/pan controls, fullscreen API triggers, and automatic reconnect backoff.

---

## 4. Bugs & Runtime Failures

### 4.1 Fatal Startup Crashes

#### 4.1.1 Missing `secrets` Module Import in `auth.py`
* **File & Lines**: `argus/dashboard/backend/auth.py:18`
* **Root Cause**: `JWT_SECRET = os.environ.get("ARGUS_JWT_SECRET", secrets.token_hex(32))`. When `ARGUS_JWT_SECRET` is not set, `secrets.token_hex(32)` is evaluated at import time, raising `NameError: name 'secrets' is not defined`.
* **Fix**: Add `import secrets` to module imports.

#### 4.1.2 Argument Count Mismatch in `get_auth_dependency()` Across 4 Routers
* **Definition**: `argus/dashboard/backend/auth.py:89-90`:
  ```python
  def get_auth_dependency():
      def dependency(request: Request): ...
  ```
* **Faulty Router Calls**:
  - `routes/events.py:16`: `dependencies=[Depends(get_auth_dependency(settings))]`
  - `routes/faces.py:19`: `dependencies=[Depends(get_auth_dependency(settings))]`
  - `routes/settings.py:14`: `dependencies=[Depends(get_auth_dependency(settings))]`
  - `routes/system.py:22`: `dependencies=[Depends(get_auth_dependency(settings))]`
* **Root Cause**: `get_auth_dependency()` accepts 0 positional parameters, but 4 routers pass `settings`. When `app.py` imports these routers, Python raises `TypeError: get_auth_dependency() takes 0 positional arguments but 1 was given`, crashing the server before route registration.
* **Fix**: Remove `settings` argument from all router declarations: `dependencies=[Depends(get_auth_dependency())]`.

---

### 4.2 Fatal Login Lockout
* **File & Lines**: `argus/dashboard/backend/routes/setup.py:63-66, 278-284` vs `auth.py:33-36`
* **Root Cause**:
  `setup.py` persists user credentials formatted as:
  ```json
  {
    "admin": {
      "password_hash": "pbkdf2:sha256:260000:salt_hex:dk_hex",
      "role": "admin"
    }
  }
  ```
  `auth.py` attempts to read:
  ```python
  salt = bytes.fromhex(stored["salt"])
  key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
  return key.hex() == stored["hash"]
  ```
  Accessing `stored["salt"]` raises `KeyError: 'salt'`, returning HTTP 500 on every login attempt.
* **Fix**: Align the hash generation and verification functions to parse the standardized `pbkdf2:sha256:iterations:salt:hash` string or store explicit fields (`salt`, `hash`, `iterations`).

---

### 4.3 Frontend Fatal Crash in Events Page
* **File & Lines**: `frontend/src/components/pages/Events.tsx:13-16, 42` vs `backend/routes/events.py:25`
* **Root Cause**:
  The backend endpoint `GET /api/events` returns a JSON array: `list[EventSummary]`.
  The frontend caller expects an object:
  ```typescript
  apiFetch<{items: EventSummary[]}>('/api/events')
    .then(res => setEvents(res.items))
  ```
  `res.items` evaluates to `undefined`. `setEvents(undefined)` sets state to undefined. On line 42, `events.length === 0` throws:
  `TypeError: Cannot read properties of undefined (reading 'length')`. Because no Error Boundary wraps the page, the application crashes to a white screen.
* **Fix**: Update `Events.tsx` to handle array responses directly:
  ```typescript
  apiFetch<EventSummary[]>('/api/events')
    .then(res => setEvents(Array.isArray(res) ? res : (res as any)?.items || []))
    .catch(() => setEvents([]));
  ```

---

### 4.4 Infinite 401 Redirect Loop & Orphaned Route
* **File & Lines**: `frontend/src/api/client.ts:10-13` and `frontend/src/App.tsx:56-64`
* **Root Cause**:
  1. `client.ts` intercepts HTTP 401 responses and triggers `window.location.href = '/login'`.
  2. `App.tsx` routes include `/`, `/live`, `/events`, `/faces`, `/system`, `/settings`, and `* -> Navigate to="/"`.
  3. Route `/login` is **not registered** in `App.tsx`.
  4. When redirected to `/login`, the router matches `*` and redirects to `/`. The dashboard mounts, executes API calls, receives 401, redirects to `/login`, and enters an infinite browser refresh loop.
  5. `frontend/src/components/pages/Login.tsx` exists on disk but is orphaned (never imported).
* **Fix**: Register `<Route path="/login" element={<Login />} />` in `App.tsx`.

---

### 4.5 WebSocket Memory Leaks & Schema Desynchronization

#### 4.5.1 React 19 StrictMode Connection Leak
* **File & Lines**: `frontend/src/hooks/useLiveEvents.ts:9-38` and `useLiveStats.ts:9-37`
* **Root Cause**: In React 19 development mode, StrictMode mounts, unmounts, and remounts components. The cleanup function runs synchronously while the async `apiFetch('/api/auth/ticket')` promise is pending. At cleanup time, `ws` is undefined. When the promise resolves, WebSocket connections are established without active component references, leaking open sockets.
* **Fix**: Use an `AbortController` and an active mounting flag inside the hook to abort socket creation if unmounted before ticket acquisition.

#### 4.5.2 Alert Payload Schema Mismatch
* **Backend Model (`backend/models.py:60-67`)**:
  `AlertEventWS`: `id`, `camera_name`, `severity`, `is_suspicious`, `message`, `thumbnail_path`, `created_at`.
* **Frontend Interface (`frontend/src/types/index.ts:54-66`)**:
  `LiveEvent`: `event_id`, `camera`, `llm_description`, `triggered_at`, `confidence`.
* **Impact**: Field names disagree (`id` vs `event_id`, `camera_name` vs `camera`, `message` vs `llm_description`, `created_at` vs `triggered_at`). `AlertFeed.tsx` displays blank camera names, missing descriptions, and duplicate `undefined` React keys.
* **Fix**: Unify the schema definitions across backend Pydantic models and frontend TypeScript interfaces.

---

### 4.6 Synchronous Event Loop Blocking Traps

#### 4.6.1 Synchronous Directory Globbing in MJPEG Stream
* **File & Lines**: `backend/routes/cameras.py:52-75`
* **Root Cause**: `glob.glob(search_pattern)` executes a synchronous filesystem scan inside an async generator running every 100ms per connected viewer. In directories with thousands of images, `glob.glob` blocks the asyncio event loop for 50–200ms, freezing all incoming API requests and WebSocket broadcasts.
* **Fix**: Replace disk polling with an in-memory frame buffer updated directly by `StreamWorker`.

#### 4.6.2 Synchronous Subprocess Execution (`nvidia-smi`)
* **File & Lines**: `backend/routes/system.py:55-66`
* **Root Cause**: `subprocess.run(["nvidia-smi", ...])` is executed synchronously on the event loop in `GET /api/system/stats`, blocking for 50–150ms per request.
* **Fix**: Offload to `asyncio.to_thread(subprocess.run, ...)` or use `asyncio.create_subprocess_exec`.

#### 4.6.3 Synchronous Network Calls in Setup Wizard
* **File & Lines**: `backend/routes/setup.py:359, 373`
* **Root Cause**: `urllib.request.urlopen` is invoked directly inside `async def test_connection()`, freezing the server for up to 8 seconds if target endpoints time out.
* **Fix**: Use `httpx.AsyncClient` with non-blocking async requests.

#### 4.6.4 Synchronous Disk Reads in REST Endpoints
* **File & Lines**: `routes/cameras.py:48`, `routes/faces.py:84`, `routes/settings.py:52,65`, `auth.py:30`
* **Root Cause**: Synchronous `open()` and YAML/JSON serialization occur directly on the asyncio event loop.
* **Fix**: Wrap blocking disk I/O in `asyncio.to_thread` or use `aiofiles`.

#### 4.6.5 Un-Awaited Lifespan Tasks on Shutdown
* **File & Lines**: `backend/app.py:50-51`
* **Root Cause**: Background tasks `task1` and `task2` are cancelled but never awaited (`task1.cancel(); task2.cancel()`), triggering unhandled `CancelledError` exceptions during Uvicorn shutdown.
* **Fix**: `await asyncio.gather(task1, task2, return_exceptions=True)`.

---

### 4.7 Broken Stubs & Missing Media Endpoints

#### 4.7.1 Face Enrollment Stub Deletes Uploaded Photos
* **File & Lines**: `backend/routes/faces.py:77-93`
* **Root Cause**: `enroll_face` writes images to a temporary directory, returns a dummy `profile_id: 0`, and then in `finally:` immediately calls `shutil.rmtree(temp_dir)`. It never invokes InsightFace, never generates embeddings, never stores records in SQLite, and never updates FAISS.
* **Fix**: Connect `POST /api/faces/enroll` to the real `FaceRecognizer` thread pool and FAISS index.

#### 4.7.2 FAISS Vector Leak on Profile Deletion
* **File & Lines**: `backend/routes/faces.py:65-70`
* **Root Cause**: `DELETE /api/faces/{profile_id}` deletes the profile from SQLite but does not modify `EmbeddingDB`. FAISS continues to match incoming camera frames against the deleted profile ID.
* **Fix**: Implement an index rebuild or mapped index removal in `EmbeddingDB`.

#### 4.7.3 Missing Media Endpoints
* **Deficiency**:
  - `Faces.tsx:48` requests `/api/faces/img/{face.id}` — endpoint does not exist.
  - `EventDetail.tsx` requires `/api/events/{id}/clip` and `/api/events/{id}/thumbnail` — endpoints do not exist.
  - `app.py` mounts `/assets` but does not mount or serve `thumbnails_path` or `recordings_path`.
* **Fix**: Implement dedicated media streaming endpoints with path sanitization and HTTP 206 byte-range support.

#### 4.7.4 Setup Directory Path Calculation Bug
* **File & Lines**: `backend/routes/setup.py:28-32`
* **Root Cause**: `_PROJECT_ROOT = Path(__file__).resolve().parents[5]`. Resolving 5 parent directories from `routes/setup.py` points to `/home/ujjwal/homelab` instead of the Argus project root (`parents[4]`), causing `config.yaml` and `.dashboard_users.json` to be written outside the repository.
* **Fix**: Update index to `parents[4]`.

---

## 5. Missing Configurations & Feature Gaps

### 5.1 Camera Management & RTSP Controls
1. **Missing CRUD API Endpoints**: The backend lacks endpoints to add (`POST /api/cameras`), edit (`PUT /api/cameras/{name}`), delete (`DELETE /api/cameras/{name}`), or probe streams (`POST /api/cameras/test-stream`).
2. **Missing RTSP Transport Knobs**: `rtsp_transport: tcp` is hardcoded in `argus/core/stream.py:34-40`. Cameras requiring UDP, RTP over UDP, or custom socket timeouts (`stimeout`) cannot be configured.
3. **Sub-Stream Support**: High-resolution streams (4K/1080p) are expensive to decode continuously for live UI preview. A secondary low-resolution RTSP sub-stream URL (`rtsp_sub_url`) is required for live monitoring, while the main stream is used for recording.
4. **Polygon Detection Zones**: `CameraConfig` does not support polygon exclusion/inclusion zones (`zones: list[list[list[int]]]`). Motion detection cannot be masked to ignore trees, roads, or neighbor properties.
5. **OpenCV MOG2 Sensitivity Parameters**: `history`, `var_threshold`, and `detect_shadows` in `argus/core/motion.py` are hardcoded to defaults and cannot be tuned from the dashboard.

---

### 5.2 Storage, Video Recording & RAM Memory Buffering
1. **RAM Memory Budget & Ceiling**: Uncompressed BGR24 frames at 1080p consume ~6.22 MB/frame. At 15 FPS for 10 seconds, a single camera buffer occupies ~933 MB of RAM. Four cameras consume ~3.7 GB of host memory. `StorageConfig` lacks memory budget ceilings, buffer compression options, or auto-downscaling.
2. **Missing Pre/Post Buffer Settings**: `pre_buffer_seconds` and `post_event_seconds` are missing from the dashboard UI.
3. **Disk Quota & Emergency Pruning**: Retention sweeps run on a hardcoded 24-hour interval (`argus/storage/local.py:90-95`). There is no disk quota percentage setting (e.g. 85% max utilization) to trigger emergency pruning when disk space runs low.
4. **Storage Path Misalignment**: `StorageConfig.local_path = "./data/clips"` conflicts with `Settings.recordings_path = "argus/data/recordings"`. The dashboard cannot configure or reconcile these destinations.

---

### 5.3 AI Vision & LLM Intelligence Controls
1. **Empty Detection Tab**: `SettingsPage.tsx` lines 163-167 displays a placeholder message for Detection. None of YOLOv8's settings (`model`, `confidence`, `classes`, `device`) can be configured.
2. **Class Names vs Integer Bug**: `config.example.yaml` specifies `classes: [person]` (strings), but `DetectionConfig.classes` expects `list[int]`. Supplying string class names causes validation crashes.
3. **LLM Provider Controls**: `LLMConfig` supports `ollama`, `openai`, `anthropic`, `gemini`, and `disabled`. The dashboard UI lacks fields for Ollama host endpoint (`llm.ollama.host`), API keys, `scene_prompt` customization, and `filter_by_suspicion`.
4. **Laya 421M Decision Gate**: Settings for `suspicion_threshold` and `urgency_threshold` are entirely absent from the UI.
5. **AutoLearner Candidate Review**: `UnknownFaceTracker` clusters unknown faces, but there are no backend endpoints or frontend interfaces to review, label, approve, or dismiss discovered candidates.

---

### 5.4 Alerts, Bot Integrations & Two-Way Callbacks
1. **Discord Settings Omission**: Discord bot token, channel ID, and guild ID cannot be configured from the UI.
2. **Telegram Credentials Omission**: The dashboard only exposes an "Enable Telegram" checkbox; `bot_token` and `chat_id` cannot be configured.
3. **Quiet Hours Scheduling**: `QuietHoursConfig` (`start`, `end`, `override_on_suspicious`, `action: hold | drop`) is missing from the UI.
4. **Rate Limiting & Cooldown Knobs**: Cooldown intervals and rate limits cannot be adjusted from the dashboard.
5. **Broken Two-Way Bot Callbacks**: In `argus/__main__.py:254`, `AlertManager` is started without a `callback_handler`, disabling interactive Telegram/Discord button actions ("Learn Face", "Mark False Positive").

---

### 5.5 Configuration Persistence, Cache & Zero-Downtime Hot-Reload
1. **Settings Cache Stagnation**: `get_settings()` uses `@functools.lru_cache(maxsize=1)`. Updating `config.yaml` via `PUT /api/settings` does not call `get_settings.cache_clear()`, leaving the in-memory settings stale.
2. **Safe Secret Preservation**: Masked secrets (`"********"`) sent by the frontend overwrite real credentials on disk.
3. **Zero Hot-Reload Architecture**: Active workers (`StreamWorker`, `EventOrchestrator`, `AlertManager`) do not reload settings dynamically.
4. **Destructive System Restart**: `routes/system.py:restart_system` uses `os.execv` across threads, risking process corruption, socket abandonment, and uncommitted SQLite transactions.

---

## 6. Concrete Premium-Grade Architectural Solutions & Phased Implementation Roadmap

### 6.1 Strictly Typed Configuration Schemas & Safe Secret Handling

Create `argus/dashboard/backend/schemas/settings.py` defining strict Pydantic schemas:

```python
from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, Field, SecretStr, field_validator

class CameraUpdateRequest(BaseModel):
    name: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    rtsp_url: str = Field(..., min_length=5)
    rtsp_sub_url: str | None = None
    transport: Literal["tcp", "udp"] = "tcp"
    stimeout_seconds: Annotated[int, Field(ge=1, le=30)] = 5
    fps: Annotated[int, Field(ge=1, le=60)] = 15
    resolution: list[int] = Field(default=[1920, 1080])
    pre_buffer_seconds: Annotated[int, Field(ge=1, le=30)] = 5
    post_event_seconds: Annotated[int, Field(ge=5, le=300)] = 30
    motion_threshold: Annotated[float, Field(ge=0.001, le=1.0)] = 0.005
    motion_history: Annotated[int, Field(ge=50, le=2000)] = 500
    motion_var_threshold: Annotated[float, Field(ge=4.0, le=64.0)] = 16.0
    motion_detect_shadows: bool = False
    zones: list[list[list[int]]] = Field(default_factory=list)
    disabled: bool = False

class DetectionUpdateRequest(BaseModel):
    model: str = Field(default="yolov8n.pt")
    confidence: Annotated[float, Field(ge=0.1, le=1.0)] = 0.60
    classes: list[str] = Field(default=["person"])
    device: Literal["auto", "cuda", "cpu", "mps"] = "auto"

    @field_validator("classes")
    @classmethod
    def validate_classes(cls, classes: list[str]) -> list[str]:
        valid = {"person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "bird", "cat", "dog"}
        for c in classes:
            if c.lower() not in valid:
                raise ValueError(f"Unsupported class: {c}")
        return [c.lower() for c in classes]

class LayaUpdateRequest(BaseModel):
    enabled: bool = True
    model_id: str = "convaiinnovations/laya-typed-decisions"
    suspicion_threshold: Annotated[float, Field(ge=0.1, le=1.0)] = 0.60
    urgency_threshold: Annotated[float, Field(ge=1.0, le=10.0)] = 6.0

class LLMUpdateRequest(BaseModel):
    provider: Literal["ollama", "openai", "anthropic", "gemini", "disabled"] = "ollama"
    model: str = "llava"
    ollama_host: str = "http://localhost:11434"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    timeout_seconds: Annotated[int, Field(ge=5, le=120)] = 30
    filter_by_suspicion: bool = False
    scene_prompt: str = Field(..., min_length=10)
    laya: LayaUpdateRequest = Field(default_factory=LayaUpdateRequest)

class QuietHoursUpdateRequest(BaseModel):
    enabled: bool = False
    start: str = Field(default="23:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(default="07:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    override_on_suspicious: bool = True
    action: Literal["hold", "drop"] = "hold"

class AlertsUpdateRequest(BaseModel):
    routing: Literal["telegram", "discord", "both"] = "both"
    cooldown_seconds: Annotated[int, Field(ge=0, le=3600)] = 60
    max_rate_per_second: Annotated[float, Field(gt=0.0, le=100.0)] = 30.0
    quiet_hours: QuietHoursUpdateRequest = Field(default_factory=QuietHoursUpdateRequest)
    telegram_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    discord_enabled: bool = False
    discord_bot_token: str | None = None
    discord_channel_id: str | None = None
    discord_guild_id: str | None = None

class StorageUpdateRequest(BaseModel):
    backend: Literal["local", "rclone"] = "local"
    local_path: str = "./data/clips"
    recordings_path: str = "argus/data/recordings"
    retention_days: Annotated[int, Field(ge=0, le=365)] = 30
    max_disk_usage_percent: Annotated[int, Field(ge=50, le=95)] = 85
    rclone_remote: str | None = None
    rclone_path: str | None = None

class FullSettingsUpdateRequest(BaseModel):
    cameras: list[CameraUpdateRequest]
    detection: DetectionUpdateRequest
    llm: LLMUpdateRequest
    alerts: AlertsUpdateRequest
    storage: StorageUpdateRequest
```

#### Safe Secret Preservation Pattern
In `argus/dashboard/backend/routes/settings.py`:
```python
def preserve_secret(new_val: str | None, current_secret: SecretStr | str | None) -> str | None:
    """Retains existing secret if new value is empty, None, or masked with asterisks."""
    if not new_val or new_val == "********":
        if isinstance(current_secret, SecretStr):
            return current_secret.get_secret_value()
        return current_secret
    return new_val
```

---

### 6.2 In-Memory Pub/Sub Event Bus (`DashboardEventBus`)

To eliminate the external Kafka dependency for live WebSocket alert delivery, implement a shared in-process `DashboardEventBus`:

```python
import asyncio
from typing import Set, Dict, Any

class DashboardEventBus:
    """Thread-safe, async in-process pub/sub event bus."""
    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers.discard(q)

    def publish_nowait(self, event: Dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest event to maintain low latency
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass

dashboard_bus = DashboardEventBus()
```

In `argus/pipeline/orchestrator.py`: when an event is persisted to SQLite, emit `dashboard_bus.publish_nowait(event.model_dump())`.
In `ws_kafka_bridge()` (`events_ws.py`): subscribe to `dashboard_bus.subscribe()` if Kafka is disabled, receiving live events immediately in real time.

---

### 6.3 Hardened Authentication, Single-Use Nonces & Bounded Sockets

1. **Unified Password Hashing**: PBKDF2-HMAC-SHA256 with 260,000 iterations:
   ```python
   def hash_password(password: str) -> dict:
       salt = secrets.token_hex(16)
       dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 260_000)
       return {"salt": salt, "hash": dk.hex(), "iterations": 260_000}

   def verify_password(password: str, stored: dict) -> bool:
       salt = bytes.fromhex(stored["salt"])
       iterations = stored.get("iterations", 260_000)
       dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
       return secrets.compare_digest(dk.hex(), stored["hash"])
   ```
2. **Ephemeral Single-Use Nonce Store**: As specified in Section 2.1.2.
3. **Bounded WebSocket Client Worker**:
   ```python
   class BoundedWSClient:
       def __init__(self, websocket: WebSocket):
           self.websocket = websocket
           self.queue = asyncio.Queue(maxsize=100)

       async def writer_loop(self):
           try:
               while True:
                   message = await self.queue.get()
                   await self.websocket.send_text(message)
           except Exception:
               pass
   ```

---

### 6.4 High-Performance Live Video Streaming & Canvas Bounding Box Engine

1. **In-Memory MJPEG Frame Distributor**:
   Attach an in-memory frame buffer to `StreamWorker`:
   ```python
   class FrameHub:
       def __init__(self):
           self._latest_jpeg: Dict[str, bytes] = {}
           self._events: Dict[str, asyncio.Event] = {}

       def update_frame(self, camera_name: str, frame_bgr: np.ndarray):
           _, encoded = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
           self._latest_jpeg[camera_name] = encoded.tobytes()
           if camera_name in self._events:
               self._events[camera_name].set()

       async def stream(self, camera_name: str):
           event = self._events.setdefault(camera_name, asyncio.Event())
           while True:
               await event.wait()
               event.clear()
               jpeg = self._latest_jpeg.get(camera_name)
               if jpeg:
                   yield (b"--frame\r\n"
                          b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
   ```
2. **React Canvas Bounding Box Overlay**:
   Render detections dynamically over camera frames in `CameraMonitor.tsx`:
   ```tsx
   function renderBoundingBoxes(
     canvas: HTMLCanvasElement,
     detections: Detection[],
     frameWidth: number,
     frameHeight: number
   ) {
     const ctx = canvas.getContext('2d');
     if (!ctx) return;
     ctx.clearRect(0, 0, canvas.width, canvas.height);
     const scaleX = canvas.width / frameWidth;
     const scaleY = canvas.height / frameHeight;

     for (const det of detections) {
       const [x1, y1, x2, y2] = det.box;
       ctx.strokeStyle = det.class_name === 'person' ? '#ef4444' : '#3b82f6';
       ctx.lineWidth = 2;
       ctx.strokeRect(x1 * scaleX, y1 * scaleY, (x2 - x1) * scaleX, (y2 - y1) * scaleY);
       
       ctx.fillStyle = ctx.strokeStyle;
       ctx.font = '12px sans-serif';
       ctx.fillText(`${det.class_name} ${(det.confidence * 100).toFixed(0)}%`, x1 * scaleX + 4, y1 * scaleY + 14);
     }
   }
   ```

---

### 6.5 End-to-End Face Enrollment & FAISS Vector Index Synchronization

1. **Enrollment Pipeline**:
   - `POST /api/faces/enroll`:
     1. Read uploaded images into memory buffers.
     2. Decode frames with `cv2.imdecode` in an executor thread.
     3. Extract 512-dim face embeddings via `FaceRecognizer`.
     4. Normalize and average embeddings across all uploaded sample images.
     5. Insert `FaceProfile` record into SQLite database session.
     6. Insert vector into `EmbeddingDB` using `embedding_db.add(profile_id, avg_embedding)`.
     7. Save thumbnail face crop to `data/faces/{profile_id}.jpg`.
2. **FAISS Vector Deletion**:
   - Update `EmbeddingDB` to support index rebuilding upon deletion:
     ```python
     def delete(self, profile_id: int) -> None:
         # Filter out target profile ID and rebuild index
         remaining = [(pid, vec) for pid, vec in self._store if pid != profile_id]
         self._index.reset()
         self._store.clear()
         for pid, vec in remaining:
             self.add(pid, vec)
     ```

---

### 6.6 AutoLearner Candidate Management Interface

Implement endpoints in `backend/routes/faces.py`:
- `GET /api/faces/unknown` — returns list of `UnknownFaceTracker` clusters (id, appearance_count, first_seen, last_seen, thumbnail_url).
- `POST /api/faces/unknown/{id}/enroll` — accepts `name: str`, creates official `FaceProfile`, adds embedding to FAISS, and removes from tracker.
- `POST /api/faces/unknown/{id}/ignore` — marks candidate as ignored (`is_ignored = True`).
- `DELETE /api/faces/unknown/{id}` — deletes candidate cluster and cached thumbnail.

---

### 6.7 Phased Implementation Roadmap

```
┌────────────────────────────────────────────────────────────────────────┐
│                        PHASED EXECUTION ROADMAP                        │
├────────────────────────────────────────────────────────────────────────┤
│ Phase 1: Boot & Security Hardening                                     │
│   ├── Fix NameError 'secrets' & router signature mismatches            │
│   ├── Unify PBKDF2 password hashing & fix login KeyError               │
│   ├── Patch SPA static file serving path traversal                     │
│   ├── Enforce authentication & nonces on /ws/stats and /ws/events      │
│   └── Implement Safe Secret Preservation in settings router            │
├────────────────────────────────────────────────────────────────────────┤
│ Phase 2: Core Contracts & Real-Time Event Bus                          │
│   ├── Implement in-memory DashboardEventBus for live alerts            │
│   ├── Harmonize AlertEventWS & LiveEvent schema definitions            │
│   ├── Wrap React application in security-themed Error Boundary         │
│   ├── Register /login route and implement AuthProvider                 │
│   └── Rebuild useWebSocket with exponential backoff & auto-reconnect   │
├────────────────────────────────────────────────────────────────────────┤
│ Phase 3: Configuration & Camera Management                             │
│   ├── Deploy strictly typed Pydantic update schemas                    │
│   ├── Implement Camera CRUD & RTSP stream probing endpoints            │
│   ├── Connect ConfigEventBus for zero-downtime worker reloads          │
│   ├── Expose RAM buffer budget & storage quota controls                │
│   └── Wire Telegram/Discord two-way callback handler in __main__.py    │
├────────────────────────────────────────────────────────────────────────┤
│ Phase 4: UI/UX & Video Monitoring Station                              │
│   ├── Replace 17 mock data views with dynamic API consumers            │
│   ├── Implement FrameHub in-memory MJPEG streaming                     │
│   ├── Deploy CameraMonitor with Canvas YOLO bounding box overlay       │
│   ├── Overhaul EventDetail with ClipPlayer & frame-stepping controls   │
│   ├── Eliminate theme FOUC & implement responsive mobile drawer        │
│   └── Build AutoLearner Candidate Review interface in Faces page       │
├────────────────────────────────────────────────────────────────────────┤
│ Phase 5: Verification & System Hardening                               │
│   ├── Pytest regression suite covering auth, routers, and schemas      │
│   ├── Playwright end-to-end testing of login, live view, and settings  │
│   ├── Security audit validation (SSRF, path traversal, auth bypass)    │
│   └── Concurrency stress testing under 50 concurrent WebSockets        │
└────────────────────────────────────────────────────────────────────────┘
```

#### Detailed Phase Breakdown

* **Phase 1: Boot & Security Hardening (Immediate)**
  - Add `import secrets` and persist `JWT_SECRET` in `backend/auth.py`.
  - Fix `get_auth_dependency()` calls in `events.py`, `faces.py`, `settings.py`, and `system.py`.
  - Harmonize `setup.py` and `auth.py` password hashing to PBKDF2-HMAC-SHA256 (260,000 iterations).
  - Fix `SecretStr` comparison in `auth.py:40` using `get_secret_value()`.
  - Fix SPA path traversal in `app.py:90-95` with strict `os.path.commonpath` / `startswith` validation.
  - Implement single-use nonces and authentication checks on `/ws/stats` and `/ws/events`.
  - Apply `preserve_secret()` in `routes/settings.py`.

* **Phase 2: Core Contracts & Real-Time Event Bus**
  - Implement `DashboardEventBus` and wire it into `pipeline/orchestrator.py` and `websocket/events_ws.py`.
  - Align `AlertEventWS` and `LiveEvent` schemas (`id`, `camera_name`, `severity`, `is_suspicious`, `message`, `thumbnail_path`, `created_at`).
  - Fix `Events.tsx` array parsing and prevent white screen crashes.
  - Register `/login` route in `App.tsx` and integrate `Login.tsx`.
  - Build resilient `useWebSocket` hook with exponential backoff and cleanup safeguards.
  - Introduce global and per-page `ErrorBoundary` components.

* **Phase 3: Configuration & Camera Management**
  - Implement `CameraUpdateRequest`, `DetectionUpdateRequest`, `LLMUpdateRequest`, `AlertsUpdateRequest`, and `StorageUpdateRequest` schemas.
  - Implement camera management endpoints (`POST`, `PUT`, `DELETE /api/cameras`) and `POST /api/cameras/test-stream`.
  - Add `rtsp_transport`, `stimeout`, `zones`, and OpenCV MOG2 sensitivity settings to `CameraConfig`.
  - Implement `ConfigEventBus` to notify running workers without `os.execv` restarts.
  - Add RAM buffer budgeting and disk quota emergency pruning to `StorageConfig`.
  - Wire two-way `callback_handler` into `AlertManager` in `argus/__main__.py`.

* **Phase 4: UI/UX & Video Monitoring Station**
  - Replace all 17 mock states with real API data flows.
  - Implement in-memory `FrameHub` connecting `StreamWorker` directly to the live view generator.
  - Build `CameraMonitor.tsx` with Canvas overlay for YOLO bounding boxes and digital zoom.
  - Enhance `EventDetail.tsx` and `ClipPlayer.tsx` with MP4 video streaming, frame stepping, and false-positive marking.
  - Inject `class="dark"` into `index.html` to eliminate FOUC, and wire the header theme switcher.
  - Implement collapsible mobile navigation drawer and responsive 2-column tablet camera grid.
  - Build the AutoLearner candidate review UI in `Faces.tsx`.

* **Phase 5: Verification & System Hardening**
  - Execute backend unit tests: `pytest tests/dashboard/` covering auth, schemas, and routes.
  - Verify zero blocking I/O on the asyncio event loop under concurrent load.
  - Verify all security vulnerabilities are mitigated via automated security scanning.
  - Run frontend linting and build checks: `npm run lint && npm run build`.

---
*End of Master Dashboard Architecture & Remediation Plan.*
