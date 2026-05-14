import pandas as pd
import schedule
import time
import mysql.connector
import requests
from datetime import datetime, timedelta
from configuration import DB_CONFIG

# Slack config
TEAMS_WEBHOOK_URL = "https://kingrevolution.webhook.office.com/webhookb2/c85bd28b-4dea-40d2-a38b-8139fd783683@1df4ce7a-fa8a-42ff-9802-1f1be9c52d8d/IncomingWebhook/61ee9ebe1b8b423f906ad44666d03cdd/a24d1176-99a1-4e2c-a116-37730eb3acd5/V22RH-nOPYL4c4RT8bASAlwnMmWHCmhUA9uWOdfh59Lgs1"
#SLACK_MENTION = "<C09FV443JBC>"  # Same user/channel mention

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
                send_teams_alert(alert)
                previous_hourly_alerts.append(alert_key)
                anomalies_found += 1
            else:
                print(f"🔁 Duplicate alert for {created_at} already sent.")

        total_checked += 1

    print(f"🧾 Checked {total_checked} 10-minute window(s).")
    label = "anomaly" if anomalies_found == 1 else "anomalies"
    print(f"🚨 Detected {anomalies_found} {label} with transactions >= 10 or amount >= $50.")

def send_teams_alert(alert):
    """Send alert to Microsoft Teams using MessageCard format."""
    print("\n📤 Sending Teams alert...")

    emoji = "🚨" if alert['type'] == "alert" else "⚠️"
    payload = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": "Transaction Alert",
        "themeColor": "FF6B6B",
        "sections": [
            {
                "activityTitle": f"{emoji} Transaction Alert",
                "activitySubtitle": "Anomaly Detected",
                "facts": [
                    {"name": "🕒 Time:", "value": f"{alert['time']} (Time of Anomaly)"},
                    {"name": "💰 Current Amount:", "value": f"${alert['current_amount']:.2f}"},
                    {"name": "📊 Transactions Count:", "value": f"{alert['transaction_count']}"},
                ],
            }
        ],
    }

    response = requests.post(TEAMS_WEBHOOK_URL, json=payload)

    if response.status_code == 200:
        print("✅ Teams alert sent successfully!")
    else:
        print(f"❌ Failed to send Teams alert. Status: {response.status_code}, Response: {response.text}")

# Schedule every 10 minutes
schedule.every(10).minutes.do(detect_timed_anomalies)  # Check every 10 minutes
print("\n📌 Timed Transaction Monitoring Started. Checking every 10 minutes.")

# Initial check when the script starts
detect_timed_anomalies()

while True:
    schedule.run_pending()
    time.sleep(1)
