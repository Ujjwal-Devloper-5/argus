import { apiFetch } from './client';
import type { EventSummary, EventDetail } from '../types';

export interface EventQueryParams {
  skip?: number;
  limit?: number;
  camera_name?: string;
  severity?: string;
  suspicious_only?: boolean;
  search?: string;
}

export async function fetchEvents(params?: EventQueryParams): Promise<EventSummary[]> {
  const query = new URLSearchParams();
  if (params?.skip) query.set('skip', params.skip.toString());
  if (params?.limit) query.set('limit', params.limit.toString());
  if (params?.camera_name) query.set('camera_name', params.camera_name);
  if (params?.severity) query.set('severity', params.severity);
  if (params?.suspicious_only) query.set('suspicious_only', 'true');
  if (params?.search) query.set('search', params.search);

  const qs = query.toString();
  return apiFetch<EventSummary[]>(`/api/events${qs ? `?${qs}` : ''}`);
}

export async function fetchEventDetail(id: number | string): Promise<EventDetail> {
  return apiFetch<EventDetail>(`/api/events/${id}`);
}

export async function fetchEventStats(): Promise<{
  total_24h: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
  threat_level: string;
}> {
  return apiFetch('/api/events/stats');
}
