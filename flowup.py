from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import datetime
import pickle
import os
import re
import email.utils
import pytz

# Gmail scopes: read-only for now
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

class EmailFollowUpSystem:
    def __init__(self):
        self.service = self.get_gmail_service()
        
    def get_gmail_service(self):
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
                
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
                
        return build('gmail', 'v1', credentials=creds)

    def get_sent_emails(self, days_ago=30):
        """Get sent emails from the last 30 days"""
        query = f"in:sent after:{(datetime.datetime.now() - datetime.timedelta(days=days_ago)).strftime('%Y/%m/%d')}"
        results = self.service.users().messages().list(userId='me', q=query).execute()
        return results.get('messages', [])

    def get_email_details(self, msg_id):
        """Get detailed information about an email"""
        msg = self.service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        headers = msg['payload']['headers']
        
        subject = next(h['value'] for h in headers if h['name'].lower() == 'subject')
        to = next(h['value'] for h in headers if h['name'].lower() == 'to')
        date = next(h['value'] for h in headers if h['name'].lower() == 'date')
        
        return {
            'id': msg_id,
            'subject': subject,
            'to': to,
            'date': date,
            'thread_id': msg['threadId']
        }

    def check_for_response(self, thread_id):
        """Check if there's been a response in the thread"""
        thread = self.service.users().threads().get(userId='me', id=thread_id).execute()
        messages = thread['messages']
        
        # If there's only one message in the thread, no response received
        if len(messages) == 1:
            return False
            
        # Check if the last message in the thread was from someone else
        last_msg = messages[-1]
        headers = last_msg['payload']['headers']
        from_header = next(h['value'] for h in headers if h['name'].lower() == 'from')
        
        # If the last message is from you, no response received
        return not from_header.lower().endswith('@gmail.com')  # Replace with your email domain

    def check_unanswered_sent_emails(self, days_ago=30):
        """Check for all sent emails that haven't received responses"""
        query = f"in:sent after:{(datetime.datetime.now() - datetime.timedelta(days=days_ago)).strftime('%Y/%m/%d')}"
        results = self.service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        
        unanswered_emails = []
        
        for message in messages:
            details = self.get_email_details(message['id'])
            
            # Skip if it's a reply to someone else's email
            if self.is_reply_email(details['subject']):
                continue
                
            # Check if there's been a response
            has_response = self.check_for_response(details['thread_id'])
            
            if not has_response:
                # Parse the email date properly
                parsed_date = email.utils.parsedate_to_datetime(details['date'])
                days_waiting = (datetime.datetime.now(pytz.UTC) - parsed_date).days
                
                unanswered_emails.append({
                    'subject': details['subject'],
                    'to': details['to'],
                    'date': details['date'],
                    'days_waiting': days_waiting
                })
        
        return unanswered_emails

    def is_reply_email(self, subject):
        """Check if the email is a reply (starts with Re: or similar)"""
        reply_patterns = ['^re:', '^fwd:', '^fw:']
        return any(re.match(pattern, subject.lower()) for pattern in reply_patterns)

    def identify_follow_ups_needed(self):
        """Main function to identify emails needing follow-up"""
        sent_emails = self.get_sent_emails()
        follow_ups_needed = []
        
        for email in sent_emails:
            details = self.get_email_details(email['id'])
            
            # Check if this email seems to require a response
            subject = details['subject'].lower()
            requires_response = any(keyword in subject for keyword in 
                ['question', 'request', 'follow up', 'please', '?'])
            
            if requires_response:
                has_response = self.check_for_response(details['thread_id'])
                if not has_response:
                    # Parse the email date properly
                    parsed_date = email.utils.parsedate_to_datetime(details['date'])
                    days_waiting = (datetime.datetime.now(pytz.UTC) - parsed_date).days
                    
                    follow_ups_needed.append({
                        'subject': details['subject'],
                        'to': details['to'],
                        'date': details['date'],
                        'days_waiting': days_waiting
                    })
        
        return follow_ups_needed

    def generate_follow_up_report(self):
        """Generate a comprehensive report of emails needing follow-up"""
        # Get emails that explicitly need responses (based on keywords)
        explicit_follow_ups = self.identify_follow_ups_needed()
        # Get all unanswered sent emails
        unanswered_emails = self.check_unanswered_sent_emails()
        
        print("\n=== Email Follow-up Report ===\n")
        
        print("1. Emails Explicitly Requiring Response:")
        print("-" * 50)
        if not explicit_follow_ups:
            print("No explicit follow-ups needed at this time.")
        else:
            for email in sorted(explicit_follow_ups, key=lambda x: x['days_waiting'], reverse=True):
                print(f"Subject: {email['subject']}")
                print(f"To: {email['to']}")
                print(f"Sent: {email['date']}")
                print(f"Waiting for: {email['days_waiting']} days")
                print("-" * 50)
        
        print("\n2. All Unanswered Sent Emails:")
        print("-" * 50)
        if not unanswered_emails:
            print("No unanswered emails found.")
        else:
            for email in sorted(unanswered_emails, key=lambda x: x['days_waiting'], reverse=True):
                print(f"Subject: {email['subject']}")
                print(f"To: {email['to']}")
                print(f"Sent: {email['date']}")
                print(f"Waiting for: {email['days_waiting']} days")
                print("-" * 50)

def main():
    follow_up_system = EmailFollowUpSystem()
    follow_up_system.generate_follow_up_report()

if __name__ == "__main__":
    main()
