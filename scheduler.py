"""
scheduler.py — Runs main.py every day at 8:00 AM automatically.
"""

import schedule
import time
from main import main

schedule.every().day.at("08:00").do(main)

print("Scheduler running — daily scan at 08:00 AM")
print("Press Ctrl+C to stop.\n")

# Run once immediately on start
main()

while True:
    schedule.run_pending()
    time.sleep(60)
