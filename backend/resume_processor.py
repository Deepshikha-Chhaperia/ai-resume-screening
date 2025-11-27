import io
import PyPDF2
import fitz
from docx import Document
from pdf2image import convert_from_bytes
import pytesseract
from PIL import Image
from config import Config
import logging
import re

logger = logging.getLogger(__name__)

class ResumeProcessor:
    def __init__(self):
        if Config.TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_CMD
    
    def extract_text(self, file_data, filename):
        """Extract text from PDF or DOCX file"""
        try:
            # Check file content first (magic bytes validation)
            if not self._validate_file_content(file_data, filename):
                logger.warning(f"File {filename} failed content validation")
                return ""
            
            if filename.lower().endswith('.pdf'):
                return self._extract_from_pdf(file_data)
            elif filename.lower().endswith(('.docx', '.doc')):
                return self._extract_from_docx(file_data)
            else:
                logger.warning(f"Unsupported file format: {filename}")
                return ""
        except Exception as e:
            logger.error(f"Error extracting text from {filename}: {e}")
            return ""
    
    def _validate_file_content(self, file_data, filename):
        """Check if file content matches the file extension using magic bytes"""
        if len(file_data) < 8:
            logger.warning(f"File {filename} too small for validation")
            return False
        
        if filename.lower().endswith('.pdf'):
            # PDF files must start with %PDF
            if not file_data.startswith(b'%PDF'):
                logger.warning(f"File {filename} claims to be PDF but doesn't have PDF header")
                return False
                
        elif filename.lower().endswith('.docx'):
            # DOCX files are ZIP files, must start with PK
            if not file_data.startswith(b'PK'):
                logger.warning(f"File {filename} claims to be DOCX but doesn't have ZIP header")
                return False
                
        elif filename.lower().endswith('.doc'):
            # DOC files have OLE signature
            if not file_data.startswith(b'\xd0\xcf\x11\xe0'):
                logger.warning(f"File {filename} claims to be DOC but doesn't have OLE header")
                return False
        
        return True
    
    def _extract_from_pdf(self, file_data):
        """Extract text from PDF, with OCR fallback for scanned documents"""
        text = ""
        
        # Try text-based extraction first
        try:
            pdf_file = io.BytesIO(file_data)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        except Exception as e:
            logger.warning(f"PyPDF2 extraction failed: {e}")
        
        # If minimal text extracted, try PyMuPDF
        if len(text.strip()) < 100:
            try:
                pdf_document = fitz.open(stream=file_data, filetype="pdf")
                text = ""
                for page in pdf_document:
                    text += page.get_text() + "\n"
                pdf_document.close()
            except Exception as e:
                logger.warning(f"PyMuPDF extraction failed: {e}")
        
        # If still minimal text, use OCR
        if len(text.strip()) < 100:
            logger.info("Text-based extraction yielded minimal content. Attempting OCR...")
            text = self._ocr_pdf(file_data)
        
        return text.strip()
    
    def _ocr_pdf(self, file_data):
        """Perform OCR on PDF pages"""
        try:
            # Use the configured Poppler path if available
            poppler_path = getattr(Config, 'POPPLER_PATH', None)
            if poppler_path:
                images = convert_from_bytes(file_data, poppler_path=poppler_path)
            else:
                images = convert_from_bytes(file_data)
                
            text = ""
            for i, image in enumerate(images):
                logger.info(f"Performing OCR on page {i+1}")
                page_text = pytesseract.image_to_string(image)
                text += page_text + "\n"
            return text
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return ""
    
    def _extract_from_docx(self, file_data):
        """Extract text from DOCX file"""
        try:
            doc = Document(io.BytesIO(file_data))
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            return text.strip()
        except Exception as e:
            logger.error(f"DOCX extraction failed: {e}")
            return ""
    
    def extract_email_from_text(self, text):
        """Extract email address from text"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(email_pattern, text)
        return matches[0] if matches else None
    
    def extract_phone_from_text(self, text):
        """Extract phone number from text"""
        phone_pattern = r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
        matches = re.findall(phone_pattern, text)
        return matches[0] if matches else None
    
    def validate_candidate_data(self, parsed_data, sender_email, sender_name):
        """Validate parsed data against email metadata"""
        validation_flags = []
        
        # Check email match
        resume_email = parsed_data.get('contact_email', '').lower()
        if resume_email and resume_email != sender_email.lower():
            validation_flags.append({
                'type': 'email_mismatch',
                'message': f"Resume email ({resume_email}) doesn't match sender ({sender_email})"
            })
        
        # Check name similarity (basic check)
        resume_name = parsed_data.get('full_name', '').lower()
        if resume_name and sender_name:
            sender_name_clean = sender_name.lower().split('<')[0].strip()
            if resume_name not in sender_name_clean and sender_name_clean not in resume_name:
                validation_flags.append({
                    'type': 'name_mismatch',
                    'message': f"Resume name ({resume_name}) may not match sender ({sender_name_clean})"
                })
        
        return validation_flags