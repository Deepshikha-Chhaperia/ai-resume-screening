const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

export interface ParsedJson {
  full_name?: string;
  contact_email?: string;
  phone?: string;
  summary?: string;
  skills?: string[];
  work_experience?: Array<{
    role: string;
    company: string;
    duration: string;
    description: string;
  }>;
  education?: Array<{
    degree: string;
    institution: string;
    year: string;
  }>;
  links?: {
    linkedin?: string;
    github?: string;
    portfolio?: string;
  };
}

export interface ValidationFlag {
  type: string;
  message: string;
}

export interface Candidate {
  id: string;
  source_email: string;
  sender_name: string;
  email_subject: string;
  raw_email_body: string;
  resume_url: string;
  extracted_text: string;
  parsed_json: ParsedJson;
  validation_flags: ValidationFlag[];
  status: string;
  created_at: string;
  updated_at: string;
  fit_score: number;
  summary: string;
  matching_skills: string[];
  concerns: string[];
  recruiter_comments: string;
  job_description: string;
}

export interface Stats {
  total_candidates: number;
  screened_candidates: number;
  average_fit_score: number;
}

export const api = {
  async getCandidates(): Promise<Candidate[]> {
    const response = await fetch(`${API_BASE_URL}/candidates`);
    const data = await response.json();
    if (!data.success) throw new Error(data.error);
    return data.data;
  },

  async getCandidate(id: string): Promise<Candidate> {
    const response = await fetch(`${API_BASE_URL}/candidates/${id}`);
    const data = await response.json();
    if (!data.success) throw new Error(data.error);
    return data.data;
  },

  async deleteCandidate(id: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/candidates/${id}`, {
      method: 'DELETE',
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error);
  },

  async getStats(): Promise<Stats> {
    const response = await fetch(`${API_BASE_URL}/stats`);
    const data = await response.json();
    if (!data.success) throw new Error(data.error);
    return data.data;
  },

  async triggerEmailProcessing() {
    const response = await fetch(`${API_BASE_URL}/process-test-email`, {
      method: 'POST',
    });
    return response.json();
  },

  async sendInvite(candidateId: string, opts?: { calendarLink?: string | null, start_iso?: string | null, end_iso?: string | null }) {
    const body: any = {};
    if (opts?.calendarLink) body.calendar_link = opts.calendarLink;
    if (opts?.start_iso) body.start_iso = opts.start_iso;
    if (opts?.end_iso) body.end_iso = opts.end_iso;

    const response = await fetch(`${API_BASE_URL}/candidates/${candidateId}/invite`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || 'Failed to send invite');
    return data;
  },

  async doneReviewing() {
    const response = await fetch(`${API_BASE_URL}/review/done`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: true }),
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || 'Failed to send feedback');
    return data;
  },

  async exportCandidates() {
    const response = await fetch(`${API_BASE_URL}/candidates/export`);
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error || 'Failed to export candidates');
    }
    return response.blob();
  },

  async downloadResume(candidateId: string) {
    const response = await fetch(`${API_BASE_URL}/candidates/${candidateId}/resume`);
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || 'Failed to download resume');
    }
    
    // Check if it's a JSON response (redirect) or binary data (direct download)
    const contentType = response.headers.get('content-type');
    
    if (contentType && contentType.includes('application/json')) {
      // Handle redirect response
      const result = await response.json();
      if (result.success && result.redirect && result.download_url) {
        window.open(result.download_url, '_blank');
        return result;
      } else {
        throw new Error(result.error || 'Failed to download resume');
      }
    } else {
      // Handle direct file download
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      
      // Try to get filename from Content-Disposition header
      const disposition = response.headers.get('Content-Disposition');
      let filename = `resume_${candidateId}.pdf`;
      if (disposition && disposition.includes('filename=')) {
        const filenameMatch = disposition.match(/filename="(.+)"/);
        if (filenameMatch) {
          filename = filenameMatch[1];
        }
      }
      
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      return { success: true, message: 'File downloaded successfully' };
    }
  },
};