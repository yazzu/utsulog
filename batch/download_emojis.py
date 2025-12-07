import csv
import os
import requests
import time

# Options
CSV_PATH = 'csv_data/youtubeemoji.csv'
OUTPUT_DIR = 'frontend/public/custom_emojis'
SLEEP_TIME = 0.1  # Be nice to the server

def download_emojis():
    # Ensure output directory exists
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Created directory: {OUTPUT_DIR}")

    # Read CSV
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        count = 0
        for row in reader:
            label = row['Emoji label']
            url = row['Src']
            
            if not label or not url:
                continue

            # Clean filename: remove ':' and create .png filename
            # User requested {Emoji label}.png, but usually we strip colons for files.
            # If the user really wants colons, we can remove the .strip(':') part.
            # Assuming standard behavior of stripping colons for filenames.
            filename = label.strip(':') + '.png'
            filepath = os.path.join(OUTPUT_DIR, filename)

            print(f"Downloading {label} -> {filepath} ...")
            
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                
                with open(filepath, 'wb') as out_file:
                    out_file.write(response.content)
                
                count += 1
                time.sleep(SLEEP_TIME)
                
            except Exception as e:
                print(f"Failed to download {label}: {e}")

    print(f"Done. Downloaded {count} emojis to {OUTPUT_DIR}")

if __name__ == "__main__":
    download_emojis()
