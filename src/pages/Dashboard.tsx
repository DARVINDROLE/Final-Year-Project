import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { VisitorCard } from '@/components/VisitorCard';
import { getVisitorLogs, logout, isAuthenticated, ownerReply, type Visitor, getAssetUrl } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';
import {
  Bell,
  LogOut,
  History,
  Send,
  Mic,
  X,
  AlertTriangle,
  RefreshCw,
  Users,
  Clock,
  MessageSquare,
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

export default function Dashboard() {
  const [visitors, setVisitors] = useState<Visitor[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedVisitor, setSelectedVisitor] = useState<Visitor | null>(null);
  const [replyText, setReplyText] = useState('');
  const [showReplyModal, setShowReplyModal] = useState(false);
  const [respondingVisitor, setRespondingVisitor] = useState<Visitor | null>(null);
  
  const navigate = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    if (!isAuthenticated()) {
      navigate('/login');
      return;
    }
    loadVisitors();
  }, [navigate]);

  const loadVisitors = async () => {
    setIsLoading(true);
    try {
      const logs = await getVisitorLogs();
      setVisitors(logs);
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to load visitor logs.',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
    toast({
      title: 'Logged out',
      description: 'You have been logged out successfully.',
    });
  };

  const handleViewVisitor = (visitor: Visitor) => {
    setSelectedVisitor(visitor);
  };

  const handleRespond = (visitor: Visitor) => {
    setRespondingVisitor(visitor);
    setShowReplyModal(true);
  };

  const sendReply = async () => {
    if (!replyText.trim() || !respondingVisitor) return;

    try {
      await ownerReply(respondingVisitor.id, replyText, false);
      toast({
        title: 'Reply sent',
        description: 'Your message has been sent to the visitor.',
      });
      setReplyText('');
      setShowReplyModal(false);
      setRespondingVisitor(null);
      loadVisitors();
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to send reply.',
      });
    }
  };

  const handleEmergency = () => {
    toast({
      variant: 'destructive',
      title: 'Emergency Alert',
      description: 'Emergency services have been notified.',
    });
  };

  const activeVisitors = visitors.filter(v => v.status === 'active');
  const recentVisitors = visitors.filter(v => v.status !== 'active').slice(0, 5);

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

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
                <p className="text-xs text-muted-foreground">Kandell Residence</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={loadVisitors} disabled={isLoading}>
                <RefreshCw className={`w-4 h-4 mr-1 ${isLoading ? 'animate-spin' : ''}`} />
                Refresh
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

      {/* Main Content */}
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
                <p className="text-sm text-muted-foreground">Today's Visitors</p>
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

        {/* Emergency Button */}
        <div className="mb-6">
          <Button 
            variant="destructive" 
            className="w-full md:w-auto"
            onClick={handleEmergency}
          >
            <AlertTriangle className="w-4 h-4 mr-2" />
            Emergency Alert
          </Button>
        </div>

        {/* Active Visitors */}
        {activeVisitors.length > 0 && (
          <section className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <h2 className="text-lg font-semibold text-foreground">Active Visitors</h2>
              <Badge className="bg-green-500/10 text-green-500 border-green-500/20">
                {activeVisitors.length} at door
              </Badge>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {activeVisitors.map(visitor => (
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

        {/* Recent Visitors */}
        <section>
          <h2 className="text-lg font-semibold text-foreground mb-4">Recent Visitors</h2>
          {recentVisitors.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {recentVisitors.map(visitor => (
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
              <p className="text-muted-foreground">No visitors yet today</p>
            </div>
          )}
        </section>
      </main>

      {/* View Visitor Dialog */}
      <Dialog open={!!selectedVisitor} onOpenChange={() => setSelectedVisitor(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Visitor Details</DialogTitle>
            <DialogDescription>
              {selectedVisitor?.aiSummary}
            </DialogDescription>
          </DialogHeader>
          
          {selectedVisitor && (
            <div className="space-y-4">
              {/* Visitor Image */}
              {selectedVisitor.imageUrl && (
                <div className="w-full h-48 rounded-lg overflow-hidden bg-muted">
                  <img 
                    src={getAssetUrl(selectedVisitor.imageUrl)} 
                    alt="Visitor" 
                    className="w-full h-full object-cover"
                  />
                </div>
              )}

              {/* Transcript */}
              <ScrollArea className="h-64 rounded-lg border border-border p-4">
                <div className="space-y-3">
                  {selectedVisitor.transcript.map((entry, index) => (
                    <div
                      key={index}
                      className={`p-3 rounded-lg ${
                        entry.role === 'visitor'
                          ? 'bg-primary/10 border border-primary/20'
                          : 'bg-muted'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-muted-foreground">
                          {entry.role === 'visitor' ? 'Visitor' : 'Doorbell'}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {formatTime(entry.timestamp)}
                        </span>
                      </div>
                      <p className="text-sm text-foreground">{entry.content}</p>
                    </div>
                  ))}
                </div>
              </ScrollArea>

              {/* Actions */}
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
            <DialogDescription>
              Send a message to the visitor at your door
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4">
            <div className="flex gap-2">
              <Input
                placeholder="Type your message..."
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && sendReply()}
              />
              <Button onClick={sendReply} disabled={!replyText.trim()}>
                <Send className="w-4 h-4" />
              </Button>
            </div>

            {/* Quick replies */}
            <div className="flex flex-wrap gap-2">
              {[
                "I'll be right there!",
                "Please wait a moment",
                "Leave it at the door",
                "I'm not available",
              ].map((text) => (
                <Button
                  key={text}
                  variant="outline"
                  size="sm"
                  onClick={() => setReplyText(text)}
                >
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
