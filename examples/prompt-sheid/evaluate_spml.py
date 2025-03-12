#!/usr/bin/env python3
import os
import sys
import csv
import json
import time
from tqdm import tqdm
from collections import Counter
from prompt_shield import shield_prompt
from dotenv import load_dotenv
import requests

def load_csv_file(file_path):
    """Load a CSV file and return its contents as a list of dictionaries."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # Read the first few lines to debug
            first_lines = []
            for i, line in enumerate(f):
                if i < 5:  # Read first 5 lines
                    first_lines.append(line.strip())
                else:
                    break
            
            # Reset file pointer to beginning
            f.seek(0)
            
            # Try to read as CSV
            reader = csv.DictReader(f)
            data = list(reader)
            
            # Debug information
            if not data:
                print(f"CSV file exists but contains no data rows")
                print(f"First few lines of the file:")
                for line in first_lines:
                    print(f"  {line}")
                return []
            
            # Check if 'Prompt' column exists
            if 'Prompt' not in data[0]:
                print(f"CSV file does not contain a 'Prompt' column")
                print(f"Available columns: {list(data[0].keys())}")
                
                # Try to find a similar column
                possible_prompt_columns = [col for col in data[0].keys() if 'prompt' in col.lower()]
                if possible_prompt_columns:
                    print(f"Possible prompt columns found: {possible_prompt_columns}")
                    
                    # Use the first matching column
                    prompt_col = possible_prompt_columns[0]
                    print(f"Using '{prompt_col}' as the prompt column")
                    
                    # Rename the column in each row
                    for row in data:
                        row['Prompt'] = row[prompt_col]
                
            return data
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        print(f"Current working directory: {os.getcwd()}")
        print(f"Checking if file exists with absolute path: {os.path.abspath(file_path)}")
        return None
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return None

def evaluate_spml_prompts(csv_data, api_key):
    """
    Evaluate all prompts from the SPML dataset.
    
    Args:
        csv_data (list): List of dictionaries containing CSV data
        api_key (str): Azure Content Safety API key
    
    Returns:
        tuple: (results, stats) where results is a list of evaluation results and
               stats is a dictionary of statistics
    """
    results = []
    stats = {
        "total": 0,
        "actual_attacks": 0,
        "flagged": 0,
        "true_positives": 0,
        "false_positives": 0,
        "true_negatives": 0,
        "false_negatives": 0,
        "errors": Counter()
    }
    
    # Count total valid prompts
    valid_prompts = [row for row in csv_data if 'Prompt' in row and row['Prompt']]
    stats["total"] = len(valid_prompts)
    
    print(f"Found {len(valid_prompts)} SPML prompts to evaluate")
    
    # Process each prompt
    for i, row in enumerate(tqdm(valid_prompts, desc="Evaluating prompts")):
        prompt = row['Prompt']
        
        # Determine if this is an actual attack based on the "Prompt injection" field
        is_attack = False
        if 'Prompt injection' in row and row['Prompt injection'] == '1':
            is_attack = True
            stats["actual_attacks"] += 1
        
        # Check if prompt is too long (API limit is 10,000 chars)
        if len(prompt) > 10000:
            error_type = "prompt_too_long"
            stats["errors"][error_type] += 1
            print(f"Skipping prompt: Prompt too long ({len(prompt)} chars)")
            
            # Store the result with error information
            results.append({
                "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                "is_attack": is_attack,
                "classification": "error",
                "error": error_type,
                "prompt_length": len(prompt)
            })
            continue
        
        # Call the API with retry logic
        max_retries = 3
        retry_delay = 2  # seconds
        response = None
        error_type = None
        
        for retry in range(max_retries):
            try:
                response = shield_prompt(api_key, user_prompt=prompt)
                break  # Success, exit retry loop
            except requests.exceptions.ConnectionError as e:
                error_type = "connection_error"
                if retry < max_retries - 1:
                    print(f"Connection error, retrying in {retry_delay} seconds... ({retry+1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    print(f"Failed to evaluate prompt after {max_retries} retries: {str(e)[:100]}...")
                    stats["errors"][error_type] += 1
            except Exception as e:
                error_type = "api_error"
                print(f"API error: {str(e)[:100]}...")
                stats["errors"][error_type] += 1
                break  # Don't retry for other types of errors
        
        if not response:
            # Store the result with error information
            results.append({
                "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                "is_attack": is_attack,
                "classification": "error",
                "error": error_type
            })
            continue
        
        # Extract classification information
        api_flagged = False
        
        # Check if attackDetected is present in the response
        if "userPromptAnalysis" in response and "attackDetected" in response["userPromptAnalysis"]:
            if response["userPromptAnalysis"]["attackDetected"]:
                api_flagged = True
                stats["flagged"] += 1
            else:
                api_flagged = False
        # Fallback to the previous method if the new field isn't available
        elif "shieldedPrompt" in response:
            api_flagged = True
            stats["flagged"] += 1
        else:
            api_flagged = False
        
        # Update confusion matrix stats
        if is_attack and api_flagged:
            stats["true_positives"] += 1
            classification = "true_positive"
        elif not is_attack and api_flagged:
            stats["false_positives"] += 1
            classification = "false_positive"
        elif is_attack and not api_flagged:
            stats["false_negatives"] += 1
            classification = "false_negative"
        else:  # not is_attack and not api_flagged
            stats["true_negatives"] += 1
            classification = "true_negative"
        
        # Store the result
        results.append({
            "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
            "is_attack": is_attack,
            "api_flagged": api_flagged,
            "classification": classification,
            "response": response
        })
        
        # Print current stats every 10 prompts or at the end
        processed_count = i + 1
        if processed_count % 10 == 0 or processed_count == len(valid_prompts):
            error_count = sum(stats["errors"].values())
            valid_processed = processed_count - error_count
            
            if valid_processed > 0:
                tp = stats["true_positives"]
                fp = stats["false_positives"]
                tn = stats["true_negatives"]
                fn = stats["false_negatives"]
                
                precision = tp / (tp + fp) if (tp + fp) > 0 else 0
                recall = tp / (tp + fn) if (tp + fn) > 0 else 0
                accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0
                f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
                
                print(f"\nProgress update ({processed_count}/{len(valid_prompts)}):")
                print(f"  Accuracy: {accuracy:.4f}")
                print(f"  Precision: {precision:.4f}")
                print(f"  Recall: {recall:.4f}")
                print(f"  F1 Score: {f1:.4f}")
                print(f"  Confusion Matrix: [TP: {tp}, FP: {fp}, TN: {tn}, FN: {fn}]")
                if error_count > 0:
                    print(f"  Errors: {error_count} ({error_count/processed_count*100:.2f}%)")
    
    return results, stats

def main():
    # Load environment variables
    load_dotenv()
    api_key = os.getenv("AZURE_CONTENT_SAFETY_KEY")
    
    if not api_key:
        print("Error: API key not found. Please set AZURE_CONTENT_SAFETY_KEY in your .env file.")
        sys.exit(1)
    
    # Try multiple possible paths for the CSV file
    possible_paths = [
        "data/SPML/spml_prompt_injection.csv",
        "/home/yunwei37/ebpf/satml-llmail-injection/data/SPML/spml_prompt_injection.csv",
        "../data/SPML/spml_prompt_injection.csv",
        "../../data/SPML/spml_prompt_injection.csv"
    ]
    
    csv_file = None
    csv_data = None
    
    for path in possible_paths:
        print(f"Trying path: {path}")
        if os.path.isfile(path):
            csv_file = path
            csv_data = load_csv_file(path)
            if csv_data:
                print(f"Successfully loaded CSV from: {path}")
                break
    
    if not csv_file:
        print("Error: Could not find the CSV file in any of the expected locations")
        sys.exit(1)
    
    if not csv_data:
        print("Error: Failed to load CSV data")
        sys.exit(1)
    
    # Check for the 'Prompt injection' column
    if csv_data and 'Prompt injection' not in csv_data[0]:
        print(f"CSV file does not contain a 'Prompt injection' column")
        print(f"Available columns: {list(csv_data[0].keys())}")
        
        # Try to find a similar column
        possible_injection_columns = [col for col in csv_data[0].keys() 
                                     if 'injection' in col.lower() or 'attack' in col.lower()]
        if possible_injection_columns:
            print(f"Possible injection columns found: {possible_injection_columns}")
            
            # Use the first matching column
            injection_col = possible_injection_columns[0]
            print(f"Using '{injection_col}' as the injection column")
            
            # Rename the column in each row
            for row in csv_data:
                row['Prompt injection'] = row[injection_col]
    
    # Evaluate the prompts
    results, stats = evaluate_spml_prompts(csv_data, api_key)
    
    # Calculate valid evaluations (excluding errors)
    error_count = sum(stats["errors"].values())
    valid_count = stats["total"] - error_count
    
    # Calculate final metrics
    if valid_count > 0:
        tp = stats["true_positives"]
        fp = stats["false_positives"]
        tn = stats["true_negatives"]
        fn = stats["false_negatives"]
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        # Print final statistics
        print("\n=== Final Evaluation Results ===")
        print(f"Total prompts: {stats['total']}")
        print(f"Valid evaluations: {valid_count} ({valid_count/stats['total']*100:.2f}%)")
        print(f"Actual attacks: {stats['actual_attacks']} ({stats['actual_attacks']/valid_count*100:.2f}% of valid)")
        print(f"API flagged: {stats['flagged']} ({stats['flagged']/valid_count*100:.2f}% of valid)")
        
        print("\nPerformance Metrics:")
        print(f"  Accuracy: {accuracy:.4f}")
        print(f"  Precision: {precision:.4f}")
        print(f"  Recall: {recall:.4f}")
        print(f"  F1 Score: {f1:.4f}")
        
        print("\nConfusion Matrix:")
        print(f"  True Positives: {tp} ({tp/valid_count*100:.2f}%)")
        print(f"  False Positives: {fp} ({fp/valid_count*100:.2f}%)")
        print(f"  True Negatives: {tn} ({tn/valid_count*100:.2f}%)")
        print(f"  False Negatives: {fn} ({fn/valid_count*100:.2f}%)")
    
    if error_count > 0:
        print("\nError breakdown:")
        for error_type, count in stats["errors"].items():
            print(f"  {error_type}: {count} ({count/error_count*100:.2f}% of errors)")
    
    # Save detailed results to a file
    output_file = "spml_evaluation_results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nDetailed results saved to {output_file}")

if __name__ == "__main__":
    main() 