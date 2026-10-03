import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Sidebar } from './components/shell/Sidebar';
import { Header } from './components/shell/Header';
import { CommandPalette } from './components/shell/CommandPalette';
import Overview from './components/pages/Overview';
import LiveView from './components/pages/LiveView';
import Events from './components/pages/Events';
import EventDetail from './components/pages/EventDetail';
import Faces from './components/pages/Faces';
import SystemHealth from './components/pages/SystemHealth';
import SettingsPage from './components/pages/SettingsPage';
import SetupWizard, { CreateUserWall } from './components/pages/SetupWizard';

// ─────────────────────────────────────────────────────────────────────────────
// Bootstrap: check setup status before rendering anything
// ─────────────────────────────────────────────────────────────────────────────

type AppState = 'loading' | 'setup_wizard' | 'create_user' | 'ready';

interface SetupStatus {
  needs_setup: boolean;
  needs_user: boolean;
  config_exists: boolean;
  user_exists: boolean;
}

function LoadingScreen() {
  return (
    <div className="w-screen h-screen bg-background flex flex-col items-center justify-center gap-4">
      <div className="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center animate-pulse">
        <svg className="w-6 h-6 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.955 11.955 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
        </svg>
      </div>
      <p className="text-sm text-muted-foreground animate-pulse">Starting Argus Security Dashboard...</p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Dashboard shell
// ─────────────────────────────────────────────────────────────────────────────

function Dashboard() {
  const [activeId, setActiveId] = useState('overview');

  return (
    <BrowserRouter>
      <div className="w-screen h-screen flex bg-background text-foreground overflow-hidden font-sans">
        <Sidebar activeId={activeId} onSelect={setActiveId} />
        <div className="flex-1 flex flex-col min-w-0 bg-background overflow-hidden relative">
          <Header activeId={activeId} />
          <main className="flex-1 overflow-y-auto">
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/live" element={<LiveView />} />
              <Route path="/events" element={<Events />} />
              <Route path="/events/:id" element={<EventDetail />} />
              <Route path="/faces" element={<Faces />} />
              <Route path="/system" element={<SystemHealth />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          </main>
        </div>
        <CommandPalette />
      </div>
    </BrowserRouter>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Root App — checks setup status, routes to wizard/user-create/dashboard
// ─────────────────────────────────────────────────────────────────────────────

export default function App() {
  const [appState, setAppState] = useState<AppState>('loading');

  // Apply dark mode immediately
  useEffect(() => {
    document.documentElement.classList.add('dark');
  }, []);

  // On mount: check /api/setup/status
  useEffect(() => {
    let cancelled = false;
    const checkStatus = async () => {
      try {
        const res = await fetch('/api/setup/status');
        if (!res.ok) {
          // If server unreachable, just show dashboard (config may exist already)
          if (!cancelled) setAppState('ready');
          return;
        }
        const status: SetupStatus = await res.json();
        if (cancelled) return;
        if (status.needs_setup) {
          setAppState('setup_wizard');
        } else if (status.needs_user) {
          setAppState('create_user');
        } else {
          setAppState('ready');
        }
      } catch {
        // Network error — optimistically show dashboard
        if (!cancelled) setAppState('ready');
      }
    };
    checkStatus();
    return () => { cancelled = true; };
  }, []);

  const handleSetupComplete = () => {
    // After wizard completes, check if we need user creation
    setAppState('create_user');
  };

  const handleUserCreated = () => {
    setAppState('ready');
  };

  if (appState === 'loading') return <LoadingScreen />;

  if (appState === 'setup_wizard') {
    return <SetupWizard onComplete={handleSetupComplete} />;
  }

  if (appState === 'create_user') {
    return <CreateUserWall onCreated={handleUserCreated} />;
  }

  return <Dashboard />;
}
