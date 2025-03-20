import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Database Configuration
DB_CONFIG = {
    "host": "10.10.8.111",
    "user": "abubakker",
    "password": "K29m@ZU5Oh3#",  
    "database": "slickcall",
    "port": 3306
}

SMTP_CONFIG = {
    "server": "smtp.sendgrid.net",  # SMTP Server Address
    "port": 465,  # SMTP Port (SSL)
    "user": "apikey",  # SMTP Username
    "password": "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",  # SMTP Password
    "encryption": "ssl",  # Encryption method
    "sender": "Private Person <from@example.com>",  # Sender Email
    "receiver": "A Test User <to@example.com>"  # Receiver Email
}

