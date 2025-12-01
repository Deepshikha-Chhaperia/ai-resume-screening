import os
import base64
import pickle
import json
import time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from config import Config
import logging
import httplib2
import ssl
import requests

logger = logging.getLogger(__name__)
import os
import datetime
from google.oauth2 import service_account


def _normalize_token_info(token_info):
    """Make small, safe normalizations to token JSON so the google Credentials
    loader accepts common variants. In particular, accept expiry timestamps
    that use a space instead of 'T' between date and time.
    """
    if not isinstance(token_info, dict):
        return token_info

    # Common key used by Credentials JSON is 'expiry' (ISO format). Some stores
    # may write 'YYYY-MM-DD HH:MM:SS' (space) instead of 'YYYY-MM-DDTHH:MM:SS'.
    exp = token_info.get('expiry')
    if isinstance(exp, str) and 'T' not in exp and ' ' in exp:
        token_info['expiry'] = exp.replace(' ', 'T')

    return token_info

class GmailService:
    def __init__(self):
        self.service = None
        self.authenticated_user = None
        self.authenticate()
    
    def authenticate(self):
        try:
            creds = None
            
            # Try to load token from environment variable first (for Cloud Run)
            token_data = os.getenv('GMAIL_TOKEN_JSON')
            if token_data:
                try:
                    token_info = json.loads(token_data)
                    token_info = _normalize_token_info(token_info)
                    creds = Credentials.from_authorized_user_info(token_info)
                    logger.info("Loaded Gmail token from environment variable")
                except Exception as e:
                    logger.warning(f"Failed to load token from environment: {e}")
            
            # Fallback to file-based token (for local development)
            if not creds and os.path.exists(Config.GMAIL_TOKEN_PATH):
                try:
                    # Attempt to load JSON token (common when token was saved as JSON)
                    with open(Config.GMAIL_TOKEN_PATH, 'r', encoding='utf-8') as f:
                        raw = f.read()
                    token_json = json.loads(raw)
                    token_json = _normalize_token_info(token_json)
                    creds = Credentials.from_authorized_user_info(token_json)
                    logger.info("Loaded Gmail token from JSON file")
                except Exception:
                    try:
                        # Fall back to pickle (older flows saved pickled credentials)
                        with open(Config.GMAIL_TOKEN_PATH, 'rb') as token:
                            creds = pickle.load(token)
                        logger.info("Loaded Gmail token from pickle file")
                    except Exception as e:
                        logger.warning(f"Failed to load Gmail token from file: {e}")
            
            if not creds:
                logger.info("No Gmail credentials found. Attempting to authenticate...")
                try:
                    scopes = ['https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/calendar.events']
                    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', scopes)
                    creds = flow.run_local_server(port=0)
                    with open(Config.GMAIL_TOKEN_PATH, 'w') as token_file:
                        token_file.write(creds.to_json())
                    logger.info("New Gmail token obtained with calendar scope")
                except Exception as e:
                    logger.error(f"Failed to obtain new token: {e}. Please ensure credentials.json exists.")
                    self.service = None
                    return
                
            if not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Gmail token expired, attempting to refresh...")
                    creds.refresh(Request())
                    logger.info("Gmail token refreshed successfully")
                else:
                    # In Cloud Run, we can't run local server for OAuth flow
                    # The token should already be provided via environment variables
                    logger.error("Gmail token expired/invalid and cannot refresh in Cloud Run environment")
                    logger.error("Please ensure GMAIL_TOKEN_JSON contains a valid, non-expired token")
                    logger.error("Gmail integration will be disabled.")
                    self.service = None
                    return

                with open(Config.GMAIL_TOKEN_PATH, 'wb') as token:
                    pickle.dump(creds, token)
            
            # Build the Gmail service
            self.service = build('gmail', 'v1', credentials=creds)
            self.creds = creds
            
            # Find out which account the token belongs to and log it
            try:
                profile = self.service.users().getProfile(userId='me').execute()
                self.authenticated_user = profile.get('emailAddress')
                logger.info(f"Gmail service authenticated successfully as {self.authenticated_user}")
            except Exception:
                logger.info("Gmail service authenticated successfully (profile lookup failed)")
        except Exception as e:
            logger.error(f"Failed to authenticate Gmail service: {e}")
            self.service = None
    
    def get_unread_messages(self, query='is:unread'):
        if not self.service:
            logger.warning("Gmail service not available. Skipping email check.")
            return []
        
        try:
            results = self.service.users().messages().list(
                userId='me', q=query, maxResults=10).execute()
            messages = results.get('messages', [])
            return messages
        except Exception as e:
            logger.error(f"Error fetching messages: {e}")
            return []
    
    def get_message_details(self, message_id):
        if not self.service:
            logger.warning("Gmail service not available. Cannot get message details.")
            return None
            
        try:
            message = self.service.users().messages().get(
                userId='me', id=message_id, format='full').execute()
            
            headers = message['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            body = self._get_message_body(message['payload'])
            attachments = self._get_attachments(message_id, message['payload'])
            
            return {
                'id': message_id,
                'subject': subject,
                'sender': sender,
                'date': date,
                'body': body,
                'attachments': attachments
            }
        except Exception as e:
            logger.error(f"Error getting message details: {e}")
            return None
    
    def _get_message_body(self, payload):
        if 'body' in payload and 'data' in payload['body']:
            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        return ''
    
    def _get_attachments(self, message_id, payload):
        if not self.service:
            return []
            
        attachments = []
        if 'parts' in payload:
            for part in payload['parts']:
                if part.get('filename') and part['filename'].lower().endswith(('.pdf', '.docx', '.doc')):
                    attachment_id = part['body'].get('attachmentId')
                    attachment_size = part['body'].get('size', 0)
                    
                    # Check file size in metadata before downloading
                    max_size = 10 * 1024 * 1024  # 10MB
                    if attachment_size > max_size:
                        logger.warning(f"Attachment {part['filename']} ({attachment_size} bytes) exceeds size limit ({max_size} bytes). Skipping download.")
                        continue
                    
                    if attachment_id:
                        try:
                            attachment = self.service.users().messages().attachments().get(
                                userId='me', messageId=message_id, id=attachment_id).execute()
                            file_data = base64.urlsafe_b64decode(attachment['data'])
                            attachments.append({
                                'filename': part['filename'],
                                'data': file_data,
                                'mime_type': part['mimeType'],
                                'attachment_id': attachment_id
                            })
                        except Exception as e:
                            logger.error(f"Error getting attachment: {e}")
        return attachments
    
    def mark_as_read(self, message_id):
        if not self.service:
            logger.warning("Gmail service not available. Cannot mark message as read.")
            return
            
        try:
            self.service.users().messages().modify(
                userId='me', id=message_id,
                body={'removeLabelIds': ['UNREAD']}).execute()
        except Exception as e:
            logger.error(f"Error marking message as read: {e}")
    
    def send_email(self, to, subject, body):
        return self.send_email_with_attachments(to, subject, body, attachments=None, html=False)

    def send_email_with_attachments(self, to, subject, body, attachments=None, html=False):
        """Send email with optional attachments. Attachments is a list of dicts: {filename, mime_type, data(bytes)}

        Builds a multipart/mixed message with a multipart/alternative child so that
        the HTML body and a single text/calendar method=REQUEST part (if present)
        are presented together.
        """
        if not self.service:
            logger.warning("Gmail service not available. Cannot send email.")
            return False

        try:
            # Root multipart
            root = MIMEMultipart('mixed')

            # Alternative part for text/html (or text/plain) and the calendar
            alt = MIMEMultipart('alternative')
            if html:
                alt.attach(MIMEText(body, 'html'))
            else:
                alt.attach(MIMEText(body, 'plain'))

            calendar_text = None
            other_attachments = []

            # Separate calendar attachment from others (only one calendar part supported)
            if attachments:
                for att in attachments:
                    mime = (att.get('mime_type') or '').lower()
                    if mime.startswith('text/calendar') and calendar_text is None:
                        try:
                            calendar_text = att['data'].decode('utf-8') if isinstance(att['data'], (bytes, bytearray)) else str(att['data'])
                        except Exception:
                            calendar_text = str(att['data'])
                    else:
                        other_attachments.append(att)

            # Attach calendar part into the alternative part (inline) so clients can render it
            if calendar_text:
                cal_part = MIMEBase('text', 'calendar')
                cal_part.set_payload(calendar_text)
                cal_part.add_header('Content-Type', 'text/calendar; charset="UTF-8"; method=REQUEST')
                cal_part.add_header('Content-Disposition', 'inline; filename="invite.ics"')
                cal_part.add_header('Content-Class', 'urn:content-classes:calendarmessage')
                alt.attach(cal_part)

            # Attach the alternative block into root
            root.attach(alt)

            # Attach remaining non-calendar files to the root
            for att in other_attachments:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(att['data'])
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{att.get("filename","attachment")}"')
                root.attach(part)

            # Set headers
            root['To'] = to
            try:
                # Ensure From header is set to configured sender
                root['From'] = Config.SENDER_EMAIL
            except Exception:
                pass
            root['Subject'] = subject

            raw = base64.urlsafe_b64encode(root.as_bytes()).decode()

            # Send and fetch metadata to confirm delivery/labeling
            try:
                result = self.service.users().messages().send(userId='me', body={'raw': raw}).execute()
            except Exception as e:
                # Common SSL/transport errors (for example when a corporate proxy or
                # incorrect TLS negotiation causes SSL: WRONG_VERSION_NUMBER). Attempt
                # a resilient fallback using the Gmail REST endpoint with `requests`
                # and the current OAuth2 access token.
                err_msg = str(e)
                logger.error(f"Primary Gmail send failed: {err_msg}")
                try:
                    # Ensure token is valid / refreshed
                    if hasattr(self, 'creds') and self.creds and self.creds.expired and self.creds.refresh_token:
                        logger.info('Refreshing expired Gmail credentials before fallback send')
                        self.creds.refresh(Request())

                    token = getattr(self, 'creds', None) and getattr(self.creds, 'token', None)
                    if token:
                        url = 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
                        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
                        payload = {'raw': raw}
                        # Use requests with a short timeout and strict SSL verification.
                        r = requests.post(url, headers=headers, json=payload, timeout=10, verify=True)
                        if r.status_code in (200, 201):
                            result = r.json()
                            logger.info('Fallback send via HTTP succeeded')
                        else:
                            logger.error(f'Fallback HTTP send failed: {r.status_code} {r.text}')
                            raise
                    else:
                        logger.error('No OAuth token available for fallback HTTP send')
                        raise
                except Exception as e2:
                    logger.error(f'Fallback send also failed: {e2}')
                    raise
            msg_id = result.get('id') if isinstance(result, dict) else None
            if msg_id:
                try:
                    info = self.service.users().messages().get(userId='me', id=msg_id, format='metadata').execute()
                    labels = info.get('labelIds')
                    thread = info.get('threadId')
                    logger.info(f"Email sent to {to} (message id: {msg_id}) labels={labels} thread={thread}")
                except Exception as e:
                    logger.info(f"Email sent to {to} (message id: {msg_id}) - but failed to fetch message details: {e}")
                return True
            else:
                logger.warning(f"Gmail API returned unexpected send response for {to}: {result}")
                return False
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False
    
    def send_acknowledgement(self, candidate_name, candidate_email, position="Backend Engineer"):
        subject = f"Application Received - {position}"
        body_html = f"""<p>Dear {candidate_name},</p>

<p>Thank you for applying to the {position} position at Aurora Labs. We have received your application and resume.</p>

<p>Our team will review your qualifications and reach out if your profile matches our requirements.</p>

<p>We appreciate your interest in joining our team!</p>

<p>Best regards,<br/>
Aurora Labs Recruitment Team</p>"""
        return self.send_email_with_attachments(candidate_email, subject, body_html, attachments=None, html=True)

    def send_interview_invite(self, candidate_name, candidate_email, position, strengths, calendar_link=None, fit_score=None, concerns=None, summary=None, start_iso=None, end_iso=None):
        """Send recruiter-triggered interview invite with AI strengths included"""
        subject = f"Interview Update at Aurora Labs"
        strengths_text = "\n".join([f"- {s}" for s in strengths]) if strengths else ""
        # Do not include a Calendly placeholder. Only include a calendar link if a real event was created.
        schedule_link = None

        # Precompute strengths HTML; the full email body will be built after (so it can include the real event link)
        strengths_html = ''.join([f"<li>{s}</li>" for s in strengths]) if strengths else ''
        concerns_html = ''.join([f"<li>{c}</li>" for c in (concerns or [])]) if concerns else ''
        summary_text = summary or ''

        # Determine short position title for email and calendar
        position_lower = position.lower()
        if "data science" in position_lower or "machine learning" in position_lower:
            short_position = "Data Scientist"
        elif "ai engineer" in position_lower or "artificial intelligence" in position_lower:
            short_position = "AI Engineer"
        elif "security engineer" in position_lower:
            short_position = "Security Engineer"
        else:
            short_position = position.split('.')[0] if '.' in position else position
            # Limit to first 3 words to keep it short
            words = short_position.split()[:3]
            short_position = ' '.join(words)

        # Try to create a real Google Calendar event with attendees
        calendar_created = False
        try:
            creds = self.creds
            if creds:
                calendar_service = build('calendar', 'v3', credentials=creds)

                # Default to 24h from now at nearest hour if no specific time is provided
                if not start_iso or not end_iso:
                    start_dt = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
                    end_dt = start_dt + datetime.timedelta(minutes=30)
                    start_iso = start_dt.isoformat() + 'Z'
                    end_iso = end_dt.isoformat() + 'Z'

                event_summary = f"Interview: {short_position}"
                description = f"Hi {candidate_name},\n\nThank you for your interest. This is your interview slot.\n\nWhat impressed us:\n{strengths_text}\n\n{summary_text}\n\nIf this time does not work, please reply to this email.\n\nBest regards,\nAurora Labs Recruitment Team"

                event = {
                    'summary': event_summary,
                    'description': description,
                    'start': {'dateTime': start_iso, 'timeZone': 'UTC'},
                    'end': {'dateTime': end_iso, 'timeZone': 'UTC'},
                    'attendees': [{'email': candidate_email}],
                    'reminders': {'useDefault': True}
                }

                created = calendar_service.events().insert(calendarId='primary', body=event, sendUpdates='all').execute()
                logger.info(f"Calendar event created: {created.get('id')}")
                calendar_created = True
        except Exception as e:
            logger.warning(f'Google Calendar event creation failed, falling back to .ics: {e}')
            calendar_created = False

        # Always send the full email with calendar invite UI
        # Create a simple iCal event as attachment (fallback or additional)
        dtstamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
        if start_iso and end_iso:
            try:
                dtstart = datetime.datetime.fromisoformat(start_iso.replace('Z','')).strftime('%Y%m%dT%H%M%SZ')
                dtend = datetime.datetime.fromisoformat(end_iso.replace('Z','')).strftime('%Y%m%dT%H%M%SZ')
            except Exception:
                dtstart = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(time.time()+86400))
                dtend = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(time.time()+86400+1800))
        else:
            dtstart = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(time.time()+86400))
            dtend = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(time.time()+86400+1800))
        uid = f"{candidate_email}-{int(time.time())}"

        ical = f"""BEGIN:VCALENDAR
    VERSION:2.0
    PRODID:-//Aurora Labs//EN
    METHOD:REQUEST
    BEGIN:VEVENT
    UID:{uid}
    DTSTAMP:{dtstamp}
    DTSTART:{dtstart}
    DTEND:{dtend}
    SUMMARY:Interview: {short_position}
    DESCRIPTION:Interview scheduled via Aurora Labs\n\nWhat impressed us:\n{strengths_text}\n\n{summary_text}
    ORGANIZER:mailto:{Config.SENDER_EMAIL}
    ATTENDEE;CN={candidate_name};RSVP=TRUE:mailto:{candidate_email}
    STATUS:CONFIRMED
    END:VEVENT
    END:VCALENDAR
    """

        attachments = [{
            'filename': 'invite.ics',
            'mime_type': 'text/calendar',
            'data': ical.encode('utf-8')
        }]

        # Build email body with calendar invite UI
        calendar_status = "The calendar invitation has been sent to your calendar and is attached to this email." if calendar_created else "The calendar invitation is attached to this email."
        body_html = f"""
        <p>Dear {candidate_name},</p>
        <p>We'd love to invite you to a conversation about the <strong>{short_position}</strong> position. Below are a few things that stood out from your application:</p>
        <h4>What impressed us</h4>
        <ul>{strengths_html}</ul>
        <p>{calendar_status} You can accept or propose a new time by replying to this message.</p>
        <p>Warm regards,<br/>Aurora Labs Recruitment Team</p>
        """

        return self.send_email_with_attachments(candidate_email, subject, body_html, attachments=attachments, html=True)

    def send_personalized_feedback(self, candidate_name, candidate_email, position, fit_score, strengths, concerns, resources=None):
        """Send personalized feedback to candidates using AI reasoning"""
        subject = f"Application Update - {position} at Aurora Labs"
        strengths_html = ''.join([f"<li>{s}</li>" for s in strengths]) if strengths else ''
        concerns_html = ''.join([f"<li>{c}</li>" for c in (concerns or [])]) if concerns else ''

        # Normalize resources list to HTML
        resources_html = ''
        if resources:
            items = []
            for r in resources:
                if isinstance(r, (list, tuple)) and len(r) >= 2:
                    items.append(f"<li><a href=\"{r[1]}\">{r[0]}</a></li>")
                else:
                    items.append(f"<li>{r}</li>")
            resources_html = '\n'.join(items)

        # Provide default learning resources if none were provided
        if not resources:
            resources = [
                ("AWS Cloud Practitioner", "https://www.aws.training/Details/Curriculum?id=20685"),
                ("GCP Fundamentals", "https://cloud.google.com/training"),
                ("System Design: Grokking", "https://www.educative.io/courses/grokking-the-system-design-interview"),
                ("Full Stack Open", "https://fullstackopen.com/en/")
            ]
            items = []
            for r in resources:
                items.append(f"<li><a href=\"{r[1]}\">{r[0]}</a></li>")
            resources_html = '\n'.join(items)

        # Compose feedback message
        if fit_score is not None and fit_score >= 60:
            intro = f"Thank you for applying to the {position} position. We appreciated reviewing your application." 
            closing = "We appreciate your interest and encourage you to apply again when you have updates to your profile."
            body_html = f"""
            <p>Dear {candidate_name},</p>
            <p>{intro}</p>
            <p><strong>Fit score:</strong> {fit_score}</p>
            <h4>Strengths we noticed</h4>
            <ul>{strengths_html}</ul>
            {f'<h4>Concerns</h4><ul>{concerns_html}</ul>' if concerns_html else ''}
            <h4>Suggested next steps</h4>
            <p>To improve your chances for similar roles, consider gaining hands-on cloud experience and public projects demonstrating that work.</p>
            <h4>Recommended resources</h4>
            <ul>{resources_html}</ul>
            <p>{closing}</p>
            <p>Best regards,<br/>Aurora Labs Recruitment Team</p>
            """
        else:
            intro = f"Thank you for applying to the {position} position. We value your interest and want to help you improve." 
            closing = "We hope these suggestions help — please reapply after gaining experience in the suggested areas."
            body_html = f"""
            <p>Dear {candidate_name},</p>
            <p>{intro}</p>
            <p><strong>Fit score:</strong> {fit_score if fit_score is not None else 'N/A'}</p>
            <h4>Areas to improve</h4>
            <ul>{concerns_html or '<li>Provide clearer evidence of hands-on experience in targeted technologies.</li>'}</ul>
            <h4>Suggested next steps</h4>
            <p>Work on short projects that demonstrate applied skills (e.g., deploy a simple app to AWS/GCP, open-source contributions, or a design doc for a service you built).</p>
            <h4>Recommended resources</h4>
            <ul>{resources_html}</ul>
            <p>{closing}</p>
            <p>Best regards,<br/>Aurora Labs Recruitment Team</p>
            """

        return self.send_email_with_attachments(candidate_email, subject, body_html, attachments=None, html=True)