# AI Resume Screening

An intelligent recruiting assistant that automates resume processing and candidate screening. This project transforms a Gmail inbox into a streamlined candidate pipeline, leveraging AI and OCR to extract, analyze, and present candidate data in a user-friendly dashboard.

## Demo

A video demonstration of the application in action will be added soon. Stay tuned!

## Features

- **Automated Resume Processing**: Extracts text from PDF, DOCX, and scanned resumes using a robust three-layer OCR system (PyPDF2, PyMuPDF, Tesseract).
- **AI-Powered Screening**: Parses resumes into structured JSON and evaluates candidates with a fit score and reasoning.
- **AI Insights**: View AI-generated insights for each candidate, including fit scores and reasoning.
- **REST API**: Includes endpoints for interview calendar invites, exporting data for GDPR compliance, and a bulk action endpoint to send personalized feedback messages to multiple candidates, including course links to help them improve.
- **Cloud-Ready**: Designed for Google Cloud production use cases, leveraging GCS for resume storage, Cloud SQL (PostgreSQL) for data persistence, Cloud Run for scalable deployment, and VPC for secure networking.

## Tech Stack

- **Backend**: Python, Flask, PostgreSQL
- **Frontend**: React, TypeScript, TailwindCSS
- **AI & OCR**: OpenAI API, PyPDF2, PyMuPDF, Tesseract
- **Cloud**: Google Cloud Platform (Cloud Run, Cloud SQL, GCS)

## Getting Started

### Prerequisites

- Node.js and npm
- Python 3.9+
- Google Cloud SDK (for cloud deployment)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Deepshikha-Chhaperia/ai-resume-screening.git
   cd ai-resume-screening
   ```

2. Install backend dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. Install frontend dependencies:
   ```bash
   npm install
   ```

4. Start the development servers:
   - Backend:
     ```bash
     python backend/main.py
     ```
   - Frontend:
     ```bash
     npm run dev
     ```

## Environment Configuration

To run the application, create a `.env` file with the following variables:

```env
# Database Configuration
DATABASE_URL=<your_database_url>

# Gmail API Configuration
SENDER_EMAIL=<your_sender_email>

# Google Cloud Storage
GCS_BUCKET_NAME=<your_gcs_bucket_name>
GCS_CREDENTIALS_PATH=<path_to_your_gcs_credentials>
GOOGLE_CLOUD_PROJECT=<your_google_cloud_project>

# Cloud SQL
CLOUD_SQL_CONNECTION_NAME=<your_cloud_sql_connection_name>

# OpenAI API Configuration
OPENAI_API_KEY=<your_openai_api_key>
PARSING_MODEL=<parsing_model_name>
SCREENING_MODEL=<screening_model_name>

# Email Processing
POLL_INTERVAL=<poll_interval_in_seconds>
ENABLE_EMAIL_PROCESSING=<true_or_false>

# Tesseract OCR
TESSERACT_CMD=<path_to_tesseract_executable>

# Poppler PDF Utilities
POPPLER_PATH=<path_to_poppler_utilities>

# Google Calendar Integration
GOOGLE_CALENDAR_ENABLED=<true_or_false>
GOOGLE_SERVICE_ACCOUNT_JSON=<path_to_your_service_account_json>
RECRUITER_CALENDAR_ID=<your_recruiter_calendar_id>
```

## Contributing

Contributions are welcome! If you'd like to contribute, please follow these simple steps:

- Fork the repository.
- Create a feature branch: `git checkout -b feat/your-feature`.
- Make your changes, keeping them small and focused.
- Update or add tests if applicable.
- Commit and push your branch, then open a pull request against `main`.

Please do NOT commit sensitive files such as `.env`, service account JSONs, or credential files. Use `.env.example` for configuration samples. 

## License

This project is licensed under the MIT License.