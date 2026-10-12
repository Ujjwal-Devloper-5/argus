import { useState, useEffect, useRef } from 'react';
import { apiFetch } from '../api/client';
import { useAuth } from '../context/AuthContext';

interface WebSocketOptions {
  endpoint: string; // e.g. '/ws/events'
  onMessage: (data: unknown) => void;
  enabled?: boolean;
}

export function useWebSocket({ endpoint, onMessage, enabled = true }: WebSocketOptions) {
  const { isAuthenticated } = useAuth();
  const [connected, setConnected] = useState(false);
  const [reconnectCount, setReconnectCount] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const mountedRef = useRef(true);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onMessageRef = useRef(onMessage);

  // Keep onMessageRef up to date without triggering reconnection loops
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    mountedRef.current = true;

    // Do NOT connect if disabled or not authenticated
    if (!enabled || !isAuthenticated) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setConnected(false);
      return;
    }

    let retryCount = 0;

    const connect = async () => {
      if (!mountedRef.current || !isAuthenticated) return;

      try {
        const res = await apiFetch<{ ticket: string }>('/api/auth/ticket');
        if (!mountedRef.current || !isAuthenticated) return;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.port === '5173' ? 'localhost:8501' : window.location.host;
        const ws = new WebSocket(`${protocol}//${host}${endpoint}?ticket=${res.ticket}`);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!mountedRef.current) {
            ws.close();
            return;
          }
          setConnected(true);
          retryCount = 0;
          setReconnectCount(0);
        };

        ws.onclose = () => {
          if (!mountedRef.current) return;
          setConnected(false);
          wsRef.current = null;

          // Exponential backoff: 2s, 4s, 8s, up to 30s
          const delay = Math.min(2000 * Math.pow(1.5, retryCount), 30000);
          retryCount++;
          setReconnectCount(retryCount);
          retryTimerRef.current = setTimeout(connect, delay);
        };

        ws.onmessage = (msg) => {
          try {
            const data = JSON.parse(msg.data);
            if (data?.type === 'heartbeat') return;
            onMessageRef.current(data);
          } catch (e) {
            console.error('WS parse error:', e);
          }
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch (err) {
        if (!mountedRef.current) return;
        // Ticket acquisition failed — retry with backoff
        const delay = Math.min(3000 * Math.pow(1.5, retryCount), 30000);
        retryCount++;
        setReconnectCount(retryCount);
        retryTimerRef.current = setTimeout(connect, delay);
      }
    };

    connect();

    return () => {
      mountedRef.current = false;
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [endpoint, enabled, isAuthenticated]);

  return { connected, reconnectCount };
}
