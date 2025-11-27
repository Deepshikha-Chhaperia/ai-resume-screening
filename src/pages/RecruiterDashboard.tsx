import React, { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';

type Candidate = {
  id: string;
  sender_name?: string;
  source_email?: string;
  status?: string;
  fit_score?: number;
  created_at?: string;
  recruiter_comments?: any;
  analysis_json?: any;
};

export default function RecruiterDashboard() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [metrics, setMetrics] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [remainingCount, setRemainingCount] = useState(0);
  const [inviteDialogOpen, setInviteDialogOpen] = useState(false);
  const [inviteCandidateId, setInviteCandidateId] = useState<string | null>(null);
  const [inviteStartLocal, setInviteStartLocal] = useState<string | null>(null);
  const [inviteEndLocal, setInviteEndLocal] = useState<string | null>(null);
  const [failures, setFailures] = useState<Array<any>>([]);
  const [failuresDialogOpen, setFailuresDialogOpen] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const res = await fetch('/api/candidates');
      const data = await res.json();
      // Support multiple response shapes: { candidates: [...] } or { success: true, data: [...] }
      const candList = data.candidates || data.data || (data.success && data.data) || [];
      // Candidates are now sorted by fit_score DESC from the API
      setCandidates(candList || []);

      const m = await fetch('/api/metrics');
      const md = await m.json();
      setMetrics(md.metrics || {});
    } catch (err) {
      console.error(err);
      toast.error('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  }

  function openInviteModal(id: string) {
    // default to 24h from now
    const now = new Date();
    const start = new Date(now.getTime() + 24 * 60 * 60 * 1000);
    const end = new Date(start.getTime() + 30 * 60 * 1000);
    // format for input type datetime-local: YYYY-MM-DDTHH:MM
    const toLocalInput = (d: Date) => d.toISOString().slice(0,16);
    setInviteCandidateId(id);
    setInviteStartLocal(toLocalInput(start));
    setInviteEndLocal(toLocalInput(end));
    setInviteDialogOpen(true);
  }

  async function confirmSendInvite() {
    if (!inviteCandidateId) return;
    try {
      // convert local datetime-local to ISO Z
      const toISOZ = (local?: string|null) => {
        if (!local) return null;
        // local is like 2025-11-26T15:00
        const d = new Date(local);
        return d.toISOString();
      };
      const body: any = {};
      if (inviteStartLocal) body.start_iso = toISOZ(inviteStartLocal);
      if (inviteEndLocal) body.end_iso = toISOZ(inviteEndLocal);

      const resp = await fetch(`/api/candidates/${inviteCandidateId}/invite`, {
        method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)
      });
      if (resp.ok) {
        toast.success('Invite sent');
        setInviteDialogOpen(false);
        setInviteCandidateId(null);
        loadData();
      } else {
        const j = await resp.json().catch(()=>null);
        console.error('Invite failed', j);
        toast.error('Failed to send invite');
      }
    } catch (err) {
      console.error(err);
      toast.error('Failed to send invite');
    }
  }

  async function doneReviewing() {
    const count = candidates.filter(c => !c.status || c.status === 'pending' || c.status === 'pending_review').length;
    setRemainingCount(count);
    setDialogOpen(true);
  }

  async function confirmDoneReviewing() {
    try {
      const resp = await fetch('/api/review/done', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({confirm:true}) });
      if (resp.ok) {
        const j = await resp.json();
        if (j.failures && j.failures.length) {
          toast.success(`Sent feedback to ${j.sent} candidates — ${j.failures.length} failed`);
          setFailures(j.failures || []);
          setFailuresDialogOpen(true);
        } else {
          toast.success(`Sent feedback to ${j.sent} candidates`);
        }
        setDialogOpen(false);
        loadData();
      } else {
        toast.error('Failed to send feedback');
      }
    } catch (err) {
      console.error(err);
      toast.error('Failed to send feedback');
    }
  }

  const getBadgeVariant = (score?: number) => {
    // Standardized thresholds: 90+ green, 70-89 yellow, below 70 orange
    if (score === undefined || score === null) return 'default';
    if (score >= 90) return 'green';
    if (score >= 70) return 'yellow';
    return 'orange';
  };

  if (loading) return <div>Loading dashboard...</div>;

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-semibold">Recruiter Dashboard</h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={loadData}>Refresh</Button>
          <Button variant="secondary" onClick={doneReviewing}>Done Reviewing</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <Card>
          <CardHeader>
            <CardTitle>Total candidates</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.candidates_total || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Invites sent</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.invites_sent || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Feedback sent</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.feedback_sent || 0}</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {candidates.map(c => (
          <Card key={c.id} className="p-4">
            <div className="flex justify-between items-start">
              <div>
                <div className="font-semibold">{c.sender_name || 'Unknown'}</div>
                <div className="text-sm text-muted-foreground">{c.source_email}</div>
              </div>
              <div className="text-right">
                <Badge variant={getBadgeVariant(c.fit_score)} className="capitalize">{c.fit_score ?? '-'}</Badge>
              </div>
            </div>

            <Separator className="my-3" />

            <div>
              <div><strong>Recommendation:</strong> {c.analysis_json?.recommendation || 'N/A'}</div>
              <div className="mt-2"><strong>Strengths:</strong>
                <ul className="list-disc list-inside">
                  {(c.analysis_json?.specific_strengths || []).map((s:any, i:number)=>(<li key={i}>{s}</li>))}
                </ul>
              </div>
              <div className="mt-2"><strong>Concerns:</strong>
                <ul className="list-disc list-inside">
                  {(c.analysis_json?.specific_concerns || []).map((s:any, i:number)=>(<li key={i}>{s}</li>))}
                </ul>
              </div>
            </div>

            <div className="mt-4 flex gap-2">
              <Button onClick={()=>openInviteModal(c.id)}>Send Interview Invite</Button>
            </div>
          </Card>
        ))}
      </div>
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Send feedback to remaining candidates?</DialogTitle>
            <DialogDescription>
              This will send personalized feedback emails to the {remainingCount} remaining candidates.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4">
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
              <Button onClick={confirmDoneReviewing}>Send Feedback</Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Invite modal */}
      <Dialog open={inviteDialogOpen} onOpenChange={setInviteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Schedule Interview</DialogTitle>
            <DialogDescription>Select a time to schedule the interview (local time).</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <label className="text-sm">Start</label>
            <input type="datetime-local" value={inviteStartLocal || ''} onChange={(e)=>setInviteStartLocal(e.target.value)} className="border rounded p-2" />
            <label className="text-sm">End</label>
            <input type="datetime-local" value={inviteEndLocal || ''} onChange={(e)=>setInviteEndLocal(e.target.value)} className="border rounded p-2" />
          </div>
          <DialogFooter className="mt-4">
            <div className="flex gap-2">
              <Button variant="outline" onClick={()=>{ setInviteDialogOpen(false); setInviteCandidateId(null); }}>Cancel</Button>
              <Button onClick={confirmSendInvite}>Send Invite</Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Failures dialog */}
      <Dialog open={failuresDialogOpen} onOpenChange={setFailuresDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Feedback failures</DialogTitle>
            <DialogDescription>Some feedback emails failed to send. You can retry sending invites/feedback to these addresses.</DialogDescription>
          </DialogHeader>
          <div className="mt-4">
            {failures.length === 0 && <div>No failures.</div>}
            {failures.map((f:any,i:number)=> (
              <div key={i} className="flex items-center justify-between border-b py-2">
                <div>
                  <div className="font-medium">{f.email}</div>
                  <div className="text-sm text-muted-foreground">{f.reason}</div>
                </div>
                <div>
                  <Button onClick={()=>{ setFailuresDialogOpen(false); openInviteModal(f.id); }}>Retry Invite</Button>
                </div>
              </div>
            ))}
          </div>
          <DialogFooter className="mt-4">
            <Button onClick={()=>{ setFailuresDialogOpen(false); setFailures([]); }}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
