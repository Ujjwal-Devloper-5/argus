import os
import glob
import re

# We will modify the React frontend components to use actual API data instead of dummy data

FRONTEND_DIR = "/home/ujjwal/homelab/argus/argus/dashboard/frontend/src"

# 1. Fix LiveView.tsx
live_view_path = os.path.join(FRONTEND_DIR, "components/pages/LiveView.tsx")
with open(live_view_path, "w") as f:
    f.write("""import { useEffect, useState } from 'react';
import { apiFetch } from '../../api/client';
import type { CameraStatus } from '../../types';

export default function LiveView() {
  const [cameras, setCameras] = useState<CameraStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [timestamp, setTimestamp] = useState(Date.now());

  useEffect(() => {
    apiFetch<CameraStatus[]>('/api/cameras')
      .then(setCameras)
      .catch(err => setError(err.message));
      
    // Auto-refresh snapshot timestamp every 2 seconds for a pseudo-live feed
    const interval = setInterval(() => setTimestamp(Date.now()), 2000);
    return () => clearInterval(interval);
  }, []);

  if (error) return <div className="p-6 text-destructive">Error loading cameras: {error}</div>;

  return (
    <div className="p-6 h-full flex flex-col">
      <h1 className="text-xl font-bold mb-4">Live Camera Grid</h1>
      {cameras.length === 0 ? (
        <div className="text-muted-foreground">No cameras configured. Go to Settings to add one.</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {cameras.map(cam => (
            <div key={cam.name} className="relative rounded-xl border border-border overflow-hidden bg-black aspect-video flex items-center justify-center group">
              {cam.is_online ? (
                <img 
                  src={`/api/cameras/${cam.name}/snapshot?t=${timestamp}`} 
                  alt={cam.name}
                  className="w-full h-full object-contain"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none';
                    (e.target as HTMLImageElement).parentElement?.classList.add('bg-muted');
                  }}
                />
              ) : (
                <span className="text-destructive font-bold">OFFLINE</span>
              )}
              
              <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 p-3 opacity-0 group-hover:opacity-100 transition-opacity">
                <div className="flex items-center justify-between">
                  <span className="text-white text-sm font-bold">{cam.name}</span>
                  <div className="flex items-center gap-1.5">
                    <div className={`w-2 h-2 rounded-full ${cam.is_online ? 'bg-success pulse-online' : 'bg-muted'}`} />
                    <span className={`text-[10px] font-bold ${cam.is_online ? 'text-success' : 'text-muted-foreground'}`}>
                      {cam.is_online ? 'LIVE' : 'OFFLINE'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
""")

# 2. Fix useLiveEvents.ts
use_live_events_path = os.path.join(FRONTEND_DIR, "hooks/useLiveEvents.ts")
with open(use_live_events_path, "w") as f:
    f.write("""import { useState, useEffect } from 'react';
import type { LiveEvent } from '../types';

export function useLiveEvents() {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.port === '5173' ? 'localhost:8501' : window.location.host;
    const ws = new WebSocket(`${protocol}//${host}/ws/events`);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data);
        if (data.type === 'heartbeat') return;
        
        // Push new event to top of feed
        setEvents(prev => [data, ...prev].slice(0, 50));
      } catch (e) {
        console.error("WS error", e);
      }
    };

    return () => {
      ws.close();
    };
  }, []);

  return { events, connected };
}
""")

# 3. Fix useLiveStats.ts
use_live_stats_path = os.path.join(FRONTEND_DIR, "hooks/useLiveStats.ts")
with open(use_live_stats_path, "w") as f:
    f.write("""import { useState, useEffect } from 'react';
import type { SystemStats } from '../types';

export function useLiveStats() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.port === '5173' ? 'localhost:8501' : window.location.host;
    const ws = new WebSocket(`${protocol}//${host}/ws/stats`);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data);
        setStats(data);
      } catch (e) {
        console.error("WS stats error", e);
      }
    };

    return () => {
      ws.close();
    };
  }, []);

  return { stats, connected };
}
""")

print("React UI hooks and LiveView replaced with real API connections.")
