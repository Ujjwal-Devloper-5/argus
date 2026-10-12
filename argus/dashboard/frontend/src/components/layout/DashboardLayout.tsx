import React, { useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from '../shell/Sidebar';
import { Header } from '../shell/Header';
import { CommandPalette } from '../shell/CommandPalette';

export function DashboardLayout() {
  const location = useLocation();
  const path = location.pathname.replace('/', '') || 'overview';
  const [activeId, setActiveId] = useState(path);

  return (
    <div className="w-screen h-screen flex bg-background text-foreground overflow-hidden font-sans">
      <Sidebar activeId={activeId} onSelect={setActiveId} />
      <div className="flex-1 flex flex-col min-w-0 bg-background overflow-hidden relative">
        <Header activeId={activeId} />
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
      <CommandPalette />
    </div>
  );
}
