import os
import json
import logging
import emoji

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Input and Output Directories (Container Paths)
# Mapped from /mnt/f/Dev/utsulog/chat_logs/chat_logs_processed -> /app/chat_logs/chat_logs_processed
INPUT_DIR = '/app/chat_logs/chat_logs_processed'
# Mapped from /mnt/f/Dev/utsulog/chat_logs/chat_logs -> /app/chat_logs/chat_logs
OUTPUT_DIR = '/app/chat_logs/chat_logs'

def migrate_file(filename):
    input_path = os.path.join(INPUT_DIR, filename)
    output_path = os.path.join(OUTPUT_DIR, filename)

    logger.info(f"Processing {filename}...")

    try:
        with open(input_path, 'r', encoding='utf-8') as infile, \
             open(output_path, 'w', encoding='utf-8') as outfile:
            
            for line_num, line in enumerate(infile, 1):
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                    if 'message' in data:
                        original_message = data['message']
                        # Convert aliases like :frog: to unicode 🐸
                        # language='alias' supports standard emoji shortcodes
                        converted_message = emoji.emojize(original_message, language='alias')
                        
                        # Check if any change happened (optional logging)
                        # if original_message != converted_message:
                        #     logger.debug(f"Line {line_num}: '{original_message}' -> '{converted_message}'")
                        
                        data['message'] = converted_message
                    
                    # Write back as ndjson
                    json.dump(data, outfile, ensure_ascii=False)
                    outfile.write('\n')

                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding JSON in {filename} at line {line_num}: {e}")
                except Exception as e:
                    logger.error(f"Error processing line {line_num} in {filename}: {e}")

        logger.info(f"Finished processing {filename}")

    except FileNotFoundError:
        logger.error(f"File not found: {input_path}")
    except Exception as e:
        logger.error(f"Failed to process file {filename}: {e}")

def main():
    if not os.path.exists(INPUT_DIR):
        logger.error(f"Input directory not found: {INPUT_DIR}")
        return

    if not os.path.exists(OUTPUT_DIR):
        logger.info(f"Creating output directory: {OUTPUT_DIR}")
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    files = [f for f in os.listdir(INPUT_DIR) if f.endswith('.json')]
    logger.info(f"Found {len(files)} JSON files to process.")

    for filename in files:
        migrate_file(filename)

    logger.info("Migration completed.")

if __name__ == "__main__":
    main()
