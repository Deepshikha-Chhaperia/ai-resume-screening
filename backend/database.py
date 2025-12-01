import psycopg2
from psycopg2.extras import RealDictCursor, Json
import json
from contextlib import contextmanager
from collections import defaultdict
from datetime import datetime
from config import Config
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.connection_string = Config.DATABASE_URL
    
    @contextmanager
    def get_connection(self):
        # Try connection strategies in order so the same code works locally
        # (Docker / TCP) and in GCP (Cloud Run with unix socket).
        conn = None
        try:
            # 1) If a full DATABASE_URL is configured (could be TCP or libpq socket URL), try it first
            if self.connection_string:
                conn = psycopg2.connect(
                    self.connection_string,
                    connect_timeout=10,
                    options='-c statement_timeout=30000'
                )
                yield conn
                conn.commit()
                return

            # 2) If CLOUD_SQL_CONNECTION_NAME is set, attempt unix-socket connect
            cloud_sql_conn = getattr(Config, 'CLOUD_SQL_CONNECTION_NAME', None)
            if cloud_sql_conn:
                socket_path = f"/cloudsql/{cloud_sql_conn}"
                logger.info('Attempting unix-socket DB connect via %s', socket_path)
                conn = psycopg2.connect(
                    user=getattr(Config, 'DB_USER', None),
                    password=getattr(Config, 'DB_PASSWORD', None),
                    host=socket_path,
                    dbname=getattr(Config, 'DB_NAME', None),
                    connect_timeout=10,
                    options='-c statement_timeout=30000'
                )
                yield conn
                conn.commit()
                return

            # 3) Fall back to DB_HOST/DB_PORT (useful for local TCP Postgres)
            host = getattr(Config, 'DB_HOST', None) or '127.0.0.1'
            port = getattr(Config, 'DB_PORT', None) or 5432
            logger.info('Attempting TCP DB connect to %s:%s', host, port)
            conn = psycopg2.connect(
                user=getattr(Config, 'DB_USER', None),
                password=getattr(Config, 'DB_PASSWORD', None),
                host=host,
                port=port,
                dbname=getattr(Config, 'DB_NAME', None),
                connect_timeout=10,
                options='-c statement_timeout=30000'
            )
            yield conn
            conn.commit()

        except Exception as e:
            # Provide a helpful error with the attempted strategy hints
            logger.error('Database connection error: %s', e)
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    
    def execute_query(self, query, params=None, fetch=True):
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                if fetch:
                    return cursor.fetchall()
                return cursor.rowcount
    
    def insert_candidate(self, data):
        query = """
            INSERT INTO candidates 
            (source_email, sender_name, email_subject, raw_email_body, resume_url, 
             extracted_text, parsed_json, validation_flags, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        result = self.execute_query(query, (
            data['source_email'],
            data.get('sender_name'),
            data.get('email_subject'),
            data.get('raw_email_body'),
            data.get('resume_url'),
            data.get('extracted_text'),
            Json(data.get('parsed_json', {})),
            Json(data.get('validation_flags', {})),
            data.get('status', 'pending')
        ))
        return result[0]['id'] if result else None
    
    def insert_screening_result(self, data):
        query = """
            INSERT INTO screening_results 
            (candidate_id, job_description, fit_score, summary, matching_skills, 
             concerns, recruiter_comments, analysis_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """

        recruiter_comments = data.get('recruiter_comments')
        analysis_json = data.get('analysis_json')

        # If analysis_json is present but recruiter_comments is empty, try to serialize a short summary
        if analysis_json and not recruiter_comments:
            try:
                recruiter_comments = json.dumps({
                    'summary': analysis_json.get('summary'),
                    'recommendation': analysis_json.get('recommendation')
                })
            except Exception:
                recruiter_comments = None

        result = self.execute_query(query, (
            data['candidate_id'],
            data['job_description'],
            data['fit_score'],
            data['summary'],
            Json(data.get('matching_skills', [])),
            Json(data.get('concerns', [])),
            recruiter_comments,
            Json(analysis_json) if analysis_json is not None else None
        ))
        return result[0]['id'] if result else None

    def increment_metric(self, name, delta=1):
        """Increment a named metric in the metrics table (creates row if missing)"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO metrics (name, value) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE SET value = metrics.value + %s", (name, delta, delta))
        except Exception as e:
            logger.warning(f"Failed to increment metric {name}: {e}")

    def get_metrics(self):
        try:
            rows = self.execute_query("SELECT name, value FROM metrics", fetch=True)
            return {r['name']: r['value'] for r in rows}
        except Exception as e:
            logger.warning(f"Failed to get metrics: {e}")
            return {}
    
    def log_audit(self, candidate_id, action, details):
        query = """
            INSERT INTO audit_logs (candidate_id, action, details)
            VALUES (%s, %s, %s)
        """
        self.execute_query(query, (candidate_id, action, Json(details)), fetch=False)
    
    def get_all_candidates(self):
        query = """
            SELECT c.*, s.fit_score, s.summary, s.matching_skills, s.concerns, s.recruiter_comments, s.analysis_json
            FROM candidates c
            LEFT JOIN screening_results s ON c.id = s.candidate_id
            ORDER BY COALESCE(s.fit_score, -1) DESC, c.created_at DESC
        """
        try:
            return self.execute_query(query)
        except Exception as e:
            # Fallback for older schemas that don't have analysis_json column
            if 'analysis_json' in str(e) or 'does not exist' in str(e):
                fallback = """
                    SELECT c.*, s.fit_score, s.summary, s.matching_skills, s.concerns, s.recruiter_comments
                    FROM candidates c
                    LEFT JOIN screening_results s ON c.id = s.candidate_id
                    ORDER BY c.created_at DESC
                """
                try:
                    return self.execute_query(fallback)
                except Exception:
                    # Re-raise original error if fallback also fails
                    raise
            raise
    
    def get_candidate_by_id(self, candidate_id):
        query = """
            SELECT c.*, s.fit_score, s.summary, s.matching_skills, s.concerns, 
                   s.recruiter_comments, s.job_description, s.analysis_json
            FROM candidates c
            LEFT JOIN screening_results s ON c.id = s.candidate_id
            WHERE c.id = %s
        """
        try:
            result = self.execute_query(query, (candidate_id,))
            return result[0] if result else None
        except Exception as e:
            if 'analysis_json' in str(e) or 'does not exist' in str(e):
                fallback = """
                    SELECT c.*, s.fit_score, s.summary, s.matching_skills, s.concerns, 
                           s.recruiter_comments, s.job_description
                    FROM candidates c
                    LEFT JOIN screening_results s ON c.id = s.candidate_id
                    WHERE c.id = %s
                """
                result = self.execute_query(fallback, (candidate_id,))
                return result[0] if result else None
            raise
    
    def update_candidate_status(self, candidate_id, status):
        query = "UPDATE candidates SET status = %s, updated_at = NOW() WHERE id = %s"
        self.execute_query(query, (status, candidate_id), fetch=False)
    
    def get_active_job_description(self):
        query = "SELECT * FROM job_descriptions WHERE is_active = true LIMIT 1"
        result = self.execute_query(query)
        return result[0] if result else None

    def get_candidates_for_export(self):
        """Return full candidate dataset plus audit trail for compliance exports"""
        candidates_query = """
            SELECT c.*, s.fit_score, s.summary, s.matching_skills, s.concerns,
                   s.recruiter_comments, s.job_description, s.analysis_json
            FROM candidates c
            LEFT JOIN screening_results s ON c.id = s.candidate_id
            ORDER BY c.created_at DESC
        """
        try:
            candidates = self.execute_query(candidates_query)
        except Exception as e:
            if 'analysis_json' in str(e) or 'does not exist' in str(e):
                fallback = """
                    SELECT c.*, s.fit_score, s.summary, s.matching_skills, s.concerns,
                           s.recruiter_comments, s.job_description
                    FROM candidates c
                    LEFT JOIN screening_results s ON c.id = s.candidate_id
                    ORDER BY c.created_at DESC
                """
                candidates = self.execute_query(fallback)
            else:
                raise

        audit_logs = self.execute_query(
            "SELECT * FROM audit_logs ORDER BY timestamp ASC"
        )

        logs_by_candidate = defaultdict(list)
        general_logs = []

        for log in audit_logs:
            candidate_id = log.get('candidate_id')
            if candidate_id:
                logs_by_candidate[candidate_id].append(log)
            else:
                general_logs.append(log)

        for candidate in candidates:
            candidate_id = candidate.get('id')
            candidate['audit_logs'] = logs_by_candidate.get(candidate_id, [])

        return {
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'candidate_count': len(candidates),
            'candidates': candidates,
            'general_audit_logs': general_logs
        }

db = Database()