from datetime import datetime, timedelta
import requests
import pytz

class OutlookFollowUpSystem:
    def __init__(self, access_token):
        self.access_token = access_token
        self.headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

    def _make_request(self, url, params=None):
        """Helper method to make requests with error handling"""
        try:
            response = requests.get(url, headers=self.headers, params=params)
            
            # Handle 401 (unauthorized) - token might be expired
            if response.status_code == 401:
                raise Exception("Authentication token expired or invalid")
                
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error making request to {url}: {str(e)}")
            return None

    def get_sent_emails(self, days_ago=30):
        """Get sent emails from the last 30 days"""
        try:
            date_filter = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%dT%H:%M:%SZ')
            
            url = "https://graph.microsoft.com/v1.0/me/mailFolders/SentItems/messages"
            params = {
                '$filter': f"sentDateTime ge {date_filter}",
                '$select': 'id,subject,sentDateTime,toRecipients,conversationId',
                '$orderby': 'sentDateTime desc',
                '$top': 50
            }
            
            result = self._make_request(url, params)
            return result.get('value', []) if result else []
            
        except Exception as e:
            print(f"Error getting sent emails: {str(e)}")
            return []

    def check_for_response(self, conversation_id):
        """Check if there's been a response in the conversation"""
        url = f"https://graph.microsoft.com/v1.0/me/messages"
        params = {
            '$filter': f"conversationId eq '{conversation_id}'",
            '$orderby': 'receivedDateTime desc',
            '$select': 'from,receivedDateTime'
        }
        
        response = requests.get(url, headers=self.headers, params=params)
        if response.status_code == 200:
            messages = response.json().get('value', [])
            if len(messages) > 1:  # More than just the sent message
                latest_message = messages[0]
                # Check if the latest message is from someone else
                return latest_message['from']['emailAddress']['address'] != self.get_user_email()
        return False

    def get_user_email(self):
        """Get the current user's email address"""
        url = "https://graph.microsoft.com/v1.0/me"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json().get('userPrincipalName', '')
        return ''

    def check_unanswered_sent_emails(self, days_ago=30):
        """Check for all sent emails that haven't received responses"""
        sent_emails = self.get_sent_emails(days_ago)
        unanswered_emails = []
        
        for email in sent_emails:
            if not self.check_for_response(email['conversationId']):
                sent_date = datetime.strptime(
                    email['sentDateTime'], 
                    '%Y-%m-%dT%H:%M:%SZ'
                ).replace(tzinfo=pytz.UTC)
                
                days_waiting = (datetime.now(pytz.UTC) - sent_date).days
                
                unanswered_emails.append({
                    'subject': email['subject'],
                    'to': '; '.join(r['emailAddress']['address'] 
                                  for r in email['toRecipients']),
                    'date': email['sentDateTime'],
                    'days_waiting': days_waiting
                })
        
        return unanswered_emails

    def get_received_emails(self, days_ago=30):
        """Get received emails from the last 30 days"""
        date_filter = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        url = "https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages"
        params = {
            '$filter': f"receivedDateTime ge {date_filter}",
            '$select': 'id,subject,receivedDateTime,from,conversationId',
            '$orderby': 'receivedDateTime desc',
            '$top': 50
        }
        
        response = requests.get(url, headers=self.headers, params=params)
        if response.status_code == 200:
            return response.json().get('value', [])
        return []
    
    def check_unreplied_received_emails(self, days_ago=30):
        """Check for received emails that haven't been replied to"""
        received_emails = self.get_received_emails(days_ago)
        unreplied_emails = []
        
        user_email = self.get_user_email()
        
        for email in received_emails:
            # Skip if promotional or automated
            subject = email['subject'].lower()
            from_address = email['from']['emailAddress']['address'].lower()
            
            if any(keyword in subject for keyword in ['newsletter', 'promotion', 'sale', 'offer']):
                continue
                
            if any(keyword in from_address for keyword in ['noreply', 'no-reply', 'donotreply', 'newsletter']):
                continue
            
            # Check if user has replied
            has_replied = self.check_if_replied(email['conversationId'], user_email)
            
            if not has_replied:
                sent_date = datetime.strptime(
                    email['receivedDateTime'], 
                    '%Y-%m-%dT%H:%M:%SZ'
                ).replace(tzinfo=pytz.UTC)
                
                days_waiting = (datetime.now(pytz.UTC) - sent_date).days
                
                unreplied_emails.append({
                    'subject': email['subject'],
                    'from': email['from']['emailAddress']['address'],
                    'date': email['receivedDateTime'],
                    'days_waiting': days_waiting
                })
        
        return unreplied_emails
    
    def check_if_replied(self, conversation_id, user_email):
        """Check if the user has replied to this conversation"""
        url = f"https://graph.microsoft.com/v1.0/me/messages"
        params = {
            '$filter': f"conversationId eq '{conversation_id}'",
            '$orderby': 'receivedDateTime asc',
            '$select': 'from,sentDateTime'
        }
        
        response = requests.get(url, headers=self.headers, params=params)
        if response.status_code == 200:
            messages = response.json().get('value', [])
            
            if len(messages) <= 1:
                return False
                
            # Check if any messages after the first are from the user
            for i in range(1, len(messages)):
                if messages[i]['from']['emailAddress']['address'].lower() == user_email.lower():
                    return True
                    
            return False
        return False
    
    def generate_follow_up_report(self):
        """Generate a comprehensive report of emails needing follow-up"""
        unanswered_emails = self.check_unanswered_sent_emails()
        unreplied_received = self.check_unreplied_received_emails()
        
        # Sort by days waiting
        unanswered_emails.sort(key=lambda x: x['days_waiting'], reverse=True)
        unreplied_received.sort(key=lambda x: x['days_waiting'], reverse=True)
        
        return {
            'explicit_follow_ups': [],  # Not implemented for Outlook
            'unanswered_emails': unanswered_emails,
            'unreplied_received': unreplied_received
        } 