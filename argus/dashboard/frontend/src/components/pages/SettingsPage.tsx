import React, { useState } from 'react';
import { Save } from 'lucide-react';

const TABS = ['Cameras', 'Detection', 'LLM', 'Alerts', 'Storage', 'Kafka'];

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('LLM');

  return (
    <div className="p-6 h-full flex flex-col">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">System Configuration</h1>
        <button className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:bg-primary/90">
          <Save className="w-4 h-4" /> Save Changes
        </button>
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
            
            {activeTab === 'LLM' && (
              <div className="space-y-5 max-w-md">
                <div>
                  <label className="block text-sm font-medium mb-1.5 text-muted-foreground">Provider</label>
                  <select className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 outline-none focus:border-primary">
                    <option>ollama</option>
                    <option>openai</option>
                    <option>anthropic</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1.5 text-muted-foreground">Model Name</label>
                  <input type="text" defaultValue="llava" className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 outline-none focus:border-primary" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1.5 text-muted-foreground">Ollama Host</label>
                  <input type="text" defaultValue="http://localhost:11434" className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 outline-none focus:border-primary" />
                </div>
                <div className="pt-4 border-t border-border">
                  <label className="flex items-center gap-3">
                    <input type="checkbox" defaultChecked className="w-4 h-4 rounded border-border" />
                    <span className="text-sm font-medium">Enable Laya Fast Gate (421M)</span>
                  </label>
                  <p className="text-xs text-muted-foreground mt-1 ml-7">Use small model to filter non-suspicious events before calling heavy LLM.</p>
                </div>
              </div>
            )}
            
            {activeTab !== 'LLM' && (
              <div className="text-muted-foreground text-sm italic">
                {activeTab} settings form fields go here...
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
