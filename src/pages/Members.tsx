import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { getMembers, addMember, updateMember, deleteMember, type Member } from '@/lib/api';
import { useAuthContext } from '@/contexts/AuthContext';
import { useToast } from '@/hooks/use-toast';
import {
  ArrowLeft,
  Plus,
  Trash2,
  Edit,
  Camera,
  User,
  Phone,
  Shield,
  ShieldOff,
  UserPlus,
  Users,
  X,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';

const ROLES = ['family', 'friend', 'helper', 'tenant', 'other'] as const;

const roleColors: Record<string, string> = {
  family: 'bg-green-500/10 text-green-500 border-green-500/20',
  friend: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  helper: 'bg-purple-500/10 text-purple-500 border-purple-500/20',
  tenant: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
  other: 'bg-muted text-muted-foreground border-muted-foreground/20',
};

export default function Members() {
  const [members, setMembers] = useState<Member[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingMember, setEditingMember] = useState<Member | null>(null);

  // Form state
  const [formName, setFormName] = useState('');
  const [formPhone, setFormPhone] = useState('');
  const [formRole, setFormRole] = useState('family');
  const [formPhotoBase64, setFormPhotoBase64] = useState('');
  const [formPhotoPreview, setFormPhotoPreview] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { user } = useAuthContext();
  const { toast } = useToast();

  const loadMembers = async () => {
    setIsLoading(true);
    try {
      const data = await getMembers();
      setMembers(data);
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to load members.' });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadMembers();
  }, []);

  const resetForm = () => {
    setFormName('');
    setFormPhone('');
    setFormRole('family');
    setFormPhotoBase64('');
    setFormPhotoPreview('');
    setEditingMember(null);
  };

  const handleOpenAdd = () => {
    resetForm();
    setShowAddModal(true);
  };

  const handleOpenEdit = (member: Member) => {
    setEditingMember(member);
    setFormName(member.name);
    setFormPhone(member.phone);
    setFormRole(member.role);
    setFormPhotoBase64('');
    setFormPhotoPreview(member.photo_path ? `/static/members/${member.photo_path.split('/').pop()}` : '');
    setShowAddModal(true);
  };

  const handlePhotoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      toast({ variant: 'destructive', title: 'Too large', description: 'Photo must be under 5MB.' });
      return;
    }
    const reader = new FileReader();
    reader.onloadend = () => {
      const dataUrl = reader.result as string;
      setFormPhotoPreview(dataUrl);
      setFormPhotoBase64(dataUrl.split(',')[1] || '');
    };
    reader.readAsDataURL(file);
  };

  const handleSave = async () => {
    if (!formName.trim()) {
      toast({ variant: 'destructive', title: 'Name required', description: 'Please enter a name.' });
      return;
    }

    try {
      if (editingMember) {
        await updateMember(editingMember.id, {
          name: formName,
          phone: formPhone,
          role: formRole,
          ...(formPhotoBase64 ? { photo_base64: formPhotoBase64 } : {}),
        });
        toast({ title: 'Updated', description: `${formName} has been updated.` });
      } else {
        await addMember(formName, formPhone, formRole, formPhotoBase64 || undefined);
        toast({ title: 'Added', description: `${formName} has been added.` });
      }
      setShowAddModal(false);
      resetForm();
      loadMembers();
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to save member.' });
    }
  };

  const handleDelete = async (member: Member) => {
    try {
      await deleteMember(member.id);
      toast({ title: 'Removed', description: `${member.name} has been removed.` });
      loadMembers();
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to remove member.' });
    }
  };

  const handleTogglePermission = async (member: Member) => {
    const newPermitted = !member.permitted;
    try {
      await updateMember(member.id, { permitted: newPermitted });
      toast({
        title: newPermitted ? 'Permitted' : 'Restricted',
        description: `${member.name} is now ${newPermitted ? 'permitted' : 'restricted'}.`,
      });
      loadMembers();
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to update permission.' });
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-background/95 backdrop-blur border-b border-border">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Button variant="ghost" size="icon" asChild>
                <Link to="/dashboard">
                  <ArrowLeft className="w-5 h-5" />
                </Link>
              </Button>
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
                <Users className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h1 className="font-semibold text-foreground">House Members</h1>
                <p className="text-xs text-muted-foreground">{members.length} members registered</p>
              </div>
            </div>

            <Button onClick={handleOpenAdd} size="sm">
              <UserPlus className="w-4 h-4 mr-1" />
              Add Member
            </Button>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="container mx-auto px-4 py-6">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-8 h-8 border-4 border-primary/30 border-t-primary rounded-full animate-spin" />
          </div>
        ) : members.length === 0 ? (
          <div className="text-center py-16 bg-muted/30 rounded-xl border border-border">
            <Users className="w-16 h-16 mx-auto text-muted-foreground/50 mb-4" />
            <h2 className="text-lg font-semibold text-foreground mb-2">No Members Yet</h2>
            <p className="text-muted-foreground mb-6">
              Add family members, friends, and helpers to manage access to your home.
            </p>
            <Button onClick={handleOpenAdd}>
              <UserPlus className="w-4 h-4 mr-2" />
              Add First Member
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {members.map((member) => (
              <div
                key={member.id}
                className="bg-card rounded-xl border border-border p-4 hover:border-primary/30 transition-colors"
              >
                <div className="flex items-start gap-4">
                  {/* Avatar */}
                  <div className="w-14 h-14 rounded-full bg-muted flex items-center justify-center overflow-hidden flex-shrink-0">
                    {member.photo_path ? (
                      <img
                        src={`/static/members/${member.photo_path.split('/').pop()}`}
                        alt={member.name}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <User className="w-7 h-7 text-muted-foreground" />
                    )}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-semibold text-foreground truncate">{member.name}</h3>
                      <Badge variant="outline" className={`text-xs ${roleColors[member.role] || roleColors.other}`}>
                        {member.role}
                      </Badge>
                    </div>

                    {member.phone && (
                      <p className="text-sm text-muted-foreground flex items-center gap-1 mb-1">
                        <Phone className="w-3 h-3" />
                        {member.phone}
                      </p>
                    )}

                    <Badge
                      variant="outline"
                      className={`text-xs ${
                        member.permitted
                          ? 'bg-green-500/10 text-green-500 border-green-500/20'
                          : 'bg-red-500/10 text-red-500 border-red-500/20'
                      }`}
                    >
                      {member.permitted ? 'Permitted' : 'Restricted'}
                    </Badge>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex gap-2 mt-4 pt-3 border-t border-border">
                  <Button variant="outline" size="sm" className="flex-1" onClick={() => handleOpenEdit(member)}>
                    <Edit className="w-3 h-3 mr-1" />
                    Edit
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleTogglePermission(member)}
                  >
                    {member.permitted ? (
                      <ShieldOff className="w-3 h-3" />
                    ) : (
                      <Shield className="w-3 h-3" />
                    )}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-red-500 hover:text-red-600 hover:bg-red-500/10"
                    onClick={() => handleDelete(member)}
                  >
                    <Trash2 className="w-3 h-3" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Add/Edit Member Modal */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editingMember ? 'Edit Member' : 'Add House Member'}</DialogTitle>
            <DialogDescription>
              {editingMember
                ? `Update ${editingMember.name}'s information`
                : 'Register a new household member with their details and optional face photo'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* Photo */}
            <div className="flex flex-col items-center gap-3">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="w-24 h-24 rounded-full bg-muted border-2 border-dashed border-border hover:border-primary/50 transition-colors flex items-center justify-center overflow-hidden"
              >
                {formPhotoPreview ? (
                  <img src={formPhotoPreview} alt="Preview" className="w-full h-full object-cover" />
                ) : (
                  <Camera className="w-8 h-8 text-muted-foreground" />
                )}
              </button>
              <span className="text-xs text-muted-foreground">Click to upload face photo</span>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handlePhotoSelect}
              />
            </div>

            {/* Name */}
            <div className="space-y-2">
              <Label htmlFor="member-name">Name *</Label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="member-name"
                  placeholder="Full name"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="pl-10"
                  required
                />
              </div>
            </div>

            {/* Phone */}
            <div className="space-y-2">
              <Label htmlFor="member-phone">Phone</Label>
              <div className="relative">
                <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="member-phone"
                  placeholder="Phone number"
                  value={formPhone}
                  onChange={(e) => setFormPhone(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>

            {/* Role */}
            <div className="space-y-2">
              <Label>Role</Label>
              <Select value={formRole} onValueChange={setFormRole}>
                <SelectTrigger>
                  <SelectValue placeholder="Select role" />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map((role) => (
                    <SelectItem key={role} value={role}>
                      {role.charAt(0).toUpperCase() + role.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Actions */}
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowAddModal(false)}>
                Cancel
              </Button>
              <Button className="flex-1" onClick={handleSave}>
                {editingMember ? 'Save Changes' : 'Add Member'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
