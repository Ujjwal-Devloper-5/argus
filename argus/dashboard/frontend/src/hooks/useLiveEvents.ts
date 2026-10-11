import { useState } from 'react';
import { useWebSocket } from './useWebSocket';
import type { LiveEvent } from '../types';

export function useLiveEvents() {
  const [events, setEvents] = useState<LiveEvent[]>([]);

  const { connected } = useWebSocket({
    endpoint: '/ws/events',
    onMessage: (data) => {
      setEvents(prev => [data as LiveEvent, ...prev].slice(0, 50));
    },
  });

  return { events, connected };
}
