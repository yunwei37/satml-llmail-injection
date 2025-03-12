#!/usr/bin/env python3
import os
import sys
import yaml
import json
import time
from tqdm import tqdm
from collections import Counter
from prompt_shield import shield_prompt
from dotenv import load_dotenv
import requests

def load_yaml_rule(file_path):
    """Load a YAML rule file and return its contents."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return None

def get_rule_files(rules_dir):
    """Get all YAML rule files from the specified directory."""
    rule_files = []
    for root, _, files in os.walk(rules_dir):
        for file in files:
            if file.endswith('.yaml'):
                rule_files.append(os.path.join(root, file))
    return rule_files

def evaluate_rule_prompts(rule_files, api_key):
    """
    Evaluate all prompts from rule files.
    
    Args:
        rule_files (list): List of paths to rule files
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
        "errors": Counter(),
        "by_type": {},
        "by_severity": {}
    }
    
    print(f"Found {len(rule_files)} rule files to evaluate")
    
    # Process each rule file
    for file_path in tqdm(rule_files, desc="Evaluating rules"):
        rule_data = load_yaml_rule(file_path)
        
        if not rule_data or 'prompt' not in rule_data:
            print(f"Skipping {file_path}: Invalid format or missing prompt")
            continue
        
        prompt = rule_data['prompt']
        rule_name = rule_data.get('name', os.path.basename(file_path))
        rule_type = rule_data.get('type', 'unknown')
        severity = rule_data.get('severity', 'unknown')
        
        # Initialize counters for rule type and severity if not already present
        if rule_type not in stats["by_type"]:
            stats["by_type"][rule_type] = {"total": 0, "flagged": 0}
        if severity not in stats["by_severity"]:
            stats["by_severity"][severity] = {"total": 0, "flagged": 0}
        
        stats["total"] += 1
        stats["by_type"][rule_type]["total"] += 1
        stats["by_severity"][severity]["total"] += 1
        
        # Check if prompt is too long (API limit is 10,000 chars)
        if len(prompt) > 10000:
            error_type = "prompt_too_long"
            stats["errors"][error_type] += 1
            print(f"Skipping rule {rule_name}: Prompt too long ({len(prompt)} chars)")
            
            # Store the result with error information
            results.append({
                "rule_name": rule_name,
                "rule_type": rule_type,
                "severity": severity,
                "file_path": file_path,
                "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
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
                    print(f"Failed to evaluate rule {rule_name} after {max_retries} retries: {str(e)[:100]}...")
                    stats["errors"][error_type] += 1
            except Exception as e:
                error_type = "api_error"
                print(f"API error for rule {rule_name}: {str(e)[:100]}...")
                stats["errors"][error_type] += 1
                break  # Don't retry for other types of errors
        
        if not response:
            # Store the result with error information
            results.append({
                "rule_name": rule_name,
                "rule_type": rule_type,
                "severity": severity,
                "file_path": file_path,
                "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                "classification": "error",
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
                stats["by_type"][rule_type]["flagged"] += 1
                stats["by_severity"][severity]["flagged"] += 1
            else:
                classification = "safe"
        # Fallback to the previous method if the new field isn't available
        elif "shieldedPrompt" in response:
            classification = "flagged"
            stats["flagged"] += 1
            stats["by_type"][rule_type]["flagged"] += 1
            stats["by_severity"][severity]["flagged"] += 1
        else:
            classification = "safe"
        
        stats["classifications"][classification] += 1
        
        # Store the result
        results.append({
            "rule_name": rule_name,
            "rule_type": rule_type,
            "severity": severity,
            "file_path": file_path,
            "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
            "classification": classification,
            "response": response
        })
    
    return results, stats

def main():
    # Load environment variables
    load_dotenv()
    api_key = os.getenv("AZURE_CONTENT_SAFETY_KEY")
    
    if not api_key:
        print("Error: API key not found. Please set AZURE_CONTENT_SAFETY_KEY in your .env file.")
        sys.exit(1)
    
    # Default rules directory path
    rules_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                            "tools", "promptmap", "rules")
    
    # Check if directory exists
    if not os.path.isdir(rules_dir):
        print(f"Error: Rules directory not found at {rules_dir}")
        sys.exit(1)
    
    # Get rule files
    rule_files = get_rule_files(rules_dir)
    if not rule_files:
        print(f"Error: No rule files found in {rules_dir}")
        sys.exit(1)
    
    # Evaluate the prompts
    results, stats = evaluate_rule_prompts(rule_files, api_key)
    
    # Calculate valid evaluations (excluding errors)
    error_count = sum(stats["errors"].values())
    valid_count = stats["total"] - error_count
    
    # Print statistics
    print("\n=== Final Evaluation Results ===")
    print(f"Total rules: {stats['total']}")
    print(f"Valid evaluations: {valid_count} ({valid_count/stats['total']*100:.2f}%)")
    print(f"Errors: {error_count} ({error_count/stats['total']*100:.2f}%)")
    
    if valid_count > 0:
        print(f"Rules flagged: {stats['flagged']} ({stats['flagged']/valid_count*100:.2f}% of valid)")
        print(f"Rules considered safe: {stats['classifications']['safe']} ({stats['classifications']['safe']/valid_count*100:.2f}% of valid)")
    
    if error_count > 0:
        print("\nError breakdown:")
        for error_type, count in stats["errors"].items():
            print(f"  {error_type}: {count} ({count/error_count*100:.2f}% of errors)")
    
    # Print statistics by rule type
    print("\nResults by rule type:")
    for rule_type, type_stats in stats["by_type"].items():
        if type_stats["total"] > 0:
            flagged_rate = (type_stats["flagged"] / type_stats["total"]) * 100
            print(f"  {rule_type}: {type_stats['flagged']}/{type_stats['total']} ({flagged_rate:.2f}%)")
    
    # Print statistics by severity
    print("\nResults by severity:")
    for severity, sev_stats in stats["by_severity"].items():
        if sev_stats["total"] > 0:
            flagged_rate = (sev_stats["flagged"] / sev_stats["total"]) * 100
            print(f"  {severity}: {sev_stats['flagged']}/{sev_stats['total']} ({flagged_rate:.2f}%)")
    
    # Save detailed results to a file
    output_file = "rules_evaluation_results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nDetailed results saved to {output_file}")

if __name__ == "__main__":
    main() 