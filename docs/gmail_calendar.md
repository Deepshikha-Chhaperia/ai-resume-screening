# Gmail and Google Calendar Integration (local use)

This project supports connecting to:

- **Google Calendar** (to create interview events)
- **Gmail** (to send emails to candidates)

You do not need to deploy on Google Cloud to use these features locally, but you must create a Google Cloud project and generate credentials.

## 1. Enable Required APIs

In the Google Cloud Console:

1. Open your project
2. Go to **APIs & Services → Library**
3. Enable the following APIs:
   - **Google Calendar API**
   - **Gmail API**

## 2. Google Calendar Setup (via Service Account)

### A. Create a service account and key

1. Go to **IAM & Admin → Service Accounts**
2. Click **Create Service Account**
3. After creation, open the account → **Keys → Add Key → Create new key (JSON)**
4. Download the JSON file and store it securely

Do not commit this file to version control.

### B. Create and share a calendar

1. Open **Google Calendar**
2. Create a new calendar: left sidebar → **Other calendars → + → Create new calendar**
3. Open the calendar’s **Settings**
4. Under **Share with specific people**, add the service account email
5. Grant permission **Make changes to events**

### C. Retrieve the Calendar ID

Inside the same calendar settings → **Integrate calendar** → copy the **Calendar ID**

Format typically looks like:

`example-calendar-id@group.calendar.google.com`

### D. Add environment variables

Your backend must be provided with the following environment variables:

```env
GOOGLE_CALENDAR_ENABLED=True
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json
RECRUITER_CALENDAR_ID=example-calendar-id@group.calendar.google.com
```

Use a `.env` file or set environment variables depending on your local setup.


## 3. Gmail Setup (OAuth)

### A. Configure the OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**
2. Choose **External**
3. Add your chosen sender Gmail address under **Test users**
4. Save

### B. Create an OAuth client

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. Application type: **Desktop application**
4. Download the JSON file (client credentials)
5. Save it securely in your backend folder

Do not commit this file to version control.

### C. Run the OAuth flow locally (one-time)

Run your backend once:

```bash
python main.py
```

A browser window will open asking you to authenticate with the Gmail account. After approval, a token file will be created locally and reused automatically.

### D. Add the sender email to your environment

```env
SENDER_EMAIL=your-gmail-address
```
