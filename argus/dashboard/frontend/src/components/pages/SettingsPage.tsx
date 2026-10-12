import React, { useState, useEffect } from 'react';
import {
  Save,
  RefreshCw,
  Camera,
  Cpu,
  Brain,
  Bell,
  HardDrive,
  Network,
  Trash2,
  CheckCircle,
  AlertCircle,
  Play,
  Moon,
  Clock,
} from 'lucide-react';
import { apiFetch } from '../../api/client';

const TABS = [
  { id: 'Cameras', label: 'Cameras', icon: Camera },
  { id: 'Detection', label: 'AI Detection', icon: Cpu },
  { id: 'LLM', label: 'LLM Intelligence', icon: Brain },
  { id: 'Alerts', label: 'Alerts & Bots', icon: Bell },
  { id: 'Storage', label: 'Storage & Retention', icon: HardDrive },
  { id: 'Kafka', label: 'Message Bus', icon: Network },
];

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('Cameras');
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  const [streamTestResult, setStreamTestResult] = useState<{ cam: string; success: boolean; msg: string } | null>(null);
  const [testingStream, setTestingStream] = useState<string | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = () => {
    setLoading(true);
    apiFetch<any>('/api/settings')
      .then((res) => {
        setConfig(res);
        setLoading(false);
      })
      .catch((err) => {
        setMessage({ text: 'Error loading settings: ' + err.message, type: 'error' });
        setLoading(false);
      });
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify(config),
      });
      setMessage({ text: 'Settings saved & persistent configuration updated!', type: 'success' });
      setTimeout(() => setMessage(null), 4000);
    } catch (err: any) {
      setMessage({ text: 'Error saving settings: ' + err.message, type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const handleRestart = async () => {
    if (!confirm('This will cleanly restart the Argus surveillance engine. Continue?')) return;
    try {
      await apiFetch('/api/system/restart', { method: 'POST' });
      setMessage({ text: 'Restart triggered. Reconnecting to dashboard...', type: 'success' });
      setTimeout(() => window.location.reload(), 3500);
    } catch (err: any) {
      setMessage({ text: 'Restart failed: ' + err.message, type: 'error' });
    }
  };

  const testStreamConnection = async (camName: string, rtspUrl: string) => {
    setTestingStream(camName);
    setStreamTestResult(null);
    try {
      const res = await apiFetch<{ success: boolean; message: string }>('/api/cameras/test-stream', {
        method: 'POST',
        body: JSON.stringify({ rtsp_url: rtspUrl, timeout_seconds: 5 }),
      });
      setStreamTestResult({ cam: camName, success: res.success, msg: res.message });
    } catch (err: any) {
      setStreamTestResult({ cam: camName, success: false, msg: err.message || 'Connection failed' });
    } finally {
      setTestingStream(null);
    }
  };

  if (loading) {
    return (
      <div className="p-8 max-w-5xl mx-auto space-y-4 animate-pulse">
        <div className="h-8 w-48 bg-muted rounded" />
        <div className="h-64 bg-card border border-border rounded-xl" />
      </div>
    );
  }

  return (
    <div className="p-6 h-full flex flex-col space-y-6 max-w-7xl mx-auto">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">System Configuration</h1>
          <p className="text-xs text-muted-foreground">Adjust camera feeds, neural detection thresholds, and integrations</p>
        </div>
        <div className="flex items-center gap-3">
          {message && (
            <span
              className={`text-xs px-3 py-1.5 rounded-lg border font-medium ${
                message.type === 'success'
                  ? 'bg-success/10 text-success border-success/30'
                  : 'bg-destructive/10 text-destructive border-destructive/30'
              }`}
            >
              {message.text}
            </span>
          )}
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-1.5 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:bg-primary/90 disabled:opacity-50 transition shadow-sm"
          >
            <Save className="w-4 h-4" /> {saving ? 'Saving...' : 'Save Changes'}
          </button>
          <button
            onClick={handleRestart}
            className="flex items-center gap-1.5 px-4 py-2 border border-destructive/40 bg-destructive/10 text-destructive rounded-lg text-sm font-semibold hover:bg-destructive/20 transition"
          >
            <RefreshCw className="w-4 h-4" /> Restart Engine
          </button>
        </div>
      </div>

      {/* Main Grid */}
      <div className="flex flex-col md:flex-row gap-6 flex-1 min-h-0">
        {/* Navigation Tabs */}
        <div className="flex md:flex-col gap-1 border-b md:border-b-0 md:border-r border-border md:w-56 pb-3 md:pb-0 md:pr-4 shrink-0 overflow-x-auto">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium transition-colors text-left shrink-0 ${
                  isActive
                    ? 'bg-primary/10 text-primary font-semibold shadow-sm'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-primary' : 'text-muted-foreground'}`} />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Content Pane */}
        <div className="flex-1 overflow-y-auto pb-8">
          <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-6">
            {/* Cameras Tab */}
            {activeTab === 'Cameras' && (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-border pb-3">
                  <h2 className="text-base font-bold">RTSP Camera Inputs</h2>
                  <button
                    onClick={() => {
                      const newCam = {
                        name: `camera_${(config?.cameras?.length || 0) + 1}`,
                        rtsp_url: 'rtsp://user:pass@192.168.1.100:554/live',
                        fps: 15,
                        pre_buffer_seconds: 5,
                        post_event_seconds: 30,
                        motion_threshold: 0.005,
                        disabled: false,
                      };
                      setConfig({ ...config, cameras: [...(config?.cameras || []), newCam] });
                    }}
                    className="text-xs font-semibold px-3 py-1.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition"
                  >
                    + Add New Camera
                  </button>
                </div>

                {(!config?.cameras || config.cameras.length === 0) ? (
                  <p className="text-sm text-muted-foreground text-center py-8">
                    No cameras configured yet. Click "Add New Camera" above.
                  </p>
                ) : (
                  config.cameras.map((cam: any, i: number) => (
                    <div key={i} className="p-4 border border-border rounded-xl bg-muted/20 space-y-4">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-sm text-foreground">Camera #{i + 1} ({cam.name})</span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => testStreamConnection(cam.name, cam.rtsp_url)}
                            disabled={testingStream === cam.name}
                            className="text-xs px-2.5 py-1 bg-muted hover:bg-muted/80 rounded border border-border flex items-center gap-1 transition"
                          >
                            <Play className="w-3 h-3 text-primary" />
                            {testingStream === cam.name ? 'Probing...' : 'Test RTSP'}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              const updated = config.cameras.filter((_: any, idx: number) => idx !== i);
                              setConfig({ ...config, cameras: updated });
                            }}
                            className="p-1 text-destructive hover:bg-destructive/10 rounded transition"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>

                      {streamTestResult && streamTestResult.cam === cam.name && (
                        <div
                          className={`text-xs p-2.5 rounded-lg border flex items-center gap-2 ${
                            streamTestResult.success
                              ? 'bg-success/10 text-success border-success/30'
                              : 'bg-destructive/10 text-destructive border-destructive/30'
                          }`}
                        >
                          {streamTestResult.success ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                          <span>{streamTestResult.msg}</span>
                        </div>
                      )}

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                        <div>
                          <label className="block text-muted-foreground mb-1 font-medium">Identifier Name</label>
                          <input
                            type="text"
                            value={cam.name || ''}
                            onChange={(e) => {
                              const updated = [...config.cameras];
                              updated[i] = { ...cam, name: e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, '') };
                              setConfig({ ...config, cameras: updated });
                            }}
                            className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-xs outline-none focus:ring-1 focus:ring-primary"
                          />
                        </div>
                        <div>
                          <label className="block text-muted-foreground mb-1 font-medium">RTSP Stream URL</label>
                          <input
                            type="text"
                            value={cam.rtsp_url || ''}
                            onChange={(e) => {
                              const updated = [...config.cameras];
                              updated[i] = { ...cam, rtsp_url: e.target.value };
                              setConfig({ ...config, cameras: updated });
                            }}
                            className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-xs outline-none focus:ring-1 focus:ring-primary"
                          />
                        </div>
                        <div>
                          <label className="block text-muted-foreground mb-1 font-medium">Target FPS ({cam.fps || 15})</label>
                          <input
                            type="number"
                            min="1"
                            max="60"
                            value={cam.fps || 15}
                            onChange={(e) => {
                              const updated = [...config.cameras];
                              updated[i] = { ...cam, fps: parseInt(e.target.value) || 15 };
                              setConfig({ ...config, cameras: updated });
                            }}
                            className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-xs outline-none"
                          />
                        </div>
                        <div>
                          <label className="block text-muted-foreground mb-1 font-medium">Pre-buffer (seconds)</label>
                          <input
                            type="number"
                            min="1"
                            max="30"
                            value={cam.pre_buffer_seconds || 5}
                            onChange={(e) => {
                              const updated = [...config.cameras];
                              updated[i] = { ...cam, pre_buffer_seconds: parseInt(e.target.value) || 5 };
                              setConfig({ ...config, cameras: updated });
                            }}
                            className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-xs outline-none"
                          />
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* AI Detection Tab */}
            {activeTab === 'Detection' && (
              <div className="space-y-6 max-w-xl">
                <div className="border-b border-border pb-3">
                  <h2 className="text-base font-bold">Ultralytics YOLOv8 Detection Engine</h2>
                  <p className="text-xs text-muted-foreground">Adjust model weight size, confidence thresholds, and class filtering</p>
                </div>

                <div className="space-y-4 text-xs">
                  <div>
                    <label className="block font-medium text-foreground mb-1">Model Architecture</label>
                    <select
                      value={config?.detection?.model || 'yolov8n.pt'}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          detection: { ...(config?.detection || {}), model: e.target.value },
                        })
                      }
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs outline-none"
                    >
                      <option value="yolov8n.pt">YOLOv8 Nano (Fastest, ~3.2M params)</option>
                      <option value="yolov8s.pt">YOLOv8 Small (Balanced, ~11.2M params)</option>
                      <option value="yolov8m.pt">YOLOv8 Medium (High accuracy, ~25.9M params)</option>
                    </select>
                  </div>

                  <div>
                    <div className="flex justify-between font-medium text-foreground mb-1">
                      <span>Minimum Confidence Threshold</span>
                      <span className="font-bold text-primary">
                        {((config?.detection?.confidence ?? 0.6) * 100).toFixed(0)}%
                      </span>
                    </div>
                    <input
                      type="range"
                      min="0.1"
                      max="0.95"
                      step="0.05"
                      value={config?.detection?.confidence ?? 0.6}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          detection: {
                            ...(config?.detection || {}),
                            confidence: parseFloat(e.target.value),
                          },
                        })
                      }
                      className="w-full accent-primary cursor-pointer"
                    />
                  </div>

                  <div>
                    <label className="block font-medium text-foreground mb-1">Hardware Acceleration Device</label>
                    <select
                      value={config?.detection?.device || 'auto'}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          detection: { ...(config?.detection || {}), device: e.target.value },
                        })
                      }
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs outline-none"
                    >
                      <option value="auto">Auto-detect (CUDA if NVIDIA GPU present, else CPU)</option>
                      <option value="cuda">Force NVIDIA CUDA (RTX 3050)</option>
                      <option value="cpu">Force Host CPU</option>
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* LLM Tab */}
            {activeTab === 'LLM' && (
              <div className="space-y-6 max-w-xl">
                <div className="border-b border-border pb-3">
                  <h2 className="text-base font-bold">Multimodal Scene Intelligence (VLM)</h2>
                  <p className="text-xs text-muted-foreground">Synthesize detailed natural language incident reports</p>
                </div>

                <div className="space-y-4 text-xs">
                  <div>
                    <label className="block font-medium text-foreground mb-1">Provider</label>
                    <select
                      value={config?.llm?.provider || 'ollama'}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          llm: { ...(config?.llm || {}), provider: e.target.value },
                        })
                      }
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs outline-none"
                    >
                      <option value="ollama">Ollama (Local Private Inference)</option>
                      <option value="openai">OpenAI (GPT-4o Mini)</option>
                      <option value="anthropic">Anthropic (Claude 3.5 Sonnet)</option>
                      <option value="gemini">Google Gemini (Gemini 1.5 Flash)</option>
                      <option value="disabled">Disabled</option>
                    </select>
                  </div>

                  {config?.llm?.provider === 'ollama' && (
                    <div>
                      <label className="block font-medium text-foreground mb-1">Ollama Host Endpoint</label>
                      <input
                        type="text"
                        value={config?.llm?.ollama_host || 'http://localhost:11434'}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            llm: { ...(config?.llm || {}), ollama_host: e.target.value },
                          })
                        }
                        className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-xs outline-none"
                      />
                    </div>
                  )}

                  <div>
                    <label className="block font-medium text-foreground mb-1">Model Name</label>
                    <input
                      type="text"
                      value={config?.llm?.model || 'llava'}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          llm: { ...(config?.llm || {}), model: e.target.value },
                        })
                      }
                      className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-xs outline-none"
                    />
                  </div>

                  <div>
                    <label className="block font-medium text-foreground mb-1">Scene Analysis Prompt</label>
                    <textarea
                      rows={3}
                      value={config?.llm?.scene_prompt || 'Describe what is occurring in the scene in detail.'}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          llm: { ...(config?.llm || {}), scene_prompt: e.target.value },
                        })
                      }
                      className="w-full bg-background border border-border rounded-lg p-2.5 text-xs outline-none"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Alerts & Bots Tab */}
            {activeTab === 'Alerts' && (
              <div className="space-y-6 max-w-xl">
                <div className="border-b border-border pb-3">
                  <h2 className="text-base font-bold">Alert Channels & Two-Way Bot Callbacks</h2>
                  <p className="text-xs text-muted-foreground">Configure Telegram and Discord real-time notifications</p>
                </div>

                <div className="space-y-5 text-xs">
                  <div>
                    <label className="block font-medium text-foreground mb-1">Dispatch Routing</label>
                    <select
                      value={config?.alerts?.routing || 'both'}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          alerts: { ...(config?.alerts || {}), routing: e.target.value },
                        })
                      }
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs outline-none"
                    >
                      <option value="both">Both Telegram and Discord</option>
                      <option value="telegram">Telegram Only</option>
                      <option value="discord">Discord Only</option>
                    </select>
                  </div>

                  {/* Telegram */}
                  <div className="p-4 border border-border rounded-xl bg-muted/20 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-sm">Telegram Bot</span>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={config?.alerts?.telegram?.enabled || false}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              alerts: {
                                ...(config?.alerts || {}),
                                telegram: {
                                  ...(config?.alerts?.telegram || {}),
                                  enabled: e.target.checked,
                                },
                              },
                            })
                          }
                          className="w-4 h-4 accent-primary"
                        />
                        <span className="font-semibold">Enabled</span>
                      </label>
                    </div>

                    <div>
                      <label className="block text-muted-foreground mb-1">Bot Token</label>
                      <input
                        type="password"
                        placeholder="********"
                        value={config?.alerts?.telegram?.bot_token || ''}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            alerts: {
                              ...(config?.alerts || {}),
                              telegram: {
                                ...(config?.alerts?.telegram || {}),
                                bot_token: e.target.value,
                              },
                            },
                          })
                        }
                        className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-xs outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-muted-foreground mb-1">Chat ID</label>
                      <input
                        type="text"
                        value={config?.alerts?.telegram?.chat_id || ''}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            alerts: {
                              ...(config?.alerts || {}),
                              telegram: {
                                ...(config?.alerts?.telegram || {}),
                                chat_id: e.target.value,
                              },
                            },
                          })
                        }
                        className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-xs outline-none"
                      />
                    </div>
                  </div>

                  {/* Quiet Hours */}
                  <div className="p-4 border border-border rounded-xl bg-muted/20 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-sm flex items-center gap-1.5">
                        <Moon className="w-4 h-4 text-warning" /> Quiet Hours Schedule
                      </span>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={config?.alerts?.quiet_hours?.enabled || false}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              alerts: {
                                ...(config?.alerts || {}),
                                quiet_hours: {
                                  ...(config?.alerts?.quiet_hours || {}),
                                  enabled: e.target.checked,
                                },
                              },
                            })
                          }
                          className="w-4 h-4 accent-primary"
                        />
                        <span className="font-semibold">Active</span>
                      </label>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-muted-foreground mb-1">Start Time (UTC)</label>
                        <input
                          type="text"
                          value={config?.alerts?.quiet_hours?.start || '23:00'}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              alerts: {
                                ...(config?.alerts || {}),
                                quiet_hours: {
                                  ...(config?.alerts?.quiet_hours || {}),
                                  start: e.target.value,
                                },
                              },
                            })
                          }
                          className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-xs outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-muted-foreground mb-1">End Time (UTC)</label>
                        <input
                          type="text"
                          value={config?.alerts?.quiet_hours?.end || '07:00'}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              alerts: {
                                ...(config?.alerts || {}),
                                quiet_hours: {
                                  ...(config?.alerts?.quiet_hours || {}),
                                  end: e.target.value,
                                },
                              },
                            })
                          }
                          className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-xs outline-none"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Storage Tab */}
            {activeTab === 'Storage' && (
              <div className="space-y-6 max-w-xl">
                <div className="border-b border-border pb-3">
                  <h2 className="text-base font-bold">Storage & Retention Policy</h2>
                  <p className="text-xs text-muted-foreground">Manage disk quota, incident MP4 clips, and cloud replication</p>
                </div>

                <div className="space-y-4 text-xs">
                  <div>
                    <label className="block font-medium text-foreground mb-1">Retention Window (Days)</label>
                    <input
                      type="number"
                      min="1"
                      max="365"
                      value={config?.storage?.retention_days || 30}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          storage: {
                            ...(config?.storage || {}),
                            retention_days: parseInt(e.target.value) || 30,
                          },
                        })
                      }
                      className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-xs outline-none"
                    />
                  </div>

                  <div>
                    <label className="block font-medium text-foreground mb-1">Storage Backend</label>
                    <select
                      value={config?.storage?.backend || 'local'}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          storage: { ...(config?.storage || {}), backend: e.target.value },
                        })
                      }
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs outline-none"
                    >
                      <option value="local">Local Filesystem Only</option>
                      <option value="rclone">Rclone Multi-Cloud (Google Drive, S3, B2)</option>
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* Message Bus Tab */}
            {activeTab === 'Kafka' && (
              <div className="space-y-6 max-w-xl">
                <div className="border-b border-border pb-3">
                  <h2 className="text-base font-bold">Kafka & In-Memory Event Streaming</h2>
                  <p className="text-xs text-muted-foreground">Manage distributed cluster streaming vs standalone mode</p>
                </div>

                <div className="space-y-4 text-xs">
                  <div className="p-4 border border-border rounded-xl bg-muted/20 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-sm">Apache Kafka Streaming</span>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={config?.kafka?.enabled || false}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              kafka: { ...(config?.kafka || {}), enabled: e.target.checked },
                            })
                          }
                          className="w-4 h-4 accent-primary"
                        />
                        <span className="font-semibold">Enabled</span>
                      </label>
                    </div>
                    <p className="text-muted-foreground text-[11px]">
                      When disabled, Argus automatically utilizes its built-in non-blocking in-memory `DashboardEventBus` to stream all live events directly to the dashboard.
                    </p>
                  </div>

                  <div>
                    <label className="block font-medium text-foreground mb-1">Bootstrap Brokers</label>
                    <input
                      type="text"
                      value={config?.kafka?.bootstrap_servers || 'localhost:9092'}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          kafka: { ...(config?.kafka || {}), bootstrap_servers: e.target.value },
                        })
                      }
                      className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-xs outline-none"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
