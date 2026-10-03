import React from 'react';
import { Severity } from '../../types';

export function SeverityBadge({ severity }: { severity: Severity }) {
  const colors = {
    critical: 'bg-destructive/15 text-destructive border-destructive/30',
    warning: 'bg-warning/15 text-warning border-warning/30',
    info: 'bg-primary/15 text-primary border-primary/30',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-bold border uppercase tracking-wider ${colors[severity]}`}>
      {severity}
    </span>
  );
}
