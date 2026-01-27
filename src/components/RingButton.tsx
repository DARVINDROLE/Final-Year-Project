import { useState } from 'react';
import { Bell } from 'lucide-react';
import { cn } from '@/lib/utils';

interface RingButtonProps {
  onRing: () => void;
  isActive: boolean;
  disabled?: boolean;
}

export function RingButton({ onRing, isActive, disabled }: RingButtonProps) {
  const [ripples, setRipples] = useState<number[]>([]);

  const handleClick = () => {
    if (disabled || isActive) return;
    
    // Add ripple effect
    const newRipple = Date.now();
    setRipples(prev => [...prev, newRipple]);
    
    // Remove ripple after animation
    setTimeout(() => {
      setRipples(prev => prev.filter(r => r !== newRipple));
    }, 1000);

    onRing();
  };

  return (
    <div className="relative flex items-center justify-center">
      {/* Outer glow rings */}
      <div 
        className={cn(
          "absolute w-72 h-72 rounded-full transition-all duration-1000",
          isActive 
            ? "bg-doorbell-ring/10 animate-scale-pulse" 
            : "bg-doorbell-glow/5"
        )}
      />
      <div 
        className={cn(
          "absolute w-56 h-56 rounded-full transition-all duration-700",
          isActive 
            ? "bg-doorbell-ring/15 animate-scale-pulse" 
            : "bg-doorbell-glow/10"
        )}
        style={{ animationDelay: '0.2s' }}
      />
      
      {/* Ripple effects */}
      {ripples.map(ripple => (
        <div
          key={ripple}
          className="absolute w-44 h-44 rounded-full border-2 border-doorbell-ring/50 animate-ripple"
        />
      ))}
      
      {/* Main button */}
      <button
        onClick={handleClick}
        disabled={disabled || isActive}
        className={cn(
          "relative w-44 h-44 rounded-full flex items-center justify-center ring-button",
          "bg-gradient-to-br from-doorbell-surface to-doorbell-bg",
          "border-4 transition-all duration-300",
          isActive
            ? "border-doorbell-ring ring-glow-active cursor-wait"
            : "border-doorbell-glow/50 ring-glow hover:border-doorbell-glow cursor-pointer",
          disabled && "opacity-50 cursor-not-allowed"
        )}
        aria-label="Ring doorbell"
      >
        {/* Inner ring */}
        <div 
          className={cn(
            "absolute inset-3 rounded-full border-2 transition-colors duration-300",
            isActive ? "border-doorbell-ring/30" : "border-doorbell-glow/20"
          )}
        />
        
        {/* Bell icon */}
        <Bell 
          className={cn(
            "w-16 h-16 transition-all duration-300",
            isActive 
              ? "text-doorbell-ring animate-pulse" 
              : "text-doorbell-glow"
          )}
          strokeWidth={1.5}
        />
      </button>
      
      {/* Text label */}
      <div className="absolute -bottom-16 text-center">
        <p 
          className={cn(
            "text-lg font-medium tracking-wider uppercase transition-colors duration-300",
            isActive ? "text-doorbell-ring" : "text-doorbell-glow/80"
          )}
        >
          {isActive ? "Connected" : "Press to Ring"}
        </p>
      </div>
    </div>
  );
}
