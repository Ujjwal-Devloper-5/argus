import React, { useState } from 'react';
import { LayoutDashboard, Camera, AlertTriangle, Users, Activity, Settings, Lock, Shield, X, Menu, ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const navGroups = [
  {
    items: [
      { id: 'overview',  title: 'Overview',     icon: LayoutDashboard, path: '/' },
      { id: 'live',      title: 'Live View',    icon: Camera, badge: 'LIVE', path: '/live' },
      { id: 'events',    title: 'Events',       icon: AlertTriangle, badge: 3, path: '/events' },
    ]
  },
  {
    heading: 'Intelligence',
    items: [
      { id: 'faces',     title: 'Face Gallery', icon: Users, path: '/faces' },
      { id: 'system',    title: 'System Health', icon: Activity, path: '/system' },
    ]
  },
  {
    heading: 'Configuration',
    items: [
      { id: 'settings',  title: 'Settings',     icon: Settings, path: '/settings' },
    ]
  }
];

export function Sidebar({ activeId, onSelect }: { activeId: string, onSelect: (id: string) => void }) {
  const navigate = useNavigate();

  const handleSelect = (item: any) => {
    onSelect(item.id);
    navigate(item.path || '/');
  };

  return (
    <div className="w-[260px] h-full bg-card/95 border-r border-border p-3.5 flex flex-col select-none z-10 shrink-0">
      <div className="flex items-center gap-3 px-2.5 py-2 mb-3">
        <div className="w-8 h-8 rounded-lg bg-primary/20 border border-primary/30 flex items-center justify-center">
          <Shield className="w-4 h-4 text-primary" />
        </div>
        <div>
          <div className="text-[13px] font-bold text-foreground">ARGUS</div>
          <div className="text-[11px] text-muted-foreground">Security Operations</div>
        </div>
        <div className="ml-auto flex items-center gap-1">
          <div className="w-2 h-2 rounded-full bg-success pulse-online" />
          <span className="text-[10px] text-success font-bold">LIVE</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto flex flex-col gap-5 mt-1 hide-scrollbar">
        {navGroups.map((group, idx) => (
          <div key={idx} className="flex flex-col gap-1">
            {group.heading && (
              <span className="px-2.5 mb-1 text-[11px] font-bold tracking-wider text-muted-foreground/60 uppercase">
                {group.heading}
              </span>
            )}
            {group.items.map(item => {
              const isActive = activeId === item.id;
              return (
                <div
                  key={item.id}
                  onClick={() => handleSelect(item)}
                  className={`group flex items-center justify-between px-2.5 py-[7.5px] rounded-lg cursor-pointer transition-all duration-150 ${isActive ? 'bg-primary/10 text-primary font-semibold' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}
                >
                  <div className="flex items-center gap-2.5">
                    <item.icon className={`w-4 h-4 ${isActive ? 'text-primary' : 'group-hover:text-foreground'}`} />
                    <span className="text-[13px]">{item.title}</span>
                  </div>
                  {(item as any).badge && (
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${(item as any).badge === 'LIVE' ? 'bg-success/20 text-success' : 'bg-primary/20 text-primary'}`}>
                      {(item as any).badge}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <div className="mt-auto pt-3 border-t border-border">
        <div className="group flex items-center px-2.5 py-[7.5px] rounded-lg cursor-pointer text-muted-foreground hover:bg-muted hover:text-foreground">
          <Lock className="w-4 h-4 mr-2.5" />
          <span className="text-[13px]">Lock Dashboard</span>
        </div>
      </div>
    </div>
  );
}
