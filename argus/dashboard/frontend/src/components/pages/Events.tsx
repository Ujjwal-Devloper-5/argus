import React from 'react';
import { SeverityBadge } from '../ui/SeverityBadge';
import { useNavigate } from 'react-router-dom';

const mockEvents = [
  { id: 1001, camera_name: 'front_door', severity: 'critical' as const, is_suspicious: true, created_at: '2023-10-01T14:52:00Z', llm_description: 'Unknown individual lingering...', similarity_score: 0.18 },
  { id: 1000, camera_name: 'garage', severity: 'info' as const, is_suspicious: false, created_at: '2023-10-01T14:40:00Z', llm_description: 'Person walking across driveway', similarity_score: 0.95 },
];

export default function Events() {
  const navigate = useNavigate();
  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">Security Events</h1>
        <div className="flex gap-2">
          <select className="bg-card border border-border rounded px-3 py-1 text-sm outline-none"><option>All Cameras</option></select>
          <select className="bg-card border border-border rounded px-3 py-1 text-sm outline-none"><option>All Severities</option></select>
        </div>
      </div>
      
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">Severity</th>
              <th className="px-4 py-3 font-medium">Time</th>
              <th className="px-4 py-3 font-medium">Camera</th>
              <th className="px-4 py-3 font-medium">Description</th>
              <th className="px-4 py-3 font-medium">Match</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {mockEvents.map(ev => (
              <tr key={ev.id} onClick={() => navigate(`/events/${ev.id}`)} className="hover:bg-muted/50 cursor-pointer">
                <td className="px-4 py-3"><SeverityBadge severity={ev.severity} /></td>
                <td className="px-4 py-3">{new Date(ev.created_at).toLocaleTimeString()}</td>
                <td className="px-4 py-3">{ev.camera_name}</td>
                <td className="px-4 py-3 truncate max-w-xs">{ev.llm_description}</td>
                <td className="px-4 py-3">{Math.round(ev.similarity_score * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
