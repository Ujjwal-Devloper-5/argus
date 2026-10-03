import React from 'react';
import { VideoOff } from 'lucide-react';

export function ClipPlayer({ src }: { src: string | null }) {
  if (!src) return <div className="aspect-video bg-muted rounded-lg flex items-center justify-center text-muted-foreground"><VideoOff className="w-8 h-8 mr-2"/>No clip recorded</div>;
  return <video controls className="w-full rounded-lg shadow-lg border border-border" src={src} />;
}
