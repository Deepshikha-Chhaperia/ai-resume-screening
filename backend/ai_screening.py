import requests
import json
from config import Config
import logging

logger = logging.getLogger(__name__)

class AIScreeningAgent:
    def __init__(self):
        self.api_key = Config.OPENROUTER_API_KEY
        self.base_url = Config.OPENROUTER_BASE_URL
        self.parsing_model = Config.PARSING_MODEL
        self.screening_model = Config.SCREENING_MODEL
    
    def parse_resume(self, resume_text):
        """Parse resume text into structured JSON using AI"""
        prompt = f"""You are an expert resume parser. Extract structured information from the following resume text.

Resume Text:
{resume_text}

Extract and return ONLY a valid JSON object with this exact structure:
{{
  "full_name": "string",
  "contact_email": "string",
  "phone": "string",
  "summary": "brief professional summary",
  "skills": ["skill1", "skill2", "skill3"],
  "work_experience": [
    {{
      "role": "string",
      "company": "string",
      "duration": "string",
      "description": "string"
    }}
  ],
  "education": [
    {{
      "degree": "string",
      "institution": "string",
      "year": "string"
    }}
  ],
  "links": {{
    "linkedin": "url or null",
    "github": "url or null",
    "portfolio": "url or null"
  }}
}}

Return ONLY the JSON object, no other text."""

        try:
            # Use a lower max_tokens to avoid exceeding credit limits on OpenRouter
            response = self._call_api(prompt, self.parsing_model, max_tokens=800)
            parsed_data = json.loads(response)
            return parsed_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.error(f"Response was: {response}")
            return self._create_fallback_parse(resume_text)
        except Exception as e:
            logger.error(f"Error parsing resume: {e}")
            return self._create_fallback_parse(resume_text)
    
    def screen_candidate(self, parsed_data, job_description):
        """Screen candidate against job description and return fit score and analysis"""
        # Build the prompt without using an f-string to avoid interpreting literal braces
        schema = """
{
    "fit_score": 0,                         # integer 0-100
    "summary": "",                        # 3-5 sentence candidate-specific summary
    "matching_skills": [                    # list skills that match the job with brief proficiency/evidence
        ""
    ],
    "specific_strengths": [                  # 3-5 short bullet points each with a short evidence sentence
        ""
    ],
    "specific_concerns": [                   # 2-3 short bullet points describing gaps or risks
        ""
    ],
    "recommendation": "",                  # one of: "strong_yes", "consider", "pass"
    "recommendation_reason": "",            # 1-2 short paragraphs explaining the recommendation
    "resources": [                          # 3-5 AI-suggested resources (courses, books, tutorials) based on candidate's profile and gaps
        ""
    ]
}
"""

        prompt = (
            "You are an experienced technical recruiter. Screen this candidate for the job position.\n\n"
            "Job Description:\n" + (job_description or '') + "\n\n"
            "Candidate Profile:\n" + json.dumps(parsed_data, indent=2) + "\n\n"
            "Analyze the candidate thoroughly against the specific job requirements and return ONLY a valid JSON object with this exact structure:\n"
            + schema
            + "\n\nScoring Guidelines:\n"
            "- 90-100: Exceptional match, exceeds requirements\n"
            "- 75-89: Strong match, meets most requirements\n"
            "- 60-74: Good match, meets core requirements\n"
            "- 40-59: Partial match, missing key skills\n"
            "- 0-39: Poor match, significant gaps\n\n"
            "For the 'resources' field, suggest 3-5 relevant learning resources (courses, books, tutorials, certifications) that would help the candidate improve their skills based on their current profile and any gaps identified in the analysis. Make suggestions specific to their background and the job requirements.\n\n"
            "Important: Base your analysis ONLY on the actual candidate data provided. Do not invent details. Each field must be specific to this candidate and the job description. Return ONLY the JSON object, no other text."
        )

        try:
            # Limit max tokens for screening to reduce cost and avoid 402 from API
            response = self._call_api(prompt, self.screening_model, max_tokens=800)
            screening_data = json.loads(response)
            # Ensure minimal fields exist
            screening_data.setdefault('fit_score', 0)
            screening_data.setdefault('summary', '')
            screening_data.setdefault('matching_skills', [])
            screening_data.setdefault('specific_strengths', [])
            screening_data.setdefault('specific_concerns', [])
            screening_data.setdefault('recommendation', 'consider')
            screening_data.setdefault('recommendation_reason', '')
            return screening_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse screening response as JSON: {e}")
            logger.info("Falling back to heuristic screening")
            return self._heuristic_screen(parsed_data, job_description)
        except Exception as e:
            logger.error(f"Error screening candidate: {e}")
            logger.info("Falling back to heuristic screening due to API failure")
            return self._heuristic_screen(parsed_data, job_description)
    
    def generate_recruiter_comments(self, parsed_data, screening_data):
        """Generate personalized recruiter comments with personality"""
        prompt = f"""You are Sarah, a friendly and insightful technical recruiter at Aurora Labs. Write a brief, personalized comment about this candidate.

Candidate: {parsed_data.get('full_name', 'Unknown')}
Fit Score: {screening_data.get('fit_score', 0)}
Summary: {screening_data.get('summary', '')}

Write 2-3 sentences with personality that:
- Sounds natural and conversational
- Highlights what excites you or concerns you
- Suggests next steps (interview, technical assessment, pass)

Be honest but professional. Show enthusiasm for strong candidates."""

        try:
            response = self._call_api(prompt, self.screening_model, max_tokens=200)
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating recruiter comments: {e}")
            return "Candidate profile reviewed. Will discuss with hiring team."
    
    def _call_api(self, prompt, model, max_tokens=2000):
        """Make API call to OpenRouter"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://auroralabs.example",
            "X-Title": "Resume Screening System"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code != 200:
            # Provide clearer logs for billing/credit errors
            if response.status_code == 402:
                logger.error(f"API call failed with 402 (insufficient credits): {response.text}")
                raise Exception(f"API call failed: 402 - insufficient credits: {response.text}")
            logger.error(f"API call failed: {response.status_code} - {response.text}")
            raise Exception(f"API call failed: {response.status_code}")
        
        result = response.json()
        return result['choices'][0]['message']['content']
    
    def _create_fallback_parse(self, resume_text):
        """Create basic fallback parsing if AI fails"""
        from resume_processor import ResumeProcessor
        processor = ResumeProcessor()

        # Simple deterministic fallback parsing - keep it conservative and safe
        try:
            full_text = resume_text or ''
            lines = [l.strip() for l in full_text.splitlines() if l.strip()]
            full_name = lines[0] if len(lines) > 0 else ''
            summary = ' '.join(lines[1:3]) if len(lines) > 1 else ''
            contact_email = processor.extract_email_from_text(full_text) or ''
            phone = processor.extract_phone_from_text(full_text) or ''

            parsed = {
                'full_name': full_name,
                'contact_email': contact_email,
                'phone': phone,
                'summary': summary,
                'skills': [],
                'work_experience': [],
                'education': [],
                'links': {'linkedin': None, 'github': None, 'portfolio': None}
            }

            return parsed
        except Exception as e:
            logger.error(f"Fallback parse failed: {e}")
            # As a last resort, return minimal empty structure
            return {
                'full_name': '',
                'contact_email': '',
                'phone': '',
                'summary': '',
                'skills': [],
                'work_experience': [],
                'education': [],
                'links': {'linkedin': None, 'github': None, 'portfolio': None}
            }

    def _heuristic_screen(self, parsed_data, job_description):
        """Cheap local heuristic screening when AI provider is unavailable.

        Produces the same JSON shape as the AI screening but using simple
        keyword and profile heuristics. This enables processing to continue
        even when the external model is down or out of credits.
        """
        jd = (job_description or '').lower()
        skills = [s.lower() for s in parsed_data.get('skills', []) if isinstance(s, str)]

        # Count matching skills by substring match
        matching = [s for s in skills if s and s in jd]
        matching_skills = matching[:10]

        # Estimate experience from number of work_experience entries
        exp_count = len(parsed_data.get('work_experience', []) or [])

        # Degree bonus
        education = parsed_data.get('education', []) or []
        degree_bonus = 5 if any('master' in (e.get('degree') or '').lower() or 'phd' in (e.get('degree') or '').lower() for e in education) else 0

        # Base score depends on matches found
        base = 40
        score = base + min(40, len(matching_skills) * 10) + min(20, exp_count * 3) + degree_bonus
        score = max(0, min(100, int(score)))

        # Build strengths and concerns lists
        strengths = []
        for s in matching_skills[:5]:
            strengths.append(f"Has relevant skill: {s}")

        if exp_count:
            strengths.append(f"{exp_count} relevant roles listed in work experience")

        concerns = []
        if not matching_skills:
            concerns.append("No clear matching skills found in resume for this job description")
        if exp_count == 0:
            concerns.append("No work experience entries detected; verify resume content")

        # Recommendation mapping
        if score >= 90:
            recommendation = 'strong_yes'
        elif score >= 75:
            recommendation = 'consider'
        elif score >= 60:
            recommendation = 'consider'
        else:
            recommendation = 'pass'

        recommendation_reason = (
            f"Heuristic screening based on {len(matching_skills)} matching skills and {exp_count} experience entries. "
            f"This is an automated fallback result and may be less accurate than AI screening."
        )

        summary = f"Heuristic: {len(matching_skills)} skill matches, {exp_count} roles listed."

        return {
            'fit_score': score,
            'summary': summary,
            'matching_skills': matching_skills,
            'specific_strengths': strengths,
            'specific_concerns': concerns,
            'recommendation': recommendation,
            'recommendation_reason': recommendation_reason
        }

ai_agent = AIScreeningAgent()