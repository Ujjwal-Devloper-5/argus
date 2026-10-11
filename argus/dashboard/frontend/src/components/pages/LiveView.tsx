import { useEffect, useState } from 'react';
import { apiFetch } from '../../api/client';
import type { CameraStatus } from '../../types';

export default function LiveView() {
  const [cameras, setCameras] = useState<CameraStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  

  useEffect(() => {
    apiFetch<CameraStatus[]>('/api/cameras')
      .then(setCameras)
      .catch(err => setError(err.message));
      
    // Auto-refresh snapshot timestamp every 2 seconds for a pseudo-live feed
    
  }, []);

  if (error) return <div className="p-6 text-destructive">Error loading cameras: {error}</div>;

  return (
    <div className="p-6 h-full flex flex-col">
      <h1 className="text-xl font-bold mb-4">Live Camera Grid</h1>
      {cameras.length === 0 ? (
        <div className="text-muted-foreground">No cameras configured. Go to Settings to add one.</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {cameras.map(cam => (
            <div key={cam.name} className="relative rounded-xl border border-border overflow-hidden bg-black aspect-video flex items-center justify-center group">
              {cam.is_online ? (
                <img 
                  src={`/api/cameras/${cam.name}/stream`} 
                  alt={cam.name}
                  className="w-full h-full object-contain"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none';
                    (e.target as HTMLImageElement).parentElement?.classList.add('bg-muted');
                  }}
                />
              ) : (
                <span className="text-destructive font-bold">OFFLINE</span>
              )}
              
              <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 p-3 opacity-0 group-hover:opacity-100 transition-opacity">
                <div className="flex items-center justify-between">
                  <span className="text-white text-sm font-bold">{cam.name}</span>
                  <div className="flex items-center gap-1.5">
                    <div className={`w-2 h-2 rounded-full ${cam.is_online ? 'bg-success pulse-online' : 'bg-muted'}`} />
                    <span className={`text-[10px] font-bold ${cam.is_online ? 'text-success' : 'text-muted-foreground'}`}>
                      {cam.is_online ? 'LIVE' : 'OFFLINE'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
