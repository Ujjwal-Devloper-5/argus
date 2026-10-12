import { useEffect, useState } from 'react';
import { SeverityBadge } from '../ui/SeverityBadge';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../../api/client';
import type { EventSummary } from '../../types';

export default function Events() {
  const navigate = useNavigate();
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<EventSummary[] | {items: EventSummary[]}>('/api/events')
      .then(res => {
        const list = Array.isArray(res) ? res : ((res as any)?.items || []);
        setEvents(list);
      })
      .catch(() => setEvents([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 h-full flex flex-col">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">Security Events</h1>
        <div className="flex gap-2">
          <select className="bg-card border border-border rounded px-3 py-1 text-sm outline-none"><option>All Cameras</option></select>
          <select className="bg-card border border-border rounded px-3 py-1 text-sm outline-none"><option>All Severities</option></select>
        </div>
      </div>
      
      <div className="bg-card border border-border rounded-xl overflow-hidden overflow-y-auto flex-1">
        <table className="w-full text-left text-sm">
          <thead className="bg-muted/50 text-muted-foreground sticky top-0">
            <tr>
              <th className="px-4 py-3 font-medium">Severity</th>
              <th className="px-4 py-3 font-medium">Time</th>
              <th className="px-4 py-3 font-medium">Camera</th>
              <th className="px-4 py-3 font-medium">Description</th>
              <th className="px-4 py-3 font-medium">Match</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading ? <tr><td colSpan={5} className="p-8 text-center text-muted-foreground">Loading events...</td></tr> : 
             events.length === 0 ? <tr><td colSpan={5} className="p-8 text-center text-muted-foreground">No events found.</td></tr> :
             events.map(ev => (
              <tr key={ev.id} onClick={() => navigate(`/events/${ev.id}`)} className="hover:bg-muted/50 cursor-pointer">
                <td className="px-4 py-3"><SeverityBadge severity={ev.severity} /></td>
                <td className="px-4 py-3">{new Date(ev.created_at).toLocaleTimeString()}</td>
                <td className="px-4 py-3">{ev.camera_name}</td>
                <td className="px-4 py-3 truncate max-w-xs">{ev.llm_description || "No analysis"}</td>
                <td className="px-4 py-3">{ev.similarity_score ? Math.round(ev.similarity_score * 100) + '%' : 'N/A'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
