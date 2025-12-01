import os
import logging
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _build_db_url(user, password, host, port, dbname):
    # Basic builder for a postgres URL
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


class Config:
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'True') == 'True'

    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    DB_HOST = os.getenv('DB_HOST')
    DB_PORT = os.getenv('DB_PORT')
    DB_NAME = os.getenv('DB_NAME')

    # Priority for database configuration:
    # 1. Explicit DATABASE_URL env var (developer override)
    # 2. CLOUD_SQL_DATABASE_URL (Cloud Run / production)
    # 3. Try connecting to localhost quickly (useful when running a local docker postgres)
    # 4. Fall back to DB_HOST/DB_PORT from env
    _explicit_url = os.getenv('DATABASE_URL')
    _cloud_url = os.getenv('CLOUD_SQL_DATABASE_URL')
    # Optional Cloud SQL instance connection name (project:region:instance)
    CLOUD_SQL_CONNECTION_NAME = os.getenv('CLOUD_SQL_CONNECTION_NAME')

    def _get_database_url(explicit, cloud, user, password, host, port, dbname, cloud_sql_conn):
        """Return the effective DATABASE_URL.

        Priority: explicit > cloud > env variables. When using env variables,
        require all to be present and prefer the configured `DB_HOST` for a
        quick TCP check (do not hardcode 127.0.0.1).
        """
        if explicit:
            logger.info('Using explicit DATABASE_URL from environment')
            return explicit
        if cloud:
            logger.info('Using CLOUD_SQL_DATABASE_URL from environment')
            return cloud

        # If a Cloud SQL instance name is provided, prefer building a unix-socket
        # style connection string that Cloud Run will use when the instance is
        # attached via --add-cloudsql-instances. This avoids embedding IPs.
        if cloud_sql_conn:
            logger.info('Using CLOUD_SQL_CONNECTION_NAME to build DATABASE_URL')
            password_quoted = urllib.parse.quote_plus(password or '')
            # Build a URL that avoids placing the socket path in the hostname
            return f"postgresql://{user}:{password_quoted}@/{dbname}?host=/cloudsql/{cloud_sql_conn}"

        missing = [k for k, v in (
            ('DB_USER', user), ('DB_PASSWORD', password), ('DB_HOST', host),
            ('DB_PORT', port), ('DB_NAME', dbname)) if not v]
        if missing:
            raise RuntimeError(
                "Missing required DB environment variables: " + ", ".join(missing) +
                ". Set `DATABASE_URL` or provide these vars in your .env file."
            )

        # Parse port and try a quick TCP check against the configured DB_HOST.
        try:
            port_int = int(port)
        except Exception:
            port_int = None

        chosen_host = host
        if port_int is not None:
            try:
                import socket
                sock = socket.create_connection((host, port_int), timeout=1)
                sock.close()
                logger.info('TCP listener detected on %s:%s; using DB_HOST', host, port)
            except Exception:
                logger.info('No TCP listener on %s:%s; will still use DB_HOST', host, port)

        # URL-encode the password to avoid breaking the URL when containing
        # special characters.
        password_quoted = urllib.parse.quote_plus(password)
        return _build_db_url(user, password_quoted, chosen_host, port, dbname)

    DATABASE_URL = _get_database_url(
        _explicit_url, _cloud_url, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME, CLOUD_SQL_CONNECTION_NAME
    )
    
    # Gmail API - Use absolute paths to work from any directory
    _backend_dir = os.path.dirname(os.path.abspath(__file__))
    GMAIL_CREDENTIALS_PATH = os.getenv('GMAIL_CREDENTIALS_PATH') or os.path.join(_backend_dir, 'credentials.json')
    GMAIL_TOKEN_PATH = os.getenv('GMAIL_TOKEN_PATH') or os.path.join(_backend_dir, 'token.json')
    GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 
                    'https://www.googleapis.com/auth/gmail.send',
                    'https://www.googleapis.com/auth/gmail.modify']
    
    GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
    GCS_CREDENTIALS_PATH = os.getenv('GCS_CREDENTIALS_PATH')
    
    # OpenRouter API
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
    OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'
    
    # AI Model Selection
    PARSING_MODEL = os.getenv('PARSING_MODEL', 'openai/gpt-3.5-turbo')
    SCREENING_MODEL = os.getenv('SCREENING_MODEL', 'openai/gpt-3.5-turbo')
    
    # Email Processing
    POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '300'))  # 5 minutes
    SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'demoraptorai@gmail.com')
    
    # File Processing
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc'}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    # Tesseract OCR - path must be provided via environment when needed
    TESSERACT_CMD = os.getenv('TESSERACT_CMD')

    # Poppler PDF utilities - path must be provided via environment when needed
    POPPLER_PATH = os.getenv('POPPLER_PATH')
    
    # Optional Google Calendar integration
    GOOGLE_CALENDAR_ENABLED = os.getenv('GOOGLE_CALENDAR_ENABLED', 'False') == 'True'
    GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', os.path.join(_backend_dir, 'gcalendar-service-account.json'))
    # If using a shared calendar, set its calendar ID (e.g. your-calendar@group.calendar.google.com)
    RECRUITER_CALENDAR_ID = os.getenv('RECRUITER_CALENDAR_ID', '')