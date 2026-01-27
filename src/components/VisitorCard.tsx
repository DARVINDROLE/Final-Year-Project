import { cn } from '@/lib/utils';
import { 
  Package, 
  Users, 
  AlertCircle, 
  Home,
  HelpCircle,
  Clock,
  MessageSquare,
  Eye
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { type Visitor, getAssetUrl } from '@/lib/api';

interface VisitorCardProps {
  visitor: Visitor;
  onView: (visitor: Visitor) => void;
  onRespond: (visitor: Visitor) => void;
  isActive?: boolean;
}

const visitorTypeConfig = {
  delivery: {
    icon: Package,
    label: 'Delivery',
    color: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  },
  friend: {
    icon: Users,
    label: 'Friend/Family',
    color: 'bg-green-500/10 text-green-500 border-green-500/20',
  },
  solicitor: {
    icon: AlertCircle,
    label: 'Solicitor',
    color: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
  },
  neighbor: {
    icon: Home,
    label: 'Neighbor',
    color: 'bg-purple-500/10 text-purple-500 border-purple-500/20',
  },
  unknown: {
    icon: HelpCircle,
    label: 'Unknown',
    color: 'bg-muted text-muted-foreground border-muted-foreground/20',
  },
};

const statusConfig = {
  active: {
    label: 'Active',
    color: 'bg-green-500/10 text-green-500 border-green-500/20',
  },
  completed: {
    label: 'Completed',
    color: 'bg-muted text-muted-foreground border-muted-foreground/20',
  },
  ignored: {
    label: 'Ignored',
    color: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
  },
};

export function VisitorCard({ visitor, onView, onRespond, isActive }: VisitorCardProps) {
  const typeConfig = visitorTypeConfig[visitor.visitorType];
  const TypeIcon = typeConfig.icon;
  const status = statusConfig[visitor.status];

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date.toDateString() === today.toDateString()) {
      return 'Today';
    } else if (date.toDateString() === yesterday.toDateString()) {
      return 'Yesterday';
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  return (
    <div 
      className={cn(
        "visitor-card p-4 transition-all duration-300",
        isActive && "ring-2 ring-primary/50 border-primary/30"
      )}
    >
      <div className="flex gap-4">
        {/* Visitor Image */}
        <div className="relative flex-shrink-0">
          <div className="w-20 h-20 rounded-lg overflow-hidden bg-muted">
            {visitor.imageUrl ? (
              <img 
                src={getAssetUrl(visitor.imageUrl)} 
                alt="Visitor" 
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <TypeIcon className="w-8 h-8 text-muted-foreground" />
              </div>
            )}
          </div>
          {isActive && (
            <div className="absolute -top-1 -right-1 w-4 h-4 bg-green-500 rounded-full border-2 border-card animate-pulse" />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className={cn("text-xs", typeConfig.color)}>
                <TypeIcon className="w-3 h-3 mr-1" />
                {typeConfig.label}
              </Badge>
              <Badge variant="outline" className={cn("text-xs", status.color)}>
                {status.label}
              </Badge>
            </div>
          </div>

          <p className="text-sm text-foreground font-medium mb-1 line-clamp-2">
            {visitor.aiSummary}
          </p>

          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatDate(visitor.timestamp)} at {formatTime(visitor.timestamp)}
            </span>
            <span className="flex items-center gap-1">
              <MessageSquare className="w-3 h-3" />
              {visitor.transcript.length} messages
            </span>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2 mt-4 pt-3 border-t border-border">
        <Button 
          variant="outline" 
          size="sm" 
          className="flex-1"
          onClick={() => onView(visitor)}
        >
          <Eye className="w-4 h-4 mr-1" />
          View
        </Button>
        {visitor.status === 'active' && (
          <Button 
            size="sm" 
            className="flex-1"
            onClick={() => onRespond(visitor)}
          >
            <MessageSquare className="w-4 h-4 mr-1" />
            Respond
          </Button>
        )}
      </div>
    </div>
  );
}
