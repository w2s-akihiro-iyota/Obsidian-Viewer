import re
from datetime import datetime

def parse_obsidian_date(date_str):
    """
    Parses Obsidian date format like: "火曜日, 3月 4日 2025, 4:03:46 午後"
    """
    if not isinstance(date_str, str):
        return None
        
    # Remove weekday (everything before first comma) if present
    if ',' in date_str:
        clean_str = date_str.split(',', 1)[1].strip()
    else:
        clean_str = date_str.strip()
        
    # Replace Japanese AM/PM
    clean_str = clean_str.replace('午後', 'PM').replace('午前', 'AM')
    
    # Extract parts using regex
    # Expected format after cleanup: "3月 4日 2025, 4:03:46 PM"
    # Regex to handle "Month月 Day日 Year, Time AM/PM"
    match = re.search(r'(\d+)月\s*(\d+)日\s*(\d+),\s*(\d+):(\d+):(\d+)\s*(PM|AM)', clean_str)
    
    if match:
        month, day, year, hour, minute, second, ampm = match.groups()
        dt_str = f"{year}-{month}-{day} {hour}:{minute}:{second} {ampm}"
        try:
            return datetime.strptime(dt_str, "%Y-%m-%d %I:%M:%S %p")
        except ValueError:
            return None
            
    return None

test_dates = [
    "火曜日, 3月 4日 2025, 4:03:46 午後",
    "水曜日, 4月 16日 2025, 12:35:46 午後",
    "木曜日, 4月 24日 2025, 9:55:24 午前",
    "火曜日, 2月 13日 2024, 12:24:35 午後"
]

for d in test_dates:
    dt = parse_obsidian_date(d)
    print(f"Original: {d} -> Parsed: {dt}")
