from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import email.utils
import pytz
import re

class EmailFollowUpSystem:
    def __init__(self, credentials):
        self.service = build('gmail', 'v1', credentials=credentials)
        
    def get_sent_emails(self, days_ago=30):
        """Get sent emails from the last 30 days"""
        query = f"in:sent after:{(datetime.now() - timedelta(days=days_ago)).strftime('%Y/%m/%d')}"
        results = self.service.users().messages().list(userId='me', q=query).execute()
        return results.get('messages', [])

    def get_received_emails(self, days_ago=30):
        """Get received emails from the last 30 days"""
        query = f"in:inbox after:{(datetime.now() - timedelta(days=days_ago)).strftime('%Y/%m/%d')}"
        results = self.service.users().messages().list(userId='me', q=query).execute()
        return results.get('messages', [])

    def get_email_details(self, msg_id):
        """Get detailed information about an email"""
        msg = self.service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        headers = msg['payload']['headers']
        
        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
        to = next((h['value'] for h in headers if h['name'].lower() == 'to'), 'Unknown Recipient')
        from_header = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
        date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown Date')
        
        return {
            'id': msg_id,
            'subject': subject,
            'to': to,
            'from': from_header,
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
        from_header = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
        
        # Get user's email
        profile = self.service.users().getProfile(userId='me').execute()
        user_email = profile['emailAddress']
        
        # If the last message is from the user, no response received
        return not from_header.lower().find(user_email.lower()) >= 0

    def is_reply_email(self, subject):
        """Check if the email is a reply (starts with Re: or similar)"""
        reply_patterns = ['^re:', '^fwd:', '^fw:']
        return any(re.match(pattern, subject.lower()) for pattern in reply_patterns)

    def check_unanswered_sent_emails(self, days_ago=30):
        """Check for all sent emails that haven't received responses"""
        query = f"in:sent after:{(datetime.now() - timedelta(days=days_ago)).strftime('%Y/%m/%d')}"
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
                try:
                    parsed_date = email.utils.parsedate_to_datetime(details['date'])
                    days_waiting = (datetime.now(pytz.UTC) - parsed_date).days
                except:
                    days_waiting = 0  # Default if date parsing fails
                
                unanswered_emails.append({
                    'subject': details['subject'],
                    'to': details['to'],
                    'date': details['date'],
                    'days_waiting': days_waiting
                })
        
        return unanswered_emails

    def check_unreplied_received_emails(self, days_ago=30):
        """Check for received emails that haven't been replied to"""
        received_emails = self.get_received_emails(days_ago)
        unreplied_emails = []
        
        for email in received_emails:
            details = self.get_email_details(email['id'])
            
            # Skip if it's a promotional or automated email
            subject = details['subject'].lower()
            from_address = details.get('from', '').lower()
            
            # Skip if likely automated/promotional
            if any(keyword in subject for keyword in ['newsletter', 'promotion', 'sale', 'offer', 'no-reply']):
                continue
                
            if any(keyword in from_address for keyword in ['noreply', 'no-reply', 'donotreply', 'newsletter']):
                continue
            
            # Check if you've replied
            has_replied = self.check_if_replied(details['thread_id'])
            
            if not has_replied:
                # Parse the email date properly
                try:
                    parsed_date = email.utils.parsedate_to_datetime(details['date'])
                    days_waiting = (datetime.now(pytz.UTC) - parsed_date).days
                except:
                    days_waiting = 0
                
                unreplied_emails.append({
                    'subject': details['subject'],
                    'from': details.get('from', 'Unknown Sender'),
                    'date': details['date'],
                    'days_waiting': days_waiting
                })
        
        return unreplied_emails
    
    def check_if_replied(self, thread_id):
        """Check if the user has replied to this thread"""
        thread = self.service.users().threads().get(userId='me', id=thread_id).execute()
        messages = thread['messages']
        
        if len(messages) <= 1:
            # Only one message in thread, so no reply
            return False
        
        # Get user's email
        profile = self.service.users().getProfile(userId='me').execute()
        user_email = profile['emailAddress']
        
        # Check if any messages after the first one are from the user
        for i in range(1, len(messages)):
            msg = messages[i]
            headers = msg['payload']['headers']
            from_header = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
            
            if user_email.lower() in from_header.lower():
                return True
                
        return False

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
                    try:
                        parsed_date = email.utils.parsedate_to_datetime(details['date'])
                        days_waiting = (datetime.now(pytz.UTC) - parsed_date).days
                    except:
                        days_waiting = 0  # Default if date parsing fails
                    
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
        # Get all unreplied received emails
        unreplied_received = self.check_unreplied_received_emails()
        
        # Sort by days waiting
        explicit_follow_ups.sort(key=lambda x: x.get('days_waiting', 0), reverse=True)
        unanswered_emails.sort(key=lambda x: x.get('days_waiting', 0), reverse=True)
        unreplied_received.sort(key=lambda x: x.get('days_waiting', 0), reverse=True)
        
        return {
            'explicit_follow_ups': explicit_follow_ups,
            'unanswered_emails': unanswered_emails,
            'unreplied_received': unreplied_received
        } 