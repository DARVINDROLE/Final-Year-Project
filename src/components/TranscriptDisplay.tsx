import { cn } from '@/lib/utils';
import { User, Bot } from 'lucide-react';

interface TranscriptEntry {
  role: 'visitor' | 'doorbell';
  content: string;
  timestamp: string;
}

interface TranscriptDisplayProps {
  entries: TranscriptEntry[];
  currentTranscript?: string;
  isListening?: boolean;
}

export function TranscriptDisplay({ 
  entries, 
  currentTranscript,
  isListening 
}: TranscriptDisplayProps) {
  return (
    <div className="w-full max-w-md mx-auto space-y-3">
      {entries.map((entry, index) => (
        <div
          key={index}
          className={cn(
            "flex gap-3 p-4 rounded-xl fade-in",
            entry.role === 'visitor' 
              ? "bg-primary/10 border border-primary/20" 
              : "bg-doorbell-surface/80 border border-doorbell-glow/20"
          )}
          style={{ animationDelay: `${index * 0.1}s` }}
        >
          <div 
            className={cn(
              "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
              entry.role === 'visitor' 
                ? "bg-primary/20" 
                : "bg-doorbell-glow/20"
            )}
          >
            {entry.role === 'visitor' ? (
              <User className="w-4 h-4 text-primary" />
            ) : (
              <Bot className="w-4 h-4 text-doorbell-glow" />
            )}
          </div>
          
          <div className="flex-1 min-w-0">
            <p 
              className={cn(
                "text-sm font-medium mb-1",
                entry.role === 'visitor' 
                  ? "text-primary" 
                  : "text-doorbell-glow"
              )}
            >
              {entry.role === 'visitor' ? 'You' : 'Doorbell'}
            </p>
            <p className="text-foreground/90 leading-relaxed">
              {entry.content}
            </p>
          </div>
        </div>
      ))}

      {/* Current speech being transcribed */}
      {isListening && currentTranscript && (
        <div className="flex gap-3 p-4 rounded-xl bg-primary/5 border border-primary/10 border-dashed">
          <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-primary/10">
            <User className="w-4 h-4 text-primary animate-pulse" />
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-primary/70 mb-1">Speaking...</p>
            <p className="text-foreground/60 italic">{currentTranscript}</p>
          </div>
        </div>
      )}
    </div>
  );
}
