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
    "server": "sandbox.smtp.mailtrap.io",  # SMTP Server Address
    "port": 2525,  # SMTP Port (Mailtrap default)
    "user": "ec58c7879be716",  # SMTP Username
    "password": "b422665d06017c",  # SMTP Password
    "sender": "Private Person <from@example.com>",  # Sender Email
    "receiver": "A Test User <to@example.com>"  # Receiver Email
}

