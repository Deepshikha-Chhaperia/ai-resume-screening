from flask import Flask, jsonify, request, send_file, Response
from flask_cors import CORS
from config import Config
from database import Database
from gmail_service import GmailService
from resume_processor import ResumeProcessor
from ai_screening import ai_agent
from storage import save_resume_file
import logging
import threading
import time
import io
import os
import json
import psycopg2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Initialize services
db = Database()
gmail_service = GmailService()
resume_processor = ResumeProcessor()

# Track processed messages to avoid duplicates
processed_messages = set()

# Email processing thread
def process_emails_loop():
    """Background thread to continuously process new emails"""
    logger.info("Email processing loop started")
    while True:
        try:
            process_new_emails()
            time.sleep(Config.POLL_INTERVAL)
        except Exception as e:
            logger.error(f"Error in email processing loop: {e}")
            time.sleep(60)

def process_new_emails():
    """Process all unread emails with resume attachments"""
    logger.info("Checking for new emails...")
    messages = gmail_service.get_unread_messages(query='has:attachment is:unread')
    
    for message in messages:
        try:
            process_single_email(message['id'])
        except Exception as e:
            logger.exception(f"Error processing message {message['id']}: {e}")

def process_single_email(message_id):
    """Process a single email message"""
    # Skip if already processed (check in-memory first, then database)
    if message_id in processed_messages:
        logger.info(f"Message {message_id} already processed in memory. Skipping.")
        return
    
    # Check if message was already processed in database (check both audit logs AND existing candidates)
    existing_processing = db.execute_query(
        "SELECT id FROM audit_logs WHERE action = 'email_processed' AND details->>'message_id' = %s",
        (message_id,),
        fetch=True
    )
    
    if existing_processing:
        logger.info(f"Message {message_id} already processed in database. Skipping.")
        processed_messages.add(message_id)  # Add to memory for faster future checks
        return
    
    # Get message details first to check if we already have candidates from this email
    message_details = gmail_service.get_message_details(message_id)
    if not message_details:
        return
    
    # Extract sender info
    sender_full = message_details['sender']
    sender_email = sender_full.split('<')[-1].strip('>') if '<' in sender_full else sender_full
    
    logger.info(f"Processing message {message_id}")
    processed_messages.add(message_id)
    
    # Log that we're starting to process this email
    db.log_audit(None, 'email_processing_started', {
        'message_id': message_id,
        'timestamp': time.time()
    })
    
    # Extract sender name (we already have the details and sender_email)
    sender_name = sender_full.split('<')[0].strip() if '<' in sender_full else sender_email.split('@')[0]
    
    # Process all attachments for this email
    email_processed_successfully = False
    candidate_name = sender_name
    applied_position = None  # Will be determined dynamically
    
    seen_attachments = set()
    for attachment in message_details['attachments']:
        attachment_key = attachment.get('attachment_id') or attachment.get('filename')
        if attachment_key in seen_attachments:
            logger.info(f"Attachment {attachment.get('filename')} already processed in this email. Skipping duplicate.")
            continue
        seen_attachments.add(attachment_key)
        try:
            result = process_resume_attachment(
                attachment,
                sender_email,
                sender_name,
                message_details['subject'],
                message_details['body']
            )
            if result and result.get('success'):
                email_processed_successfully = True
                # Get the candidate name and position from the processed result
                candidate_name = result.get('candidate_name', sender_name)
                applied_position = result.get('applied_position', applied_position)
        except Exception as e:
            logger.exception(f"Error processing attachment: {e}")
    
    # Send acknowledgment email ONCE per email (not per attachment)
    if email_processed_successfully:
        gmail_service.send_acknowledgement(candidate_name, sender_email, applied_position)
        logger.info(f"Acknowledgment email sent to {sender_email} for {applied_position}")
        
        # Mark as read ONLY if processing was successful
        gmail_service.mark_as_read(message_id)
        logger.info(f"Email {message_id} marked as read after successful processing")
    else:
        logger.warning(f"Email {message_id} NOT marked as read due to processing failure - will be retried")
    
    # Log completion
    db.log_audit(None, 'email_processed', {
        'message_id': message_id,
        'sender_email': sender_email,
        'processed_successfully': email_processed_successfully,
        'timestamp': time.time()
    })

def get_position_patterns_from_db():
    """Get position detection patterns from database job descriptions"""
    try:
        positions = db.execute_query(
            "SELECT title FROM job_descriptions WHERE is_active = true ORDER BY title",
            fetch=True
        )

        if not positions:
            # Fallback basic patterns
            return {
                'AI Engineer': ['ai engineer', 'ai engineering', 'artificial intelligence'],
                'Backend Engineer': ['backend engineer', 'backend developer', 'backend dev'],
                'Frontend Engineer': ['frontend engineer', 'frontend developer', 'frontend dev'],
                'Full Stack Engineer': ['full stack', 'fullstack', 'full-stack'],
                'Data Scientist': ['data scientist', 'data science', 'machine learning']
            }

        position_patterns = {}
        for pos in positions:
            title = pos.get('title') if isinstance(pos, dict) else pos
            if not title:
                continue
            patterns = generate_position_patterns(title)
            position_patterns[title] = patterns

        return position_patterns
    except Exception as e:
        logger.error(f"Error getting position patterns from DB: {e}")
        # Fallback to basic patterns if DB unavailable
        return {
            'AI Engineer': ['ai engineer', 'ai engineering', 'artificial intelligence'],
            'Backend Engineer': ['backend engineer', 'backend developer', 'backend dev'],
            'Frontend Engineer': ['frontend engineer', 'frontend developer', 'frontend dev'],
            'Full Stack Engineer': ['full stack', 'fullstack', 'full-stack'],
            'Data Scientist': ['data scientist', 'data science', 'machine learning']
        }


@app.route('/api/candidates/<candidate_id>/invite', methods=['POST'])
def api_send_invite(candidate_id):
    """Send interview invite to a candidate and update status"""
    try:
        candidate = db.get_candidate_by_id(candidate_id)
        if not candidate:
            return jsonify({'error': 'candidate not found'}), 404

        # Extract email and name
        email = candidate.get('source_email')
        name = (candidate.get('sender_name') or '').strip() or candidate.get('parsed_json', {}).get('full_name', 'Applicant')
        # Prefer structured AI analysis if present (analysis_json), fallback to recruiter_comments
        strengths = []
        concerns = []
        fit_score = None
        summary = None
        try:
            analysis = candidate.get('analysis_json') or candidate.get('parsed_json') or candidate.get('recruiter_comments')
            if analysis:
                parsed = json.loads(analysis) if isinstance(analysis, str) else analysis
                strengths = parsed.get('specific_strengths') or parsed.get('matching_skills') or []
                concerns = parsed.get('specific_concerns') or []
                fit_score = parsed.get('fit_score')
                summary = parsed.get('summary')
        except Exception:
            strengths = []
            concerns = []
            fit_score = None
            summary = None

        position = candidate.get('job_description') or 'the role'
        calendar_link = None
        start_iso = None
        end_iso = None
        if request.is_json:
            payload = request.get_json() or {}
            calendar_link = payload.get('calendar_link')
            start_iso = payload.get('start_iso')
            end_iso = payload.get('end_iso')

        sent = gmail_service.send_interview_invite(name, email, position, strengths, calendar_link, fit_score=fit_score, concerns=concerns, summary=summary, start_iso=start_iso, end_iso=end_iso)
        if sent:
            db.update_candidate_status(candidate_id, 'interview_invited')
            db.log_audit(candidate_id, 'invite_sent', {'sent_to': email})
            try:
                db.increment_metric('invites_sent', 1)
            except Exception:
                pass
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'failed to send email'}), 500
    except Exception as e:
        logger.error(f"Error sending invite: {e}")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/candidates/<candidate_id>/status', methods=['POST'])
def api_update_status(candidate_id):
    """Update candidate status (pending_review -> interview_invited -> feedback_sent)"""
    try:
        payload = request.get_json() or {}
        status = payload.get('status')
        if not status:
            return jsonify({'error': 'status required'}), 400
        db.update_candidate_status(candidate_id, status)
        db.log_audit(candidate_id, 'status_update', {'status': status})
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating status: {e}")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/review/done', methods=['POST'])
def api_done_reviewing():
    """Send feedback emails to remaining candidates. Requires JSON {"confirm": true} to run."""
    try:
        payload = request.get_json() or {}
        if not payload.get('confirm'):
            return jsonify({'error': 'confirmation required'}), 400
        candidates = db.get_all_candidates()
        # Consider 'screened' candidates as eligible for feedback as well
        eligible_statuses = (None, 'pending', 'pending_review', 'screened')
        remaining = [c for c in candidates if c.get('status') in eligible_statuses]
        logger.info(f"api_done_reviewing: found {len(candidates)} total candidates, {len(remaining)} remaining to send feedback (eligible_statuses={eligible_statuses})")
        sent_count = 0
        failures = []
        for cand in remaining:
            cid = cand.get('id')
            email = cand.get('source_email')
            name = (cand.get('sender_name') or '').strip() or (cand.get('parsed_json') or {}).get('full_name', 'Applicant')
            logger.info(f"api_done_reviewing: attempting feedback for candidate id={cid} email={email}")
            # Extract analysis (prefer structured analysis_json)
            strengths = []
            concerns = []
            try:
                analysis = cand.get('analysis_json') or cand.get('parsed_json') or cand.get('recruiter_comments')
                if analysis:
                    parsed_rc = json.loads(analysis) if isinstance(analysis, str) else analysis
                    strengths = parsed_rc.get('specific_strengths') or parsed_rc.get('matching_skills') or []
                    concerns = parsed_rc.get('specific_concerns') or []
            except Exception:
                strengths = cand.get('matching_skills') or []
                concerns = cand.get('concerns') or []

            fit_score = cand.get('fit_score') or 0
            resources = []
            try:
                analysis_json = cand.get('analysis_json')
                if analysis_json:
                    parsed_analysis = json.loads(analysis_json) if isinstance(analysis_json, str) else analysis_json
                    resources = parsed_analysis.get('resources') or []
            except Exception:
                resources = []
            if not resources and fit_score < 60:
                # Fallback to predefined resources if AI didn't provide any
                resources = [
                    ("AWS Fundamentals", "https://www.aws.training/"),
                    ("System Design Basics", "https://www.educative.io/courses/grokking-the-system-design-interview")
                ]

            try:
                sent_ok = gmail_service.send_personalized_feedback(name, email, cand.get('job_description') or 'the role', fit_score, strengths, concerns, resources)
                logger.info(f"api_done_reviewing: send_personalized_feedback returned {sent_ok} for {email}")
                if not sent_ok:
                    logger.warning(f"Failed to send feedback to {email}")
                    failures.append({'id': cid, 'email': email, 'reason': 'mail_send_failed'})
                    continue

                db.update_candidate_status(cid, 'feedback_sent')
                db.log_audit(cid, 'feedback_sent', {'sent_to': email})
                try:
                    db.increment_metric('feedback_sent', 1)
                except Exception:
                    pass
                sent_count += 1
                logger.info(f"api_done_reviewing: feedback sent and status updated for candidate id={cid}")
            except Exception as e:
                logger.exception(f"Exception while sending feedback to {email}: {e}")
                failures.append({'id': cid, 'email': email, 'reason': str(e)})

        return jsonify({'success': True, 'sent': sent_count, 'failures': failures})
    except Exception as e:
        logger.error(f"Error in done reviewing: {e}")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/metrics', methods=['GET'])
def api_get_metrics():
    try:
        metrics = db.get_metrics()
        return jsonify({'metrics': metrics})
    except Exception as e:
        logger.error(f"Error fetching metrics: {e}")
        return jsonify({'error': 'failed to fetch metrics'}), 500

def generate_position_patterns(title):
    """Generate search patterns for a position title"""
    title_lower = title.lower()
    patterns = [title_lower]
    
    # Add common variations
    if 'engineer' in title_lower:
        patterns.append(title_lower.replace('engineer', 'developer'))
        patterns.append(title_lower.replace('engineer', 'dev'))
    
    if 'ai' in title_lower:
        patterns.extend(['artificial intelligence', 'ai specialist', 'ai developer', 'ai'])  # Added standalone 'ai'
    
    if 'backend' in title_lower:
        patterns.extend(['server side', 'api developer', 'backend dev'])
    
    if 'frontend' in title_lower:
        patterns.extend(['ui developer', 'react developer', 'frontend dev'])
    
    if 'full stack' in title_lower:
        patterns.extend(['fullstack', 'full-stack', 'full stack developer'])
    
    if 'data scientist' in title_lower:
        patterns.extend(['data science', 'machine learning', 'ml engineer', 'data analyst'])
    
    # Add senior variations if not already present
    if 'senior' not in title_lower:
        patterns.append(f"senior {title_lower}")
    
    return patterns

def extract_job_position_from_email(subject, body):
    """Extract job position from email subject or body"""
    text_to_search = f"{subject} {body}".lower()
    
    # Get position patterns dynamically from database
    position_patterns = get_position_patterns_from_db()
    
    # Check each position pattern
    for position, patterns in position_patterns.items():
        for pattern in patterns:
            if pattern in text_to_search:
                return position
    
    # If no specific position found, try to infer from available job descriptions
    # This will query the database for the best match
    available_positions = get_available_job_positions()
    for position in available_positions:
        # Simple keyword matching with position title
        position_words = position.lower().split()
        if any(word in text_to_search for word in position_words if len(word) > 2):
            return position
    
    # Default fallback - return None to indicate no specific position detected
    return None

def get_available_job_positions():
    """Get list of available job positions from database"""
    try:
        positions = db.execute_query(
            "SELECT title FROM job_descriptions WHERE is_active = true ORDER BY title",
            fetch=True
        )
        return [pos['title'] for pos in positions] if positions else []
    except:
        return []

def get_job_description_for_position(position_title):
    """Get job description that best matches the position title"""
    # Handle None or empty position title
    if not position_title:
        return db.get_active_job_description()
    
    # First try exact match
    exact_match = db.execute_query(
        "SELECT * FROM job_descriptions WHERE LOWER(title) = LOWER(%s) AND is_active = true LIMIT 1",
        (position_title,),
        fetch=True
    )
    
    if exact_match:
        return exact_match[0]
    
    # If no exact match, look for partial match (safely handle position_title)
    first_word = position_title.split()[0] if position_title and ' ' in position_title else position_title
    partial_match = db.execute_query(
        "SELECT * FROM job_descriptions WHERE LOWER(title) LIKE LOWER(%s) AND is_active = true LIMIT 1",
        (f"%{first_word}%",),  # Match first word (e.g., "Backend" from "Backend Engineer")
        fetch=True
    )
    
    if partial_match:
        return partial_match[0]
    
    # Fallback to default active job description
    return db.get_active_job_description()

def process_resume_attachment(attachment, sender_email, sender_name, subject, body):
    """Process a resume attachment through the full pipeline"""
    filename = attachment['filename']
    file_data = attachment['data']
    
    logger.info(f"Processing resume: {filename}")
    
    # Extract the job position they're applying for
    applied_position = extract_job_position_from_email(subject, body)
    logger.info(f"Detected application for position: {applied_position}")
    
    # Get the specific job description for this position
    job_desc = get_job_description_for_position(applied_position)
    if not job_desc:
        logger.warning(f"No job description found for position: {applied_position}")
        return {
            'success': False,
            'reason': 'no_job_description',
            'candidate_name': sender_name
        }
    
    # Check if we already processed this email/resume combination (simpler check)
    existing_candidate = db.execute_query(
        """SELECT c.id FROM candidates c 
           WHERE c.source_email = %s 
           AND c.parsed_json->>'resume_filename' = %s""",
        (sender_email, filename),
        fetch=True
    )
    
    if existing_candidate:
        logger.info(f"Resume {filename} from {sender_email} already processed. Skipping.")
        return {
            'success': False,
            'reason': 'duplicate_application',
            'candidate_name': sender_name
        }
    
    # Step 1: Extract text
    extracted_text = resume_processor.extract_text(file_data, filename)
    if not extracted_text:
        logger.warning(f"No text extracted from {filename}")
        return {
            'success': False,
            'reason': 'text_extraction_failed',
            'candidate_name': sender_name
        }
    
    # Step 2: Parse with AI
    logger.info("Parsing resume with AI...")
    parsed_data = ai_agent.parse_resume(extracted_text)
    
    # Add filename and position to parsed data for tracking
    if parsed_data:
        parsed_data['resume_filename'] = filename
        parsed_data['applied_position'] = applied_position
    
    # Step 3: Validate data
    validation_flags = resume_processor.validate_candidate_data(
        parsed_data, sender_email, sender_name
    )
    
    # Step 4: Store candidate in database
    # Save resume file (GCS if configured, otherwise local file)
    resume_url = save_resume_file(file_data, filename)

    candidate_data = {
        'source_email': sender_email,
        'sender_name': sender_name,
        'email_subject': subject,
        'raw_email_body': body,
        'resume_url': resume_url,
        'extracted_text': extracted_text,
        'parsed_json': parsed_data,
        'validation_flags': validation_flags,
        'status': 'processing'
    }
    
    candidate_id = db.insert_candidate(candidate_data)
    logger.info(f"Candidate stored with ID: {candidate_id}")
    try:
        db.increment_metric('candidates_total', 1)
    except Exception:
        pass
    
    # Log audit
    db.log_audit(candidate_id, 'email_received', {
        'sender': sender_email,
        'filename': filename
    })
    
    # Step 5: Screen candidate for the specific position
    logger.info(f"Screening candidate with AI for position: {applied_position}")
    screening_result = ai_agent.screen_candidate(
        parsed_data,
        job_desc['description']
    )
    
    # Generate recruiter comments
    recruiter_comments = ai_agent.generate_recruiter_comments(
        parsed_data,
        screening_result
    )
    
    # Store screening results
    screening_data = {
        'candidate_id': candidate_id,
        'job_description': job_desc['description'],
        'fit_score': screening_result.get('fit_score', 0),
        'summary': screening_result.get('summary', ''),
        'matching_skills': screening_result.get('matching_skills', []) or screening_result.get('matching_skills', []),
        'concerns': screening_result.get('concerns', []) or screening_result.get('specific_concerns', []),
        'recruiter_comments': recruiter_comments,
        # store full AI analysis JSON as analysis_json for richer retrieval (stored in recruiter_comments if DB schema unchanged)
        'analysis_json': screening_result
    }
    
    db.insert_screening_result(screening_data)
    logger.info(f"Screening completed for {applied_position}. Fit score: {screening_result.get('fit_score')}")
    
    # Log audit
    db.log_audit(candidate_id, 'screening_completed', {
        'fit_score': screening_result.get('fit_score'),
        'position': applied_position,
        'job_id': job_desc['id']
    })
    
    # Update candidate status
    db.update_candidate_status(candidate_id, 'screened')
    
    # Return candidate info for acknowledgment email
    candidate_name = parsed_data.get('full_name', sender_name)
    logger.info(f"Processing completed for {filename}")
    
    return {
        'success': True,
        'candidate_id': candidate_id,
        'candidate_name': candidate_name,
        'applied_position': applied_position
    }

# API Routes
@app.route('/api/candidates', methods=['GET'])
def get_candidates():
    """Get all candidates with screening results"""
    try:
        logger.info("Fetching candidates from database...")
        start_time = time.time()
        
        candidates = db.get_all_candidates()
        
        elapsed_time = time.time() - start_time
        logger.info(f"Fetched {len(candidates)} candidates in {elapsed_time:.2f} seconds")
        
        return jsonify({
            'success': True,
            'data': candidates,
            'count': len(candidates),
            'query_time': round(elapsed_time, 2)
        })
    except psycopg2.OperationalError as e:
        logger.error(f"Database connection error: {e}")
        return jsonify({
            'success': False,
            'error': 'Database connection failed'
        }), 503
    except Exception as e:
        logger.error(f"Error fetching candidates: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/candidates/export', methods=['GET'])
def export_candidates():
    """Download full candidate dataset for compliance exports"""
    try:
        export_payload = db.get_candidates_for_export()
        timestamp = time.strftime('%Y%m%d-%H%M%S')
        response = Response(
            json.dumps(export_payload, default=str),
            mimetype='application/json'
        )
        response.headers['Content-Disposition'] = (
            f'attachment; filename=candidates-export-{timestamp}.json'
        )
        return response
    except Exception as e:
        logger.error(f"Error exporting candidates: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to export candidate data'
        }), 500

@app.route('/api/candidates/<candidate_id>', methods=['GET'])
def get_candidate(candidate_id):
    """Get detailed candidate information"""
    try:
        candidate = db.get_candidate_by_id(candidate_id)
        if not candidate:
            return jsonify({
                'success': False,
                'error': 'Candidate not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': candidate
        })
    except Exception as e:
        logger.error(f"Error fetching candidate: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/candidates/<candidate_id>', methods=['DELETE'])
def delete_candidate(candidate_id):
    """Delete candidate data (GDPR compliance)"""
    try:
        db.execute_query(
            "DELETE FROM candidates WHERE id = %s",
            (candidate_id,),
            fetch=False
        )
        return jsonify({
            'success': True,
            'message': 'Candidate deleted successfully'
        })
    except Exception as e:
        logger.error(f"Error deleting candidate: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get dashboard statistics"""
    try:
        logger.info("Fetching statistics from database...")
        start_time = time.time()
        
        total = db.execute_query("SELECT COUNT(*) as count FROM candidates")[0]['count']
        screened = db.execute_query(
            "SELECT COUNT(*) as count FROM candidates WHERE status = 'screened'"
        )[0]['count']
        avg_score = db.execute_query(
            "SELECT AVG(fit_score) as avg FROM screening_results"
        )[0]['avg'] or 0
        
        elapsed_time = time.time() - start_time
        logger.info(f"Fetched statistics in {elapsed_time:.2f} seconds")
        
        return jsonify({
            'success': True,
            'data': {
                'total_candidates': total,
                'screened_candidates': screened,
                'average_fit_score': round(float(avg_score), 1)
            },
            'query_time': round(elapsed_time, 2)
        })
    except psycopg2.OperationalError as e:
        logger.error(f"Database connection error: {e}")
        return jsonify({
            'success': False,
            'error': 'Database connection failed'
        }), 503
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/process-test-email', methods=['POST'])
def process_test_email():
    """Manually trigger email processing for testing"""
    try:
        logger.info("Manual email processing triggered via API")
        
        # Check if Gmail service is available
        if not gmail_service.service:
            logger.error("Gmail service is not available - authentication failed")
            return jsonify({
                'success': False,
                'error': 'Gmail service not authenticated'
            }), 500
        
        # Use the original process_new_emails function which has proper duplicate checking
        process_new_emails()
        
        return jsonify({
            'success': True,
            'message': 'Email processing triggered successfully'
        })
    except Exception as e:
        logger.error(f"Error processing emails: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/candidates/<candidate_id>/resume', methods=['GET'])
def download_resume(candidate_id):
    """Download or redirect to candidate's resume"""
    try:
        candidate = db.get_candidate_by_id(candidate_id)
        if not candidate:
            return jsonify({
                'success': False,
                'error': 'Candidate not found'
            }), 404
        
        resume_url = candidate.get('resume_url')
        if not resume_url:
            return jsonify({
                'success': False,
                'error': 'No resume found for this candidate'
            }), 404
        
        # If it's a public GCS URL, redirect to it
        if resume_url.startswith('https://storage.googleapis.com/'):
            return jsonify({
                'success': True,
                'download_url': resume_url,
                'redirect': True
            })
        
        # If it's a GCS path, stream it through our backend
        elif resume_url.startswith('gs://'):
            try:
                from storage import stream_gcs_file
                return stream_gcs_file(resume_url, candidate.get('sender_name', 'candidate'))
            except Exception as e:
                logger.error(f"Failed to stream GCS file: {e}")
                return jsonify({
                    'success': False,
                    'error': 'Failed to download resume from cloud storage'
                }), 500
        # If it's a local file, stream it
        elif resume_url.startswith('file://'):
            import os
            file_path = resume_url.replace('file://', '')
            if os.path.exists(file_path):
                return send_file(file_path, as_attachment=True)
            else:
                return jsonify({
                    'success': False,
                    'error': 'Resume file not found'
                }), 404
        
        # Fallback
        return jsonify({
            'success': False,
            'error': 'Invalid resume URL format'
        }), 400
        
    except Exception as e:
        logger.error(f"Error downloading resume: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/clear-processed-cache', methods=['POST'])
def clear_processed_cache():
    """Clear the in-memory processed messages cache for testing"""
    global processed_messages
    processed_messages.clear()
    logger.info("Cleared in-memory processed messages cache")
    return jsonify({
        'success': True,
        'message': f'Cleared processed messages cache'
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    gmail_status = "connected" if gmail_service.service else "disconnected"
    return jsonify({
        'status': 'healthy',
        'service': 'Resume Screening API',
        'gmail_service': gmail_status,
        'email_processing_enabled': ENABLE_EMAIL_PROCESSING
    })

import os

# Add environment variable to control email processing
ENABLE_EMAIL_PROCESSING = os.getenv('ENABLE_EMAIL_PROCESSING', 'true').lower() == 'true'

# Frontend serving routes
@app.route('/')
def serve_frontend():
    """Serve the frontend index.html"""
    return send_file('static/index.html')

@app.route('/<path:path>')
def serve_static(path):
    """Serve static frontend files"""
    try:
        return send_file(f'static/{path}')
    except:
        # If file not found, serve index.html for client-side routing
        return send_file('static/index.html')

if __name__ == '__main__':
    # Determine email processing configuration
    enable_email_env = os.environ.get('ENABLE_EMAIL_PROCESSING', 'true').lower()
    ENABLE_EMAIL_PROCESSING = enable_email_env in ['true', '1', 'yes']
    
    if ENABLE_EMAIL_PROCESSING:
        should_start_thread = True
        # When running with Flask's reloader, only start the thread in the reloaded process
        if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
            should_start_thread = False

        if should_start_thread and not globals().get('_email_thread_started'):
            logger.info("Email processing ENABLED - starting background thread")
            email_thread = threading.Thread(target=process_emails_loop, daemon=True)
            email_thread.start()
            globals()['_email_thread_started'] = True
            logger.info("Email processing background thread started")
    else:
        logger.info("Email processing DISABLED - set ENABLE_EMAIL_PROCESSING=true to enable")
    
    # Run Flask app on the port Cloud Run (or local dev) expects
    port = int(os.environ.get('PORT', '5000'))
    app.run(host='0.0.0.0', port=port, debug=Config.DEBUG)
