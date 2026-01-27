import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Bell, Shield, Mic, Clock, ChevronRight, Home } from 'lucide-react';

export default function Index() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-primary/5">
      {/* Hero Section */}
      <div className="container mx-auto px-4 py-12 md:py-24">
        <div className="flex flex-col items-center text-center max-w-3xl mx-auto">
          {/* Logo */}
          <div className="w-20 h-20 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-8 animate-ring-pulse">
            <Bell className="w-10 h-10 text-primary" />
          </div>

          <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-foreground mb-6 leading-tight">
            Smart Doorbell
            <span className="block text-primary">AI-Powered</span>
          </h1>

          <p className="text-lg md:text-xl text-muted-foreground mb-10 max-w-2xl">
            Welcome visitors intelligently with AI-powered conversations. 
            Handle deliveries, greet guests, and manage your home's entrance remotely.
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row gap-4 mb-16">
            <Button size="lg" className="text-lg px-8" asChild>
              <Link to="/doorbell">
                <Bell className="w-5 h-5 mr-2" />
                Visitor Entrance
              </Link>
            </Button>
            <Button size="lg" variant="outline" className="text-lg px-8" asChild>
              <Link to="/login">
                <Shield className="w-5 h-5 mr-2" />
                Owner Login
              </Link>
            </Button>
          </div>

          {/* Features */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full">
          <div className="bg-card p-6 rounded-xl border border-border/50">
            <h3 className="font-semibold text-foreground mb-2">Smart Responses</h3>
            <p className="text-muted-foreground text-sm">
              AI-powered responses handle common visitor scenarios automatically.
            </p>
          </div>

            <div className="bg-card rounded-xl border border-border p-6 text-left hover:border-primary/30 transition-colors">
              <div className="w-12 h-12 rounded-lg bg-accent/10 flex items-center justify-center mb-4">
                <Home className="w-6 h-6 text-accent" />
              </div>
              <h3 className="font-semibold text-foreground mb-2">Smart Responses</h3>
              <p className="text-sm text-muted-foreground">
                AI understands visitor intent - deliveries, guests, neighbors, and more.
              </p>
            </div>

            <div className="bg-card rounded-xl border border-border p-6 text-left hover:border-primary/30 transition-colors">
              <div className="w-12 h-12 rounded-lg bg-success/10 flex items-center justify-center mb-4">
                <Clock className="w-6 h-6 text-success" />
              </div>
              <h3 className="font-semibold text-foreground mb-2">Real-time Dashboard</h3>
              <p className="text-sm text-muted-foreground">
                View visitor snapshots, transcripts, and respond from anywhere.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Quick Links */}
      <div className="border-t border-border bg-muted/30">
        <div className="container mx-auto px-4 py-8">
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 text-sm">
            <Link 
              to="/doorbell" 
              className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
            >
              Doorbell Interface
              <ChevronRight className="w-4 h-4" />
            </Link>
            <span className="hidden sm:inline text-border">|</span>
            <Link 
              to="/login" 
              className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
            >
              Owner Dashboard
              <ChevronRight className="w-4 h-4" />
            </Link>
            <span className="hidden sm:inline text-border">|</span>
            <Link 
              to="/history" 
              className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
            >
              Visitor History
              <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-border">
        <div className="container mx-auto px-4 py-6">
          <p className="text-center text-sm text-muted-foreground">
            Smart Doorbell System • Kandell Residence • Powered by AI
          </p>
        </div>
      </footer>
    </div>
  );
}
