#!/usr/bin/env python3
import os
import yaml
import csv
import glob

def extract_jailbreak_data():
    # Path to the jailbreak files
    path = '/home/yunwei37/ebpf/satml-llmail-injection/data/human-set1/jailbreak'
    
    # List to store all extracted data
    data = []
    
    # Get all YAML files in the directory
    yaml_files = glob.glob(os.path.join(path, '*.yaml'))
    
    # Process each file
    for file_path in yaml_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                # Parse YAML content
                content = yaml.safe_load(file)
                
                # Extract filename without extension
                filename = os.path.basename(file_path).replace('.yaml', '')
                
                # Extract relevant information
                entry = {
                    'filename': filename,
                    'title': content.get('title', ''),
                    'prompt': content.get('prompt', ''),
                    'url': content.get('url', '')
                }
                
                data.append(entry)
                print(f"Processed: {filename}")
                
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
    
    return data

def write_to_csv(data, output_file='jailbreak_prompts.csv'):
    # Define CSV headers
    headers = ['filename', 'title', 'prompt', 'url']
    
    # Write data to CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)
    
    print(f"CSV file created: {output_file}")

if __name__ == "__main__":
    # Extract data from YAML files
    jailbreak_data = extract_jailbreak_data()
    
    # Write data to CSV
    write_to_csv(jailbreak_data)
    
    print(f"Total jailbreak prompts extracted: {len(jailbreak_data)}") 