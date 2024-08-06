import sqlite3
import os
import time
import requests
import subprocess
import threading
import schedule
import logging

# Configuration
_db_address = '/etc/x-ui/x-ui.db'
_max_allowed_connections = 1
_check_cycle = 5  # seconds
_telegrambot_token = ''
_telegram_chat_id = ''  # you can get this in @cid_bot bot.
_sv_addr = 'TEST SV'

# Logging setup
logging.basicConfig(level=logging.INFO)

def get_users():
    """Fetch active users from the database."""
    users_list = []
    try:
        with sqlite3.connect(_db_address) as conn:
            cursor = conn.execute("SELECT id, remark, port FROM inbounds WHERE enable = 1")
            for c in cursor:
                users_list.append({'id': c[0], 'name': c[1], 'port': c[2]})
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
    return users_list

def disable_account(user_id):
    """Disable a user account based on user ID."""
    try:
        with sqlite3.connect(_db_address) as conn:
            conn.execute(f"UPDATE inbounds SET enable = 0 WHERE id = {user_id}")
            conn.commit()
        subprocess.run(["x-ui", "restart"], check=True)
        time.sleep(3)
    except (sqlite3.Error, subprocess.CalledProcessError) as e:
        logging.error(f"Error disabling account: {e}")

def get_connections(user_port):
    """Get unique connections to a specific port."""
    try:
        netstate_data = subprocess.run(
            ["netstat", "-np"], capture_output=True, text=True, check=True
        ).stdout
        netstate_data = subprocess.run(
            ["grep", f":{user_port}"], input=netstate_data, capture_output=True, text=True
        ).stdout
        connections = subprocess.run(
            ["awk", '{if($3!=0) print $5;}'], input=netstate_data, capture_output=True, text=True
        ).stdout
        connections = subprocess.run(
            ["cut", "-d:", "-f1"], input=connections, capture_output=True, text=True
        ).stdout
        unique_connections = set(connections.splitlines())
        return len(unique_connections)
    except subprocess.CalledProcessError as e:
        logging.error(f"Error getting connections: {e}")
        return 0

def check_new_users():
    """Check for new users and initialize checks if needed."""
    try:
        with sqlite3.connect(_db_address) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM inbounds WHERE enable = 1")
            new_counts = cursor.fetchone()[0]
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
        return

    if new_counts > 0:
        fire_up()

def fire_up():
    """Start checking users."""
    users_list = get_users()
    for user in users_list:
        checker = AccessChecker(user)
        checker.start()

class AccessChecker(threading.Thread):
    def __init__(self, user):
        super().__init__()
        self.user = user

    def run(self):
        """Check the number of connections and take action if necessary."""
        time.sleep(5)  # Wait to allow connections to establish
        logging.info(f"Checking {self.user['name']}")
        user_id = self.user['id']
        user_port = self.user['port']
        
        connection_count = get_connections(user_port)
        if connection_count > _max_allowed_connections:
            logging.info(f"Port {user_port} - Connections: {connection_count} (Limit: {_max_allowed_connections})")
            requests.get(
                f'https://api.telegram.org/bot{_telegrambot_token}/sendMessage?chat_id={_telegram_chat_id}&text={self.user["name"]}%20locked%20{_sv_addr}'
            )
            disable_account(user_id)
            logging.info(f"Inbound with port {user_port} blocked")

# Schedule and run
schedule.every(_check_cycle).seconds.do(check_new_users)

while True:
    schedule.run_pending()
    time.sleep(1)
