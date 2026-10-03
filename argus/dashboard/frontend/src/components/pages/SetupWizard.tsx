import React, { useState } from 'react';
import {
  Shield, Camera, Database, Brain, Bell, Key, CheckCircle,
  ChevronRight, ChevronLeft, Plus, Trash2, Eye, EyeOff,
  Loader2, AlertCircle, Wifi, WifiOff, TestTube
} from 'lucide-react';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface CameraEntry { name: string; rtsp_url: string; fps: number; post_event_seconds: number; }
interface LLMConfig { provider: string; model: string; ollama_host: string; laya_enabled: boolean; openai_api_key: string; anthropic_api_key: string; google_api_key: string; }
interface AlertsConfig { routing: string; telegram_enabled: boolean; telegram_bot_token: string; telegram_chat_id: string; discord_enabled: boolean; discord_bot_token: string; discord_channel_id: string; }
interface StorageConfig { backend: string; local_path: string; retention_days: number; rclone_remote: string; rclone_path: string; }
interface KafkaConfig { enabled: boolean; bootstrap_servers: string; }
interface Credentials { username: string; password: string; confirm_password: string; }

type TestState = 'idle' | 'testing' | 'ok' | 'fail';

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function StepIndicator({ steps, current }: { steps: string[]; current: number }) {
  return (
    <div className="flex items-center gap-0 mb-8">
      {steps.map((s, i) => (
        <React.Fragment key={s}>
          <div className="flex flex-col items-center gap-1">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all ${
              i < current ? 'bg-primary border-primary text-white' :
              i === current ? 'border-primary text-primary bg-primary/10' :
              'border-border text-muted-foreground'
            }`}>
              {i < current ? <CheckCircle className="w-4 h-4" /> : i + 1}
            </div>
            <span className={`text-[10px] font-medium hidden sm:block ${i === current ? 'text-primary' : 'text-muted-foreground'}`}>{s}</span>
          </div>
          {i < steps.length - 1 && (
            <div className={`flex-1 h-0.5 mx-1 transition-colors ${i < current ? 'bg-primary' : 'bg-border'}`} />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-semibold text-foreground">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Input({ ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full px-3 py-2.5 rounded-lg bg-muted/40 border border-border text-foreground text-sm outline-none
        focus:border-primary focus:ring-1 focus:ring-primary/30 transition-all placeholder:text-muted-foreground/50 ${props.className || ''}`}
    />
  );
}

function Select({ children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className="w-full px-3 py-2.5 rounded-lg bg-muted/40 border border-border text-foreground text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary/30 transition-all"
    >
      {children}
    </select>
  );
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex items-center gap-3 cursor-pointer select-none">
      <div
        onClick={() => onChange(!checked)}
        className={`relative w-10 h-5 rounded-full transition-colors ${checked ? 'bg-primary' : 'bg-muted'}`}
      >
        <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-5' : 'translate-x-0.5'}`} />
      </div>
      <span className="text-sm text-foreground">{label}</span>
    </label>
  );
}

function TestButton({ type, params, label }: { type: string; params: Record<string, string>; label: string }) {
  const [state, setState] = useState<TestState>('idle');
  const [msg, setMsg] = useState('');

  const run = async () => {
    setState('testing');
    try {
      const res = await fetch('/api/setup/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, params }),
      });
      const data = await res.json();
      setState(data.success ? 'ok' : 'fail');
      setMsg(data.message);
    } catch (e) {
      setState('fail');
      setMsg('Connection failed — server unreachable');
    }
  };

  return (
    <div className="flex flex-col gap-1.5 mt-1">
      <button
        type="button"
        onClick={run}
        disabled={state === 'testing'}
        className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold rounded-lg border border-border hover:bg-muted transition-colors disabled:opacity-60"
      >
        {state === 'testing' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <TestTube className="w-3.5 h-3.5" />}
        {state === 'testing' ? 'Testing...' : label}
        {state === 'ok' && <Wifi className="w-3.5 h-3.5 text-green-500" />}
        {state === 'fail' && <WifiOff className="w-3.5 h-3.5 text-red-500" />}
      </button>
      {msg && (
        <p className={`text-[11px] font-medium flex items-center gap-1 ${state === 'ok' ? 'text-green-500' : 'text-red-400'}`}>
          {state === 'ok' ? <CheckCircle className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
          {msg}
        </p>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Step pages
// ─────────────────────────────────────────────────────────────────────────────

function StepWelcome() {
  return (
    <div className="flex flex-col items-center text-center gap-6 py-6">
      <div className="w-20 h-20 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center">
        <Shield className="w-10 h-10 text-primary" />
      </div>
      <div>
        <h2 className="text-2xl font-bold text-foreground mb-2">Welcome to Argus</h2>
        <p className="text-muted-foreground max-w-md">
          AI-Powered self-hosted security system. This wizard will help you configure your cameras,
          AI models, notification channels, and dashboard credentials in a few steps.
        </p>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 w-full max-w-lg text-xs">
        {[
          { icon: Camera, label: 'Cameras', color: 'text-blue-400' },
          { icon: Brain, label: 'AI Models', color: 'text-purple-400' },
          { icon: Bell, label: 'Alerts', color: 'text-amber-400' },
          { icon: Key, label: 'Security', color: 'text-green-400' },
        ].map(({ icon: Icon, label, color }) => (
          <div key={label} className="flex flex-col items-center gap-2 p-3 rounded-xl border border-border bg-card">
            <Icon className={`w-5 h-5 ${color}`} />
            <span className="font-medium text-foreground">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StepCameras({ cameras, setCameras }: { cameras: CameraEntry[]; setCameras: React.Dispatch<React.SetStateAction<CameraEntry[]>> }) {
  const add = () => setCameras(c => [...c, { name: `camera_${c.length + 1}`, rtsp_url: '', fps: 15, post_event_seconds: 30 }]);
  const remove = (i: number) => setCameras(c => c.filter((_, idx) => idx !== i));
  const update = (i: number, k: keyof CameraEntry, v: string | number) =>
    setCameras(c => c.map((cam, idx) => idx === i ? { ...cam, [k]: v } : cam));

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-base font-bold text-foreground flex items-center gap-2 mb-1">
          <Camera className="w-4 h-4 text-primary" /> Camera Setup
        </h3>
        <p className="text-xs text-muted-foreground">Add your RTSP camera streams. You can add more later in Settings.</p>
      </div>
      <div className="flex flex-col gap-3 max-h-80 overflow-y-auto pr-1">
        {cameras.map((cam, i) => (
          <div key={i} className="p-4 rounded-xl border border-border bg-card/50 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-foreground uppercase tracking-wide">Camera {i + 1}</span>
              <button type="button" onClick={() => remove(i)} className="p-1 rounded text-muted-foreground hover:text-red-400 transition-colors">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Name">
                <Input value={cam.name} onChange={e => update(i, 'name', e.target.value)} placeholder="front_door" />
              </Field>
              <Field label="FPS">
                <Input type="number" min={1} max={30} value={cam.fps} onChange={e => update(i, 'fps', +e.target.value)} />
              </Field>
            </div>
            <Field label="RTSP URL" hint="rtsp://user:pass@192.168.1.x:554/stream">
              <Input value={cam.rtsp_url} onChange={e => update(i, 'rtsp_url', e.target.value)} placeholder="rtsp://admin:password@192.168.1.100:554/stream1" />
            </Field>
            <Field label="Post-event buffer (seconds)">
              <Input type="number" min={5} max={300} value={cam.post_event_seconds} onChange={e => update(i, 'post_event_seconds', +e.target.value)} />
            </Field>
          </div>
        ))}
        {cameras.length === 0 && (
          <div className="p-6 rounded-xl border-2 border-dashed border-border text-center text-muted-foreground text-sm">
            No cameras added yet. Click below to add your first camera.
          </div>
        )}
      </div>
      <button type="button" onClick={add} className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-primary/30 text-primary text-sm font-semibold hover:bg-primary/10 transition-colors">
        <Plus className="w-4 h-4" /> Add Camera
      </button>
    </div>
  );
}

function StepDatabase({ dbUrl, setDbUrl }: { dbUrl: string; setDbUrl: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-base font-bold text-foreground flex items-center gap-2 mb-1">
          <Database className="w-4 h-4 text-primary" /> Database
        </h3>
        <p className="text-xs text-muted-foreground">SQLite is perfect for single-server deployments. Use PostgreSQL for scale.</p>
      </div>
      <Field label="Database URL">
        <Input value={dbUrl} onChange={e => setDbUrl(e.target.value)} placeholder="sqlite+aiosqlite:///./data/argus.db" />
      </Field>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {[
          { label: 'SQLite (recommended)', url: 'sqlite+aiosqlite:///./data/argus.db' },
          { label: 'PostgreSQL', url: 'postgresql+asyncpg://user:pass@localhost/argus' },
        ].map(({ label, url }) => (
          <button key={label} type="button" onClick={() => setDbUrl(url)}
            className={`p-3 rounded-xl border text-left text-xs transition-all ${dbUrl === url ? 'border-primary bg-primary/5 text-primary' : 'border-border bg-card hover:border-primary/40 text-muted-foreground'}`}>
            <div className="font-semibold mb-0.5">{label}</div>
            <div className="font-mono text-[10px] truncate">{url}</div>
          </button>
        ))}
      </div>
      <TestButton type="database" params={{ url: dbUrl }} label="Test Connection" />
    </div>
  );
}

function StepLLM({ llm, setLlm }: { llm: LLMConfig; setLlm: React.Dispatch<React.SetStateAction<LLMConfig>> }) {
  const set = (k: keyof LLMConfig, v: string | boolean) => setLlm(l => ({ ...l, [k]: v }));
  const providers = ['ollama', 'openai', 'anthropic', 'gemini', 'disabled'];
  const defaultModels: Record<string, string> = { ollama: 'llava', openai: 'gpt-4o', anthropic: 'claude-3-5-sonnet-20241022', gemini: 'gemini-1.5-pro', disabled: '' };

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-base font-bold text-foreground flex items-center gap-2 mb-1">
          <Brain className="w-4 h-4 text-primary" /> AI Intelligence
        </h3>
        <p className="text-xs text-muted-foreground">Argus uses a two-brain system: fast Laya 421M for pre-screening, and a vision LLM for deep analysis.</p>
      </div>
      <Field label="Vision LLM Provider">
        <Select value={llm.provider} onChange={e => { set('provider', e.target.value); set('model', defaultModels[e.target.value] || ''); }}>
          {providers.map(p => <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>)}
        </Select>
      </Field>
      {llm.provider !== 'disabled' && (
        <Field label="Model">
          <Input value={llm.model} onChange={e => set('model', e.target.value)} placeholder={defaultModels[llm.provider]} />
        </Field>
      )}
      {llm.provider === 'ollama' && (
        <Field label="Ollama Host" hint="Run: ollama serve">
          <Input value={llm.ollama_host} onChange={e => set('ollama_host', e.target.value)} placeholder="http://localhost:11434" />
          <TestButton type="ollama" params={{ host: llm.ollama_host }} label="Test Ollama" />
        </Field>
      )}
      {llm.provider === 'openai' && (
        <Field label="OpenAI API Key">
          <Input type="password" value={llm.openai_api_key} onChange={e => set('openai_api_key', e.target.value)} placeholder="sk-..." />
        </Field>
      )}
      {llm.provider === 'anthropic' && (
        <Field label="Anthropic API Key">
          <Input type="password" value={llm.anthropic_api_key} onChange={e => set('anthropic_api_key', e.target.value)} placeholder="sk-ant-..." />
        </Field>
      )}
      {llm.provider === 'gemini' && (
        <Field label="Google API Key">
          <Input type="password" value={llm.google_api_key} onChange={e => set('google_api_key', e.target.value)} placeholder="AIza..." />
        </Field>
      )}
      <div className="p-4 rounded-xl border border-primary/20 bg-primary/5">
        <Toggle checked={llm.laya_enabled} onChange={v => set('laya_enabled', v)} label="Enable Laya 421M Decision Gate (recommended)" />
        <p className="text-[11px] text-muted-foreground mt-1.5 ml-13">
          Fast, fully local AI pre-filter. Eliminates ~80% of false positives before calling the LLM. Requires 421M model download on first run.
        </p>
      </div>
    </div>
  );
}

function StepAlerts({ alerts, setAlerts }: { alerts: AlertsConfig; setAlerts: React.Dispatch<React.SetStateAction<AlertsConfig>> }) {
  const set = (k: keyof AlertsConfig, v: string | boolean) => setAlerts(a => ({ ...a, [k]: v }));

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-base font-bold text-foreground flex items-center gap-2 mb-1">
          <Bell className="w-4 h-4 text-primary" /> Notifications
        </h3>
        <p className="text-xs text-muted-foreground">Receive interactive alerts with face photos and one-click identification. Skip if you prefer to configure later.</p>
      </div>
      <Field label="Routing">
        <Select value={alerts.routing} onChange={e => set('routing', e.target.value)}>
          <option value="telegram">Telegram only</option>
          <option value="discord">Discord only</option>
          <option value="both">Both Telegram + Discord</option>
          <option value="none">Skip for now</option>
        </Select>
      </Field>
      {(alerts.routing === 'telegram' || alerts.routing === 'both') && (
        <div className="p-4 rounded-xl border border-border bg-card/50 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-foreground">Telegram</span>
            <Toggle checked={alerts.telegram_enabled} onChange={v => set('telegram_enabled', v)} label="" />
          </div>
          {alerts.telegram_enabled && <>
            <Field label="Bot Token" hint="Create via @BotFather on Telegram">
              <Input type="password" value={alerts.telegram_bot_token} onChange={e => set('telegram_bot_token', e.target.value)} placeholder="1234567890:ABCDEF..." />
              <TestButton type="telegram" params={{ bot_token: alerts.telegram_bot_token }} label="Validate Bot" />
            </Field>
            <Field label="Chat ID" hint="Your personal Telegram user ID or group ID">
              <Input value={alerts.telegram_chat_id} onChange={e => set('telegram_chat_id', e.target.value)} placeholder="-1001234567890" />
            </Field>
          </>}
        </div>
      )}
      {(alerts.routing === 'discord' || alerts.routing === 'both') && (
        <div className="p-4 rounded-xl border border-border bg-card/50 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-foreground">Discord</span>
            <Toggle checked={alerts.discord_enabled} onChange={v => set('discord_enabled', v)} label="" />
          </div>
          {alerts.discord_enabled && <>
            <Field label="Bot Token">
              <Input type="password" value={alerts.discord_bot_token} onChange={e => set('discord_bot_token', e.target.value)} placeholder="MTI3..." />
            </Field>
            <Field label="Channel ID">
              <Input value={alerts.discord_channel_id} onChange={e => set('discord_channel_id', e.target.value)} placeholder="1234567890123456789" />
            </Field>
          </>}
        </div>
      )}
    </div>
  );
}

function StepCredentials({ creds, setCreds }: { creds: Credentials; setCreds: React.Dispatch<React.SetStateAction<Credentials>> }) {
  const set = (k: keyof Credentials, v: string) => setCreds(c => ({ ...c, [k]: v }));
  const [showPw, setShowPw] = useState(false);
  const strength = creds.password.length >= 12 ? 'strong' : creds.password.length >= 8 ? 'good' : 'weak';
  const match = creds.password && creds.confirm_password && creds.password === creds.confirm_password;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-base font-bold text-foreground flex items-center gap-2 mb-1">
          <Key className="w-4 h-4 text-primary" /> Dashboard Credentials
        </h3>
        <p className="text-xs text-muted-foreground">
          Create your admin account. The dashboard is protected — these credentials are required to log in.
          Passwords are stored as PBKDF2-SHA256 hashes, never in plain text.
        </p>
      </div>
      <Field label="Username">
        <Input value={creds.username} onChange={e => set('username', e.target.value)} placeholder="admin" autoComplete="username" />
      </Field>
      <Field label="Password" hint="Minimum 8 characters. Use 12+ for strong security.">
        <div className="relative">
          <Input
            type={showPw ? 'text' : 'password'}
            value={creds.password}
            onChange={e => set('password', e.target.value)}
            placeholder="••••••••••••"
            autoComplete="new-password"
          />
          <button type="button" onClick={() => setShowPw(p => !p)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
            {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
        {creds.password && (
          <div className="flex items-center gap-2 mt-1">
            <div className="flex-1 h-1 rounded-full bg-muted overflow-hidden">
              <div className={`h-full rounded-full transition-all ${strength === 'strong' ? 'w-full bg-green-500' : strength === 'good' ? 'w-2/3 bg-amber-400' : 'w-1/3 bg-red-400'}`} />
            </div>
            <span className={`text-[10px] font-semibold ${strength === 'strong' ? 'text-green-500' : strength === 'good' ? 'text-amber-400' : 'text-red-400'}`}>
              {strength.toUpperCase()}
            </span>
          </div>
        )}
      </Field>
      <Field label="Confirm Password">
        <Input
          type={showPw ? 'text' : 'password'}
          value={creds.confirm_password}
          onChange={e => set('confirm_password', e.target.value)}
          placeholder="••••••••••••"
          autoComplete="new-password"
        />
        {creds.confirm_password && (
          <p className={`text-[11px] font-medium flex items-center gap-1 ${match ? 'text-green-500' : 'text-red-400'}`}>
            {match ? <CheckCircle className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
            {match ? 'Passwords match' : 'Passwords do not match'}
          </p>
        )}
      </Field>
    </div>
  );
}

function StepReview({ cameras, dbUrl, llm, alerts, creds }: { cameras: CameraEntry[]; dbUrl: string; llm: LLMConfig; alerts: AlertsConfig; creds: Credentials }) {
  return (
    <div className="flex flex-col gap-4">
      <h3 className="text-base font-bold text-foreground flex items-center gap-2">
        <CheckCircle className="w-4 h-4 text-primary" /> Review & Launch
      </h3>
      <div className="space-y-2 text-xs">
        {[
          { label: 'Cameras', value: cameras.length > 0 ? `${cameras.length} configured (${cameras.map(c => c.name).join(', ')})` : '⚠️ None — add cameras in Settings later' },
          { label: 'Database', value: dbUrl || 'Not set' },
          { label: 'LLM Provider', value: `${llm.provider}${llm.model ? ` — ${llm.model}` : ''}` },
          { label: 'Laya Gate', value: llm.laya_enabled ? '✅ Enabled (fast AI pre-filter)' : '○ Disabled' },
          { label: 'Alerts', value: alerts.routing === 'none' ? 'Skipped' : `${alerts.routing} (${[alerts.telegram_enabled && 'Telegram', alerts.discord_enabled && 'Discord'].filter(Boolean).join('+') || 'not configured'})` },
          { label: 'Admin User', value: creds.username || 'Not set' },
        ].map(({ label, value }) => (
          <div key={label} className="flex items-start justify-between py-2 border-b border-border/40 last:border-0">
            <span className="font-semibold text-muted-foreground w-32 shrink-0">{label}</span>
            <span className="text-foreground text-right">{value}</span>
          </div>
        ))}
      </div>
      <div className="p-3 rounded-lg bg-primary/5 border border-primary/20 text-xs text-primary">
        Clicking <strong>Complete Setup</strong> will write <code>config/config.yaml</code> and <code>.env</code> to disk.
        Restart Argus to apply the full pipeline configuration.
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CreateUserWall — shown when config exists but no user created yet
// ─────────────────────────────────────────────────────────────────────────────

export function CreateUserWall({ onCreated }: { onCreated: () => void }) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) { setError('Passwords do not match'); return; }
    if (password.length < 8) { setError('Password must be at least 8 characters'); return; }
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/setup/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, confirm_password: confirm }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.detail || data.message || 'Failed');
      onCreated();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mx-auto mb-4">
            <Shield className="w-8 h-8 text-primary" />
          </div>
          <h1 className="text-xl font-bold text-foreground">Create Dashboard Account</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Argus is configured. Set your dashboard login credentials to continue.
          </p>
        </div>
        <form onSubmit={submit} className="bg-card border border-border rounded-2xl p-6 space-y-4">
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-xs font-medium">
              <AlertCircle className="w-4 h-4 shrink-0" /> {error}
            </div>
          )}
          <Field label="Username">
            <Input value={username} onChange={e => setUsername(e.target.value)} required autoFocus />
          </Field>
          <Field label="Password">
            <div className="relative">
              <Input type={showPw ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} required />
              <button type="button" onClick={() => setShowPw(p => !p)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </Field>
          <Field label="Confirm Password">
            <Input type={showPw ? 'text' : 'password'} value={confirm} onChange={e => setConfirm(e.target.value)} required />
          </Field>
          <button type="submit" disabled={loading}
            className="w-full py-2.5 rounded-xl bg-primary text-white font-bold text-sm flex items-center justify-center gap-2 hover:bg-primary/90 transition-colors disabled:opacity-60">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Key className="w-4 h-4" />}
            {loading ? 'Creating...' : 'Create Account & Enter Dashboard'}
          </button>
        </form>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Wizard
// ─────────────────────────────────────────────────────────────────────────────

const STEPS = ['Welcome', 'Cameras', 'Database', 'AI Model', 'Alerts', 'Account', 'Review'];

export default function SetupWizard({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState(0);
  const [cameras, setCameras] = useState<CameraEntry[]>([{ name: 'front_door', rtsp_url: '', fps: 15, post_event_seconds: 30 }]);
  const [dbUrl, setDbUrl] = useState('sqlite+aiosqlite:///./data/argus.db');
  const [llm, setLlm] = useState<LLMConfig>({ provider: 'ollama', model: 'llava', ollama_host: 'http://localhost:11434', laya_enabled: true, openai_api_key: '', anthropic_api_key: '', google_api_key: '' });
  const [alerts, setAlerts] = useState<AlertsConfig>({ routing: 'telegram', telegram_enabled: false, telegram_bot_token: '', telegram_chat_id: '', discord_enabled: false, discord_bot_token: '', discord_channel_id: '' });
  const [creds, setCreds] = useState<Credentials>({ username: 'admin', password: '', confirm_password: '' });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const isLast = step === STEPS.length - 1;

  const canNext = () => {
    if (step === 5) return creds.username && creds.password.length >= 8 && creds.password === creds.confirm_password;
    return true;
  };

  const handleComplete = async () => {
    setSubmitting(true);
    setError('');
    try {
      const payload = {
        cameras: cameras.filter(c => c.rtsp_url),
        database_url: dbUrl,
        llm,
        alerts,
        storage: { backend: 'local', local_path: './data/clips', retention_days: 30, rclone_remote: null, rclone_path: null },
        kafka: { enabled: false, bootstrap_servers: 'localhost:9092' },
        dashboard_username: creds.username,
        dashboard_password: creds.password,
      };
      const res = await fetch('/api/setup/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.detail || data.message || 'Setup failed');
      onComplete();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const stepContent = [
    <StepWelcome key="welcome" />,
    <StepCameras key="cameras" cameras={cameras} setCameras={setCameras} />,
    <StepDatabase key="db" dbUrl={dbUrl} setDbUrl={setDbUrl} />,
    <StepLLM key="llm" llm={llm} setLlm={setLlm} />,
    <StepAlerts key="alerts" alerts={alerts} setAlerts={setAlerts} />,
    <StepCredentials key="creds" creds={creds} setCreds={setCreds} />,
    <StepReview key="review" cameras={cameras} dbUrl={dbUrl} llm={llm} alerts={alerts} creds={creds} />,
  ];

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
            <Shield className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-foreground">Argus Setup Wizard</h1>
            <p className="text-xs text-muted-foreground">Step {step + 1} of {STEPS.length}</p>
          </div>
        </div>

        <StepIndicator steps={STEPS} current={step} />

        {/* Content card */}
        <div className="bg-card border border-border rounded-2xl p-6 min-h-[340px] flex flex-col">
          <div className="flex-1">
            {stepContent[step]}
          </div>

          {error && (
            <div className="mt-4 flex items-center gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-xs">
              <AlertCircle className="w-4 h-4 shrink-0" /> {error}
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between mt-6 pt-4 border-t border-border">
            <button
              type="button"
              onClick={() => setStep(s => Math.max(0, s - 1))}
              disabled={step === 0}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold border border-border hover:bg-muted transition-colors disabled:opacity-40"
            >
              <ChevronLeft className="w-4 h-4" /> Back
            </button>

            {isLast ? (
              <button
                type="button"
                onClick={handleComplete}
                disabled={submitting || !canNext()}
                className="inline-flex items-center gap-2 px-6 py-2 rounded-xl bg-primary text-white font-bold text-sm hover:bg-primary/90 transition-colors disabled:opacity-60"
              >
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                {submitting ? 'Saving...' : 'Complete Setup'}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setStep(s => Math.min(STEPS.length - 1, s + 1))}
                disabled={!canNext()}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white font-bold text-sm hover:bg-primary/90 transition-colors disabled:opacity-60"
              >
                Next <ChevronRight className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
