import React from 'react';
import { Search, Bell, Sun, Moon } from 'lucide-react';

export function Header({ activeId }: { activeId: string }) {
  const titles: Record<string, string> = {
    overview: 'Overview',
    live: 'Live View',
    events: 'Events',
    faces: 'Face Gallery',
    system: 'System Health',
    settings: 'Settings'
  };

  const title = titles[activeId] || 'Dashboard';

  return (
    <header className="h-14 border-b border-border flex items-center px-4 justify-between bg-card/40 shrink-0">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Argus</span>
        <span>/</span>
        <span className="font-semibold text-foreground">{title}</span>
      </div>

      <div className="flex items-center gap-3">
        <div className="hidden md:flex items-center gap-1.5 px-2 py-1 rounded-md border border-warning/50 bg-warning/10 text-warning text-xs font-bold">
          [●●●●○] ELEVATED
        </div>

        <button className="p-2 rounded-lg text-muted-foreground hover:bg-muted transition-colors relative">
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-destructive pulse-critical" />
        </button>

        <button className="p-2 rounded-lg text-muted-foreground hover:bg-muted transition-colors">
          <Moon className="w-4 h-4" />
        </button>

        <div className="w-8 h-8 rounded-full bg-primary/20 border border-primary flex items-center justify-center font-bold text-xs text-primary ml-2">
          AD
        </div>
      </div>
    </header>
  );
}
