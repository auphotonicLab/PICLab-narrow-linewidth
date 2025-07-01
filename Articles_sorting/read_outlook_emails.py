from O365 import Account
import os
from datetime import datetime, timedelta

def authenticate_outlook():
    """
    Authenticate with Microsoft 365 using email and password.
    Returns an authenticated account object.
    """
    # Create an account object with your email
    account = Account(credentials=('your.email@example.com', 'your_password'))
    
    # Authenticate
    if account.authenticate():
        print("Authentication successful!")
        return account
    else:
        print("Authentication failed!")
        return None

def read_emails_from_folder(account, folder_name, days_back=7):
    """
    Read emails from a specific folder.
    
    Args:
        account: Authenticated O365 account object
        folder_name: Name of the folder to read from
        days_back: Number of days to look back for emails
    """
    # Get the mailbox
    mailbox = account.mailbox()
    
    # Get the folder
    folder = mailbox.get_folder(folder_name=folder_name)
    
    if folder is None:
        print(f"Folder '{folder_name}' not found!")
        return
    
    # Calculate the date to filter from
    date_from = datetime.now() - timedelta(days=days_back)
    
    # Get messages from the folder
    messages = folder.get_messages(
        query=f"receivedDateTime ge {date_from.strftime('%Y-%m-%d')}",
        limit=50  # Limit the number of messages to retrieve
    )
    
    # Process each message
    for message in messages:
        print(f"\nSubject: {message.subject}")
        print(f"From: {message.sender}")
        print(f"Received: {message.received}")
        print(f"Body: {message.body_preview[:200]}...")  # Show first 200 characters of body

def main():
    # Authenticate
    account = authenticate_outlook()
    
    if account:
        # Specify the folder name you want to read from
        folder_name = "Inbox"  # Change this to your desired folder name
        
        # Read emails from the specified folder
        read_emails_from_folder(account, folder_name)

if __name__ == "__main__":
    main() 