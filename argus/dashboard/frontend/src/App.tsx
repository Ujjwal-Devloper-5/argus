import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import Overview from './components/pages/Overview';
import LiveView from './components/pages/LiveView';
import Events from './components/pages/Events';
import EventDetail from './components/pages/EventDetail';
import Faces from './components/pages/Faces';
import SystemHealth from './components/pages/SystemHealth';
import SettingsPage from './components/pages/SettingsPage';
import SetupWizard, { CreateUserWall } from './components/pages/SetupWizard';
import Login from './components/pages/Login';

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
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.955 11.955 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"
          />
        </svg>
      </div>
      <p className="text-sm text-muted-foreground animate-pulse">Initializing Argus Command Center...</p>
    </div>
  );
}

export default function App() {
  const [appState, setAppState] = useState<AppState>('loading');

  useEffect(() => {
    // Preserve existing theme or dark mode default
    const savedTheme = localStorage.getItem('argus_theme');
    if (savedTheme === 'light') {
      document.documentElement.classList.remove('dark');
    } else {
      document.documentElement.classList.add('dark');
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const checkStatus = async () => {
      try {
        const res = await fetch('/api/setup/status');
        if (!res.ok) {
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
        if (!cancelled) setAppState('ready');
      }
    };
    checkStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  if (appState === 'loading') return <LoadingScreen />;

  if (appState === 'setup_wizard') {
    return <SetupWizard onComplete={() => setAppState('create_user')} />;
  }

  if (appState === 'create_user') {
    return <CreateUserWall onCreated={() => setAppState('ready')} />;
  }

  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Unauthenticated Gateway */}
          <Route path="/login" element={<Login />} />

          {/* Authenticated Dashboard Core */}
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <DashboardLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<ErrorBoundary><Overview /></ErrorBoundary>} />
            <Route path="live" element={<ErrorBoundary><LiveView /></ErrorBoundary>} />
            <Route path="events" element={<ErrorBoundary><Events /></ErrorBoundary>} />
            <Route path="events/:id" element={<ErrorBoundary><EventDetail /></ErrorBoundary>} />
            <Route path="faces" element={<ErrorBoundary><Faces /></ErrorBoundary>} />
            <Route path="system" element={<ErrorBoundary><SystemHealth /></ErrorBoundary>} />
            <Route path="settings" element={<ErrorBoundary><SettingsPage /></ErrorBoundary>} />
          </Route>

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
