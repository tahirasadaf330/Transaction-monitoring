import pandas as pd 
import schedule
import time
import mysql.connector
import requests
from datetime import datetime, timedelta
from configuration import DB_CONFIG

# ✅ Use the same webhook and Slack user from topups monitor
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/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"
SLACK_MENTION = "<@C08L0NRFWDN>"  # same user/channel mention

conn = None
previous_subscriber_alerts = []

def get_db_connection():
    global conn
    try:
        if conn is None or not conn.is_connected():
            conn = mysql.connector.connect(**DB_CONFIG)
            conn.ping(reconnect=True, attempts=3, delay=5)
            print("✅ Connected to database.")
    except mysql.connector.Error as err:
        print(f"❌ DB connection error: {err}")
    return conn

def fetch_hourly_subscriber_data():
    try:
        conn = get_db_connection()
        if conn is None or not conn.is_connected():
            return pd.DataFrame()

        with conn.cursor(dictionary=True) as cursor:
            query = """
            SELECT 
                DATE(created_at) AS subscription_date,
                HOUR(created_at) AS subscription_hour,
                COUNT(msisdn) AS total_subs
            FROM subscribers
            WHERE created_at BETWEEN %s AND %s
            GROUP BY subscription_date, subscription_hour
            ORDER BY subscription_date DESC, subscription_hour DESC;
            """
            start_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d 00:00:00')
            end_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(query, (start_date, end_date))

            df = pd.DataFrame(cursor.fetchall())
            df['subscription_date'] = pd.to_datetime(df['subscription_date'])
            df['day_of_week'] = df['subscription_date'].dt.day_name()
            return df
    except mysql.connector.Error as err:
        print(f"❌ Query error: {err}")
        return pd.DataFrame()

def detect_subscriber_anomalies():
    global previous_subscriber_alerts

    print("\n📡 Checking subscriber registration anomalies...")

    df = fetch_hourly_subscriber_data()
    if df.empty:
        print("⚠️ No subscriber data found.")
        return

    now = datetime.now()
    today = now.date()
    anomalies_found = 0
    total_checked = 0

    today_data = df[df['subscription_date'].dt.date == today]
    if today_data.empty:
        print("ℹ️ No subscriber data for today yet.")
        return

    for _, row in today_data.iterrows():
        hour = row['subscription_hour']
        current_count = row['total_subs']
        day_of_week = row['day_of_week']

        # Same hour, same weekday, before today
        history = df[ 
            (df['subscription_hour'] == hour) & 
            (df['day_of_week'] == day_of_week) & 
            (df['subscription_date'].dt.date < today) 
        ]

        if history.empty or history['total_subs'].mean() == 0:
            continue

        total_checked += 1
        historical_avg = history['total_subs'].mean()
        change = current_count - historical_avg
        absolute_change = abs(change)

        # **Updated Condition**: Trigger alert if absolute change is greater than or equal to 15 subscribers
        if absolute_change >= 15:
            alert_type = "large anomaly"
            emoji = "🚨"
            color = "#e01e5a"  # red color for large anomalies

            alert_key = f"{today}_{hour}_{alert_type}"
            if alert_key not in previous_subscriber_alerts:
                alert = {
                    'day': day_of_week,
                    'hour': hour,
                    'current': current_count,
                    'mean': historical_avg,
                    'change': change,
                    'absolute_change': absolute_change,
                    'type': alert_type
                }
                send_subscriber_slack_alert(alert, emoji, color)
                previous_subscriber_alerts.append(alert_key)
                anomalies_found += 1
            else:
                print(f"🔁 Duplicate alert for hour {hour}:00 already sent.")

    print(f"🧾 Checked {total_checked} hour(s) from today.")
    print(f"🚨 Detected {anomalies_found} large anomaly{'ies' if anomalies_found != 1 else ''} with ≥15 subscriber change.")

def send_subscriber_slack_alert(alert, emoji, color):
    print("\n📤 Sending subscriber alert to Slack...")

    change_text = f"{'+' if alert['change'] >= 0 else ''}{alert['change']:.1f}"
    title = "Large Subscriber Anomaly Alert"

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{emoji} {title}"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*📅 Day:*\n{alert['day']}"},
                    {"type": "mrkdwn", "text": f"*🕒 Hour:*\n{alert['hour']}:00"},
                    {"type": "mrkdwn", "text": f"*👥 Current Subs:*\n{alert['current']}"},
                    {"type": "mrkdwn", "text": f"*📊 Average:*\n{alert['mean']:.1f}"},
                    {"type": "mrkdwn", "text": f"*🔁 Change:*\n{change_text}"},
                    {"type": "mrkdwn", "text": f"*⚡ Absolute Change:*\n{alert['absolute_change']}"}
                ]
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"{SLACK_MENTION} large subscriber registration anomaly detected."}
                ]
            }
        ],
        "attachments": [
            {
                "color": color,
                "text": f"{alert['type'].capitalize()} of subscriber registrations during this hour."
            }
        ]
    }

    response = requests.post(SLACK_WEBHOOK_URL, json=payload)
    if response.status_code == 200:
        print("✅ Slack alert sent successfully.")
    else:
        print(f"❌ Failed to send alert. Status: {response.status_code}, Response: {response.text}")

# === Scheduler ===
schedule.every(1).hour.do(detect_subscriber_anomalies)  # Check every 10 minutes
print("\n📊 Subscriber Monitoring Started. Checking every 1 hour...")
detect_subscriber_anomalies()

while True:
    schedule.run_pending()
    time.sleep(1)
