import os
import textwrap

FRONTEND_DIR = "/home/ujjwal/homelab/argus/argus/dashboard/frontend/src"

events_ts = os.path.join(FRONTEND_DIR, "hooks/useLiveEvents.ts")
with open(events_ts, "w") as f:
    f.write(textwrap.dedent('''\
    import { useState, useEffect } from 'react';
    import type { LiveEvent } from '../types';
    import { apiFetch } from '../api/client';

    export function useLiveEvents() {
      const [events, setEvents] = useState<LiveEvent[]>([]);
      const [connected, setConnected] = useState(false);

      useEffect(() => {
        let ws: WebSocket;
        let mounted = true;

        apiFetch<{ ticket: string }>('/api/auth/ticket')
          .then(res => {
            if (!mounted) return;
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.port === '5173' ? 'localhost:8501' : window.location.host;
            ws = new WebSocket(`${protocol}//${host}/ws/events?ticket=${res.ticket}`);

            ws.onopen = () => setConnected(true);
            ws.onclose = () => setConnected(false);
            ws.onmessage = (msg) => {
              try {
                const data = JSON.parse(msg.data);
                if (data.type === 'heartbeat') return;
                setEvents((prev: LiveEvent[]) => [data, ...prev].slice(0, 50));
              } catch (e) {
                console.error("WS error", e);
              }
            };
          })
          .catch(err => console.error("Failed to get WS ticket", err));

        return () => {
          mounted = false;
          if (ws) ws.close();
        };
      }, []);

      return { events, connected };
    }
    '''))

stats_ts = os.path.join(FRONTEND_DIR, "hooks/useLiveStats.ts")
with open(stats_ts, "w") as f:
    f.write(textwrap.dedent('''\
    import { useState, useEffect } from 'react';
    import type { SystemStats } from '../types';
    import { apiFetch } from '../api/client';

    export function useLiveStats() {
      const [stats, setStats] = useState<SystemStats | null>(null);
      const [connected, setConnected] = useState(false);

      useEffect(() => {
        let ws: WebSocket;
        let mounted = true;

        apiFetch<{ ticket: string }>('/api/auth/ticket')
          .then(res => {
            if (!mounted) return;
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.port === '5173' ? 'localhost:8501' : window.location.host;
            ws = new WebSocket(`${protocol}//${host}/ws/stats?ticket=${res.ticket}`);

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
          })
          .catch(err => console.error("Failed to get WS ticket", err));

        return () => {
          mounted = false;
          if (ws) ws.close();
        };
      }, []);

      return { stats, connected };
    }
    '''))
