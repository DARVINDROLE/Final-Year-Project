// ── API Configuration ────────────────────────────────────
const API_BASE_URL = import.meta.env.PROD ? '' : (import.meta.env.VITE_API_URL || '');

// ── Types ────────────────────────────────────────────────

export interface User {
  id: number;
  username: string;
  name: string;
}

export interface Visitor {
  id: string;
  timestamp: string;
  imageUrl: string | null;
  transcript: TranscriptEntry[];
  status: 'active' | 'completed' | 'ignored';
  aiSummary: string;
  visitorType: 'delivery' | 'friend' | 'solicitor' | 'neighbor' | 'unknown';
  riskScore?: number;
}

export interface TranscriptEntry {
  role: 'visitor' | 'doorbell';
  content: string;
  timestamp: string;
}

export interface DoorbellStatus {
  state: 'idle' | 'processing' | 'speaking';
  message: string;
}

export interface Member {
  id: number;
  name: string;
  phone: string;
  role: string;
  photo_path: string;
  permitted: boolean | number;
  created_at: string;
}

export interface SessionDetail {
  session: Record<string, unknown>;
  visitor: Record<string, unknown> | null;
  transcripts: TranscriptEntry[];
  actions: Record<string, unknown>[];
}

// ── Token helpers ────────────────────────────────────────

function getToken(): string | null {
  return localStorage.getItem('doorbell_token');
}

function setToken(token: string): void {
  localStorage.setItem('doorbell_token', token);
}

function clearToken(): void {
  localStorage.removeItem('doorbell_token');
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

// ── Asset URL helper ────────────────────────────────────

export function getAssetUrl(path: string | null): string | undefined {
  if (!path) return undefined;
  if (path.startsWith('http') || path.startsWith('data:')) return path;
  if (path === '/placeholder.svg') return path;
  return `${API_BASE_URL}${path}`;
}

// ── Auth API ─────────────────────────────────────────────

export async function register(username: string, password: string, name: string = ''): Promise<{ user: User; token: string }> {
  const res = await fetch(`${API_BASE_URL}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, name }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Registration failed' }));
    throw new Error(err.detail || 'Registration failed');
  }
  const data = await res.json();
  setToken(data.token);
  return data;
}

export async function login(username: string, password: string): Promise<{ user: User; token: string }> {
  const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Invalid credentials' }));
    throw new Error(err.detail || 'Invalid credentials');
  }
  const data = await res.json();
  setToken(data.token);
  return data;
}

export async function logout(): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/api/auth/logout`, {
      method: 'POST',
      headers: authHeaders(),
    });
  } catch {
    // Ignore — we clear token regardless
  }
  clearToken();
}

export async function getMe(): Promise<User | null> {
  const token = getToken();
  if (!token) return null;
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/me`, { headers: authHeaders() });
    if (!res.ok) {
      clearToken();
      return null;
    }
    const data = await res.json();
    return data.user;
  } catch {
    return null;
  }
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

// ── Doorbell API ─────────────────────────────────────────

export async function ringDoorbell(
  imageBase64?: string | null,
  audioBase64?: string | null,
): Promise<{ sessionId: string; greeting: string; imageUrl?: string }> {
  const res = await fetch(`${API_BASE_URL}/api/ring`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      type: 'ring',
      timestamp: new Date().toISOString(),
      device_id: 'web-frontend',
      image_base64: imageBase64 || null,
      audio_base64: audioBase64 || null,
      metadata: { source: 'web' },
    }),
  });
  if (!res.ok) throw new Error('Failed to ring doorbell');
  return res.json();
}

export async function getSessionStatus(sessionId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE_URL}/api/session/${sessionId}/status`);
  if (!res.ok) throw new Error('Failed to get session status');
  return res.json();
}

export async function getSessionDetail(sessionId: string): Promise<SessionDetail> {
  const res = await fetch(`${API_BASE_URL}/api/session/${sessionId}/detail`);
  if (!res.ok) throw new Error('Session not found');
  return res.json();
}

export async function getAIReply(
  sessionId: string,
  message: string,
): Promise<{ reply: string; summary: string; visitorType: string }> {
  const res = await fetch(`${API_BASE_URL}/api/ai-reply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message, owner: false }),
  });
  if (!res.ok) throw new Error('Failed to get AI reply');
  const data = await res.json();
  return {
    reply: data.reply || 'Please wait while I notify the owner.',
    summary: data.summary || '',
    visitorType: data.visitorType || 'unknown',
  };
}

export async function ownerReply(sessionId: string, message: string): Promise<void> {
  await fetch(`${API_BASE_URL}/api/owner-reply`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ session_id: sessionId, message, owner: true }),
  });
}

// ── Transcription API ────────────────────────────────────

export async function transcribeAudio(
  audioBase64: string,
): Promise<{ transcript: string; confidence: number }> {
  const res = await fetch(`${API_BASE_URL}/api/transcribe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ audio_base64: audioBase64 }),
  });
  if (!res.ok) throw new Error('Failed to transcribe audio');
  return res.json();
}

// ── Logs ─────────────────────────────────────────────────

export async function getVisitorLogs(limit = 50): Promise<Visitor[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/logs?limit=${limit}`);
    if (!res.ok) throw new Error('Failed to fetch logs');
    const data = await res.json();
    return transformLogs(data);
  } catch (error) {
    console.error('Fetch logs error:', error);
    return [];
  }
}

function transformLogs(data: {
  sessions: Array<Record<string, unknown>>;
  transcripts: Array<Record<string, unknown>>;
  actions: Array<Record<string, unknown>>;
  visitors?: Array<Record<string, unknown>>;
}): Visitor[] {
  const { sessions, transcripts, visitors } = data;

  const transcriptMap = new Map<string, TranscriptEntry[]>();
  for (const t of transcripts) {
    const sid = t.session_id as string;
    if (!transcriptMap.has(sid)) transcriptMap.set(sid, []);
    transcriptMap.get(sid)!.push({
      role: (t.role as string) === 'visitor' ? 'visitor' : 'doorbell',
      content: t.content as string,
      timestamp: t.timestamp as string,
    });
  }

  // Build visitor image/type/summary map
  const visitorMap = new Map<string, { imageUrl: string | null; visitorType: string; aiSummary: string }>();
  if (visitors) {
    for (const v of visitors) {
      const sid = v.session_id as string;
      const imagePath = v.image_path as string;
      // Construct URL from the image_path stored by the perception agent
      let imageUrl: string | null = null;
      if (imagePath) {
        // image_path is like "data/snaps/visitor_xxx.jpg" → serve from "/static/snaps/visitor_xxx.jpg"
        const filename = imagePath.split('/').pop();
        if (filename) imageUrl = `/static/snaps/${filename}`;
      }
      visitorMap.set(sid, {
        imageUrl,
        visitorType: (v.visitor_type as string) || 'unknown',
        aiSummary: (v.ai_summary as string) || '',
      });
    }
  }

  return sessions.map((s) => {
    const sid = s.id as string;
    const visitorInfo = visitorMap.get(sid);
    return {
      id: sid,
      timestamp: (s.created_at as string) || new Date().toISOString(),
      imageUrl: visitorInfo?.imageUrl || null,
      transcript: transcriptMap.get(sid) || [],
      status: ['completed', 'error'].includes((s.status as string) || '') ? 'completed' as const : 'active' as const,
      aiSummary: visitorInfo?.aiSummary || '',
      visitorType: (visitorInfo?.visitorType || 'unknown') as Visitor['visitorType'],
      riskScore: (s.risk_score as number) || 0,
    };
  });
}

// ── Members API ──────────────────────────────────────────

export async function getMembers(): Promise<Member[]> {
  const res = await fetch(`${API_BASE_URL}/api/members`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Failed to fetch members');
  return res.json();
}

export async function addMember(
  name: string,
  phone: string,
  role: string,
  photoBase64?: string,
): Promise<Member> {
  const res = await fetch(`${API_BASE_URL}/api/members`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ name, phone, role, photo_base64: photoBase64 || '' }),
  });
  if (!res.ok) throw new Error('Failed to add member');
  return res.json();
}

export async function updateMember(
  id: number,
  updates: { name?: string; phone?: string; role?: string; permitted?: boolean; photo_base64?: string },
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/members/${id}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error('Failed to update member');
}

export async function deleteMember(id: number): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/members/${id}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error('Failed to delete member');
}

// ── TTS (backend edge-tts with Hindi support, browser fallback) ──

export async function speakText(text: string, sessionId?: string): Promise<void> {
  // Try backend TTS first (edge-tts with Hindi/English auto-detection)
  try {
    const res = await fetch(`${API_BASE_URL}/api/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, session_id: sessionId || '' }),
    });
    if (res.ok) {
      const data = await res.json();
      if (data.audioUrl) {
        const audioUrl = `${API_BASE_URL}${data.audioUrl}`;
        return new Promise((resolve) => {
          const audio = new Audio(audioUrl);
          audio.onended = () => resolve();
          audio.onerror = () => {
            // Fall back to browser TTS on audio playback error
            _browserSpeak(text).then(resolve);
          };
          audio.play().catch(() => _browserSpeak(text).then(resolve));
        });
      }
    }
  } catch {
    // Backend TTS unavailable — fall through to browser
  }

  // Fallback: browser speech synthesis
  return _browserSpeak(text);
}

function _browserSpeak(text: string): Promise<void> {
  if ('speechSynthesis' in window) {
    return new Promise((resolve) => {
      speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      // Try to pick a Hindi voice if text contains Devanagari
      const hasHindi = /[\u0900-\u097F]/.test(text);
      if (hasHindi) {
        const voices = speechSynthesis.getVoices();
        const hindiVoice = voices.find(
          (v) => v.lang.startsWith('hi') || v.name.toLowerCase().includes('hindi'),
        );
        if (hindiVoice) utterance.voice = hindiVoice;
        utterance.lang = 'hi-IN';
      }
      utterance.onend = () => resolve();
      utterance.onerror = () => resolve();
      speechSynthesis.speak(utterance);
    });
  }
  return Promise.resolve();
}

// ── WebSocket ────────────────────────────────────────────

export function connectWebSocket(
  channel: string,
  onMessage: (data: Record<string, unknown>) => void,
): WebSocket {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsHost = import.meta.env.PROD
    ? window.location.host
    : 'localhost:8000';
  const ws = new WebSocket(`${wsProtocol}//${wsHost}/api/ws/${channel}`);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch {
      // Ignore non-JSON messages
    }
  };

  ws.onerror = (e) => console.error('WebSocket error:', e);
  ws.onclose = () => console.log('WebSocket closed for channel', channel);

  return ws;
}