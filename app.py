from flask import Flask, render_template, redirect, url_for, session, request, flash, jsonify
from flask_cors import CORS
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import os
import json
from email_follow_up import EmailFollowUpSystem
import config
from msal import ConfidentialClientApplication
from outlook_follow_up import OutlookFollowUpSystem
import logging
from datetime import datetime
from urllib.parse import quote
import requests
from whatsapp_follow_up import WhatsAppFollowUpSystem

app = Flask(__name__)
CORS(app)

# Set a fixed secret key for development
app.secret_key = 'your-fixed-dev-secret-key-change-in-production'  

# Set session type to filesystem for more reliable storage
app.config.update(
    SESSION_TYPE='filesystem',
    PERMANENT_SESSION_LIFETIME=1800,  # 30 minutes
    SESSION_USE_SIGNER=True
)

# Initialize Flask-Session
from flask_session import Session
Session(app)

# Disable OAuthlib's HTTPS verification in local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Enable session cookie security
app.config.update(
    SESSION_COOKIE_SECURE=False,  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

def credentials_from_dict(credentials_dict):
    return Credentials(
        token=credentials_dict['token'],
        refresh_token=credentials_dict['refresh_token'],
        token_uri=credentials_dict['token_uri'],
        client_id=credentials_dict['client_id'],
        client_secret=credentials_dict['client_secret'],
        scopes=credentials_dict['scopes']
    )

@app.route('/')
def index():
    error = request.args.get('error')
    if error == 'timeout':
        return render_template('index.html', 
                             error_message="Authentication timed out. Please try again.")
    return render_template('index.html')

@app.route('/authorize')
def authorize():
    # Create the flow using client secrets
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": config.CLIENT_ID,
                "client_secret": config.CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [config.REDIRECT_URI]
            }
        },
        scopes=config.SCOPES,
        redirect_uri=config.REDIRECT_URI
    )
    
    # Generate the authorization URL and state
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    # Store the state in the session for later verification
    session['state'] = state
    
    # Redirect the user to the authorization URL
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    # Add CORS headers
    response = None
    try:
        # Verify the state parameter
        state = session.get('state', None)
        if state is None:
            response = "Error: No state found in session. Please try again."
            return response
        
        # Create the flow using client secrets
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": config.CLIENT_ID,
                    "client_secret": config.CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [config.REDIRECT_URI]
                }
            },
            scopes=config.SCOPES,
            state=state,
            redirect_uri=config.REDIRECT_URI
        )
        
        # Use the authorization server's response to fetch the OAuth 2.0 tokens
        authorization_response = request.url
        print(f"Authorization response: {authorization_response}")
        flow.fetch_token(authorization_response=authorization_response)
        
        # Store the credentials in the session
        credentials = flow.credentials
        session['credentials'] = credentials_to_dict(credentials)
        
        response = redirect(url_for('dashboard'))
        return response
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        response = f"<h1>Error in OAuth Callback</h1><p>{str(e)}</p><pre>{error_traceback}</pre>"
        print(error_traceback)  # Print the error to console for debugging
        return response

@app.route('/authorize-outlook')
def authorize_outlook():
    try:
        # Generate a new state token
        state = os.urandom(16).hex()
        print(f"Generated state: {state}")  # Debug print
        
        # Store it in session
        session['outlook_state'] = state
        print(f"Session after storing state: {session}")  # Debug print
        
        # Construct authorization URL
        auth_params = {
            'client_id': config.MS_CLIENT_ID,
            'response_type': 'code',
            'redirect_uri': config.MS_REDIRECT_URI,
            'scope': 'https://graph.microsoft.com/Mail.Read offline_access',
            'state': state,
            'response_mode': 'query'
        }
        
        auth_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        auth_url += "?" + "&".join(f"{key}={quote(str(value))}" for key, value in auth_params.items())
        
        print(f"Redirecting to auth URL with state: {state}")  # Debug print
        return redirect(auth_url)
        
    except Exception as e:
        print(f"Error in authorize-outlook: {str(e)}")
        return f"Error: {str(e)}"

@app.route('/outlook-callback')
def outlook_callback():
    try:
        print("===== CALLBACK RECEIVED =====")
        print(f"Session data: {session}")
        print(f"Request args: {request.args}")
        
        # Get callback state
        callback_state = request.args.get('state')
        if not callback_state:
            return "No state parameter in callback"
        
        # Get stored state
        stored_state = session.get('outlook_state')
        print(f"Callback state: {callback_state}")
        print(f"Stored state: {stored_state}")
        
        # For testing, accept the fixed state
        if callback_state == "fixed-state-for-testing":
            print("Using fixed test state")
            stored_state = "fixed-state-for-testing"
            
        # Verify state    
        if not stored_state:
            return "Missing state parameter in session"
            
        if callback_state != stored_state:
            return f"State mismatch. Callback: {callback_state}, Stored: {stored_state}"

        # Get the code
        code = request.args.get('code')
        if not code:
            return "No code received"

        print(f"Code received: {code[:10]}...")

        # Exchange code for token
        token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        token_data = {
            'client_id': config.MS_CLIENT_ID,
            'client_secret': config.MS_CLIENT_SECRET,
            'code': code,
            'redirect_uri': config.MS_REDIRECT_URI,
            'grant_type': 'authorization_code',
            'scope': 'https://graph.microsoft.com/Mail.Read offline_access'
        }

        print("Requesting token...")
        response = requests.post(token_url, data=token_data)
        
        print(f"Token response status: {response.status_code}")
        
        if response.status_code == 200:
            token_info = response.json()
            print("Token received successfully")
            session['outlook_token'] = token_info
            session.modified = True
            return redirect(url_for('dashboard'))
        else:
            return f"Token error: {response.text}"

    except Exception as e:
        import traceback
        error = f"Callback error: {str(e)}\n{traceback.format_exc()}"
        print(error)
        return error

@app.route('/authorize-outlook-simple')
def authorize_outlook_simple():
    # Use a fixed state for debugging
    state = "fixed-state-for-testing"
    session['outlook_state'] = state
    session.modified = True  # Mark the session as modified
    
    # Construct authorization URL
    auth_params = {
        'client_id': config.MS_CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': config.MS_REDIRECT_URI,
        'scope': 'https://graph.microsoft.com/Mail.Read offline_access',
        'state': state,
        'response_mode': 'query'
    }
    
    auth_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    auth_url += "?" + "&".join(f"{key}={quote(str(value))}" for key, value in auth_params.items())
    
    # Print debug info
    print(f"Session before redirect: {session}")
    print(f"State: {state}")
    print(f"Auth URL: {auth_url}")
    
    return redirect(auth_url)

@app.route('/dashboard')
def dashboard():
    has_gmail = 'credentials' in session
    has_outlook = 'outlook_token' in session
    has_whatsapp = session.get('whatsapp_connected', False)
    
    print(f"Dashboard - Gmail connected: {has_gmail}")
    print(f"Dashboard - Outlook connected: {has_outlook}")
    
    return render_template('dashboard.html', 
                         has_gmail=has_gmail, 
                         has_outlook=has_outlook,
                         has_whatsapp=has_whatsapp)

def get_outlook_token():
    """Get a valid Outlook token, refreshing if necessary"""
    if 'outlook_token' not in session:
        return None
        
    token = session['outlook_token']
    
    # Check if token is expired
    if token.get('expires_in', 0) < 300:  # Less than 5 minutes left
        msal_app = ConfidentialClientApplication(
            config.MS_CLIENT_ID,
            authority=config.MS_AUTHORITY,
            client_credential=config.MS_CLIENT_SECRET
        )
        
        result = msal_app.acquire_token_silent(
            config.MS_GRAPH_SCOPES,
            account=None
        )
        
        if result:
            session['outlook_token'] = result
            return result['access_token']
            
    return token.get('access_token')

@app.route('/generate-report')
def generate_report():
    gmail_report = None
    outlook_report = None
    whatsapp_report = None
    
    # Process Gmail data if connected
    if 'credentials' in session:
        credentials = credentials_from_dict(session['credentials'])
        gmail_system = EmailFollowUpSystem(credentials)
        gmail_report = gmail_system.generate_follow_up_report()
    
    # Process Outlook data if connected
    if 'outlook_token' in session:
        access_token = session['outlook_token'].get('access_token')
        outlook_system = OutlookFollowUpSystem(access_token)
        outlook_report = outlook_system.generate_follow_up_report()
    
    # Process WhatsApp data if connected
    if session.get('whatsapp_connected'):
        phone = session.get('whatsapp_phone', '')
        whatsapp_system = WhatsAppFollowUpSystem(phone)
        whatsapp_report = whatsapp_system.generate_follow_up_report()
    
    return render_template('report.html', 
                         gmail_report=gmail_report,
                         outlook_report=outlook_report,
                         whatsapp_report=whatsapp_report)

@app.route('/logout')
def logout():
    # Clear Gmail credentials
    if 'credentials' in session:
        del session['credentials']
    
    # Clear Outlook token
    if 'outlook_token' in session:
        del session['outlook_token']
    
    # Clear any other session data
    session.clear()
    
    return redirect(url_for('index'))

@app.route('/debug-config')
def debug_config():
    """A route to check configuration values (don't include in production!)"""
    debug_info = {
        "CLIENT_ID": config.CLIENT_ID[:10] + "..." if config.CLIENT_ID else "Not set",
        "CLIENT_SECRET": "Set" if config.CLIENT_SECRET else "Not set",
        "REDIRECT_URI": config.REDIRECT_URI,
        "SCOPES": config.SCOPES
    }
    return debug_info

@app.route('/debug')
def debug_info():
    debug_data = {
        'headers': dict(request.headers),
        'session': {k: session.get(k) for k in session},
        'config': {
            'CLIENT_ID': config.CLIENT_ID[:10] + '...' if config.CLIENT_ID else 'Not set',
            'REDIRECT_URI': config.REDIRECT_URI,
            'SCOPES': config.SCOPES
        }
    }
    return debug_data

@app.route('/test-callback')
def test_callback():
    return """
    <h1>Callback Test Successful</h1>
    <p>If you can see this message, your callback route is working correctly.</p>
    """

@app.route('/check-config')
def check_config():
    return {
        'redirect_uri': config.MS_REDIRECT_URI,
        'client_id': config.MS_CLIENT_ID[:8] + '...',  # Show only first 8 chars for security
        'scopes': config.MS_GRAPH_SCOPES
    }

@app.route('/test-session')
def test_session():
    # Set a test value in session
    session['test'] = 'working'
    return f"""
    <h1>Session Test</h1>
    <p>Session contents: {session}</p>
    <p>Test value set. <a href="/check-session">Click here to verify</a></p>
    """

@app.route('/check-session')
def check_session():
    test_value = session.get('test', 'not found')
    return f"""
    <h1>Session Check</h1>
    <p>Test value in session: {test_value}</p>
    <p>Full session contents: {session}</p>
    """

@app.route('/clear-session')
def clear_session():
    session.clear()
    return "Session cleared. <a href='/'>Back to home</a>"

@app.errorhandler(Exception)
def handle_error(e):
    import traceback
    error_traceback = traceback.format_exc()
    print(f"Application error: {str(e)}")
    print(f"Traceback: {error_traceback}")
    return f"""
        <h1>Application Error</h1>
        <p>An error occurred: {str(e)}</p>
        <pre>{error_traceback}</pre>
        <a href="/">Back to Home</a>
    """, 500

# Add session debugging
@app.before_request
def log_request_info():
    logger.debug('Headers: %s', dict(request.headers))
    logger.debug('Body: %s', request.get_data())
    logger.debug('Session: %s', {k: session.get(k) for k in session})

@app.after_request
def log_response_info(response):
    logger.debug('Response Status: %s', response.status)
    logger.debug('Response Headers: %s', dict(response.headers))
    return response

@app.before_request
def debug_session():
    print(f"Current session: {session}")
    print(f"Current route: {request.endpoint}")

@app.route('/authorize-whatsapp')
def authorize_whatsapp():
    return render_template('whatsapp_connect.html')

@app.route('/check-whatsapp-status')
def check_whatsapp_status():
    try:
        response = requests.get('http://localhost:3000/status')
        return jsonify(response.json())
    except requests.exceptions.RequestException:
        return jsonify({'error': 'WhatsApp service not available'})

@app.route('/get-whatsapp-qr')
def get_whatsapp_qr():
    try:
        response = requests.get('http://localhost:3000/qr')
        return jsonify(response.json())
    except requests.exceptions.RequestException:
        return jsonify({'error': 'WhatsApp service not available'})

@app.route('/whatsapp-callback', methods=['POST'])
def whatsapp_callback():
    # This would process the WhatsApp API credentials
    # For now, we'll simulate a successful connection
    phone = request.form.get('phone_number')
    if phone:
        session['whatsapp_connected'] = True
        session['whatsapp_phone'] = phone
        return redirect(url_for('dashboard'))
    return "Phone number is required", 400

if __name__ == '__main__':
    print(f"Starting server with redirect URI: {config.MS_REDIRECT_URI}")
    app.run(host='localhost', port=8000, debug=True)