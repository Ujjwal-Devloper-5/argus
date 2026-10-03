import React, { useState, useEffect } from 'react';
import { Search, X } from 'lucide-react';

export function CommandPalette() {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-background/60 backdrop-blur-sm">
      <div className="absolute inset-0" onClick={() => setIsOpen(false)} />
      <div className="relative w-full max-w-xl bg-card border border-border rounded-xl shadow-2xl overflow-hidden">
        <div className="flex items-center px-4 border-b border-border">
          <Search className="w-4 h-4 text-muted-foreground mr-3" />
          <input 
            autoFocus
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="flex-1 bg-transparent py-4 outline-none text-sm text-foreground placeholder:text-muted-foreground"
            placeholder="Search events, faces, settings..."
          />
          <button onClick={() => setIsOpen(false)} className="p-1 rounded hover:bg-muted"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-2 max-h-[300px] overflow-y-auto">
          <div className="px-2 py-1 text-[11px] font-semibold text-muted-foreground uppercase">Results</div>
          {/* Mock results */}
          <div className="px-3 py-2 rounded-lg hover:bg-muted cursor-pointer text-sm">Navigate to Settings</div>
          <div className="px-3 py-2 rounded-lg hover:bg-muted cursor-pointer text-sm">Search events for "{query}"</div>
        </div>
      </div>
    </div>
  );
}
