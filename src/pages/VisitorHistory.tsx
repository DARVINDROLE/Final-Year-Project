import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { VisitorCard } from '@/components/VisitorCard';
import { getVisitorLogs, type Visitor, getAssetUrl } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';
import {
  Bell,
  ArrowLeft,
  Search,
  Calendar,
  Filter,
  Package,
  Users,
  Home,
  AlertCircle,
  HelpCircle,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

type VisitorType = 'all' | 'delivery' | 'friend' | 'solicitor' | 'neighbor' | 'unknown';

export default function VisitorHistory() {
  const [visitors, setVisitors] = useState<Visitor[]>([]);
  const [filteredVisitors, setFilteredVisitors] = useState<Visitor[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<VisitorType>('all');
  const [selectedVisitor, setSelectedVisitor] = useState<Visitor | null>(null);

  const { toast } = useToast();

  useEffect(() => {
    loadVisitors();
  }, []);

  useEffect(() => {
    let filtered = visitors;

    // Filter by type
    if (typeFilter !== 'all') {
      filtered = filtered.filter(v => v.visitorType === typeFilter);
    }

    // Filter by search
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(v => 
        v.aiSummary.toLowerCase().includes(query) ||
        v.transcript.some(t => t.content.toLowerCase().includes(query))
      );
    }

    setFilteredVisitors(filtered);
  }, [visitors, typeFilter, searchQuery]);

  const loadVisitors = async () => {
    setIsLoading(true);
    try {
      const logs = await getVisitorLogs();
      setVisitors(logs);
      setFilteredVisitors(logs);
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to load visitor history.',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleViewVisitor = (visitor: Visitor) => {
    setSelectedVisitor(visitor);
  };

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  const formatDate = (timestamp: string) => {
    return new Date(timestamp).toLocaleDateString([], {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
    });
  };

  // Group visitors by date
  const groupedVisitors = filteredVisitors.reduce((groups, visitor) => {
    const date = formatDate(visitor.timestamp);
    if (!groups[date]) {
      groups[date] = [];
    }
    groups[date].push(visitor);
    return groups;
  }, {} as Record<string, Visitor[]>);

  const typeIcons = {
    all: Filter,
    delivery: Package,
    friend: Users,
    neighbor: Home,
    solicitor: AlertCircle,
    unknown: HelpCircle,
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-background/95 backdrop-blur border-b border-border">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Button variant="ghost" size="sm" asChild>
                <Link to="/dashboard">
                  <ArrowLeft className="w-4 h-4 mr-1" />
                  Back
                </Link>
              </Button>
              <div className="h-6 w-px bg-border" />
              <div className="flex items-center gap-2">
                <Calendar className="w-5 h-5 text-primary" />
                <h1 className="font-semibold text-foreground">Visitor History</h1>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Filters */}
      <div className="container mx-auto px-4 py-4 border-b border-border bg-muted/30">
        <div className="flex flex-col sm:flex-row gap-4">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search visitors..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>

          {/* Type Filter */}
          <Select value={typeFilter} onValueChange={(v) => setTypeFilter(v as VisitorType)}>
            <SelectTrigger className="w-full sm:w-48">
              <SelectValue placeholder="Filter by type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">
                <span className="flex items-center gap-2">
                  <Filter className="w-4 h-4" />
                  All Types
                </span>
              </SelectItem>
              <SelectItem value="delivery">
                <span className="flex items-center gap-2">
                  <Package className="w-4 h-4" />
                  Delivery
                </span>
              </SelectItem>
              <SelectItem value="friend">
                <span className="flex items-center gap-2">
                  <Users className="w-4 h-4" />
                  Friend/Family
                </span>
              </SelectItem>
              <SelectItem value="neighbor">
                <span className="flex items-center gap-2">
                  <Home className="w-4 h-4" />
                  Neighbor
                </span>
              </SelectItem>
              <SelectItem value="solicitor">
                <span className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  Solicitor
                </span>
              </SelectItem>
              <SelectItem value="unknown">
                <span className="flex items-center gap-2">
                  <HelpCircle className="w-4 h-4" />
                  Unknown
                </span>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Result count */}
        <p className="text-sm text-muted-foreground mt-3">
          {filteredVisitors.length} visitor{filteredVisitors.length !== 1 ? 's' : ''} found
        </p>
      </div>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
          </div>
        ) : Object.keys(groupedVisitors).length > 0 ? (
          <div className="space-y-8">
            {Object.entries(groupedVisitors).map(([date, dateVisitors]) => (
              <section key={date}>
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                    <Calendar className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <h2 className="font-semibold text-foreground">{date}</h2>
                    <p className="text-sm text-muted-foreground">
                      {dateVisitors.length} visitor{dateVisitors.length !== 1 ? 's' : ''}
                    </p>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {dateVisitors.map(visitor => (
                    <VisitorCard
                      key={visitor.id}
                      visitor={visitor}
                      onView={handleViewVisitor}
                      onRespond={() => {}}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <Calendar className="w-12 h-12 mx-auto text-muted-foreground/50 mb-3" />
            <p className="text-muted-foreground">No visitors found</p>
            {searchQuery && (
              <Button
                variant="link"
                onClick={() => setSearchQuery('')}
                className="mt-2"
              >
                Clear search
              </Button>
            )}
          </div>
        )}
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

              {/* Timestamp */}
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Calendar className="w-4 h-4" />
                {formatDate(selectedVisitor.timestamp)} at {formatTime(selectedVisitor.timestamp)}
              </div>

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
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
