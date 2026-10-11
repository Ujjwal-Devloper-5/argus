import os

FRONTEND_DIR = "/home/ujjwal/homelab/argus/argus/dashboard/frontend/src"

events_path = os.path.join(FRONTEND_DIR, "components/pages/Events.tsx")
with open(events_path, "w") as f:
    f.write("""import { useEffect, useState } from 'react';
import { SeverityBadge } from '../ui/SeverityBadge';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../../api/client';
import type { EventSummary } from '../../types';

export default function Events() {
  const navigate = useNavigate();
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<{items: EventSummary[]}>('/api/events')
      .then(res => setEvents(res.items))
      .catch(console.error)
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
                <td className="px-4 py-3 truncate max-w-xs">{ev.llm_analysis || "No analysis"}</td>
                <td className="px-4 py-3">{ev.similarity_score ? Math.round(ev.similarity_score * 100) + '%' : 'N/A'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
""")

faces_path = os.path.join(FRONTEND_DIR, "components/pages/Faces.tsx")
with open(faces_path, "w") as f:
    f.write("""import { useEffect, useState } from 'react';
import { Upload, User, Trash2 } from 'lucide-react';
import { apiFetch } from '../../api/client';
import type { FaceProfile } from '../../types';

export default function Faces() {
  const [faces, setFaces] = useState<FaceProfile[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadFaces();
  }, []);

  const loadFaces = () => {
    setLoading(true);
    apiFetch<FaceProfile[]>('/api/faces')
      .then(setFaces)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  const deleteFace = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this face?')) return;
    apiFetch(`/api/faces?face_id=${id}`, { method: 'DELETE' })
      .then(loadFaces)
      .catch(console.error);
  };

  return (
    <div className="p-6 space-y-8">
      <div>
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold">Known Faces</h1>
          <button className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:bg-primary/90 transition">Enroll New Face</button>
        </div>
        
        {loading ? <div className="text-muted-foreground p-8 text-center">Loading faces...</div> :
         faces.length === 0 ? <div className="text-muted-foreground p-8 text-center bg-card border border-border rounded-xl">No known faces enrolled yet.</div> :
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {faces.map(face => (
            <div key={face.face_id} className="bg-card border border-border rounded-xl p-4 text-center flex flex-col items-center relative group">
              <button onClick={(e) => deleteFace(face.face_id, e)} className="absolute top-2 right-2 p-1.5 bg-destructive text-destructive-foreground rounded opacity-0 group-hover:opacity-100 transition">
                <Trash2 className="w-3 h-3" />
              </button>
              <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-3 overflow-hidden border border-border">
                {face.thumbnail_path ? (
                  <img src={`/api/faces/img/${face.face_id}`} alt={face.name} className="w-full h-full object-cover" />
                ) : (
                  <User className="w-8 h-8 text-muted-foreground" />
                )}
              </div>
              <span className="font-semibold text-sm truncate w-full">{face.name}</span>
              <span className="text-xs text-muted-foreground">{face.appearances} events</span>
            </div>
          ))}
        </div>}
      </div>

      <div className="border-t border-border pt-8">
        <h2 className="text-lg font-bold mb-4">Unknown Regulars</h2>
        <div className="bg-card border border-border rounded-xl p-8 text-center border-dashed">
          <Upload className="mx-auto mb-2 text-muted-foreground w-8 h-8" />
          <p className="text-muted-foreground text-sm mb-4">Drop face photos here or click to browse to manually enroll</p>
          <p className="text-xs text-muted-foreground">Auto-learning will surface frequent unknown faces here.</p>
        </div>
      </div>
    </div>
  );
}
""")

print("Events and Faces components patched.")
