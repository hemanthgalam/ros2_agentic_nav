// Server-side only: the FastAPI backend URL is never exposed to the browser,
// unlike the rosbridge WebSocket which the browser connects to directly.
export const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
