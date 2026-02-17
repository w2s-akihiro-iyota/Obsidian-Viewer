
from datetime import datetime, timezone, timedelta

def test_jst_timestamp():
    JST = timezone(timedelta(hours=9))
    timestamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"Current JST Timestamp: {timestamp}")
    
    # Comparison check (optional, but good for logs)
    # The system time provided in metadata is 2026-02-17 10:28:49+09:00
    # So we expect something around 2026-02-17 10:xx:xx
    if timestamp.startswith("2026-02-17 10:"):
        print("Success: Timestamp matches expected JST hour/date.")
    else:
        print("Warning: Timestamp does not match expected metadata time. Please check environment timezone.")

if __name__ == "__main__":
    test_jst_timestamp()
