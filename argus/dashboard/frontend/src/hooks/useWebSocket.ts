import { useState, useEffect, useRef, useCallback } from 'react';
import { apiFetch } from '../api/client';

interface WebSocketOptions {
  endpoint: string; // e.g. '/ws/events'
  onMessage: (data: unknown) => void;
}

export function useWebSocket({ endpoint, onMessage }: WebSocketOptions) {
  const [connected, setConnected] = useState(false);
  const [reconnectCount, setReconnectCount] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const mountedRef = useRef(true);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(async () => {
    if (!mountedRef.current) return;

    try {
      const res = await apiFetch<{ ticket: string }>('/api/auth/ticket');
      if (!mountedRef.current) return;

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.port === '5173' ? 'localhost:8501' : window.location.host;
      const ws = new WebSocket(`${protocol}//${host}${endpoint}?ticket=${res.ticket}`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) { ws.close(); return; }
        setConnected(true);
        setReconnectCount(0);
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setConnected(false);
        wsRef.current = null;
        // Exponential backoff: 1s, 2s, 4s, 8s, max 30s
        const delay = Math.min(1000 * Math.pow(2, reconnectCount), 30000);
        setReconnectCount(c => c + 1);
        retryTimerRef.current = setTimeout(connect, delay);
      };

      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          if (data?.type === 'heartbeat') return;
          onMessage(data);
        } catch (e) {
          console.error('WS parse error:', e);
        }
      };

      ws.onerror = () => {
        ws.close();
      };

    } catch (err) {
      if (!mountedRef.current) return;
      // Failed to get ticket (likely 401) — wait before retry
      retryTimerRef.current = setTimeout(connect, 5000);
    }
  }, [endpoint, onMessage, reconnectCount]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  return { connected, reconnectCount };
}
