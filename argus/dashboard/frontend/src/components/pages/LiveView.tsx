import React, { useEffect, useState } from 'react';
import {
  Camera,
  RefreshCw,
  Maximize2,
  AlertCircle,
  Plus,
  Radio,
  Play,
  CheckCircle,
  X,
  Settings,
  ShieldAlert,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../../api/client';
import type { CameraStatus } from '../../types';

interface ProbeResult {
  success: boolean;
  message: string;
  codec?: string;
  resolution?: string;
  fps?: number;
  preview_base64?: string;
}

export default function LiveView() {
  const [cameras, setCameras] = useState<CameraStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [streamKeys, setStreamKeys] = useState<Record<string, number>>({});

  // Add Camera Modal state
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [newCamName, setNewCamName] = useState('');
  const [newCamRtsp, setNewCamRtsp] = useState('');
  const [newCamFps, setNewCamFps] = useState(15);
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<ProbeResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Quick Diagnostics Modal for existing camera
  const [diagCam, setDiagCam] = useState<CameraStatus | null>(null);
  const [diagResult, setDiagResult] = useState<ProbeResult | null>(null);
  const [diagLoading, setDiagLoading] = useState(false);

  const navigate = useNavigate();

  const loadCameras = () => {
    setLoading(true);
    apiFetch<CameraStatus[]>('/api/cameras')
      .then((data) => {
        setCameras(data || []);
        setError(null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadCameras();
  }, []);

  const refreshStream = (camName: string) => {
    setStreamKeys((prev) => ({
      ...prev,
      [camName]: (prev[camName] || 0) + 1,
    }));
  };

  const toggleFullscreen = (elementId: string) => {
    const el = document.getElementById(elementId);
    if (!el) return;
    if (!document.fullscreenElement) {
      el.requestFullscreen().catch(console.error);
    } else {
      document.exitFullscreen().catch(console.error);
    }
  };

  const handleProbeNew = async () => {
    if (!newCamRtsp.trim()) {
      setProbeResult({ success: false, message: 'Please enter an RTSP stream URL' });
      return;
    }
    setProbing(true);
    setProbeResult(null);
    try {
      const res = await apiFetch<ProbeResult>('/api/cameras/test-stream', {
        method: 'POST',
        body: JSON.stringify({ rtsp_url: newCamRtsp.trim(), timeout_seconds: 6 }),
      });
      setProbeResult(res);
    } catch (err: any) {
      setProbeResult({ success: false, message: err.message || 'Connection test failed' });
    } finally {
      setProbing(false);
    }
  };

  const handleSaveNewCamera = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCamName.trim() || !newCamRtsp.trim()) return;

    setSaving(true);
    setSaveError(null);
    try {
      await apiFetch<CameraStatus>('/api/cameras', {
        method: 'POST',
        body: JSON.stringify({
          name: newCamName.trim().toLowerCase().replace(/[^a-z0-9_-]/g, ''),
          rtsp_url: newCamRtsp.trim(),
          fps: Number(newCamFps) || 15,
          disabled: false,
        }),
      });

      setIsAddOpen(false);
      setNewCamName('');
      setNewCamRtsp('');
      setProbeResult(null);
      loadCameras();
    } catch (err: any) {
      setSaveError(err.message || 'Failed to save camera');
    } finally {
      setSaving(false);
    }
  };

  const handleDiagnoseCamera = async (cam: CameraStatus) => {
    setDiagCam(cam);
    setDiagResult(null);
    setDiagLoading(true);
    try {
      // Look up full config to probe
      const settings = await apiFetch<any>('/api/settings');
      const found = (settings?.cameras || []).find((c: any) => c.name === cam.name);
      const urlToTest = found?.rtsp_url || cam.rtsp_url;
      const res = await apiFetch<ProbeResult>('/api/cameras/test-stream', {
        method: 'POST',
        body: JSON.stringify({ rtsp_url: urlToTest, timeout_seconds: 6 }),
      });
      setDiagResult(res);
    } catch (err: any) {
      setDiagResult({ success: false, message: err.message || 'Diagnostic probe failed' });
    } finally {
      setDiagLoading(false);
    }
  };

  return (
    <div className="p-6 h-full flex flex-col space-y-6 max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Radio className="w-5 h-5 text-primary animate-pulse" /> Live Surveillance Feeds
          </h1>
          <p className="text-xs text-muted-foreground">
            Low-latency multipart video streaming with real-time neural pipeline
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadCameras}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-border bg-card rounded-lg text-xs font-medium hover:bg-muted transition"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Reload List
          </button>
          <button
            onClick={() => {
              setIsAddOpen(true);
              setProbeResult(null);
              setSaveError(null);
            }}
            className="flex items-center gap-1.5 px-3.5 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-semibold hover:bg-primary/90 transition shadow-sm"
          >
            <Plus className="w-4 h-4" /> Add Camera
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 gap-5 animate-pulse">
          <div className="aspect-video bg-muted/40 rounded-2xl border border-border/50" />
          <div className="aspect-video bg-muted/40 rounded-2xl border border-border/50" />
        </div>
      ) : error ? (
        <div className="p-8 bg-destructive/10 border border-destructive/20 text-destructive rounded-2xl text-center space-y-3">
          <AlertCircle className="w-10 h-10 mx-auto opacity-80" />
          <p className="font-semibold text-sm">{error}</p>
          <button
            onClick={loadCameras}
            className="px-4 py-1.5 bg-primary text-primary-foreground text-xs rounded-lg font-medium shadow"
          >
            Retry Connection
          </button>
        </div>
      ) : cameras.length === 0 ? (
        <div className="bg-card border border-border rounded-2xl p-12 text-center flex flex-col items-center justify-center my-auto space-y-4 shadow-sm">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
            <Camera className="w-8 h-8" />
          </div>
          <h2 className="text-base font-bold text-foreground">No Surveillance Cameras Configured</h2>
          <p className="text-xs text-muted-foreground max-w-md">
            Argus connects to your RTSP security cameras to stream live video and run continuous edge object & face analysis.
          </p>
          <button
            onClick={() => setIsAddOpen(true)}
            className="px-5 py-2.5 bg-primary text-primary-foreground rounded-xl text-xs font-semibold hover:bg-primary/90 transition shadow-sm flex items-center gap-2"
          >
            <Plus className="w-4 h-4" /> Add Your First Camera
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 gap-5">
          {cameras.map((cam) => {
            const containerId = `cam-container-${cam.name}`;
            const key = streamKeys[cam.name] || 0;
            const streamUrl = `/api/cameras/${cam.name}/stream?t=${key}`;

            return (
              <div
                key={cam.name}
                id={containerId}
                className="relative rounded-2xl border border-border/80 overflow-hidden bg-black aspect-video flex items-center justify-center group shadow-md"
              >
                {cam.is_online ? (
                  <img
                    key={`${cam.name}-${key}`}
                    src={streamUrl}
                    alt={`Live feed for ${cam.name}`}
                    className="w-full h-full object-contain"
                    onError={(e) => {
                      const img = e.target as HTMLImageElement;
                      const parent = img.parentElement;
                      if (parent) {
                        const fallback = parent.querySelector('.stream-fallback');
                        if (fallback) fallback.classList.remove('hidden');
                      }
                      // Auto reconnect stream after 3.5s if signal dropped
                      setTimeout(() => {
                        refreshStream(cam.name);
                      }, 3500);
                    }}
                    onLoad={(e) => {
                      const img = e.target as HTMLImageElement;
                      img.style.display = 'block';
                      const parent = img.parentElement;
                      if (parent) {
                        const fallback = parent.querySelector('.stream-fallback');
                        if (fallback) fallback.classList.add('hidden');
                      }
                    }}
                  />
                ) : (
                  <div className="flex flex-col items-center gap-2 text-destructive">
                    <ShieldAlert className="w-8 h-8 opacity-70" />
                    <span className="text-xs font-bold tracking-widest uppercase">Stream Disabled</span>
                  </div>
                )}

                {/* Stream Disconnected Fallback */}
                <div className="stream-fallback hidden absolute inset-0 bg-zinc-950 flex flex-col items-center justify-center p-4 text-center">
                  <Camera className="w-8 h-8 text-muted-foreground opacity-30 mb-2" />
                  <span className="text-xs font-bold text-foreground">Waiting for Stream Signal...</span>
                  <span className="text-[11px] text-muted-foreground mt-1 max-w-xs truncate">{cam.rtsp_url}</span>
                  <div className="flex items-center gap-2 mt-3">
                    <button
                      onClick={() => refreshStream(cam.name)}
                      className="px-3 py-1 bg-primary text-primary-foreground text-xs rounded-md font-medium flex items-center gap-1.5 transition"
                    >
                      <RefreshCw className="w-3 h-3" /> Reconnect
                    </button>
                    <button
                      onClick={() => handleDiagnoseCamera(cam)}
                      className="px-3 py-1 bg-muted hover:bg-muted/80 text-foreground text-xs rounded-md font-medium flex items-center gap-1.5 transition"
                    >
                      <Play className="w-3 h-3" /> Probe
                    </button>
                  </div>
                </div>

                {/* Top Badge: Camera Name & State */}
                <div className="absolute top-3 left-3 bg-black/70 backdrop-blur-md px-2.5 py-1 rounded-lg flex items-center gap-2 border border-white/10 shadow-sm">
                  <span className="text-white text-xs font-bold tracking-wide uppercase">{cam.name}</span>
                  <div className="flex items-center gap-1">
                    <div
                      className={`w-2 h-2 rounded-full ${cam.is_online ? 'bg-success animate-pulse' : 'bg-muted'}`}
                    />
                    <span
                      className={`text-[10px] font-bold ${cam.is_online ? 'text-success' : 'text-muted-foreground'}`}
                    >
                      {cam.is_online ? 'LIVE' : 'OFFLINE'}
                    </span>
                  </div>
                </div>

                {/* Top Right Controls */}
                <div className="absolute top-3 right-3 flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => handleDiagnoseCamera(cam)}
                    title="Diagnose & Test RTSP stream"
                    className="p-1.5 bg-black/70 hover:bg-black/90 text-white rounded-md backdrop-blur border border-white/10 transition"
                  >
                    <Play className="w-3.5 h-3.5 text-primary" />
                  </button>
                  <button
                    onClick={() => refreshStream(cam.name)}
                    title="Reconnect feed"
                    className="p-1.5 bg-black/70 hover:bg-black/90 text-white rounded-md backdrop-blur border border-white/10 transition"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => toggleFullscreen(containerId)}
                    title="Fullscreen"
                    className="p-1.5 bg-black/70 hover:bg-black/90 text-white rounded-md backdrop-blur border border-white/10 transition"
                  >
                    <Maximize2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Bottom Overlay: Stats & Link */}
                <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent p-3 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-between text-xs text-white/80">
                  <span>Incidents: {cam.total_events}</span>
                  <button
                    onClick={() => navigate('/settings')}
                    className="text-[11px] text-white/70 hover:text-white flex items-center gap-1"
                  >
                    <Settings className="w-3 h-3" /> Configure
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add Camera Modal with Live Visual Preview */}
      {isAddOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
            <div className="p-5 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Camera className="w-5 h-5 text-primary" />
                <h3 className="text-base font-bold text-foreground">Add New RTSP Camera</h3>
              </div>
              <button
                onClick={() => setIsAddOpen(false)}
                className="p-1 rounded-lg text-muted-foreground hover:bg-muted transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSaveNewCamera} className="p-5 space-y-4 overflow-y-auto">
              <div>
                <label className="block text-xs font-semibold text-foreground mb-1">
                  Camera Identifier <span className="text-destructive">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. front_door, garage, driveway"
                  value={newCamName}
                  onChange={(e) => setNewCamName(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))}
                  className="w-full bg-background border border-border rounded-xl px-3 py-2 text-xs outline-none focus:ring-1 focus:ring-primary"
                />
                <span className="text-[10px] text-muted-foreground">Lowercase letters, numbers, and underscores only.</span>
              </div>

              <div>
                <label className="block text-xs font-semibold text-foreground mb-1">
                  RTSP Stream URL <span className="text-destructive">*</span>
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    required
                    placeholder="rtsp://user:pass@192.168.0.200:554/stream1"
                    value={newCamRtsp}
                    onChange={(e) => setNewCamRtsp(e.target.value)}
                    className="flex-1 bg-background border border-border rounded-xl px-3 py-2 text-xs outline-none focus:ring-1 focus:ring-primary"
                  />
                  <button
                    type="button"
                    onClick={handleProbeNew}
                    disabled={probing || !newCamRtsp.trim()}
                    className="px-3.5 py-2 bg-muted hover:bg-muted/80 text-foreground border border-border rounded-xl text-xs font-semibold flex items-center gap-1.5 transition shrink-0 disabled:opacity-50"
                  >
                    <Play className="w-3.5 h-3.5 text-primary" />
                    {probing ? 'Probing...' : 'Test Feed'}
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-foreground mb-1">Target FPS</label>
                <input
                  type="number"
                  min="1"
                  max="60"
                  value={newCamFps}
                  onChange={(e) => setNewCamFps(Number(e.target.value) || 15)}
                  className="w-28 bg-background border border-border rounded-xl px-3 py-1.5 text-xs outline-none"
                />
              </div>

              {/* Probe Result Box with Live Frame Preview */}
              {probeResult && (
                <div
                  className={`text-xs p-3.5 rounded-xl border space-y-2 ${
                    probeResult.success
                      ? 'bg-success/10 text-success border-success/30'
                      : 'bg-destructive/10 text-destructive border-destructive/30'
                  }`}
                >
                  <div className="flex items-center gap-2 font-semibold">
                    {probeResult.success ? <CheckCircle className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
                    <span>{probeResult.message}</span>
                  </div>

                  {probeResult.preview_base64 && (
                    <div className="mt-2 space-y-2 pt-2 border-t border-success/20">
                      <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono">
                        {probeResult.resolution && (
                          <span className="px-2 py-0.5 rounded bg-success/20 font-bold text-success">
                            {probeResult.resolution}
                          </span>
                        )}
                        {probeResult.codec && (
                          <span className="px-2 py-0.5 rounded bg-card/80 border border-border uppercase">
                            {probeResult.codec}
                          </span>
                        )}
                        {probeResult.fps && (
                          <span className="px-2 py-0.5 rounded bg-card/80 border border-border">
                            {probeResult.fps} FPS
                          </span>
                        )}
                      </div>
                      <div className="relative rounded-xl overflow-hidden border border-border/80 bg-black aspect-video max-w-full shadow-inner">
                        <img
                          src={probeResult.preview_base64}
                          alt="Decoded stream preview"
                          className="w-full h-full object-contain"
                        />
                        <span className="absolute bottom-1 right-2 text-[10px] bg-black/80 backdrop-blur-sm text-white px-2 py-0.5 rounded-md">
                          Live Verified Frame
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {saveError && (
                <div className="p-3 bg-destructive/10 border border-destructive/20 text-destructive text-xs rounded-xl flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{saveError}</span>
                </div>
              )}

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-border">
                <button
                  type="button"
                  onClick={() => setIsAddOpen(false)}
                  className="px-4 py-2 border border-border rounded-xl text-xs font-medium hover:bg-muted transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving || !newCamName.trim() || !newCamRtsp.trim()}
                  className="px-5 py-2 bg-primary text-primary-foreground rounded-xl text-xs font-bold hover:bg-primary/90 transition shadow disabled:opacity-50"
                >
                  {saving ? 'Connecting...' : 'Save & Connect Camera'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Diagnostics Modal */}
      {diagCam && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl w-full max-w-lg shadow-2xl p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <Radio className="w-5 h-5 text-primary" />
                <h3 className="text-base font-bold text-foreground">Diagnostic Probe: {diagCam.name}</h3>
              </div>
              <button
                onClick={() => setDiagCam(null)}
                className="p-1 rounded-lg text-muted-foreground hover:bg-muted transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {diagLoading ? (
              <div className="py-12 text-center space-y-3 animate-pulse">
                <RefreshCw className="w-8 h-8 mx-auto text-primary animate-spin" />
                <p className="text-xs text-muted-foreground">Probing stream & decoding live video frame...</p>
              </div>
            ) : diagResult ? (
              <div className="space-y-3">
                <div
                  className={`text-xs p-3.5 rounded-xl border flex items-center gap-2 font-semibold ${
                    diagResult.success
                      ? 'bg-success/10 text-success border-success/30'
                      : 'bg-destructive/10 text-destructive border-destructive/30'
                  }`}
                >
                  {diagResult.success ? <CheckCircle className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
                  <span>{diagResult.message}</span>
                </div>

                {diagResult.preview_base64 && (
                  <div className="relative rounded-xl overflow-hidden border border-border/80 bg-black aspect-video shadow-inner">
                    <img
                      src={diagResult.preview_base64}
                      alt="Diagnostic live frame"
                      className="w-full h-full object-contain"
                    />
                    <span className="absolute bottom-2 right-2 text-[10px] bg-black/80 backdrop-blur-sm text-white px-2 py-0.5 rounded-md">
                      {diagResult.resolution} {diagResult.codec?.toUpperCase()} @ {diagResult.fps} FPS
                    </span>
                  </div>
                )}
              </div>
            ) : null}

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setDiagCam(null)}
                className="px-4 py-2 bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold rounded-xl"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
