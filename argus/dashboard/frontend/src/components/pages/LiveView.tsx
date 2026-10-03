import React from 'react';

const cameras = [
  { name: 'front_door', is_online: true, has_critical: true },
  { name: 'garage', is_online: true, has_critical: false },
  { name: 'backyard', is_online: true, has_critical: false },
  { name: 'driveway', is_online: false, has_critical: false },
];

export default function LiveView() {
  return (
    <div className="p-6 h-full flex flex-col">
      <h1 className="text-xl font-bold mb-4">Live Camera Grid</h1>
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        {cameras.map(cam => (
          <div key={cam.name} className="relative rounded-xl border border-border overflow-hidden bg-muted aspect-video flex items-center justify-center">
            {cam.is_online ? (
              <span className="text-muted-foreground">Camera Feed: {cam.name}</span>
            ) : (
              <span className="text-destructive font-bold">OFFLINE</span>
            )}
            
            <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 p-3">
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
            
            {cam.has_critical && <div className="absolute inset-0 border-2 border-destructive rounded-xl pulse-critical pointer-events-none" />}
          </div>
        ))}
      </div>
    </div>
  );
}
