// API Configuration
// If in Production (Vercel), use relative path (empty string) to leverage rewrites.
// If in Development, use the env var or default to localhost.
const API_BASE_URL = import.meta.env.PROD 
  ? '' 
  : (import.meta.env.VITE_API_URL || 'http://localhost:8000');

export function getAssetUrl(path: string | null): string | undefined {
  if (!path) return undefined;
  if (path.startsWith('http') || path.startsWith('data:')) return path;
  if (path === '/placeholder.svg') return path;
  // If it's a relative path from the backend (like /captures/...)
  return `${API_BASE_URL}${path}`;
}

export interface Visitor {
  id: string;
  timestamp: string;
  imageUrl: string | null;
  transcript: TranscriptEntry[];
  status: 'active' | 'completed' | 'ignored';
  aiSummary: string;
  visitorType: 'delivery' | 'friend' | 'solicitor' | 'neighbor' | 'unknown';
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

// API Functions
export async function ringDoorbell(image?: string | null): Promise<{ sessionId: string; greeting: string; imageUrl?: string }> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/ring`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image }),
    });
    if (!response.ok) throw new Error('Failed to ring doorbell');
    return response.json();
  } catch (error) {
    console.error('Ring doorbell error:', error);
    // Mock response for demo
    return {
      sessionId: `visitor_${Date.now()}`,
      greeting: "Hello! Welcome to the Kandell residence. How may I help you today?",
    };
  }
}

export async function captureImage(imageSrc?: string | null): Promise<{ imageUrl: string }> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/capture-image`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: imageSrc }),
    });
    if (!response.ok) throw new Error('Failed to capture image');
    return response.json();
  } catch (error) {
    console.error('Capture image error:', error);
    // Return placeholder for demo
    return {
      imageUrl: '/placeholder.svg',
    };
  }
}

export async function getAIReply(
  sessionId: string,
  message: string
): Promise<{ reply: string; summary: string; visitorType: string }> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/ai-reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId, message }),
    });
    if (!response.ok) throw new Error('Failed to get AI reply');
    return response.json();
  } catch (error) {
    console.error('AI reply error:', error);
    // Mock response for demo
    return {
      reply: "Thank you for visiting! I've notified the owner. Please wait a moment.",
      summary: "Visitor inquiry",
      visitorType: "unknown",
    };
  }
}

export async function speakText(text: string): Promise<void> {
  // We use browser SpeechSynthesis API exclusively now, as Vercel backend cannot play audio.
  if ('speechSynthesis' in window) {
    return new Promise((resolve) => {
      // Cancel any ongoing speech
      speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0; 
      utterance.pitch = 1.0;
      
      utterance.onend = () => {
        resolve();
      };
      
      utterance.onerror = (e) => {
        console.error('Browser TTS error:', e);
        resolve(); // Resolve anyway so the app doesn't hang
      };

      speechSynthesis.speak(utterance);
    });
  } else {
    console.warn("Browser does not support SpeechSynthesis");
    return Promise.resolve();
  }
}

export async function getVisitorLogs(): Promise<Visitor[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/logs`);
    if (!response.ok) throw new Error('Failed to fetch logs');
    return response.json();
  } catch (error) {
    console.error('Fetch logs error:', error);
    // Return mock data for demo
    return getMockVisitors();
  }
}

export async function ownerReply(
  sessionId: string,
  message: string
): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/api/owner-reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId, message }),
    });
  } catch (error) {
    console.error('Owner reply error:', error);
  }
}

// Mock data for demo purposes
function getMockVisitors(): Visitor[] {
  return [
    {
      id: 'visitor_1',
      timestamp: new Date(Date.now() - 3600000).toISOString(),
      imageUrl: '/placeholder.svg',
      transcript: [
        { role: 'doorbell', content: 'Hello! Welcome to the Kandell residence. How may I help you?', timestamp: new Date(Date.now() - 3600000).toISOString() },
        { role: 'visitor', content: 'Hi, I have a package for delivery.', timestamp: new Date(Date.now() - 3595000).toISOString() },
        { role: 'doorbell', content: 'Thank you! Please leave the package in the Parcel Box to the left.', timestamp: new Date(Date.now() - 3590000).toISOString() },
      ],
      status: 'completed',
      aiSummary: 'Delivery person with a package',
      visitorType: 'delivery',
    },
    {
      id: 'visitor_2',
      timestamp: new Date(Date.now() - 7200000).toISOString(),
      imageUrl: '/placeholder.svg',
      transcript: [
        { role: 'doorbell', content: 'Hello! Welcome to the Kandell residence. How may I help you?', timestamp: new Date(Date.now() - 7200000).toISOString() },
        { role: 'visitor', content: "Hi, it's Sarah from next door!", timestamp: new Date(Date.now() - 7195000).toISOString() },
        { role: 'doorbell', content: "Hello Sarah! Nice to see you. I'll notify the owner right away.", timestamp: new Date(Date.now() - 7190000).toISOString() },
      ],
      status: 'completed',
      aiSummary: 'Neighbor Sarah stopping by',
      visitorType: 'neighbor',
    },
  ];
}

// Authentication (simple demo implementation)
export async function login(username: string, password: string): Promise<{ success: boolean; token?: string }> {
  // In production, this should call your Pi backend
  if (username === 'admin' && password === 'doorbell') {
    const token = btoa(`${username}:${Date.now()}`);
    localStorage.setItem('doorbell_token', token);
    return { success: true, token };
  }
  return { success: false };
}

export function logout(): void {
  localStorage.removeItem('doorbell_token');
}

export function isAuthenticated(): boolean {
  return !!localStorage.getItem('doorbell_token');
}