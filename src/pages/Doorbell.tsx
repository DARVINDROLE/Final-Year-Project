import { useState, useCallback, useRef, useEffect } from 'react';
import Webcam from 'react-webcam';
import { RingButton } from '@/components/RingButton';
import { StatusIndicator } from '@/components/StatusIndicator';
import { TranscriptDisplay } from '@/components/TranscriptDisplay';
import { ringDoorbell, getAIReply, speakText } from '@/lib/api';
import { Home, Mic, MicOff, Camera, CameraOff, Maximize, Minimize } from 'lucide-react';
import { useSpeechRecognition } from '@/hooks/useSpeechRecognition';

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
  
  const webcamRef = useRef<Webcam>(null);

  const toggleFullScreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().then(() => {
        setIsFullscreen(true);
      }).catch((err) => {
        console.error(`Error attempting to enable full-screen mode: ${err.message} (${err.name})`);
      });
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
        setIsFullscreen(false);
      }
    }
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  const handleCameraError = useCallback((error: string | DOMException) => {
    console.error('Camera error:', error);
    const errorName = (error as DOMException).name || (error as any).toString();
    
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
    console.log('Camera started successfully');
    setIsCameraReady(true);
    setCameraError(null);
  }, []);

  const requestCameraAccess = async () => {
    try {
      setCameraError(null);
      await navigator.mediaDevices.getUserMedia({ video: true });
      // The Webcam component will handle the rest via onUserMedia
    } catch (err) {
      handleCameraError(err as DOMException);
    }
  };

  const handleSendMessage = useCallback(async (message: string) => {
    if (!message.trim()) return;

    // Add visitor message to transcript
    const visitorEntry: TranscriptEntry = {
      role: 'visitor',
      content: message,
      timestamp: new Date().toISOString(),
    };
    setTranscript(prev => [...prev, visitorEntry]);
    setManualInput('');

    // Process with AI
    setState('processing');
    setStatusMessage('Thinking...');

    try {
      const { reply } = await getAIReply(sessionId || '', message);
      
      // Add AI response to transcript
      const doorbellEntry: TranscriptEntry = {
        role: 'doorbell',
        content: reply,
        timestamp: new Date().toISOString(),
      };
      setTranscript(prev => [...prev, doorbellEntry]);

      // Speak the reply
      setState('speaking');
      setStatusMessage('Speaking...');
      await speakText(reply);

      // Go back to waiting for input
      setState('awaiting_input');
      setStatusMessage('Listening...');

    } catch (error) {
      console.error('AI reply error:', error);
      setState('idle');
      setStatusMessage('Error processing your message');
    }
  }, [sessionId]);

  const { isListening, error: speechError, startListening, stopListening } = useSpeechRecognition({
    onResult: (text) => {
      handleSendMessage(text);
    },
    onEnd: () => {
      // If we are still in awaiting_input but not listening, we might want to restart?
      // For now, let's keep it simple.
    }
  });

  // Start listening automatically when state changes to awaiting_input
  useEffect(() => {
    if (state === 'awaiting_input') {
      startListening();
    } else {
      stopListening();
    }
  }, [state, startListening, stopListening]);

  // Update status message with speech error if present
  useEffect(() => {
    if (speechError) {
      setStatusMessage(`Mic Error: ${speechError}`);
    }
  }, [speechError]);

  const handleRing = useCallback(async () => {
    setState('ringing');
    setStatusMessage('Connecting...');
    setTranscript([]);

    try {
      // Capture image from webcam if available
      let imageSrc: string | null = null;
      if (webcamRef.current && isCameraReady) {
        imageSrc = webcamRef.current.getScreenshot();
      } else {
        console.warn("Camera not ready, sending without image");
      }

      // Ring the doorbell and get greeting (passing the image)
      const { sessionId: newSessionId, greeting } = await ringDoorbell(imageSrc);
      setSessionId(newSessionId);

      // Play greeting
      setState('greeting');
      setStatusMessage('');
      
      const doorbellEntry: TranscriptEntry = {
        role: 'doorbell',
        content: greeting,
        timestamp: new Date().toISOString(),
      };
      setTranscript([doorbellEntry]);
      
      setState('speaking');
      setStatusMessage('Speaking...');
      await speakText(greeting);

      // Start waiting for input after greeting
      setState('awaiting_input');
      setStatusMessage('Listening...');

    } catch (error) {
      console.error('Ring error:', error);
      setState('idle');
      setStatusMessage('Connection failed. Please try again.');
    }
  }, [isCameraReady]);

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (manualInput.trim()) {
      handleSendMessage(manualInput);
    }
  };

  // Handle end conversation
  const handleEndConversation = useCallback(() => {
    setState('idle');
    setSessionId(null);
    setTranscript([]);
    setStatusMessage('');
    stopListening();
  }, [stopListening]);

  // Map state to status for StatusIndicator
  const getStatus = () => {
    switch (state) {
      case 'ringing':
      case 'processing':
        return 'processing';
      case 'awaiting_input':
        return isListening ? 'speaking' : 'idle'; // Pulse if listening
      case 'greeting':
      case 'speaking':
        return 'speaking';
      default:
        return 'idle';
    }
  };

  const isNotFoundError = cameraError && cameraError.includes('No camera found');

  return (
    <div className="doorbell-page min-h-screen flex flex-col items-center justify-center p-6">
      {/* Hidden Webcam for Capture */}
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
        <span className="text-doorbell-glow/60 text-sm font-medium tracking-wide">
          KANDELL RESIDENCE
        </span>
      </div>
      
      {/* Camera Status (Top Right) */}
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
        
        {/* Camera Error Message */}
        {cameraError && (
          <div className={`w-full text-center p-2 mb-4 text-xs rounded border ${ 
            isNotFoundError 
              ? 'text-amber-400 bg-amber-950/30 border-amber-900/50' 
              : 'text-red-400 bg-red-950/30 border-red-900/50'
          }`}> 
            {cameraError}
          </div>
        )}

        {/* Ring Button */}
        <div className="mb-8">
          <RingButton 
            onRing={handleRing}
            isActive={state !== 'idle'}
            disabled={state === 'processing'}
          />
        </div>

        {/* Status Indicator */}
        {state !== 'idle' && (
          <StatusIndicator 
            status={getStatus()}
            message={statusMessage}
          />
        )}

        {/* Input Controls */}
        {state === 'awaiting_input' && (
          <div className="w-full flex flex-col gap-4 mt-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex items-center justify-center gap-4">
              <div className={`p-4 rounded-full transition-all duration-300 ${isListening ? 'bg-red-500/20 text-red-500 animate-pulse' : 'bg-doorbell-glow/10 text-doorbell-glow/40'}`}>
                {isListening ? <Mic className="w-8 h-8" /> : <MicOff className="w-8 h-8" />}
              </div>
              <div className="flex flex-col">
                <span className="text-doorbell-glow font-medium">
                  {isListening ? 'I\'m listening...' : 'Microphone off'}
                </span>
                <span className="text-doorbell-glow/40 text-xs">
                  Speak now or use the text box below
                </span>
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
        <p className="text-doorbell-glow/40 text-xs">
          Smart Doorbell System • Voice Enabled
        </p>
      </div>
    </div>
  );
}
