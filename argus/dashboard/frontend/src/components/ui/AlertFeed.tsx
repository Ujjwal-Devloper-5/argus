import React from 'react';
import { LiveEvent } from '../../types';
import { SeverityBadge } from './SeverityBadge';

export function AlertFeed({ events }: { events: LiveEvent[] }) {
  return (
    <div className="flex flex-col gap-2">
      {events.map(ev => (
        <div key={ev.event_id} className="p-3 bg-muted/30 border border-border rounded-lg flex gap-3">
          <div className={`w-2 rounded-full ${ev.is_suspicious ? 'bg-destructive' : 'bg-primary'}`} />
          <div className="flex-1">
            <div className="flex items-center justify-between mb-1">
              <span className="font-bold text-sm">{ev.camera}</span>
              <span className="text-xs text-muted-foreground">Just now</span>
            </div>
            <p className="text-sm text-foreground line-clamp-2">{ev.llm_description}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
