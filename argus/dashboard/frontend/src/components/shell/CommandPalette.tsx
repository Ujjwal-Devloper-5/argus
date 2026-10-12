import React, { useState, useEffect } from 'react';
import { Search, X, Monitor, Camera, ShieldAlert, Users, Activity, Settings as SettingsIcon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface CommandItem {
  label: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
}

const COMMANDS: CommandItem[] = [
  { label: 'Overview Dashboard', path: '/', icon: Monitor, description: 'Incident telemetry, threat levels, and live events' },
  { label: 'Live Camera Monitoring', path: '/live', icon: Camera, description: 'Multi-camera grid with streaming video' },
  { label: 'Events & Threats Feed', path: '/events', icon: ShieldAlert, description: 'Search and inspect AI-detected incidents' },
  { label: 'Face Gallery & Biometrics', path: '/faces', icon: Users, description: 'Enrolled identities and AutoLearner candidate review' },
  { label: 'System Health & Metrics', path: '/system', icon: Activity, description: 'GPU, CPU, RAM, and streaming bus status' },
  { label: 'Configuration & Settings', path: '/settings', icon: SettingsIcon, description: 'Tune YOLOv8, LLM prompts, cameras, and bots' },
];

export function CommandPalette() {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      }
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  if (!isOpen) return null;

  const filtered = COMMANDS.filter(
    (c) =>
      c.label.toLowerCase().includes(query.toLowerCase()) ||
      c.description.toLowerCase().includes(query.toLowerCase())
  );

  const handleSelect = (path: string) => {
    navigate(path);
    setIsOpen(false);
    setQuery('');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/60 backdrop-blur-sm p-4">
      <div className="absolute inset-0" onClick={() => setIsOpen(false)} />
      <div className="relative w-full max-w-xl bg-card border border-border rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-100">
        <div className="flex items-center px-4 border-b border-border">
          <Search className="w-4 h-4 text-muted-foreground mr-3" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1 bg-transparent py-3.5 outline-none text-sm text-foreground placeholder:text-muted-foreground"
            placeholder="Search commands, views, cameras, or settings..."
          />
          <button
            onClick={() => setIsOpen(false)}
            className="p-1 rounded-lg text-muted-foreground hover:bg-muted transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-2 max-h-[340px] overflow-y-auto space-y-1">
          <div className="px-3 py-1.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            Navigation & Controls
          </div>

          {filtered.length === 0 ? (
            <div className="p-6 text-center text-xs text-muted-foreground">
              No commands matching "{query}"
            </div>
          ) : (
            filtered.map((item) => {
              const Icon = item.icon;
              return (
                <div
                  key={item.path}
                  onClick={() => handleSelect(item.path)}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-primary/10 hover:text-primary cursor-pointer text-sm transition-colors group"
                >
                  <div className="p-1.5 rounded-lg bg-muted group-hover:bg-primary/20 text-muted-foreground group-hover:text-primary transition">
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-foreground group-hover:text-primary text-xs">
                      {item.label}
                    </div>
                    <div className="text-[11px] text-muted-foreground truncate">
                      {item.description}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="border-t border-border px-4 py-2 bg-muted/20 flex justify-between items-center text-[11px] text-muted-foreground">
          <span>Press ESC to exit</span>
          <span className="font-mono">Ctrl + K</span>
        </div>
      </div>
    </div>
  );
}
