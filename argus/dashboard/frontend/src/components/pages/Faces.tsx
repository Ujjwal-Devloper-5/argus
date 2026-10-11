import { useEffect, useState } from 'react';
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

  const deleteFace = (id: number, e: React.MouseEvent) => {
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
            <div key={face.id} className="bg-card border border-border rounded-xl p-4 text-center flex flex-col items-center relative group">
              <button onClick={(e) => deleteFace(face.id, e)} className="absolute top-2 right-2 p-1.5 bg-destructive text-destructive-foreground rounded opacity-0 group-hover:opacity-100 transition">
                <Trash2 className="w-3 h-3" />
              </button>
              <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-3 overflow-hidden border border-border">
                {face.thumbnail_path ? (
                  <img src={`/api/faces/img/${face.id}`} alt={face.name} className="w-full h-full object-cover" />
                ) : (
                  <User className="w-8 h-8 text-muted-foreground" />
                )}
              </div>
              <span className="font-semibold text-sm truncate w-full">{face.name}</span>
              <span className="text-xs text-muted-foreground">{face.total_events} events</span>
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
