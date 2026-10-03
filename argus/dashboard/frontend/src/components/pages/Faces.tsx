import React from 'react';
import { Upload, User } from 'lucide-react';

export default function Faces() {
  return (
    <div className="p-6 space-y-8">
      <div>
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold">Known Faces</h1>
          <button className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:bg-primary/90">Enroll New Face</button>
        </div>
        
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {[1,2,3].map(i => (
            <div key={i} className="bg-card border border-border rounded-xl p-4 text-center flex flex-col items-center">
              <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-3">
                <User className="w-8 h-8 text-muted-foreground" />
              </div>
              <span className="font-semibold text-sm">Employee {i}</span>
              <span className="text-xs text-muted-foreground">42 events</span>
            </div>
          ))}
        </div>
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
