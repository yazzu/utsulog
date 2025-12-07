import csv
import json
import os

# Configuration
CSV_DIR = 'csv_data'
OUTPUT_FILE = 'frontend/public/emojis.json'
CSV_FILES = ['customeemoji.csv', 'youtubeemoji.csv']

def main():
    emoji_map = {}

    for csv_file in CSV_FILES:
        csv_path = os.path.join(CSV_DIR, csv_file)
        if not os.path.exists(csv_path):
            print(f"Warning: CSV file not found: {csv_path}")
            continue

        print(f"Processing {csv_path}...")
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    label = row.get('Emoji label')
                    src = row.get('Src')
                    
                    if label and src:
                        # Normalize local URLs for development
                        if src.startswith('https://utsulog.in/'):
                            src = src.replace('https://utsulog.in/', '/')
                        
                        emoji_map[label] = src
        except Exception as e:
            print(f"Error reading {csv_path}: {e}")

    # Write to JSON
    try:
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(emoji_map, f, ensure_ascii=False, indent=2)
        print(f"Successfully generated {OUTPUT_FILE} with {len(emoji_map)} emojis.")
    except Exception as e:
        print(f"Error writing to {OUTPUT_FILE}: {e}")

if __name__ == "__main__":
    main()
