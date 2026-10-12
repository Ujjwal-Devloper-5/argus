import { apiFetch } from './client';
import type { CameraStatus } from '../types';

export async function fetchCameras(): Promise<CameraStatus[]> {
  return apiFetch<CameraStatus[]>('/api/cameras');
}

export async function addCamera(camera: Partial<CameraStatus>): Promise<CameraStatus> {
  return apiFetch<CameraStatus>('/api/cameras', {
    method: 'POST',
    body: JSON.stringify(camera),
  });
}

export async function updateCamera(name: string, camera: Partial<CameraStatus>): Promise<CameraStatus> {
  return apiFetch<CameraStatus>(`/api/cameras/${name}`, {
    method: 'PUT',
    body: JSON.stringify(camera),
  });
}

export async function deleteCamera(name: string): Promise<{ success: boolean; message: string }> {
  return apiFetch<{ success: boolean; message: string }>(`/api/cameras/${name}`, {
    method: 'DELETE',
  });
}

export async function testStream(rtspUrl: string): Promise<{ success: boolean; message: string }> {
  return apiFetch<{ success: boolean; message: string }>('/api/cameras/test-stream', {
    method: 'POST',
    body: JSON.stringify({ rtsp_url: rtspUrl }),
  });
}
