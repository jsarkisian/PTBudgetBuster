export function connectWS(engagementId, onEvent) {
  const token = localStorage.getItem("token");
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = import.meta.env.VITE_API_URL
    ? new URL(import.meta.env.VITE_API_URL).host
    : window.location.host;
  const url = `${protocol}//${host}/ws/${engagementId}?token=${token}`;

  const ws = new WebSocket(url);
  ws.onmessage = (e) => {
    try { onEvent(JSON.parse(e.data)); } catch {}
  };
  ws.onclose = () => {
    setTimeout(() => connectWS(engagementId, onEvent), 3000);
  };
  return ws;
}
