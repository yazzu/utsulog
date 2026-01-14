import os
import json
import glob

def main():
    base_dir = os.getenv('LOCAL_CHAT_LOGS_DIR')
    if not base_dir:
        print("Error: LOCAL_CHAT_LOGS_DIR environment variable is not set.")
        return

    input_dir = os.path.join(base_dir, "chat_logs")
    output_dir = os.path.join(base_dir, "chat_logs_processed")

    if not os.path.exists(input_dir):
        print(f"Error: Input directory '{input_dir}' does not exist.")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    json_files = glob.glob(os.path.join(input_dir, "*.json"))
    
    if not json_files:
        print(f"No JSON files found in {input_dir}")
        return

    print(f"Found {len(json_files)} files in {input_dir}")

    for file_path in json_files:
        filename = os.path.basename(file_path)
        output_path = os.path.join(output_dir, filename)
        
        print(f"Processing: {filename}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f_in, \
                 open(output_path, 'w', encoding='utf-8') as f_out:
                
                for line in f_in:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        if isinstance(data, dict):
                            data['type'] = 'chat'
                            json.dump(data, f_out, ensure_ascii=False)
                            f_out.write('\n')
                        else:
                            print(f"Warning: Line in {filename} is not a JSON object. Skipping.")
                    except json.JSONDecodeError as e:
                        print(f"Warning: JSON decode error in {filename}: {e}. Skipping line.")
                        
        except Exception as e:
            print(f"Error processing {filename}: {e}")

    print("Batch processing completed.")

if __name__ == "__main__":
    main()
