import { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { VisitorCard } from '@/components/VisitorCard';
import {
  getVisitorLogs,
  ownerReply,
  connectWebSocket,
  type Visitor,
  getAssetUrl,
  getSessionDetail,
  transcribeAudio,
} from '@/lib/api';
import { useAuthContext } from '@/contexts/AuthContext';
import { useToast } from '@/hooks/use-toast';
import {
  Bell,
  LogOut,
  History,
  Send,
  Mic,
  MicOff,
  X,
  AlertTriangle,
  RefreshCw,
  Users,
  Clock,
  MessageSquare,
  UserCog,
  Eye,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';

const LIVE_API_BASE = window.location.origin.includes('localhost') || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8000'
  : window.location.origin;

export default function Dashboard() {
  const [visitors, setVisitors] = useState<Visitor[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedVisitor, setSelectedVisitor] = useState<Visitor | null>(null);
  const [replyText, setReplyText] = useState('');
  const [showReplyModal, setShowReplyModal] = useState(false);
  const [respondingVisitor, setRespondingVisitor] = useState<Visitor | null>(null);
  const [isRecordingReply, setIsRecordingReply] = useState(false);
  const [activeSession, setActiveSession] = useState<{
    sessionId: string;
    imageUrl: string | null;
    greeting: string;
  } | null>(null);
  const [weaponAlert, setWeaponAlert] = useState<{
    sessionId: string;
    labels: string[];
    confidence: number;
    timestamp: number;
  } | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  const { user, logout } = useAuthContext();
  const { toast } = useToast();

  // ── Load visitors ────────────────────────────────────────
  const loadVisitors = useCallback(async () => {
    setIsLoading(true);
    try {
      const logs = await getVisitorLogs();
      setVisitors(logs);
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to load visitor logs.' });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  // Stable refs so WebSocket handler always uses latest toast/loadVisitors
  // without causing the WS effect to reconnect on every render.
  const toastRef = useRef(toast);
  const loadVisitorsRef = useRef(loadVisitors);
  useEffect(() => { toastRef.current = toast; }, [toast]);
  useEffect(() => { loadVisitorsRef.current = loadVisitors; }, [loadVisitors]);

  useEffect(() => {
    loadVisitors();
  }, [loadVisitors]);

  // ── WebSocket for live ring notifications + weapon alerts ──
  // Connects ONCE with auto-reconnect. Uses refs for toast/loadVisitors.
  useEffect(() => {
    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      if (cancelled) return;
      const ws = connectWebSocket('owner', (data) => {
        if (data.type === 'new_ring') {
          const sid = data.sessionId as string;
          const imageUrl = (data.imageUrl as string) || null;
          const greeting = (data.greeting as string) || '';
          toastRef.current({ title: 'New visitor!', description: 'Someone is at the door.' });
          setActiveSession({ sessionId: sid, imageUrl, greeting });
          loadVisitorsRef.current();
        }
        if (data.type === 'weapon_alert') {
          const sid = data.sessionId as string;
          const labels = (data.weapon_labels as string[]) || [];
          const confidence = (data.weapon_confidence as number) || 0;
          const timestamp = (data.timestamp as number) || Date.now() / 1000;
          setWeaponAlert({ sessionId: sid, labels, confidence, timestamp });
          toastRef.current({
            variant: 'destructive',
            title: '⚠️ WEAPON DETECTED!',
            description: `Danger: ${labels.join(', ')} detected (${(confidence * 100).toFixed(0)}% confidence)`,
          });
          setTimeout(() => setWeaponAlert(null), 30000);
        }
        // Auto-end: visitor went inactive (e.g. delivery person left)
        if (data.type === 'session_ended') {
          const sid = data.sessionId as string;
          setActiveSession((prev) => (prev?.sessionId === sid ? null : prev));
          toastRef.current({
            title: 'Session ended',
            description: `Visitor session ended (${(data.reason as string) || 'inactive'}).`,
          });
          loadVisitorsRef.current();
        }
      });
      wsRef.current = ws;

      // Auto-reconnect on close (backend restart, network glitch, etc.)
      const origOnClose = ws.onclose;
      ws.onclose = (e) => {
        if (origOnClose) origOnClose.call(ws, e);
        if (!cancelled) {
          console.log('WebSocket disconnected, reconnecting in 2s...');
          reconnectTimer = setTimeout(connect, 2000);
        }
      };
    }

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Auto-detect active session from loaded visitors ──────
  // Fallback: if the WebSocket new_ring was missed (e.g. page loaded after ring),
  // pick up the latest active visitor session and show it as the live view.
  useEffect(() => {
    if (activeSession) return; // already showing a live session
    const active = visitors.find((v) => v.status === 'active');
    if (active) {
      setActiveSession({
        sessionId: active.id,
        imageUrl: active.imageUrl,
        greeting: active.transcript[0]?.content || '',
      });
    }
  }, [visitors, activeSession]);

  // ── Handlers ─────────────────────────────────────────────
  const handleLogout = async () => {
    await logout();
    toast({ title: 'Logged out', description: 'You have been logged out successfully.' });
  };

  const handleViewVisitor = (visitor: Visitor) => setSelectedVisitor(visitor);

  const handleRespond = (visitor: Visitor) => {
    setRespondingVisitor(visitor);
    setShowReplyModal(true);
  };

  const sendReply = async () => {
    if (!replyText.trim() || !respondingVisitor) return;
    try {
      await ownerReply(respondingVisitor.id, replyText);
      toast({ title: 'Reply sent', description: 'Your message has been sent to the visitor.' });
      setReplyText('');
      setShowReplyModal(false);
      setRespondingVisitor(null);
      loadVisitors();
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to send reply.' });
    }
  };

  // ── Voice reply ──────────────────────────────────────────
  const toggleVoiceRecording = async () => {
    if (isRecordingReply) {
      // Stop recording
      const mr = mediaRecorderRef.current;
      if (mr && mr.state !== 'inactive') {
        mr.stop();
      }
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mr = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        audioChunksRef.current = [];

        mr.ondataavailable = (e) => {
          if (e.data.size > 0) audioChunksRef.current.push(e.data);
        };

        mr.onstop = async () => {
          stream.getTracks().forEach((t) => t.stop());
          setIsRecordingReply(false);
          // Transcribe the recorded audio using backend STT
          const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
          if (blob.size > 1000) {
            try {
              const reader = new FileReader();
              const base64 = await new Promise<string | null>((resolve) => {
                reader.onloadend = () => {
                  const result = (reader.result as string).split(',')[1] || null;
                  resolve(result);
                };
                reader.readAsDataURL(blob);
              });
              if (base64) {
                const { transcript } = await transcribeAudio(base64);
                if (transcript?.trim()) {
                  setReplyText(transcript);
                } else {
                  toast({ title: 'Could not transcribe', description: 'Please type your message instead.' });
                }
              }
            } catch {
              toast({ variant: 'destructive', title: 'Transcription failed', description: 'Please type your message instead.' });
            }
          }
        };

        mr.start();
        mediaRecorderRef.current = mr;
        setIsRecordingReply(true);
      } catch {
        toast({ variant: 'destructive', title: 'Mic Error', description: 'Could not access microphone.' });
      }
    }
  };

  const handleEmergency = () => {
    toast({ variant: 'destructive', title: 'Emergency Alert', description: 'Emergency services have been notified.' });
  };

  const activeVisitors = visitors.filter((v) => v.status === 'active');
  const recentVisitors = visitors.filter((v) => v.status !== 'active').slice(0, 10);

  const formatTime = (timestamp: string) =>
    new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-background/95 backdrop-blur border-b border-border">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
                <Bell className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h1 className="font-semibold text-foreground">Dashboard</h1>
                <p className="text-xs text-muted-foreground">
                  {user?.name || user?.username || 'Owner'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={loadVisitors} disabled={isLoading}>
                <RefreshCw className={`w-4 h-4 mr-1 ${isLoading ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
              <Button variant="outline" size="sm" asChild>
                <Link to="/members">
                  <UserCog className="w-4 h-4 mr-1" />
                  Members
                </Link>
              </Button>
              <Button variant="outline" size="sm" asChild>
                <Link to="/history">
                  <History className="w-4 h-4 mr-1" />
                  History
                </Link>
              </Button>
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                <LogOut className="w-4 h-4 mr-1" />
                Logout
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="container mx-auto px-4 py-6">
        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-card rounded-xl border border-border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                <Users className="w-5 h-5 text-green-500" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{activeVisitors.length}</p>
                <p className="text-sm text-muted-foreground">Active Visitors</p>
              </div>
            </div>
          </div>
          <div className="bg-card rounded-xl border border-border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <Clock className="w-5 h-5 text-primary" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{visitors.length}</p>
                <p className="text-sm text-muted-foreground">Total Sessions</p>
              </div>
            </div>
          </div>
          <div className="bg-card rounded-xl border border-border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center">
                <MessageSquare className="w-5 h-5 text-accent" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">
                  {visitors.reduce((acc, v) => acc + v.transcript.length, 0)}
                </p>
                <p className="text-sm text-muted-foreground">Total Messages</p>
              </div>
            </div>
          </div>
        </div>

        {/* Emergency */}
        <div className="mb-6">
          <Button variant="destructive" className="w-full md:w-auto" onClick={handleEmergency}>
            <AlertTriangle className="w-4 h-4 mr-2" />
            Emergency Alert
          </Button>
        </div>

        {/* Weapon Alert Banner */}
        {weaponAlert && (
          <div className="mb-6 bg-red-600 text-white rounded-xl border-2 border-red-400 p-4 animate-pulse shadow-lg shadow-red-500/30">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-white/20 flex items-center justify-center">
                  <AlertTriangle className="w-7 h-7 text-white" />
                </div>
                <div>
                  <h3 className="text-lg font-bold">⚠️ WEAPON DETECTED</h3>
                  <p className="text-sm text-red-100">
                    {weaponAlert.labels.join(', ').toUpperCase()} detected with{' '}
                    {(weaponAlert.confidence * 100).toFixed(0)}% confidence
                  </p>
                  <p className="text-xs text-red-200 mt-1">
                    Session: {weaponAlert.sessionId.slice(0, 16)} •{' '}
                    {new Date(weaponAlert.timestamp * 1000).toLocaleTimeString()}
                  </p>
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  className="bg-white/20 hover:bg-white/30 text-white border-white/30"
                  onClick={() => setWeaponAlert(null)}
                >
                  <X className="w-4 h-4 mr-1" />
                  Dismiss
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Live Visitor Camera View */}
        {activeSession && (
          <section className="mb-8">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold text-foreground">Live Visitor</h2>
                <Badge className="bg-red-500/10 text-red-500 border-red-500/20 animate-pulse">
                  LIVE
                </Badge>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setActiveSession(null)}
              >
                <X className="w-4 h-4 mr-1" />
                Dismiss
              </Button>
            </div>
            <div className="bg-card rounded-xl border-2 border-primary/30 p-4">
              <div className="flex flex-col md:flex-row gap-4">
                {/* Visitor live stream */}
                <div className="w-full md:w-80 h-60 rounded-lg overflow-hidden bg-muted relative">
                  {activeSession && activeSession.sessionId ? (
                    <LiveStreamView sessionId={activeSession.sessionId} fallbackUrl={activeSession.imageUrl ? getAssetUrl(activeSession.imageUrl) : undefined} />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <Users className="w-12 h-12 text-muted-foreground/50" />
                      <span className="text-muted-foreground text-sm ml-2">No camera image</span>
                    </div>
                  )}
                  <div className="absolute top-2 left-2 bg-red-500/90 text-white text-xs px-2 py-1 rounded-full flex items-center gap-1">
                    <div className="w-2 h-2 bg-white rounded-full animate-pulse" />
                    Session: {activeSession?.sessionId.slice(0, 16) || 'N/A'}
                  </div>
                </div>

                {/* Greeting / quick actions */}
                <div className="flex-1 flex flex-col gap-3">
                  <div className="bg-muted/50 rounded-lg p-3">
                    <p className="text-xs text-muted-foreground mb-1">AI Greeting</p>
                    <p className="text-sm text-foreground">{activeSession.greeting || 'Processing...'}</p>
                  </div>
                  <div className="flex gap-2 mt-auto">
                    <Button
                      className="flex-1"
                      onClick={() => {
                        const visitor = visitors.find((v) => v.id === activeSession.sessionId);
                        if (visitor) handleRespond(visitor);
                      }}
                    >
                      <MessageSquare className="w-4 h-4 mr-2" />
                      Reply to Visitor
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => {
                        const visitor = visitors.find((v) => v.id === activeSession.sessionId);
                        if (visitor) handleViewVisitor(visitor);
                      }}
                    >
                      <Eye className="w-4 h-4 mr-2" />
                      Details
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Active */}
        {activeVisitors.length > 0 && (
          <section className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <h2 className="text-lg font-semibold text-foreground">Active Visitors</h2>
              <Badge className="bg-green-500/10 text-green-500 border-green-500/20">
                {activeVisitors.length} at door
              </Badge>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {activeVisitors.map((visitor) => (
                <VisitorCard
                  key={visitor.id}
                  visitor={visitor}
                  onView={handleViewVisitor}
                  onRespond={handleRespond}
                  isActive
                />
              ))}
            </div>
          </section>
        )}

        {/* Recent */}
        <section>
          <h2 className="text-lg font-semibold text-foreground mb-4">Recent Visitors</h2>
          {recentVisitors.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {recentVisitors.map((visitor) => (
                <VisitorCard
                  key={visitor.id}
                  visitor={visitor}
                  onView={handleViewVisitor}
                  onRespond={handleRespond}
                />
              ))}
            </div>
          ) : (
            <div className="text-center py-12 bg-muted/30 rounded-xl border border-border">
              <Bell className="w-12 h-12 mx-auto text-muted-foreground/50 mb-3" />
              <p className="text-muted-foreground">No visitors yet</p>
            </div>
          )}
        </section>
      </main>

      {/* View Visitor Dialog */}
      <Dialog open={!!selectedVisitor} onOpenChange={() => setSelectedVisitor(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Visitor Details</DialogTitle>
            <DialogDescription>{selectedVisitor?.aiSummary || 'Session details'}</DialogDescription>
          </DialogHeader>

          {selectedVisitor && (
            <div className="space-y-4">
              {selectedVisitor.imageUrl && (
                <div className="w-full h-48 rounded-lg overflow-hidden bg-muted">
                  <img
                    src={getAssetUrl(selectedVisitor.imageUrl)}
                    alt="Visitor"
                    className="w-full h-full object-cover"
                  />
                </div>
              )}

              <ScrollArea className="h-64 rounded-lg border border-border p-4">
                <div className="space-y-3">
                  {selectedVisitor.transcript.map((entry, index) => (
                    <div
                      key={index}
                      className={`p-3 rounded-lg ${
                        entry.role === 'visitor' ? 'bg-primary/10 border border-primary/20' : 'bg-muted'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-muted-foreground">
                          {entry.role === 'visitor' ? 'Visitor' : 'Doorbell'}
                        </span>
                        <span className="text-xs text-muted-foreground">{formatTime(entry.timestamp)}</span>
                      </div>
                      <p className="text-sm text-foreground">{entry.content}</p>
                    </div>
                  ))}
                </div>
              </ScrollArea>

              {selectedVisitor.status === 'active' && (
                <div className="flex gap-2">
                  <Button
                    className="flex-1"
                    onClick={() => {
                      setSelectedVisitor(null);
                      handleRespond(selectedVisitor);
                    }}
                  >
                    <MessageSquare className="w-4 h-4 mr-2" />
                    Respond
                  </Button>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Reply Modal */}
      <Dialog open={showReplyModal} onOpenChange={setShowReplyModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Reply to Visitor</DialogTitle>
            <DialogDescription>Send a text or voice message to the visitor at your door</DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="flex gap-2">
              <Input
                placeholder="Type your message..."
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && sendReply()}
              />
              <Button variant="outline" size="icon" onClick={toggleVoiceRecording}>
                {isRecordingReply ? (
                  <Mic className="w-4 h-4 text-red-500 animate-pulse" />
                ) : (
                  <MicOff className="w-4 h-4" />
                )}
              </Button>
              <Button onClick={sendReply} disabled={!replyText.trim()}>
                <Send className="w-4 h-4" />
              </Button>
            </div>

            {/* Quick replies */}
            <div className="flex flex-wrap gap-2">
              {[
                "I'll be right there!",
                'Please wait a moment',
                'Leave it at the door',
                "I'm not available right now",
              ].map((text) => (
                <Button key={text} variant="outline" size="sm" onClick={() => setReplyText(text)}>
                  {text}
                </Button>
              ))}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/**
 * LiveStreamView — polls the snapshot endpoint with fetch + blob URLs.
 * Waits for each frame to load before requesting the next one so we never
 * pile up queued requests or hit stale-timeout bugs.
 */
function LiveStreamView({ sessionId, fallbackUrl }: { sessionId: string; fallbackUrl?: string }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [consecutiveErrors, setConsecutiveErrors] = useState(0);
  const MAX_ERRORS_BEFORE_FALLBACK = 15; // ~3-4 s of failures at 250ms each

  useEffect(() => {
    let active = true;
    let currentBlobUrl: string | null = null;

    async function poll() {
      while (active) {
        try {
          const res = await fetch(
            `${LIVE_API_BASE}/api/stream/${sessionId}/snapshot?_t=${Date.now()}`,
          );
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const blob = await res.blob();
          if (!active) break;

          // Revoke previous blob URL to avoid memory leaks
          if (currentBlobUrl) URL.revokeObjectURL(currentBlobUrl);
          currentBlobUrl = URL.createObjectURL(blob);
          setBlobUrl(currentBlobUrl);
          setConsecutiveErrors(0); // reset on success
        } catch {
          if (!active) break;
          setConsecutiveErrors((prev) => prev + 1);
        }
        // Wait before next poll — small gap keeps it smooth (~4 FPS)
        await new Promise((r) => setTimeout(r, 250));
      }
    }

    poll();

    return () => {
      active = false;
      if (currentBlobUrl) URL.revokeObjectURL(currentBlobUrl);
    };
  }, [sessionId]);

  // Fall back to static image only after sustained errors and no frame ever loaded
  if (consecutiveErrors >= MAX_ERRORS_BEFORE_FALLBACK && !blobUrl && fallbackUrl) {
    return (
      <img
        src={fallbackUrl}
        alt="Visitor at door"
        className="w-full h-full object-cover"
      />
    );
  }

  return (
    <img
      src={blobUrl || fallbackUrl || ''}
      alt="Live visitor stream"
      className="w-full h-full object-cover"
    />
  );
}
