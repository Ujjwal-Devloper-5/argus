export async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(endpoint, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    credentials: 'include', // Ensure cookies are passed
  });

  if (response.status === 401) {
    // Notify AuthContext via custom event without causing hard browser page reloads
    if (typeof window !== 'undefined' && endpoint !== '/api/auth/login') {
      window.dispatchEvent(new CustomEvent('argus:unauthorized'));
    }
    let errorMsg = 'Unauthorized';
    try {
      const errData = await response.json();
      errorMsg = errData.detail || errorMsg;
    } catch {}
    throw new Error(errorMsg);
  }

  if (!response.ok) {
    let errorMsg = 'An error occurred';
    try {
      const errData = await response.json();
      errorMsg = errData.detail || errorMsg;
    } catch {}
    throw new Error(errorMsg);
  }

  return response.json();
}
