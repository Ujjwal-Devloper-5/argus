export type Severity = 'critical' | 'warning' | 'info';

export interface EventSummary {
  id: number;
  camera_name: string;
  severity: Severity;
  is_suspicious: boolean;
  thumbnail_path: string | null;
  created_at: string;
  llm_description: string;
  similarity_score: number | null;
}

export interface EventDetail extends EventSummary {
  llm_description_full: string;
  clip_local_path: string | null;
  clip_remote_url: string | null;
  camera_id: number;
  action_recommendation: string;
  laya_escalated: boolean;
  confidence: number | null;
}

export interface FaceProfile {
  id: number;
  name: string;
  created_at: string;
  last_seen: string | null;
  total_events: number;
  thumbnail_path: string | null;
}

export interface CameraStatus {
  name: string;
  rtsp_url: string;
  disabled: boolean;
  is_online: boolean;
  total_events: number;
  last_event_at: string | null;
}

export interface SystemStats {
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  gpu_vram_percent: number | null;
  uptime_seconds: number;
  total_events_today: number;
  total_alerts_sent: number;
  kafka_enabled: boolean;
  db_path: string;
}

// LiveEvent schema aligned with backend AlertEventWS model
export interface LiveEvent {
  id: number | null;
  camera_name: string;
  severity: Severity;
  is_suspicious: boolean;
  message: string;
  thumbnail_path: string | null;
  created_at: string;
  // Optional extended fields
  confidence?: number | null;
  action_recommendation?: string | null;
}

export interface Detection {
  box: [number, number, number, number]; // x1, y1, x2, y2
  class_name: string;
  confidence: number;
  track_id?: number;
}

export interface UnknownCandidate {
  id: string;
  appearance_count: number;
  first_seen: string;
  last_seen: string;
  thumbnail_url: string | null;
  similarity_to_nearest: number;
}
