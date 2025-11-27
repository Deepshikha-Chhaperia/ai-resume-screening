import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ArrowLeft, Mail, Phone, Linkedin, Github, Globe, AlertCircle, CheckCircle2, Trash2, Download } from 'lucide-react';
import { api, Candidate } from '@/lib/api';
import { toast } from 'sonner';
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

export default function CandidateDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (id) loadCandidate(id);
  }, [id]);

  const loadCandidate = async (candidateId: string) => {
    try {
      setLoading(true);
      const data = await api.getCandidate(candidateId);
      setCandidate(data);
    } catch (error) {
      toast.error('Failed to load candidate');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!id) return;
    try {
      await api.deleteCandidate(id);
      toast.success('Candidate deleted');
      navigate('/');
    } catch (error) {
      toast.error('Failed to delete candidate');
    }
  };

  const handleDownloadResume = async () => {
    if (!id) return;
    try {
      await api.downloadResume(id);
      toast.success(`Resume for ${parsedData.full_name || candidate?.sender_name} opened`);
    } catch (error) {
      toast.error('Failed to download resume');
      console.error(error);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-blue-50">
        <p className="text-lg text-muted-foreground">Loading candidate details...</p>
      </div>
    );
  }

  if (!candidate) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-blue-50">
        <div className="text-center">
          <p className="text-lg text-muted-foreground mb-4">Candidate not found</p>
          <Button onClick={() => navigate('/')}>Back to Dashboard</Button>
        </div>
      </div>
    );
  }

  const parsedData = candidate.parsed_json || {};
  const getFitScoreColor = (score: number) => {
    if (score >= 80) return 'text-green-600 bg-green-50';
    if (score >= 60) return 'text-blue-600 bg-blue-50';
    if (score >= 40) return 'text-yellow-600 bg-yellow-50';
    return 'text-red-600 bg-red-50';
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      <div className="container mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <Button variant="ghost" onClick={() => navigate('/')} className="gap-2">
            <ArrowLeft className="w-4 h-4" />
            Back to Dashboard
          </Button>
          <div className="flex items-center gap-3">
            {candidate.resume_url && (
              <Button variant="outline" onClick={handleDownloadResume} className="gap-2">
                <Download className="w-4 h-4" />
                Download Resume
              </Button>
            )}
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" className="gap-2">
                  <Trash2 className="w-4 h-4" />
                  Delete Candidate
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Are you sure?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will permanently delete this candidate's data. This action cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>

        {/* Candidate Info */}
        <Card className="border-none shadow-lg bg-white/80 backdrop-blur">
          <CardHeader>
            <div className="flex justify-between items-start">
              <div>
                <CardTitle className="text-3xl">{parsedData.full_name || candidate.sender_name}</CardTitle>
                <CardDescription className="text-lg mt-2">{parsedData.summary || 'No summary available'}</CardDescription>
              </div>
              {candidate.fit_score && (
                <div className={`text-center p-4 rounded-lg ${getFitScoreColor(candidate.fit_score)}`}>
                  <div className="text-4xl font-bold">{candidate.fit_score}</div>
                  <div className="text-sm font-medium">Fit Score</div>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-4">
              {parsedData.contact_email && (
                <div className="flex items-center gap-2">
                  <Mail className="w-4 h-4 text-muted-foreground" />
                  <span>{parsedData.contact_email}</span>
                </div>
              )}
              {parsedData.phone && (
                <div className="flex items-center gap-2">
                  <Phone className="w-4 h-4 text-muted-foreground" />
                  <span>{parsedData.phone}</span>
                </div>
              )}
              {parsedData.links?.linkedin && (
                <a href={parsedData.links.linkedin} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-blue-600 hover:underline">
                  <Linkedin className="w-4 h-4" />
                  LinkedIn
                </a>
              )}
              {parsedData.links?.github && (
                <a href={parsedData.links.github} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-blue-600 hover:underline">
                  <Github className="w-4 h-4" />
                  GitHub
                </a>
              )}
              {parsedData.links?.portfolio && (
                <a href={parsedData.links.portfolio} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-blue-600 hover:underline">
                  <Globe className="w-4 h-4" />
                  Portfolio
                </a>
              )}
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Screening Results */}
          {candidate.summary && (
            <Card className="border-none shadow-lg bg-white/80 backdrop-blur">
              <CardHeader>
                <CardTitle>Screening Summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-muted-foreground">{candidate.summary}</p>

                {candidate.matching_skills && candidate.matching_skills.length > 0 && (
                  <div>
                    <h4 className="font-semibold mb-2 flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-green-600" />
                      Matching Skills
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {candidate.matching_skills.map((skill, i) => (
                        <Badge key={i} variant="secondary">
                          {skill}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {candidate.concerns && candidate.concerns.length > 0 && (
                  <div>
                    <h4 className="font-semibold mb-2 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 text-yellow-600" />
                      Concerns
                    </h4>
                    <ul className="list-disc list-inside space-y-1 text-muted-foreground">
                      {candidate.concerns.map((concern, i) => (
                        <li key={i}>{concern}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {candidate.recruiter_comments && (
                  <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
                    <h4 className="font-semibold mb-2 text-blue-900">Recruiter Comments</h4>
                    <p className="text-blue-800">{candidate.recruiter_comments}</p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Skills */}
          {parsedData.skills && parsedData.skills.length > 0 && (
            <Card className="border-none shadow-lg bg-white/80 backdrop-blur">
              <CardHeader>
                <CardTitle>Skills</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {parsedData.skills.map((skill: string, i: number) => (
                    <Badge key={i} variant="outline">
                      {skill}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Work Experience */}
        {parsedData.work_experience && parsedData.work_experience.length > 0 && (
          <Card className="border-none shadow-lg bg-white/80 backdrop-blur">
            <CardHeader>
              <CardTitle>Work Experience</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {parsedData.work_experience.map((exp, i) => (
                <div key={i}>
                  {i > 0 && <Separator className="my-4" />}
                  <div>
                    <h4 className="font-semibold text-lg">{exp.role}</h4>
                    <p className="text-muted-foreground">
                      {exp.company} • {exp.duration}
                    </p>
                    <p className="mt-2">{exp.description}</p>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Education */}
        {parsedData.education && parsedData.education.length > 0 && (
          <Card className="border-none shadow-lg bg-white/80 backdrop-blur">
            <CardHeader>
              <CardTitle>Education</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {parsedData.education.map((edu, i) => (
                <div key={i}>
                  <h4 className="font-semibold">{edu.degree}</h4>
                  <p className="text-muted-foreground">
                    {edu.institution} • {edu.year}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Validation Flags */}
        {candidate.validation_flags && candidate.validation_flags.length > 0 && (
          <Card className="border-none shadow-lg bg-yellow-50 border-yellow-200">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-yellow-900">
                <AlertCircle className="w-5 h-5" />
                Validation Warnings
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {candidate.validation_flags.map((flag, i) => (
                  <li key={i} className="text-yellow-800">
                    <strong>{flag.type}:</strong> {flag.message}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}