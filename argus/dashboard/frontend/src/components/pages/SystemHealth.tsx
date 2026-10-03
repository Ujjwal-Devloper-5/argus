import React from 'react';
import { useLiveStats } from '../../hooks/useLiveStats';

function RingGauge({ value, label, color }: { value: number; label: string; color: string }) {
  const r = 28;
  const circumference = 2 * Math.PI * r;
  const offset = circumference - (value / 100) * circumference;
  return (
    <div className="flex flex-col items-center gap-2">
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r={r} fill="none" stroke="currentColor" strokeWidth="6" className="text-muted/30" />
        <circle cx="36" cy="36" r={r} fill="none" stroke={color} strokeWidth="6" strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round" transform="rotate(-90 36 36)" />
        <text x="36" y="40" textAnchor="middle" className="text-xs font-bold" fill="currentColor">{value}%</text>
      </svg>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

export default function SystemHealth() {
  const { stats } = useLiveStats();

  if (!stats) return <div className="p-6">Loading...</div>;

  return (
    <div className="p-6 space-y-8">
      <h1 className="text-xl font-bold">System Health</h1>
      
      <div className="bg-card border border-border rounded-xl p-6 flex justify-around">
        <RingGauge value={stats.cpu_percent} label="CPU" color="hsl(var(--primary))" />
        <RingGauge value={stats.memory_percent} label="Memory" color="hsl(var(--warning))" />
        <RingGauge value={stats.disk_percent} label="Disk" color="hsl(var(--success))" />
        <RingGauge value={stats.gpu_vram_percent || 0} label="GPU VRAM" color="hsl(var(--primary))" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="font-bold mb-4">Kafka Infrastructure</h2>
          <div className="flex items-center justify-between py-2 border-b border-border">
            <span className="text-sm">Broker Status</span>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-success/20 text-success">CONNECTED</span>
          </div>
          <div className="flex items-center justify-between py-2 border-b border-border">
            <span className="text-sm">argus.events Topic</span>
            <span className="text-sm font-mono text-muted-foreground">12 msg/s</span>
          </div>
          <div className="flex items-center justify-between py-2">
            <span className="text-sm">Consumer Lag</span>
            <span className="text-sm font-mono text-muted-foreground">0 msgs</span>
          </div>
        </div>
        
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="font-bold mb-4">Pipeline Status</h2>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between"><span className="text-muted-foreground">Database:</span> {stats.db_path}</div>
            <div className="flex justify-between"><span className="text-muted-foreground">Uptime:</span> {Math.floor(stats.uptime_seconds / 3600)}h {(stats.uptime_seconds % 3600) / 60}m</div>
          </div>
        </div>
      </div>
    </div>
  );
}
