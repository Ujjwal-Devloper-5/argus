import { apiFetch } from './client';
import type { FaceProfile, UnknownCandidate } from '../types';

export async function fetchFaces(): Promise<FaceProfile[]> {
  return apiFetch<FaceProfile[]>('/api/faces');
}

export async function fetchFaceDetail(id: number | string): Promise<FaceProfile> {
  return apiFetch<FaceProfile>(`/api/faces/${id}`);
}

export async function deleteFace(id: number | string): Promise<{ success: boolean; message: string }> {
  return apiFetch<{ success: boolean; message: string }>(`/api/faces/${id}`, {
    method: 'DELETE',
  });
}

export async function fetchUnknownCandidates(): Promise<UnknownCandidate[]> {
  return apiFetch<UnknownCandidate[]>('/api/faces/unknown');
}
