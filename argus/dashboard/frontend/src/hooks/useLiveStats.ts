import { useState } from 'react';
import { useWebSocket } from './useWebSocket';
import type { SystemStats } from '../types';

export function useLiveStats() {
  const [stats, setStats] = useState<SystemStats | null>(null);

  const { connected } = useWebSocket({
    endpoint: '/ws/stats',
    onMessage: (data) => {
      setStats(data as SystemStats);
    },
  });

  return { stats, connected };
}
