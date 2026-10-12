import React, { useEffect, useState } from 'react';
import { Bell, Sun, Moon, ShieldAlert, ShieldCheck } from 'lucide-react';
import { apiFetch } from '../../api/client';

export function Header({ activeId }: { activeId: string }) {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
  });
  const [username, setUsername] = useState('Admin');
  const [threatLevel, setThreatLevel] = useState<string>('LOW');

  useEffect(() => {
    // Fetch authenticated user
    apiFetch<{ username: string }>('/api/auth/me')
      .then((res) => setUsername(res.username || 'Admin'))
      .catch(() => {});

    // Fetch threat stats
    apiFetch<{ threat_level: string }>('/api/events/stats')
      .then((res) => setThreatLevel(res.threat_level || 'LOW'))
      .catch(() => {});
  }, []);

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    localStorage.setItem('argus_theme', next);
    document.documentElement.classList.toggle('dark', next === 'dark');
  };

  const titles: Record<string, string> = {
    overview: 'Overview',
    live: 'Live Monitoring',
    events: 'Events Feed',
    faces: 'Face Gallery',
    system: 'System Health',
    settings: 'Settings',
  };

  const title = titles[activeId] || 'Dashboard';
  const initials = username.slice(0, 2).toUpperCase();

  const threatStyle = {
    CRITICAL: 'border-destructive/50 bg-destructive/10 text-destructive',
    HIGH: 'border-destructive/40 bg-destructive/10 text-destructive',
    ELEVATED: 'border-warning/50 bg-warning/10 text-warning',
    LOW: 'border-success/50 bg-success/10 text-success',
  }[threatLevel] || 'border-border bg-muted text-muted-foreground';

  return (
    <header className="h-14 border-b border-border flex items-center px-4 justify-between bg-card/60 backdrop-blur shrink-0">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className="font-semibold text-foreground/80">Argus NVR</span>
        <span>/</span>
        <span className="font-bold text-foreground">{title}</span>
      </div>

      <div className="flex items-center gap-3">
        {/* Dynamic Threat Level */}
        <div
          className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-xs font-bold uppercase tracking-wider ${threatStyle}`}
        >
          {threatLevel === 'LOW' ? (
            <ShieldCheck className="w-3.5 h-3.5" />
          ) : (
            <ShieldAlert className="w-3.5 h-3.5 animate-pulse" />
          )}
          <span>{threatLevel} THREAT</span>
        </div>

        {/* Theme Toggle Button */}
        <button
          onClick={toggleTheme}
          title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
          className="p-2 rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        >
          {theme === 'dark' ? <Sun className="w-4 h-4 text-warning" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* User Avatar */}
        <div
          title={`Logged in as ${username}`}
          className="w-8 h-8 rounded-full bg-primary/20 border border-primary/40 flex items-center justify-center font-bold text-xs text-primary ml-1 shadow-sm"
        >
          {initials}
        </div>
      </div>
    </header>
  );
}
