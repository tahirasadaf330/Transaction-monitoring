import pandas as pd
import schedule
import time
import smtplib
import mysql.connector
from sklearn.ensemble import IsolationForest
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from configuration import DB_CONFIG, SMTP_CONFIG
from datetime import datetime, timedelta

# ✅ Global variable for MySQL connection
conn = None

# ✅ Function to Establish Persistent Database Connection
def get_db_connection():
    """Ensures a persistent connection to MySQL and auto-reconnects if needed."""
    global conn
    try:
        if conn is None or not conn.is_connected():
            conn = mysql.connector.connect(**DB_CONFIG)
            conn.ping(reconnect=True, attempts=3, delay=5)  # Ensures reconnection
            print("✅ Successfully connected to the database.")
    except mysql.connector.Error as err:
        print(f"❌ Database connection failed: {err}")
    return conn

# ✅ Function to Fetch 14 Days of Transactions (Including Today)
def fetch_transaction_data():
    try:
        conn = get_db_connection()  # Ensure persistent connection
        if conn is None or not conn.is_connected():
            return pd.DataFrame()  # Return empty if connection fails
        
        with conn.cursor(dictionary=True) as cursor:
            query = """
            SELECT DATE(created_at) AS transaction_date, SUM(amount) AS total_amount
            FROM international_topups
            WHERE created_at BETWEEN %s AND %s
            AND status LIKE 'Completed'
            GROUP BY transaction_date
            ORDER BY transaction_date DESC;
            """
            
            start_date = (datetime.now() - timedelta(days=13)).strftime('%Y-%m-%d')
            end_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

            cursor.execute(query, (start_date, end_date))
            df = pd.DataFrame(cursor.fetchall())

            # ✅ Ensure 'transaction_date' is a string for consistent sorting
            df['transaction_date'] = df['transaction_date'].astype(str)

            # ✅ Ensure data is unique, sorted, and consistent
            df = df.drop_duplicates(subset=['transaction_date']).sort_values(by='transaction_date', ascending=False)

            # ✅ Check if today's transactions exist; if not, add an empty row for today
            today_date = datetime.now().strftime('%Y-%m-%d')
            if today_date not in df['transaction_date'].values:
                df = pd.concat([pd.DataFrame([{"transaction_date": today_date, "total_amount": 0}]), df])

            return df
    except mysql.connector.Error as err:
        print(f"❌ Database query failed: {err}")
        return pd.DataFrame()  # Return empty DataFrame if error

# ✅ Global variable to store previous transactions for comparison
previous_transactions = None

# ✅ Function to Compare and Display Transactions
def display_transactions():
    global previous_transactions
    df = fetch_transaction_data()

    if df.empty:
        print("⚠️ No transactions found for display.")
        return
    
    total_sum = df['total_amount'].sum()
    print("\n📊 Total Transactions in the Last 14 Days (Including Today):")

    # ✅ Prevent duplicate printing and ensure correct ordering
    if previous_transactions is not None:
        df = df.sort_values(by='transaction_date', ascending=False)  # Sort properly
        
        new_data = df[~df['transaction_date'].isin(previous_transactions['transaction_date'])]
        changed_data = df[df['transaction_date'].isin(previous_transactions['transaction_date']) & 
                          (df['total_amount'] != previous_transactions['total_amount'])]

        if new_data.empty and changed_data.empty:
            print("✅ No changes in the last 14 days' transactions.")
        else:
            if not new_data.empty:
                print("\n🆕 New Transactions Detected:")
                for _, row in new_data.iterrows():
                    print(f"📅 {row['transaction_date']} ${row['total_amount']:.2f}")

            if not changed_data.empty:
                print("\n🔄 Updated Transactions Detected:")
                for _, row in changed_data.iterrows():
                    print(f"📅 {row['transaction_date']} Updated to: ${row['total_amount']:.2f}")

    else:
        for _, row in df.iterrows():
            print(f"📅 {row['transaction_date']} ${row['total_amount']:.2f}")

    print(f"\n💰 Total Sum of Transactions in 14 Days: ${total_sum:.2f}")

    # ✅ Store the latest execution result for the next comparison
    previous_transactions = df.copy()

    # ✅ Run anomaly detection
    detect_anomalies(df)

# ✅ Function to Train ML Model & Detect Anomalies
def detect_anomalies(df):
    print("\n🔄 Running ML-based Transaction Anomaly Detection...")

    if df.empty:
        print("⚠️ No transactions found for analysis.")
        return

    df = df.dropna()  # Remove missing values
    df = df.drop_duplicates(subset=['transaction_date'])  # Ensure unique transactions

    features = df[['total_amount']]

    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(features)  # Train the model

    df['anomaly'] = model.predict(features)
    df['anomaly'] = df['anomaly'].apply(lambda x: "Anomaly" if x == -1 else "Normal")

    anomalies = df[df['anomaly'] == "Anomaly"]
    total_transactions = df['total_amount'].sum()
    anomaly_count = len(anomalies)
    anomaly_percentage = (anomaly_count / len(df)) * 100 if len(df) > 0 else 0

    print(f"\n📊 Total Transaction Amount: ${total_transactions:.2f}, Anomalies: {anomaly_count}, Anomaly Percentage: {anomaly_percentage:.2f}%")

    if anomaly_percentage >= 10:
        send_email_alert(anomalies, anomaly_percentage, total_transactions)
    else:
        print("✅ No significant anomalies detected (Below 10%). Email not sent.")

# ✅ Function to Send Email Alerts
def send_email_alert(anomalies, anomaly_percentage, total_transactions):
    try:
        print("\n🚨 Sending Anomaly Alert Email...")
        subject = f"🚨 Transaction Anomaly Alert ({anomaly_percentage:.2f}% Anomalies) 🚨"
        body = (f"The system detected {anomaly_percentage:.2f}% anomalies in transactions:\n\n"
                f"📊 Total Transaction Amount: ${total_transactions:.2f}\n\n"
                f"{anomalies.to_string(index=False)}")

        msg = MIMEMultipart()
        msg["From"] = SMTP_CONFIG["sender"]
        msg["To"] = SMTP_CONFIG["receiver"]
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_CONFIG["server"], SMTP_CONFIG["port"]) as server:
            server.starttls()
            server.login(SMTP_CONFIG["user"], SMTP_CONFIG["password"])
            server.send_message(msg)

        print("✅ Alert email sent successfully!")

    except Exception as e:
        print(f"❌ Failed to send email: {e}")

# ✅ Schedule Task to Run Every 5 Minutes
schedule.every(5).minutes.do(display_transactions)

print("\n📌 Machine Learning-Based Transaction Monitoring Started. Running every 5 minutes...")

# ✅ Display Transactions Immediately
display_transactions()

# ✅ Keep Script Running Efficiently
while True:
    schedule.run_pending()
    time.sleep(1)
