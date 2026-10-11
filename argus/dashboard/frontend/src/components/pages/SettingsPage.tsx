import React, { useState, useEffect } from 'react';
import { Save, RefreshCw } from 'lucide-react';
import { apiFetch } from '../../api/client';

const TABS = ['Cameras', 'Detection', 'LLM', 'Alerts', 'Storage', 'Kafka'];

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('Cameras');
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    apiFetch('/api/settings')
      .then(res => { setConfig(res); setLoading(false); })
      .catch(err => { setMessage('Error loading settings: ' + err.message); setLoading(false); });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setMessage('');
    try {
      await apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify(config)
      });
      setMessage('Settings saved successfully!');
      setTimeout(() => setMessage(''), 3000);
    } catch (err: any) {
      setMessage('Error saving: ' + err.message);
    }
    setSaving(false);
  };

  const handleRestart = async () => {
    if (!confirm('This will restart the entire Argus pipeline. Continue?')) return;
    try {
      await apiFetch('/api/system/restart', { method: 'POST' });
      setMessage('System restarting... Dashboard will reconnect shortly.');
      setTimeout(() => window.location.reload(), 3000);
    } catch (err: any) {
      setMessage('Restart failed: ' + err.message);
    }
  };

  if (loading) return <div className="p-6">Loading settings...</div>;

  return (
    <div className="p-6 h-full flex flex-col">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">System Configuration</h1>
        <div className="flex items-center gap-3">
          {message && <span className="text-sm font-medium text-success">{message}</span>}
          <button onClick={handleSave} disabled={saving} className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:bg-primary/90 disabled:opacity-50">
            <Save className="w-4 h-4" /> {saving ? 'Saving...' : 'Save Changes'}
          </button>
          <button onClick={handleRestart} className="flex items-center gap-2 px-4 py-2 bg-destructive text-destructive-foreground rounded-lg text-sm font-semibold hover:bg-destructive/90">
            <RefreshCw className="w-4 h-4" /> Restart Engine
          </button>
        </div>
      </div>

      <div className="flex gap-6 flex-1 min-h-0">
        <div className="w-48 flex flex-col gap-1 border-r border-border pr-6">
          {TABS.map(tab => (
            <button 
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`text-left px-3 py-2 rounded-lg text-sm transition-colors ${activeTab === tab ? 'bg-primary/10 text-primary font-semibold' : 'text-muted-foreground hover:bg-muted'}`}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto pr-6 pb-6">
          <div className="bg-card border border-border rounded-xl p-6">
            <h2 className="text-lg font-bold mb-6">{activeTab} Settings</h2>

            {activeTab === 'Cameras' && (
              <div className="space-y-4">
                {config?.cameras?.map((cam: any, i: number) => (
                  <div key={i} className="p-4 border border-border rounded-lg bg-muted/20">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-medium text-muted-foreground mb-1">Name</label>
                        <input type="text" value={cam.name || ''} onChange={e => {
                          const newCameras = [...config.cameras];
                          newCameras[i] = { ...cam, name: e.target.value };
                          setConfig({...config, cameras: newCameras});
                        }} className="w-full bg-background border border-border rounded px-2 py-1 outline-none text-sm" />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-muted-foreground mb-1">RTSP URL</label>
                        <input type="text" value={cam.rtsp_url || ''} onChange={e => {
                          const newCameras = [...config.cameras];
                          newCameras[i] = { ...cam, rtsp_url: e.target.value };
                          setConfig({...config, cameras: newCameras});
                        }} className="w-full bg-background border border-border rounded px-2 py-1 outline-none text-sm" />
                      </div>
                    </div>
                  </div>
                ))}
                <button onClick={() => setConfig({...config, cameras: [...(config.cameras || []), { name: 'new_cam', rtsp_url: '' }]})} className="text-sm text-primary font-semibold hover:underline">
                  + Add Camera
                </button>
              </div>
            )}

            {activeTab === 'LLM' && (
              <div className="space-y-5 max-w-md">
                <div>
                  <label className="block text-sm font-medium mb-1.5 text-muted-foreground">Provider</label>
                  <select value={config?.llm?.provider || 'ollama'} onChange={e => setConfig({...config, llm: {...config.llm, provider: e.target.value}})} className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 outline-none focus:border-primary">
                    <option value="ollama">Ollama (Local)</option>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1.5 text-muted-foreground">Model</label>
                  <input type="text" value={config?.llm?.model || ''} onChange={e => setConfig({...config, llm: {...config.llm, model: e.target.value}})} className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 outline-none focus:border-primary" />
                </div>
              </div>
            )}

            {activeTab === 'Alerts' && (
              <div className="space-y-5 max-w-md">
                <div>
                  <label className="block text-sm font-medium mb-1.5 text-muted-foreground">Routing</label>
                  <select value={config?.alerts?.routing || 'both'} onChange={e => setConfig({...config, alerts: {...config.alerts, routing: e.target.value}})} className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 outline-none focus:border-primary">
                    <option value="telegram">Telegram Only</option>
                    <option value="discord">Discord Only</option>
                    <option value="both">Both</option>
                  </select>
                </div>
                <div className="pt-4 border-t border-border">
                  <h3 className="font-semibold mb-3">Telegram</h3>
                  <label className="flex items-center gap-3 mb-3">
                    <input type="checkbox" checked={config?.alerts?.telegram?.enabled || false} onChange={e => setConfig({...config, alerts: {...config.alerts, telegram: {...config.alerts.telegram, enabled: e.target.checked}}})} className="w-4 h-4 rounded border-border" />
                    <span className="text-sm font-medium">Enable Telegram</span>
                  </label>
                </div>
              </div>
            )}

            {activeTab === 'Storage' && (
              <div className="space-y-5 max-w-md">
                <div>
                  <label className="block text-sm font-medium mb-1.5 text-muted-foreground">Retention Days</label>
                  <input type="number" value={config?.storage?.retention_days || 30} onChange={e => setConfig({...config, storage: {...config.storage, retention_days: parseInt(e.target.value)}})} className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 outline-none focus:border-primary" />
                </div>
                <div className="pt-4 border-t border-border">
                  <label className="flex items-center gap-3 mb-3">
                    <input type="checkbox" checked={config?.storage?.cloud_sync?.enabled || false} onChange={e => setConfig({...config, storage: {...config.storage, cloud_sync: {...config.storage.cloud_sync, enabled: e.target.checked}}})} className="w-4 h-4 rounded border-border" />
                    <span className="text-sm font-medium">Enable Cloud Sync (Rclone)</span>
                  </label>
                </div>
              </div>
            )}

            {['Detection', 'Kafka'].includes(activeTab) && (
              <div className="text-muted-foreground text-sm italic">
                Configure {activeTab} settings in config.yaml directly for advanced tuning.
              </div>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}
