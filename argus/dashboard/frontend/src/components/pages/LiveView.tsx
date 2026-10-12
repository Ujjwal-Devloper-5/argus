import React, { useEffect, useState, useRef } from 'react';
import { Camera, RefreshCw, Maximize2, AlertCircle, Plus, Eye, Radio } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../../api/client';
import type { CameraStatus } from '../../types';

export default function LiveView() {
  const [cameras, setCameras] = useState<CameraStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [streamKeys, setStreamKeys] = useState<Record<string, number>>({});
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

  return (
    <div className="p-6 h-full flex flex-col space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Radio className="w-5 h-5 text-primary animate-pulse" /> Live Surveillance Feeds
          </h1>
          <p className="text-xs text-muted-foreground">Low-latency multipart video streaming with edge neural analysis</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadCameras}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-border bg-card rounded-lg text-xs font-medium hover:bg-muted transition"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Reload List
          </button>
          <button
            onClick={() => navigate('/settings')}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-semibold hover:bg-primary/90 transition shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" /> Manage Cameras
          </button>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 animate-pulse">
          <div className="aspect-video bg-muted rounded-xl" />
          <div className="aspect-video bg-muted rounded-xl" />
        </div>
      ) : error ? (
        <div className="p-6 bg-destructive/10 border border-destructive/20 text-destructive rounded-xl text-center">
          <AlertCircle className="w-8 h-8 mx-auto mb-2" />
          <p className="font-semibold">{error}</p>
          <button
            onClick={loadCameras}
            className="mt-3 px-4 py-1.5 bg-primary text-primary-foreground text-xs rounded-lg font-medium"
          >
            Retry Connection
          </button>
        </div>
      ) : cameras.length === 0 ? (
        <div className="bg-card border border-border rounded-2xl p-12 text-center flex flex-col items-center justify-center my-auto space-y-3">
          <Camera className="w-12 h-12 text-muted-foreground opacity-40" />
          <h2 className="text-base font-bold text-foreground">No Surveillance Cameras Configured</h2>
          <p className="text-xs text-muted-foreground max-w-md">
            Argus needs at least one RTSP video source configured to begin active neural monitoring and threat detection.
          </p>
          <button
            onClick={() => navigate('/settings')}
            className="mt-2 px-5 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:bg-primary/90 transition shadow"
          >
            Open Settings to Add Camera
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
                    src={streamUrl}
                    alt={`Live feed for ${cam.name}`}
                    className="w-full h-full object-contain"
                    onError={(e) => {
                      const img = e.target as HTMLImageElement;
                      img.style.display = 'none';
                      const parent = img.parentElement;
                      if (parent) {
                        const fallback = parent.querySelector('.stream-fallback');
                        if (fallback) fallback.classList.remove('hidden');
                      }
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
                    <AlertCircle className="w-8 h-8 opacity-70" />
                    <span className="text-xs font-bold tracking-widest uppercase">Stream Disabled</span>
                  </div>
                )}

                {/* Stream Disconnected Fallback */}
                <div className="stream-fallback hidden absolute inset-0 bg-zinc-950 flex flex-col items-center justify-center p-4 text-center">
                  <Camera className="w-8 h-8 text-muted-foreground opacity-30 mb-2" />
                  <span className="text-xs font-bold text-foreground">Waiting for Stream Frames...</span>
                  <span className="text-[11px] text-muted-foreground mt-1">Connecting to {cam.rtsp_url}</span>
                  <button
                    onClick={() => refreshStream(cam.name)}
                    className="mt-3 px-3 py-1 bg-muted hover:bg-muted/80 text-foreground text-xs rounded-md font-medium flex items-center gap-1.5 transition"
                  >
                    <RefreshCw className="w-3 h-3" /> Reconnect
                  </button>
                </div>

                {/* Top Badge: Camera Name & State */}
                <div className="absolute top-3 left-3 bg-black/60 backdrop-blur-sm px-2.5 py-1 rounded-md flex items-center gap-2 border border-white/10">
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

                {/* Top Right: Fullscreen & Refresh Controls */}
                <div className="absolute top-3 right-3 flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => refreshStream(cam.name)}
                    title="Reconnect stream"
                    className="p-1.5 bg-black/60 hover:bg-black/90 text-white rounded-md backdrop-blur border border-white/10 transition"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => toggleFullscreen(containerId)}
                    title="Fullscreen"
                    className="p-1.5 bg-black/60 hover:bg-black/90 text-white rounded-md backdrop-blur border border-white/10 transition"
                  >
                    <Maximize2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Bottom Overlay: Event Stats */}
                <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent p-3 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-between text-xs text-white/80">
                  <span>Total Incidents: {cam.total_events}</span>
                  {cam.last_event_at && (
                    <span className="text-[11px] text-white/60">
                      Last: {new Date(cam.last_event_at).toLocaleTimeString()}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
