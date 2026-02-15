import { useState, useCallback, useRef, useEffect } from 'react';
import Webcam from 'react-webcam';
import { RingButton } from '@/components/RingButton';
import { StatusIndicator } from '@/components/StatusIndicator';
import { TranscriptDisplay } from '@/components/TranscriptDisplay';
import { ringDoorbell, getAIReply, speakText, connectWebSocket, transcribeAudio } from '@/lib/api';
import { Home, Mic, MicOff, Camera, CameraOff, Maximize, Minimize } from 'lucide-react';

type DoorbellState = 'idle' | 'ringing' | 'greeting' | 'awaiting_input' | 'processing' | 'speaking';

interface TranscriptEntry {
  role: 'visitor' | 'doorbell';
  content: string;
  timestamp: string;
}

export default function Doorbell() {
  const [state, setState] = useState<DoorbellState>('idle');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [statusMessage, setStatusMessage] = useState<string>('');
  const [manualInput, setManualInput] = useState('');

  const [isCameraReady, setIsCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Audio recording state
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  const webcamRef = useRef<Webcam>(null);

  // ── Fullscreen ──────────────────────────────────────────
  const toggleFullScreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', handler);
    return () => document.removeEventListener('fullscreenchange', handler);
  }, []);

  // ── Camera ──────────────────────────────────────────────
  const handleCameraError = useCallback((error: string | DOMException) => {
    const errorName = (error as DOMException).name || String(error);
    if (errorName === 'NotFoundError' || errorName.includes('not found')) {
      setCameraError('No camera found. You can still ring the doorbell.');
    } else if (errorName === 'NotAllowedError' || errorName.includes('permission')) {
      setCameraError('Camera access denied. Please enable camera permissions.');
    } else {
      setCameraError('Camera error. Ringing will proceed without video.');
    }
    setIsCameraReady(false);
  }, []);

  const handleCameraSuccess = useCallback(() => {
    setIsCameraReady(true);
    setCameraError(null);
  }, []);

  const requestCameraAccess = async () => {
    try {
      setCameraError(null);
      await navigator.mediaDevices.getUserMedia({ video: true });
    } catch (err) {
      handleCameraError(err as DOMException);
    }
  };

  // ── Audio recording helpers ────────────────────────────
  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      mediaRecorder.start();
      mediaRecorderRef.current = mediaRecorder;
      setIsRecording(true);
    } catch (err) {
      console.error('Mic access error:', err);
      setStatusMessage('Microphone access denied');
    }
  }, []);

  const stopRecording = useCallback((): Promise<string | null> => {
    return new Promise((resolve) => {
      const mr = mediaRecorderRef.current;
      if (!mr || mr.state === 'inactive') {
        setIsRecording(false);
        resolve(null);
        return;
      }

      mr.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        // Stop all tracks
        mr.stream.getTracks().forEach((t) => t.stop());
        setIsRecording(false);

        if (blob.size < 1000) {
          resolve(null);
          return;
        }

        // Convert to base64
        const reader = new FileReader();
        reader.onloadend = () => {
          const base64 = (reader.result as string).split(',')[1] || null;
          resolve(base64);
        };
        reader.readAsDataURL(blob);
      };

      mr.stop();
    });
  }, []);

  // ── WebSocket for owner replies ────────────────────────
  useEffect(() => {
    if (!sessionId) return;

    const ws = connectWebSocket(sessionId, (data) => {
      if (data.type === 'owner_reply' && data.message) {
        const entry: TranscriptEntry = {
          role: 'doorbell',
          content: `[Owner] ${data.message}`,
          timestamp: new Date().toISOString(),
        };
        setTranscript((prev) => [...prev, entry]);
        speakText(String(data.message));
      }
    });
    wsRef.current = ws;

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [sessionId]);

  // ── Message handling ───────────────────────────────────
  const handleSendMessage = useCallback(
    async (message: string) => {
      if (!message.trim()) return;

      setTranscript((prev) => [
        ...prev,
        { role: 'visitor', content: message, timestamp: new Date().toISOString() },
      ]);
      setManualInput('');

      setState('processing');
      setStatusMessage('Thinking...');

      try {
        const { reply } = await getAIReply(sessionId || '', message);
        setTranscript((prev) => [
          ...prev,
          { role: 'doorbell', content: reply, timestamp: new Date().toISOString() },
        ]);

        setState('speaking');
        setStatusMessage('Speaking...');
        await speakText(reply);

        setState('awaiting_input');
        setStatusMessage('Listening — speak or type your message');
      } catch {
        setState('idle');
        setStatusMessage('Error processing your message');
      }
    },
    [sessionId],
  );

  // ── Ring doorbell ──────────────────────────────────────
  const handleRing = useCallback(async () => {
    setState('ringing');
    setStatusMessage('Connecting...');
    setTranscript([]);

    try {
      // Capture image
      let imageBase64: string | null = null;
      if (webcamRef.current && isCameraReady) {
        const dataUrl = webcamRef.current.getScreenshot();
        if (dataUrl) imageBase64 = dataUrl.split(',')[1] || null;
      }

      // Start a short audio recording (3 seconds) for initial greeting
      await startRecording();
      setStatusMessage('Recording... speak now');
      await new Promise((r) => setTimeout(r, 3000));
      const audioBase64 = await stopRecording();

      setStatusMessage('Processing...');
      const { sessionId: newSessionId, greeting } = await ringDoorbell(imageBase64, audioBase64);
      setSessionId(newSessionId);

      setState('greeting');
      setStatusMessage('');

      setTranscript([{ role: 'doorbell', content: greeting, timestamp: new Date().toISOString() }]);

      setState('speaking');
      setStatusMessage('Speaking...');
      await speakText(greeting);

      setState('awaiting_input');
      setStatusMessage('Listening — speak or type your message');
    } catch (error) {
      console.error('Ring error:', error);
      setState('idle');
      setStatusMessage('Connection failed. Please try again.');
    }
  }, [isCameraReady, startRecording, stopRecording]);

  // ── Submit recorded audio as message ───────────────────
  const handleVoiceSubmit = useCallback(async () => {
    if (isRecording) {
      const audioBase64 = await stopRecording();
      if (audioBase64) {
        setState('processing');
        setStatusMessage('Transcribing your audio...');
        try {
          // Send audio to backend for Groq Whisper transcription
          const { transcript } = await transcribeAudio(audioBase64);
          if (transcript && transcript.trim()) {
            // Send the transcribed text as a follow-up message
            handleSendMessage(transcript);
          } else {
            setState('awaiting_input');
            setStatusMessage('Could not understand audio. Please try again or type your message.');
          }
        } catch {
          setState('awaiting_input');
          setStatusMessage('Failed to transcribe audio. Please try again or type your message.');
        }
      }
    } else {
      await startRecording();
    }
  }, [isRecording, startRecording, stopRecording, handleSendMessage]);

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (manualInput.trim()) handleSendMessage(manualInput);
  };

  const handleEndConversation = useCallback(() => {
    setState('idle');
    setSessionId(null);
    setTranscript([]);
    setStatusMessage('');
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach((t) => t.stop());
    }
    setIsRecording(false);
    wsRef.current?.close();
  }, []);

  const getStatus = () => {
    switch (state) {
      case 'ringing':
      case 'processing':
        return 'processing';
      case 'greeting':
      case 'speaking':
        return 'speaking';
      default:
        return 'idle';
    }
  };

  const isNotFoundError = cameraError?.includes('No camera found');

  return (
    <div className="doorbell-page min-h-screen flex flex-col items-center justify-center p-6">
      {/* Hidden Webcam */}
      <div className="absolute opacity-0 pointer-events-none">
        <Webcam
          audio={false}
          ref={webcamRef}
          screenshotFormat="image/jpeg"
          width={640}
          height={480}
          onUserMedia={handleCameraSuccess}
          onUserMediaError={handleCameraError}
        />
      </div>

      {/* Header */}
      <div className="absolute top-6 left-6 flex items-center gap-2">
        <Home className="w-5 h-5 text-doorbell-glow/60" />
        <span className="text-doorbell-glow/60 text-sm font-medium tracking-wide">SMART DOORBELL</span>
      </div>

      {/* Camera / Fullscreen buttons */}
      <div className="absolute top-6 right-6 flex gap-3">
        <button
          onClick={toggleFullScreen}
          className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-doorbell-surface border border-doorbell-glow/30 text-doorbell-glow text-xs font-medium hover:bg-doorbell-glow/10 transition-colors"
        >
          {isFullscreen ? <Minimize className="w-4 h-4" /> : <Maximize className="w-4 h-4" />}
          <span>{isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}</span>
        </button>

        {!isCameraReady ? (
          <button
            onClick={isNotFoundError ? undefined : requestCameraAccess}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
              isNotFoundError
                ? 'bg-amber-500/10 border border-amber-500/30 text-amber-500 cursor-default'
                : 'bg-red-500/10 border border-red-500/30 text-red-500 hover:bg-red-500/20'
            }`}
          >
            <CameraOff className="w-4 h-4" />
            <span>{isNotFoundError ? 'No Camera' : 'Enable Camera'}</span>
          </button>
        ) : (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-green-500/10 border border-green-500/30 text-green-500 text-xs font-medium">
            <Camera className="w-4 h-4" />
            <span>Camera Active</span>
          </div>
        )}
      </div>

      {/* Main Content */}
      <div className="flex flex-col items-center gap-8 w-full max-w-lg">
        {cameraError && (
          <div
            className={`w-full text-center p-2 mb-4 text-xs rounded border ${
              isNotFoundError
                ? 'text-amber-400 bg-amber-950/30 border-amber-900/50'
                : 'text-red-400 bg-red-950/30 border-red-900/50'
            }`}
          >
            {cameraError}
          </div>
        )}

        {/* Ring Button */}
        <div className="mb-8">
          <RingButton onRing={handleRing} isActive={state !== 'idle'} disabled={state === 'processing'} />
        </div>

        {/* Status */}
        {state !== 'idle' && <StatusIndicator status={getStatus()} message={statusMessage} />}

        {/* Transcript */}
        {transcript.length > 0 && (
          <TranscriptDisplay entries={transcript} isListening={isRecording} />
        )}

        {/* Input Controls */}
        {state === 'awaiting_input' && (
          <div className="w-full flex flex-col gap-4 mt-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex items-center justify-center gap-4">
              <button
                onClick={handleVoiceSubmit}
                className={`p-4 rounded-full transition-all duration-300 ${
                  isRecording
                    ? 'bg-red-500/20 text-red-500 animate-pulse'
                    : 'bg-doorbell-glow/10 text-doorbell-glow/60 hover:bg-doorbell-glow/20'
                }`}
              >
                {isRecording ? <Mic className="w-8 h-8" /> : <MicOff className="w-8 h-8" />}
              </button>
              <div className="flex flex-col">
                <span className="text-doorbell-glow font-medium">
                  {isRecording ? 'Recording... tap to stop' : 'Tap mic or type below'}
                </span>
                <span className="text-doorbell-glow/40 text-xs">Speak or type your message</span>
              </div>
            </div>

            <div className="flex gap-3 justify-center">
              <button
                onClick={handleEndConversation}
                className="px-6 py-2 bg-doorbell-surface text-doorbell-glow border border-doorbell-glow/30 rounded-full text-sm font-medium hover:bg-doorbell-glow/10 transition-colors"
              >
                End Conversation
              </button>
            </div>

            <form onSubmit={handleManualSubmit} className="flex gap-2 w-full mt-2">
              <input
                type="text"
                value={manualInput}
                onChange={(e) => setManualInput(e.target.value)}
                placeholder="Or type your message..."
                className="flex-1 bg-doorbell-surface border border-doorbell-glow/30 rounded-lg px-4 py-2 text-foreground focus:outline-none focus:border-doorbell-glow/60 text-sm"
              />
              <button
                type="submit"
                disabled={!manualInput.trim()}
                className="bg-doorbell-glow/20 text-doorbell-glow border border-doorbell-glow/30 rounded-lg px-4 py-2 hover:bg-doorbell-glow/30 disabled:opacity-50 text-sm"
              >
                Send
              </button>
            </form>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="absolute bottom-6 text-center">
        <p className="text-doorbell-glow/40 text-xs">Smart Doorbell System • Voice & Video Enabled</p>
      </div>
    </div>
  );
}
