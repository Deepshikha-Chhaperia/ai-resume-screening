import os
import logging
from config import Config

logger = logging.getLogger(__name__)

try:
    from google.cloud import storage as gcs
    GCS_AVAILABLE = True
except Exception:
    GCS_AVAILABLE = False


def save_resume_file(file_bytes: bytes, filename: str) -> str:
    """
    Save a resume file either to Google Cloud Storage (if credentials present)
    or to a local `resumes/` folder. Returns a URL or path that can be used
    to retrieve the file later.
    """
    # Prefer GCS when available and credentials provided
    if GCS_AVAILABLE:
        try:
            # Try to use Application Default Credentials first
            if os.path.exists(Config.GCS_CREDENTIALS_PATH):
                try:
                    # Check if it's a service account file or ADC
                    with open(Config.GCS_CREDENTIALS_PATH, 'r') as f:
                        import json
                        cred_data = json.load(f)
                        if 'client_email' in cred_data:
                            # Service account file
                            client = gcs.Client.from_service_account_json(Config.GCS_CREDENTIALS_PATH)
                        else:
                            # Application Default Credentials - specify project explicitly
                            project_id = os.getenv('GOOGLE_CLOUD_PROJECT', Config.GCS_BUCKET_NAME.split('-')[0])
                            client = gcs.Client(project=project_id)
                except Exception:
                    # Fallback to default ADC with explicit project
                    project_id = os.getenv('GOOGLE_CLOUD_PROJECT', Config.GCS_BUCKET_NAME.split('-')[0])
                    client = gcs.Client(project=project_id)
            else:
                # Use default Application Default Credentials with explicit project
                project_id = os.getenv('GOOGLE_CLOUD_PROJECT', Config.GCS_BUCKET_NAME.split('-')[0])
                client = gcs.Client(project=project_id)
            
            bucket = client.bucket(Config.GCS_BUCKET_NAME)
            blob_path = f"resumes/{filename}"
            blob = bucket.blob(blob_path)
            blob.upload_from_string(file_bytes)
            
            # Try to make public (best-effort). If the bucket policy prevents it,
            # we'll still return the gs:// path which can be used server-side.
            try:
                blob.make_public()
                public_url = blob.public_url
                logger.info(f"Uploaded resume to GCS and made public: {public_url}")
                return public_url
            except Exception:
                gs_url = f"gs://{Config.GCS_BUCKET_NAME}/{blob_path}"
                logger.info(f"Uploaded resume to GCS: {gs_url} (not public)")
                return gs_url
        except Exception as e:
            logger.error(f"Failed to upload to GCS: {e}")

    # Fallback: save locally under backend/resumes/
    local_dir = os.path.join(os.path.dirname(__file__), 'resumes')
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, filename)
    try:
        with open(local_path, 'wb') as f:
            f.write(file_bytes)
        abs_path = os.path.abspath(local_path)
        logger.info(f"Saved resume locally: {abs_path}")
        return f"file://{abs_path}"
    except Exception as e:
        logger.error(f"Failed to save resume locally: {e}")
        # As a last resort, return a placeholder path
        return f"resumes/{filename}"


def make_blob_public(gs_path: str) -> str:
    """
    Make a GCS blob public and return the public URL
    gs_path should be in format: gs://bucket-name/path/to/file
    """
    if not GCS_AVAILABLE:
        raise Exception("Google Cloud Storage is not available")
    
    try:
        # Parse the gs:// path
        if not gs_path.startswith('gs://'):
            raise ValueError("Path must start with gs://")
        
        path_parts = gs_path[5:].split('/', 1)  # Remove gs:// and split
        bucket_name = path_parts[0]
        blob_name = path_parts[1] if len(path_parts) > 1 else ""
        
        # Create client and get the blob
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT', bucket_name.split('-')[0])
        client = gcs.Client(project=project_id)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Make the blob public
        blob.make_public()
        
        # Return the public URL
        public_url = blob.public_url
        logger.info(f"Made blob public: {public_url}")
        return public_url
        
    except Exception as e:
        logger.error(f"Failed to make blob public for {gs_path}: {e}")
        raise


def generate_signed_url(gs_path: str, expiration_minutes: int = 60) -> str:
    """
    Generate a signed URL for a GCS object that allows temporary access
    gs_path should be in format: gs://bucket-name/path/to/file
    """
    if not GCS_AVAILABLE:
        raise Exception("Google Cloud Storage is not available")
    
    try:
        # Parse the gs:// path
        if not gs_path.startswith('gs://'):
            raise ValueError("Path must start with gs://")
        
        path_parts = gs_path[5:].split('/', 1)  # Remove gs:// and split
        bucket_name = path_parts[0]
        blob_name = path_parts[1] if len(path_parts) > 1 else ""
        
        # Create client and get the blob
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT', bucket_name.split('-')[0])
        client = gcs.Client(project=project_id)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Generate signed URL
        from datetime import datetime, timedelta
        expiration = datetime.utcnow() + timedelta(minutes=expiration_minutes)
        
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=expiration,
            method="GET"
        )
        
        logger.info(f"Generated signed URL for {gs_path}")
        return signed_url
        
    except Exception as e:
        logger.error(f"Failed to generate signed URL for {gs_path}: {e}")
        raise


def stream_gcs_file(gs_path: str, candidate_name: str = "candidate"):
    """
    Stream a file from GCS through the backend API
    This works even with uniform bucket-level access enabled
    """
    from flask import Response
    import mimetypes
    
    if not GCS_AVAILABLE:
        raise Exception("Google Cloud Storage is not available")
    
    try:
        # Parse the gs:// path
        if not gs_path.startswith('gs://'):
            raise ValueError("Path must start with gs://")
        
        path_parts = gs_path[5:].split('/', 1)  # Remove gs:// and split
        bucket_name = path_parts[0]
        blob_name = path_parts[1] if len(path_parts) > 1 else ""
        
        # Create client and get the blob
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT', bucket_name.split('-')[0])
        client = gcs.Client(project=project_id)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Check if blob exists
        if not blob.exists():
            raise Exception("File not found in cloud storage")
        
        # Get file extension and determine mime type
        filename = blob_name.split('/')[-1]  # Get just the filename
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = 'application/octet-stream'
        
        # Download the blob content
        blob_data = blob.download_as_bytes()
        
        logger.info(f"Streaming {gs_path} ({len(blob_data)} bytes)")
        
        # Create a safe filename for download
        safe_filename = f"{candidate_name}_{filename}".replace(' ', '_').replace('/', '_')
        
        # Return as a Flask Response with proper headers
        return Response(
            blob_data,
            mimetype=mime_type,
            headers={
                'Content-Disposition': f'attachment; filename="{safe_filename}"',
                'Content-Length': str(len(blob_data))
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to stream file from {gs_path}: {e}")
        raise
