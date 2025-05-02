import pandas as pd
import schedule
import time
import mysql.connector
import requests
from datetime import datetime, timedelta
from configuration import DB_CONFIG

# Slack config
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/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"
SLACK_MENTION = "<@C08L0NRFWDN>"  # Same user/channel mention

conn = None
previous_hourly_alerts = []

def get_db_connection():
    global conn
    try:
        if conn is None or not conn.is_connected():
            conn = mysql.connector.connect(**DB_CONFIG)
            conn.ping(reconnect=True, attempts=3, delay=5)
            print("✅ Successfully connected to the database.")
    except mysql.connector.Error as err:
        print(f"❌ Database connection failed: {err}")
    return conn

def fetch_timed_transaction_data():
    try:
        conn = get_db_connection()
        if conn is None or not conn.is_connected():
            return pd.DataFrame()

        with conn.cursor(dictionary=True) as cursor:
            query = """
            SELECT 
                created_at,
                SUM(amount) AS total_amount,
                COUNT(*) AS transaction_count
            FROM international_topups
            WHERE created_at BETWEEN %s AND %s
              AND status = 'Completed'
            GROUP BY FLOOR(UNIX_TIMESTAMP(created_at) / 600)  -- 10-minute intervals
            ORDER BY created_at DESC;
            """

            # Fetch the data from the last 14 days
            start_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d 00:00:00')
            end_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            cursor.execute(query, (start_date, end_date))
            df = pd.DataFrame(cursor.fetchall())

            df['created_at'] = pd.to_datetime(df['created_at'])
            return df
    except mysql.connector.Error as err:
        print(f"❌ Database query failed: {err}")
        return pd.DataFrame()

def detect_timed_anomalies():
    global previous_hourly_alerts

    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Get the current time
    print(f"\n🔄 Checking for anomalies at {current_time}...")  # Log the exact time the script runs

    df = fetch_timed_transaction_data()
    if df.empty:
        print("⚠️ No transaction data found.")
        return

    anomalies_found = 0
    total_checked = 0

    # Get today's date and last week's date
    today = datetime.now().date()
    last_week = today - timedelta(weeks=1)

    # Filter current week's data
    current_week_data = df[df['created_at'].dt.date == today]

    # Iterate over the current week's data and compare with the criteria
    for _, row in current_week_data.iterrows():
        created_at = row['created_at']
        current_amount = row['total_amount']
        current_count = row['transaction_count']

        # Check if the transaction count >= 10 or total amount >= $50
        if current_count >= 10 or current_amount >= 50:
            alert_key = f"{created_at}_{current_amount}_{current_count}"

            # Check if an alert for this window has already been sent
            if alert_key not in previous_hourly_alerts:
                alert = {
                    'time': created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'current_amount': current_amount,
                    'transaction_count': current_count,
                    'type': "alert",  # New alert type
                }
                send_slack_alert(alert)
                previous_hourly_alerts.append(alert_key)
                anomalies_found += 1
            else:
                print(f"🔁 Duplicate alert for {created_at} already sent.")

        total_checked += 1

    print(f"🧾 Checked {total_checked} 10-minute window(s).")
    print(f"🚨 Detected {anomalies_found} anomaly{'ies' if anomalies_found != 1 else ''} with transactions >= 10 or amount >= $50.")

def send_slack_alert(alert):
    print("\n📤 Sending Slack alert...")

    emoji = "🚨" if alert['type'] == "alert" else "⚠️"
    change_text = f"${alert['current_amount']:.2f}"

    payload = {
        "text": f"{SLACK_MENTION} timed transaction anomaly detected.",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{emoji} Transaction Alert"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*🕒 Time:*\n{alert['time']} (Time of Anomaly)"},
                    {"type": "mrkdwn", "text": f"*💰 Current Amount:*\n${alert['current_amount']:.2f}"},
                    {"type": "mrkdwn", "text": f"*📊 Transactions Count:*\n{alert['transaction_count']}"}
                ]
            }
        ]
    }

    response = requests.post(SLACK_WEBHOOK_URL, json=payload)

    if response.status_code == 200:
        print("✅ Slack alert sent successfully!")
    else:
        print(f"❌ Failed to send Slack alert. Status: {response.status_code}, Response: {response.text}")

# Schedule every 10 minutes

# Initial check when the script starts
detect_timed_anomalies()
