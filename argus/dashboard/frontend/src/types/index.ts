export type Severity = 'critical' | 'warning' | 'info';

export interface EventSummary {
  id: number;
  camera_name: string;
  severity: Severity;
  is_suspicious: boolean;
  thumbnail_path: string | null;
  created_at: string;
  llm_description: string;
  similarity_score: number;
}

export interface EventDetail extends EventSummary {
  llm_description_full: string;
  clip_local_path: string | null;
  clip_remote_url: string | null;
  camera_id: number;
  action_recommendation: string;
  laya_escalated: boolean;
  confidence: number;
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

export interface LiveEvent {
  event_id: number | null;
  camera: string;
  face_hash: string;
  is_suspicious: boolean;
  escalated_by_laya: boolean;
  confidence: number;
  llm_description: string;
  action_recommendation: string;
  clip_path: string | null;
  thumbnail_path: string | null;
  triggered_at: string;
}
