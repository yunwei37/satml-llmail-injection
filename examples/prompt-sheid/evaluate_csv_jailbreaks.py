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
            reader = csv.DictReader(f)
            return list(reader)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return None

def evaluate_jailbreak_prompts(csv_data, api_key):
    """
    Evaluate all jailbreak prompts in the given CSV data.
    
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
        "flagged": 0, 
        "classifications": Counter(),
        "errors": Counter()
    }
    
    # Count total valid prompts
    valid_prompts = [row for row in csv_data if 'prompt' in row and row['prompt']]
    stats["total"] = len(valid_prompts)
    
    print(f"Found {len(valid_prompts)} jailbreak prompts to evaluate")
    
    # Process each prompt
    for i, row in enumerate(tqdm(valid_prompts, desc="Evaluating prompts")):
        prompt = row['prompt']
        source = row.get('source', 'unknown')
        platform = row.get('platform', 'unknown')
        
        # Check if prompt is too long (API limit is 10,000 chars)
        if len(prompt) > 10000:
            error_type = "prompt_too_long"
            stats["errors"][error_type] += 1
            print(f"Skipping prompt from {source} on {platform}: Prompt too long ({len(prompt)} chars)")
            
            # Store the result with error information
            results.append({
                "platform": platform,
                "source": source,
                "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                "classification": "error",
                "jailbreak": row.get('jailbreak', 'unknown'),
                "error": error_type,
                "prompt_length": len(prompt)
            })
            continue
        
        # Call the API with retry logic
        max_retries = 3
        retry_delay = 2  # seconds
        response = None
        
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
                "platform": platform,
                "source": source,
                "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                "classification": "error",
                "jailbreak": row.get('jailbreak', 'unknown'),
                "error": error_type
            })
            continue
        
        # Extract classification information
        classification = "unknown"
        
        # Check if attackDetected is present in the response
        if "userPromptAnalysis" in response and "attackDetected" in response["userPromptAnalysis"]:
            if response["userPromptAnalysis"]["attackDetected"]:
                classification = "flagged"
                stats["flagged"] += 1
            else:
                classification = "safe"
        # Fallback to the previous method if the new field isn't available
        elif "shieldedPrompt" in response:
            classification = "flagged"
            stats["flagged"] += 1
        else:
            classification = "safe"
        
        stats["classifications"][classification] += 1
        
        # Store the result
        results.append({
            "platform": platform,
            "source": source,
            "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
            "classification": classification,
            "jailbreak": row.get('jailbreak', 'unknown'),
            "response": response
        })
        
        # Print current success rate every 5 prompts or at the end
        processed_count = i + 1
        if processed_count % 5 == 0 or processed_count == len(valid_prompts):
            flagged_count = stats["flagged"]
            error_count = sum(stats["errors"].values())
            valid_processed = processed_count - error_count
            
            if valid_processed > 0:
                flagged_rate = (flagged_count / valid_processed) * 100
                safe_count = valid_processed - flagged_count
                safe_rate = (safe_count / valid_processed) * 100
                
                print(f"\nProgress update ({processed_count}/{len(valid_prompts)}):")
                print(f"  Flagged: {flagged_count} ({flagged_rate:.2f}%)")
                print(f"  Safe: {safe_count} ({safe_rate:.2f}%)")
                print(f"  Errors: {error_count} ({error_count/processed_count*100:.2f}%)")
                if error_count > 0:
                    print(f"  Error types: {dict(stats['errors'])}")
    
    return results, stats

def main():
    # Load environment variables
    load_dotenv()
    api_key = os.getenv("AZURE_CONTENT_SAFETY_KEY")
    
    if not api_key:
        print("Error: API key not found. Please set AZURE_CONTENT_SAFETY_KEY in your .env file.")
        sys.exit(1)
    
    # Default CSV file path
    csv_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                           "data", "jailbreak_human_set2", "jailbreak_prompts_2023_12_25.csv")
    
    # Check if file exists
    if not os.path.isfile(csv_file):
        print(f"Error: CSV file not found at {csv_file}")
        sys.exit(1)
    
    # Load CSV data
    csv_data = load_csv_file(csv_file)
    if not csv_data:
        print("Error: Failed to load CSV data")
        sys.exit(1)
    
    # Evaluate the prompts
    results, stats = evaluate_jailbreak_prompts(csv_data, api_key)
    
    # Calculate valid evaluations (excluding errors)
    error_count = sum(stats["errors"].values())
    valid_count = stats["total"] - error_count
    
    # Print statistics
    print("\n=== Final Evaluation Results ===")
    print(f"Total prompts: {stats['total']}")
    print(f"Valid evaluations: {valid_count} ({valid_count/stats['total']*100:.2f}%)")
    print(f"Errors: {error_count} ({error_count/stats['total']*100:.2f}%)")
    
    if valid_count > 0:
        print(f"Prompts flagged: {stats['flagged']} ({stats['flagged']/valid_count*100:.2f}% of valid)")
        print(f"Prompts considered safe: {stats['classifications']['safe']} ({stats['classifications']['safe']/valid_count*100:.2f}% of valid)")
    
    if error_count > 0:
        print("\nError breakdown:")
        for error_type, count in stats["errors"].items():
            print(f"  {error_type}: {count} ({count/error_count*100:.2f}% of errors)")
    
    # Save detailed results to a file
    output_file = "csv_jailbreak_evaluation_results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nDetailed results saved to {output_file}")

if __name__ == "__main__":
    main() 