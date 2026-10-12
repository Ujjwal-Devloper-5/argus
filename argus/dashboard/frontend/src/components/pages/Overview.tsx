import React, { useEffect, useState } from 'react';
import { StatCard } from '../ui/StatCard';
import { AlertFeed } from '../ui/AlertFeed';
import { useLiveEvents } from '../../hooks/useLiveEvents';
import { useLiveStats } from '../../hooks/useLiveStats';
import { apiFetch } from '../../api/client';
import { AlertTriangle, Activity, Bell, Shield, ShieldAlert, Cpu } from 'lucide-react';

interface EventStats {
  total_24h: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
  threat_level: string;
  severity_distribution: {
    critical: number;
    warning: number;
    info: number;
  };
}

export default function Overview() {
  const { events } = useLiveEvents();
  const { stats } = useLiveStats();
  const [eventStats, setEventStats] = useState<EventStats | null>(null);

  useEffect(() => {
    apiFetch<EventStats>('/api/events/stats')
      .then(setEventStats)
      .catch((err) => console.error('Failed to fetch event stats:', err));
  }, [events]);

  const total = eventStats?.total_24h || 1;
  const critPct = eventStats ? Math.max(8, Math.round((eventStats.critical_count / total) * 100)) : 10;
  const warnPct = eventStats ? Math.max(8, Math.round((eventStats.warning_count / total) * 100)) : 30;
  const infoPct = eventStats ? Math.max(8, Math.round((eventStats.info_count / total) * 100)) : 60;

  const threatColor = {
    CRITICAL: 'text-destructive bg-destructive/10 border-destructive/30',
    HIGH: 'text-destructive bg-destructive/10 border-destructive/20',
    ELEVATED: 'text-warning bg-warning/10 border-warning/20',
    LOW: 'text-success bg-success/10 border-success/20',
  }[eventStats?.threat_level || 'LOW'];

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Top Banner / Threat Status */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-card border border-border p-4 rounded-xl shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg text-primary">
            <Shield className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-lg font-bold">Argus Vision Command Center</h1>
            <p className="text-xs text-muted-foreground">Real-time edge neural surveillance active</p>
          </div>
        </div>
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border font-semibold text-xs tracking-wider uppercase ${threatColor}`}>
          <ShieldAlert className="w-4 h-4" />
          <span>Threat Level: {eventStats?.threat_level || 'MONITORING'}</span>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Events (24h)"
          value={eventStats?.total_24h ?? stats?.total_events_today ?? 0}
          icon={AlertTriangle}
        />
        <StatCard
          title="CPU Load"
          value={stats ? `${stats.cpu_percent.toFixed(0)}%` : '---'}
          icon={Cpu}
        />
        <StatCard
          title="Memory Utilized"
          value={stats ? `${stats.memory_percent.toFixed(0)}%` : '---'}
          icon={Activity}
        />
        <StatCard
          title="Alerts Dispatched"
          value={stats?.total_alerts_sent ?? 0}
          icon={Bell}
        />
      </div>

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-base">Live Activity Feed</h2>
            <span className="text-xs text-muted-foreground">Rolling 50 incidents</span>
          </div>
          <AlertFeed events={events} />
        </div>

        <div className="space-y-4">
          <h2 className="font-semibold text-base">Incident Severity Distribution</h2>
          <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-4">
            <div className="flex items-end justify-around gap-4 h-48 pt-6 pb-2 border-b border-border/50">
              {/* Info Bar */}
              <div className="flex-1 flex flex-col items-center gap-2 h-full justify-end">
                <span className="text-xs font-semibold text-muted-foreground">
                  {eventStats?.info_count ?? 0}
                </span>
                <div
                  style={{ height: `${infoPct}%` }}
                  className="w-full bg-primary/30 hover:bg-primary/50 transition-all rounded-t-md relative group cursor-pointer"
                >
                  <span className="absolute -top-7 left-1/2 -translate-x-1/2 text-[10px] bg-popover px-1.5 py-0.5 rounded shadow border border-border opacity-0 group-hover:opacity-100 transition-opacity">
                    Info
                  </span>
                </div>
                <span className="text-[11px] font-medium text-muted-foreground">Info</span>
              </div>

              {/* Warning Bar */}
              <div className="flex-1 flex flex-col items-center gap-2 h-full justify-end">
                <span className="text-xs font-semibold text-warning">
                  {eventStats?.warning_count ?? 0}
                </span>
                <div
                  style={{ height: `${warnPct}%` }}
                  className="w-full bg-warning/30 hover:bg-warning/50 transition-all rounded-t-md relative group cursor-pointer"
                >
                  <span className="absolute -top-7 left-1/2 -translate-x-1/2 text-[10px] bg-popover px-1.5 py-0.5 rounded shadow border border-border opacity-0 group-hover:opacity-100 transition-opacity">
                    Warning
                  </span>
                </div>
                <span className="text-[11px] font-medium text-warning">Warning</span>
              </div>

              {/* Critical Bar */}
              <div className="flex-1 flex flex-col items-center gap-2 h-full justify-end">
                <span className="text-xs font-semibold text-destructive">
                  {eventStats?.critical_count ?? 0}
                </span>
                <div
                  style={{ height: `${critPct}%` }}
                  className="w-full bg-destructive/40 hover:bg-destructive/60 transition-all rounded-t-md relative group cursor-pointer"
                >
                  <span className="absolute -top-7 left-1/2 -translate-x-1/2 text-[10px] bg-popover px-1.5 py-0.5 rounded shadow border border-border opacity-0 group-hover:opacity-100 transition-opacity">
                    Critical
                  </span>
                </div>
                <span className="text-[11px] font-medium text-destructive">Critical</span>
              </div>
            </div>

            <div className="grid grid-cols-3 text-center text-xs text-muted-foreground pt-1">
              <div>
                <span className="block font-bold text-foreground">{eventStats?.info_count ?? 0}</span>
                <span>Normal</span>
              </div>
              <div>
                <span className="block font-bold text-warning">{eventStats?.warning_count ?? 0}</span>
                <span>Anomalies</span>
              </div>
              <div>
                <span className="block font-bold text-destructive">{eventStats?.critical_count ?? 0}</span>
                <span>Threats</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
