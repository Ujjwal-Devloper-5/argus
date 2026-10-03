export function useWebSocket(url: string, onMessage: (data: unknown) => void) {
  return { connected: true, reconnectCount: 0 };
}
