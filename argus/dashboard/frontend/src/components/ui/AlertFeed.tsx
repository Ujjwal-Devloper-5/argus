import React from 'react';
import { LiveEvent } from '../../types';

function formatRelativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

export function AlertFeed({ events }: { events: LiveEvent[] }) {
  return (
    <div className="flex flex-col gap-2">
      {events.map((ev, idx) => (
        <div key={ev.id ?? idx} className="p-3 bg-muted/30 border border-border rounded-lg flex gap-3">
          <div className={`w-2 rounded-full ${ev.is_suspicious ? 'bg-destructive' : 'bg-primary'}`} />
          <div className="flex-1">
            <div className="flex items-center justify-between mb-1">
              <span className="font-bold text-sm">{ev.camera_name}</span>
              <span className="text-xs text-muted-foreground">{formatRelativeTime(ev.created_at)}</span>
            </div>
            <p className="text-sm text-foreground line-clamp-2">{ev.message}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
