import { useState, useEffect } from 'react';
import type { LiveEvent } from '../types';

export function useLiveEvents() {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    setConnected(true);
    setEvents([
      {
        event_id: 1001,
        camera: 'front_door',
        face_hash: 'abc',
        is_suspicious: true,
        escalated_by_laya: true,
        confidence: 0.94,
        llm_description: 'Unknown individual lingering near entrance for >2 minutes, exhibiting suspicious body language',
        action_recommendation: 'Verify intent',
        clip_path: null,
        thumbnail_path: null,
        triggered_at: new Date().toISOString()
      },
      {
        event_id: 1000,
        camera: 'garage',
        face_hash: 'def',
        is_suspicious: false,
        escalated_by_laya: false,
        confidence: 0.71,
        llm_description: 'Person walking across driveway, normal gait',
        action_recommendation: 'None',
        clip_path: null,
        thumbnail_path: null,
        triggered_at: new Date(Date.now() - 300000).toISOString()
      }
    ]);
  }, []);

  return { events, connected };
}
