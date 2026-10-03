import React from 'react';
export function LoadingSkeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse bg-muted rounded-md ${className}`} />;
}
