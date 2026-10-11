import os
import textwrap

FRONTEND_DIR = "/home/ujjwal/homelab/argus/argus/dashboard/frontend/src"

# 1. Update client.ts to include credentials
client_ts = os.path.join(FRONTEND_DIR, "api/client.ts")
with open(client_ts, "w") as f:
    f.write(textwrap.dedent('''\
    export async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
      const response = await fetch(endpoint, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
      });

      if (response.status === 401) {
        window.location.href = '/login';
        throw new Error('Unauthorized');
      }

      if (!response.ok) {
        let errorMsg = 'An error occurred';
        try {
          const errData = await response.json();
          errorMsg = errData.detail || errorMsg;
        } catch (e) {}
        throw new Error(errorMsg);
      }
      
      return response.json();
    }
    '''))

# 2. Add Login.tsx
login_tsx = os.path.join(FRONTEND_DIR, "components/pages/Login.tsx")
with open(login_tsx, "w") as f:
    f.write(textwrap.dedent('''\
    import React, { useState } from 'react';
    import { apiFetch } from '../../api/client';

    export default function Login() {
      const [username, setUsername] = useState('');
      const [password, setPassword] = useState('');
      const [error, setError] = useState('');

      const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
          await apiFetch('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password })
          });
          window.location.href = '/';
        } catch (err: any) {
          setError(err.message);
        }
      };

      return (
        <div className="min-h-screen flex items-center justify-center bg-background">
          <form onSubmit={handleLogin} className="bg-card p-8 rounded-xl shadow-xl border border-border w-full max-w-md">
            <h1 className="text-2xl font-bold mb-6 text-center">Argus Dashboard Login</h1>
            {error && <div className="bg-destructive/20 text-destructive p-3 rounded mb-4 text-sm font-semibold">{error}</div>}
            <div className="mb-4">
              <label className="block text-sm font-medium mb-1.5 text-muted-foreground">Username</label>
              <input type="text" value={username} onChange={e => setUsername(e.target.value)} className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 outline-none focus:border-primary" />
            </div>
            <div className="mb-6">
              <label className="block text-sm font-medium mb-1.5 text-muted-foreground">Password</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 outline-none focus:border-primary" />
            </div>
            <button type="submit" className="w-full bg-primary text-primary-foreground py-2 rounded-lg font-bold hover:bg-primary/90">Sign In</button>
          </form>
        </div>
      );
    }
    '''))

# 3. Update App.tsx routing
app_tsx = os.path.join(FRONTEND_DIR, "App.tsx")
with open(app_tsx, "r") as f:
    app_content = f.read()

if "import Login from './components/pages/Login'" not in app_content:
    app_content = app_content.replace(
        "import SetupWizard from './components/pages/SetupWizard';",
        "import SetupWizard from './components/pages/SetupWizard';\nimport Login from './components/pages/Login';"
    )
    app_content = app_content.replace(
        "<Route path=\"/setup\" element={<SetupWizard />} />",
        "<Route path=\"/setup\" element={<SetupWizard />} />\n        <Route path=\"/login\" element={<Login />} />"
    )
    # Exclude login and setup from redirect logic
    app_content = app_content.replace(
        "if (window.location.pathname !== '/setup') {",
        "if (window.location.pathname !== '/setup' && window.location.pathname !== '/login') {"
    )
    with open(app_tsx, "w") as f:
        f.write(app_content)

# 4. Update LiveView.tsx to use MJPEG stream endpoint
live_view_tsx = os.path.join(FRONTEND_DIR, "components/pages/LiveView.tsx")
with open(live_view_tsx, "r") as f:
    lv_content = f.read()

# Replace the pseudo-live polling with real MJPEG stream
lv_content = lv_content.replace(
    """src={`/api/cameras/${cam.name}/snapshot?t=${timestamp}`}""",
    """src={`/api/cameras/${cam.name}/stream`}"""
)
lv_content = lv_content.replace(
    "const interval = setInterval(() => setTimestamp(Date.now()), 2000);\n    return () => clearInterval(interval);",
    ""
)
lv_content = lv_content.replace(
    "const [timestamp, setTimestamp] = useState(Date.now());",
    ""
)

with open(live_view_tsx, "w") as f:
    f.write(lv_content)

# 5. Update WebSockets to use ticket auth
for hook_file in ["hooks/useLiveEvents.ts", "hooks/useLiveStats.ts"]:
    path = os.path.join(FRONTEND_DIR, hook_file)
    with open(path, "r") as f:
        hook_content = f.read()
    
    if "apiFetch<{ ticket: string }>('/api/auth/ticket')" not in hook_content:
        # Rewrite the useEffect to fetch ticket first
        # Very simple targeted replace
        new_effect = textwrap.dedent("""\
        useEffect(() => {
          let ws: WebSocket;
          let mounted = true;

          apiFetch<{ ticket: string }>('/api/auth/ticket')
            .then(res => {
              if (!mounted) return;
              const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
              const host = window.location.port === '5173' ? 'localhost:8501' : window.location.host;
              const endpoint = hook_name === 'events' ? '/ws/events' : '/ws/stats';
              ws = new WebSocket(`${protocol}//${host}${endpoint}?ticket=${res.ticket}`);

              ws.onopen = () => setConnected(true);
              ws.onclose = () => setConnected(false);
              ws.onmessage = (msg) => {
                try {
                  const data = JSON.parse(msg.data);
                  if (hook_name === 'events') {
                    if (data.type === 'heartbeat') return;
                    setEvents(prev => [data, ...prev].slice(0, 50));
                  } else {
                    setStats(data);
                  }
                } catch (e) {
                  console.error("WS error", e);
                }
              };
            })
            .catch(err => console.error("Failed to get WS ticket", err));

          return () => {
            mounted = false;
            if (ws) ws.close();
          };
        }, []);
        """)
        
        # Determine which hook it is to patch correctly
        hook_type = "events" if "events" in hook_file else "stats"
        new_effect = new_effect.replace("hook_name === 'events'", f"'{hook_type}' === 'events'")
        if hook_type == "events":
            hook_content = hook_content.replace(
                "import type { LiveEvent } from '../types';",
                "import type { LiveEvent } from '../types';\nimport { apiFetch } from '../api/client';"
            )
        else:
            hook_content = hook_content.replace(
                "import type { SystemStats } from '../types';",
                "import type { SystemStats } from '../types';\nimport { apiFetch } from '../api/client';"
            )

        # Replace everything from useEffect to return
        import re
        hook_content = re.sub(r'useEffect\(\(\) => \{.*?\n  \}, \[\]\);', new_effect, hook_content, flags=re.DOTALL)
        with open(path, "w") as f:
            f.write(hook_content)

print("Frontend phase 1 refactor complete.")
