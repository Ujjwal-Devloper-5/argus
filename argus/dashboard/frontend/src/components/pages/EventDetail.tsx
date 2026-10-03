import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { ClipPlayer } from '../ui/ClipPlayer';

export default function EventDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <button onClick={() => navigate(-1)} className="flex items-center text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4 mr-2" /> Back to Events
      </button>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Event #{id}</h1>
        <span className="px-3 py-1 rounded-full bg-destructive/20 text-destructive font-bold text-sm border border-destructive/30">🚨 CRITICAL</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-4">
          <div className="bg-card border border-border rounded-xl p-4 aspect-video flex items-center justify-center text-muted-foreground">
            [Camera Snapshot Thumbnail]
          </div>
          <ClipPlayer src={null} />
        </div>
        
        <div className="space-y-6">
          <div className="bg-card border border-border rounded-xl p-5">
            <h2 className="font-bold mb-3 border-b border-border pb-2">LLM Analysis</h2>
            <p className="text-sm text-foreground mb-4">Unknown individual lingering near entrance for &gt;2 minutes, exhibiting suspicious body language while looking at the lock.</p>
            <div className="text-sm mb-2"><span className="text-muted-foreground">Recommendation:</span> Dispatch guard</div>
            <div className="text-sm mb-2"><span className="text-muted-foreground">Confidence:</span> 94%</div>
            <div className="text-sm text-destructive font-semibold">Laya Escalated: YES</div>
          </div>

          <div className="bg-card border border-border rounded-xl p-5">
            <h2 className="font-bold mb-3 border-b border-border pb-2">Face Match</h2>
            <div className="text-sm mb-4">Similarity: 18% (Unknown)</div>
            <div className="flex gap-3">
              <button className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:bg-primary/90">Enroll / Identify</button>
              <button className="px-4 py-2 border border-border rounded-lg text-sm font-semibold hover:bg-muted">Ignore</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
