import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { RefreshCw, Search, Mail, TrendingUp, Users, Award, Download, Eye, Loader2, FileDown } from 'lucide-react';
import { api, Candidate, Stats } from '@/lib/api';
import { toast } from 'sonner';

export default function Index() {
  const navigate = useNavigate();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [processing, setProcessing] = useState(false);
  const [emailChecking, setEmailChecking] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    loadData();
    
    // Set up continuous auto-refresh every 50 seconds
    const autoRefreshInterval = setInterval(() => {
      if (!emailChecking && !processing) {
        console.log('Auto-refreshing data...');
        loadData({ showSpinner: false }); // Silent refresh without toast
      }
    }, 50000); // Every 50 seconds
    
    return () => clearInterval(autoRefreshInterval);
  }, [emailChecking, processing]);

  const loadData = async ({ showSpinner = true, notify = false } = {}) => {
    try {
      if (showSpinner) {
        setLoading(true);
      }

      const [candidatesData, statsData] = await Promise.all([
        fetch(`${import.meta.env.VITE_API_URL || '/api'}/candidates?_t=${Date.now()}`)
          .then(res => res.json())
          .then(data => (data.success ? data.data : [])),
        fetch(`${import.meta.env.VITE_API_URL || '/api'}/stats?_t=${Date.now()}`)
          .then(res => res.json())
          .then(data => (data.success ? data.data : null))
      ]);

      setCandidates(candidatesData);
      setStats(statsData);
      setLastUpdated(new Date());

      if (notify) {
        toast.success(`Refreshed: ${candidatesData.length} candidates found`);
      }
    } catch (error) {
      console.error('Failed to load data:', error);
      if (notify) {
        toast.error('Failed to refresh data');
      }
    } finally {
      if (showSpinner) {
        setLoading(false);
      }
    }
  };

  const handleProcessEmails = async () => {
    try {
      setProcessing(true);
      setEmailChecking(true);
      
      toast.info('Starting email processing...', { id: 'email-status' });
      
      // Trigger email processing
      await api.triggerEmailProcessing();
      
      toast.success('Email processing started! Checking for new candidates...', { id: 'email-status' });
      setProcessing(false);
      
      // Start polling for updates every 3 seconds for up to 1 minute
      let pollCount = 0;
      const maxPolls = 20; // 20 polls × 3 seconds = 60 seconds
      
      const pollForUpdates = setInterval(async () => {
        pollCount++;
        
        try {
          console.log(`Polling for updates... attempt ${pollCount}/${maxPolls}`);
          await loadData({ showSpinner: false }); // Silent refresh with cache busting
          
          if (pollCount >= maxPolls) {
            clearInterval(pollForUpdates);
            setEmailChecking(false);
            toast.success('Email processing completed. Check manually for any new updates.', { id: 'email-status' });
          }
        } catch (error) {
          console.error('Error during polling:', error);
          clearInterval(pollForUpdates);
          setEmailChecking(false);
          toast.error('Error checking for updates', { id: 'email-status' });
        }
      }, 3000); // Poll every 3 seconds
      
    } catch (error) {
      console.error('Email processing error:', error);
      toast.error('Failed to process emails');
      setProcessing(false);
      setEmailChecking(false);
    }
  };

  const handleDownloadResume = async (candidateId: string, candidateName: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent row click navigation
    try {
      await api.downloadResume(candidateId);
      toast.success(`Resume for ${candidateName} opened`);
    } catch (error) {
      toast.error('Failed to download resume');
      console.error(error);
    }
  };

  const handleExportCandidates = async () => {
    try {
      setExporting(true);
      const blob = await api.exportCandidates();
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `candidates-export-${timestamp}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Candidate data export ready');
    } catch (error) {
      console.error('Failed to export candidates:', error);
      toast.error(error instanceof Error ? error.message : 'Failed to export candidates');
    } finally {
      setExporting(false);
    }
  };

  const [sendingInvite, setSendingInvite] = useState<Record<string, boolean>>({});
  const [inviteDialogOpen, setInviteDialogOpen] = useState(false);
  const [inviteCandidateId, setInviteCandidateId] = useState<string | null>(null);
  const [inviteStartLocal, setInviteStartLocal] = useState<string | null>(null);
  const [inviteEndLocal, setInviteEndLocal] = useState<string | null>(null);

  const openInviteModal = (candidateId: string) => {
    const now = new Date();
    const start = new Date(now.getTime() + 24 * 60 * 60 * 1000);
    const end = new Date(start.getTime() + 30 * 60 * 1000);
    const toLocalInput = (d: Date) => d.toISOString().slice(0,16);
    setInviteCandidateId(candidateId);
    setInviteStartLocal(toLocalInput(start));
    setInviteEndLocal(toLocalInput(end));
    setInviteDialogOpen(true);
  };

  const confirmSendInvite = async () => {
    if (!inviteCandidateId) return;
    try {
      setSendingInvite((s) => ({ ...s, [inviteCandidateId]: true }));
      toast.info('Sending invite...', { id: `invite-${inviteCandidateId}` });
      const toISOZ = (local?: string|null) => local ? new Date(local).toISOString() : null;
      await api.sendInvite(inviteCandidateId, { start_iso: toISOZ(inviteStartLocal), end_iso: toISOZ(inviteEndLocal) });
      toast.success('Invite sent', { id: `invite-${inviteCandidateId}` });
      setInviteDialogOpen(false);
      setInviteCandidateId(null);
      await loadData({ showSpinner: false });
    } catch (error) {
      console.error('Failed to send invite', error);
      toast.error(error instanceof Error ? error.message : 'Failed to send invite');
    } finally {
      if (inviteCandidateId) setSendingInvite((s) => ({ ...s, [inviteCandidateId]: false }));
    }
  };

  const [doneReviewingLoading, setDoneReviewingLoading] = useState(false);
  const handleDoneReviewing = async () => {
    try {
      setDoneReviewingLoading(true);
      toast.info('Sending feedback to remaining candidates...', { id: 'done-reviewing' });
      await api.doneReviewing();
      toast.success('Feedback sent to remaining candidates', { id: 'done-reviewing' });
      // Refresh list
      await loadData({ showSpinner: false });
    } catch (error) {
      console.error('Done reviewing failed', error);
      toast.error(error instanceof Error ? error.message : 'Failed to send feedback', { id: 'done-reviewing' });
    } finally {
      setDoneReviewingLoading(false);
    }
  };

  const filteredCandidates = candidates.filter(
    (c) =>
      c.sender_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.source_email?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getFitScoreColor = (score: number) => {
    // Updated thresholds: 90+ green, 70+ yellow, below -> orange
    if (score >= 90) return 'bg-green-500';
    if (score >= 70) return 'bg-yellow-500';
    return 'bg-orange-500';
  };

  const getInlineAnalysis = (c: Candidate) => {
    // Prefer structured analysis_json, then top-level summary, then recruiter_comments
    const analysis = (c as any).analysis_json || null;
    let summary = c.summary || (analysis && analysis.summary) || '';

    // Try to parse recruiter_comments if present and analysis not available
    if (!summary && c.recruiter_comments) {
      try {
        const rc = typeof c.recruiter_comments === 'string' ? JSON.parse(c.recruiter_comments) : c.recruiter_comments;
        if (rc && rc.summary) summary = rc.summary;
      } catch (_) {
        // ignore
      }
    }

    let strengths: string[] = [];
    if (analysis && Array.isArray(analysis.specific_strengths)) {
      strengths = analysis.specific_strengths.slice(0, 2);
    } else if (c.recruiter_comments) {
      try {
        const rc = typeof c.recruiter_comments === 'string' ? JSON.parse(c.recruiter_comments) : c.recruiter_comments;
        if (rc && Array.isArray(rc.specific_strengths)) strengths = rc.specific_strengths.slice(0, 2);
      } catch (_) {}
    }

    return { summary: summary ? String(summary).trim() : '', strengths };
  };

  const getStatusBadge = (status: string) => {
    const variants: Record<string, 'default' | 'secondary' | 'outline'> = {
      pending: 'outline',
      processing: 'secondary',
      screened: 'default',
    };
    return <Badge variant={variants[status] || 'default'}>{status}</Badge>;
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-blue-50">
        <div className="text-center">
          <RefreshCw className="w-12 h-12 animate-spin text-blue-600 mx-auto mb-4" />
          <p className="text-lg text-muted-foreground">Loading candidates...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      <div className="container mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
              AI Resume Screening
            </h1>
            <p className="text-muted-foreground mt-2">Automated candidate intake and evaluation system</p>
          </div>
          <div className="flex items-center gap-2">
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" className="gap-2">
                  <FileDown className="w-4 h-4" />
                  Export Data
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Export candidate data?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Exporting will create a JSON export of all candidates and audit logs. Proceed?
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleExportCandidates}>Export</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
            
            <Button onClick={handleProcessEmails} disabled={processing || emailChecking} className="gap-2">
              {processing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Processing...
                </>
              ) : emailChecking ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Checking for updates...
                </>
              ) : (
                <>
                  <Mail className="w-4 h-4" />
                  Check Emails
                </>
              )}
            </Button>
            {/* Done Reviewing button with confirm modal */}
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" className="ml-2" disabled={doneReviewingLoading}>
                  Done Reviewing
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Send feedback to remaining candidates?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will send personalized feedback emails to all candidates who remain in pending or pending_review status.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleDoneReviewing}>Send Feedback</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>

        {/* Status Bar */}
        <div className="bg-white/60 backdrop-blur rounded-lg p-3 border border-slate-200/50">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${loading ? 'bg-blue-500 animate-pulse' : 'bg-green-500'}`}></div>
                <span>{loading ? 'Refreshing data...' : 'Data up to date'}</span>
              </div>
              {emailChecking && (
                <div className="flex items-center gap-2 text-blue-600">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  <span>Auto-checking for new candidates</span>
                </div>
              )}
            </div>
            <div className="text-slate-500">
              Auto-refresh: Every 50s | Last updated: {lastUpdated.toLocaleTimeString()}
            </div>
          </div>
        </div>

        {/* Stats Cards */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <Card className="border-none shadow-lg bg-white/80 backdrop-blur">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">Total Candidates</CardTitle>
                <Users className="w-4 h-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{stats.total_candidates}</div>
              </CardContent>
            </Card>

            <Card className="border-none shadow-lg bg-white/80 backdrop-blur">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">Screened</CardTitle>
                <TrendingUp className="w-4 h-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{stats.screened_candidates}</div>
              </CardContent>
            </Card>

            <Card className="border-none shadow-lg bg-white/80 backdrop-blur">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">Avg Fit Score</CardTitle>
                <Award className="w-4 h-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{stats.average_fit_score}</div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Candidates Table */}
        <Card className="border-none shadow-lg bg-white/80 backdrop-blur">
          <CardHeader>
            <div className="flex justify-between items-center">
              <div>
                <CardTitle>Candidates</CardTitle>
                <CardDescription>All received applications and their screening results</CardDescription>
              </div>
              <div className="flex gap-2">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    placeholder="Search candidates..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-9 w-64"
                  />
                </div>
                <Button
                  variant="outline"
                  onClick={() => loadData({ notify: true })}
                  size="icon"
                  disabled={loading}
                >
                  <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                </Button>
              </div>
            </div>
          </CardHeader>
          
          {emailChecking && (
            <div className="px-6 py-3 border-b bg-blue-50/50 flex items-center gap-2 text-sm text-blue-600">
              <Loader2 className="w-4 h-4 animate-spin" />
              Auto-refreshing data for new candidates...
            </div>
          )}
          
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Fit Score</TableHead>
                  <TableHead>Date Received</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredCandidates.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                      No candidates found. Send resumes to the configured Gmail address.
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredCandidates.map((candidate) => (
                    <TableRow
                      key={candidate.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => navigate(`/candidate/${candidate.id}`)}
                    >
                      <TableCell className="font-medium">
                        <div className="font-medium">{candidate.sender_name || 'Unknown'}</div>
                        {/* Inline AI summary / top strengths */}
                        {(() => {
                          const inline = getInlineAnalysis(candidate);
                          return (
                            <div className="mt-1">
                              {inline.summary ? (
                                <div className="text-sm text-muted-foreground truncate max-w-md">{inline.summary}</div>
                              ) : null}
                              {inline.strengths && inline.strengths.length > 0 ? (
                                <div className="flex flex-wrap gap-2 mt-2">
                                  {inline.strengths.map((s, i) => (
                                    <span key={i} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-full">{s}</span>
                                  ))}
                                </div>
                              ) : null}
                            </div>
                          );
                        })()}
                      </TableCell>
                      <TableCell>{candidate.source_email}</TableCell>
                      <TableCell>{getStatusBadge(candidate.status)}</TableCell>
                      <TableCell>
                        {candidate.fit_score ? (
                          <div className="flex items-center gap-2">
                            <div className={`w-2 h-2 rounded-full ${getFitScoreColor(candidate.fit_score)}`} />
                            <span className="font-semibold">{candidate.fit_score}</span>
                          </div>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell>{new Date(candidate.created_at).toLocaleDateString()}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => navigate(`/candidate/${candidate.id}`)}
                          >
                            <Eye className="w-4 h-4 mr-1" />
                            View
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => { e.stopPropagation(); openInviteModal(candidate.id); }}
                            disabled={!!sendingInvite[candidate.id]}
                          >
                            <Mail className="w-4 h-4 mr-1" />
                            {sendingInvite[candidate.id] ? 'Sending...' : 'Invite'}
                          </Button>
                          {candidate.resume_url && (
                            <Button 
                              variant="outline" 
                              size="sm"
                              onClick={(e) => handleDownloadResume(candidate.id, candidate.sender_name || 'Unknown', e)}
                            >
                              <Download className="w-4 h-4 mr-1" />
                              Resume
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      {inviteDialogOpen && (
        <div className="fixed inset-0 flex items-center justify-center z-50">
          <div className="bg-white rounded shadow-lg p-6 w-96">
            <h3 className="text-lg font-semibold mb-2">Schedule Interview</h3>
            <label className="text-sm">Start</label>
            <input type="datetime-local" value={inviteStartLocal || ''} onChange={(e) => setInviteStartLocal(e.target.value)} className="border rounded p-2 w-full mb-2" />
            <label className="text-sm">End</label>
            <input type="datetime-local" value={inviteEndLocal || ''} onChange={(e) => setInviteEndLocal(e.target.value)} className="border rounded p-2 w-full mb-4" />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => { setInviteDialogOpen(false); setInviteCandidateId(null); }}>Cancel</Button>
              <Button onClick={confirmSendInvite}>Send Invite</Button>
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}