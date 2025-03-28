from dotenv import load_dotenv
import os
import json
import logging

# Load environment variables from .env file
load_dotenv()

# Load Google client secrets from downloaded JSON file
# For production, you should use environment variables instead of storing this file
client_config = {}
try:
    # If you've downloaded the client_secret.json from Google Cloud Console
    with open('client_secret.json', 'r') as f:
        client_config = json.load(f)['web']
except:
    # If using environment variables or the file doesn't exist
    pass

# Google OAuth Configuration
CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', client_config.get('client_id', ''))
CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', client_config.get('client_secret', ''))
REDIRECT_URI = os.environ.get('REDIRECT_URI', 'http://localhost:5000/oauth2callback')
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Microsoft OAuth Configuration
MS_CLIENT_ID = os.environ.get('MS_CLIENT_ID')
MS_CLIENT_SECRET = os.environ.get('MS_CLIENT_SECRET')
MS_REDIRECT_URI = os.environ.get('MS_REDIRECT_URI', 'http://localhost:8000/outlook-callback')
MS_AUTHORITY = 'https://login.microsoftonline.com/common'
MS_GRAPH_SCOPES = ['https://graph.microsoft.com/Mail.Read']

# Flask Configuration
SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24).hex())
FLASK_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex())

# Verify configuration
logger = logging.getLogger(__name__)

def verify_config():
    missing = []
    if not MS_CLIENT_ID:
        missing.append('MS_CLIENT_ID')
    if not MS_CLIENT_SECRET:
        missing.append('MS_CLIENT_SECRET')
    
    if missing:
        error_msg = f"Missing required configuration: {', '.join(missing)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.debug(f"MS_REDIRECT_URI: {MS_REDIRECT_URI}")
    logger.debug(f"MS_AUTHORITY: {MS_AUTHORITY}")
    logger.debug(f"MS_GRAPH_SCOPES: {MS_GRAPH_SCOPES}")

# Call this when the app starts
verify_config() 