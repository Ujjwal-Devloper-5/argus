import { apiFetch } from './client';
import type { SystemStats } from '../types';

export async function fetchSystemStats(): Promise<SystemStats> {
  return apiFetch<SystemStats>('/api/system/stats');
}

export async function restartSystem(): Promise<{ success: boolean; message: string }> {
  return apiFetch<{ success: boolean; message: string }>('/api/system/restart', {
    method: 'POST',
  });
}
