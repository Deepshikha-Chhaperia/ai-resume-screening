import pickle
import json
import os
from datetime import datetime

def extract_token_info():
    try:
        # Load the pickle token
        with open('token.json', 'rb') as f:
            creds = pickle.load(f)
        
        # Extract the token information in JSON format
        token_info = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes
        }
        
        print("Token information for GMAIL_TOKEN_JSON environment variable:")
        print(json.dumps(token_info, indent=2))
        
        return token_info
        
    except Exception as e:
        print(f"Error extracting token: {e}")
        return None

if __name__ == "__main__":
    extract_token_info()