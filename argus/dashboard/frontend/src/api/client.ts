const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8501';
const AUTH = btoa(`${import.meta.env.VITE_USERNAME || 'admin'}:${import.meta.env.VITE_PASSWORD || 'changeme'}`);

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      'Authorization': `Basic ${AUTH}`,
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
