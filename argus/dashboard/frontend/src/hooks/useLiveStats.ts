import { useState, useEffect } from 'react';
import type { SystemStats } from '../types';

export function useLiveStats() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    setConnected(true);
    setStats({
      cpu_percent: 45,
      memory_percent: 62,
      disk_percent: 78,
      gpu_vram_percent: 30,
      uptime_seconds: 36000,
      total_events_today: 142,
      total_alerts_sent: 12,
      kafka_enabled: true,
      db_path: './data/argus.db'
    });
  }, []);

  return { stats, connected };
}
