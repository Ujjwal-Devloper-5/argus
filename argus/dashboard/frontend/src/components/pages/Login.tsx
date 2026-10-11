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
