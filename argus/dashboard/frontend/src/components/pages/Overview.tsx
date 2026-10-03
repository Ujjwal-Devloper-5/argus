import React from 'react';
import { StatCard } from '../ui/StatCard';
import { AlertFeed } from '../ui/AlertFeed';
import { useLiveEvents } from '../../hooks/useLiveEvents';
import { useLiveStats } from '../../hooks/useLiveStats';
import { AlertTriangle, Camera, Bell, Users } from 'lucide-react';

export default function Overview() {
  const { events } = useLiveEvents();
  const { stats } = useLiveStats();

  if (!stats) return <div className="p-6">Loading...</div>;

  return (
    <div className="p-6 space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Events Today" value={stats.total_events_today} icon={AlertTriangle} />
        <StatCard title="Cameras Online" value="4 / 4" icon={Camera} />
        <StatCard title="Alerts Sent" value={stats.total_alerts_sent} icon={Bell} />
        <StatCard title="Faces Enrolled" value="12" icon={Users} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <h2 className="font-semibold">Live Alert Feed</h2>
          <AlertFeed events={events} />
        </div>
        <div className="space-y-4">
          <h2 className="font-semibold">Event Severity Breakdown</h2>
          <div className="bg-card border border-border rounded-xl p-4 flex items-end gap-2 h-48">
            <div className="flex-1 bg-primary/20 h-[60%] rounded-t relative group"><span className="absolute -top-6 left-1/2 -translate-x-1/2 text-xs opacity-0 group-hover:opacity-100">Info</span></div>
            <div className="flex-1 bg-warning/20 h-[30%] rounded-t relative group"><span className="absolute -top-6 left-1/2 -translate-x-1/2 text-xs opacity-0 group-hover:opacity-100">Warning</span></div>
            <div className="flex-1 bg-destructive/40 h-[10%] rounded-t relative group"><span className="absolute -top-6 left-1/2 -translate-x-1/2 text-xs opacity-0 group-hover:opacity-100">Critical</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}
