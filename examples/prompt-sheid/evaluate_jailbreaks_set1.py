#!/usr/bin/env python3
import os
import sys
import yaml
import json
from tqdm import tqdm
from collections import Counter
from prompt_shield import shield_prompt
from dotenv import load_dotenv

def load_yaml_file(file_path):
    """Load a YAML file and return its contents."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return None

def evaluate_jailbreak_prompts(jailbreak_dir, api_key):
    """
    Evaluate all jailbreak prompts in the given directory.
    
    Args:
        jailbreak_dir (str): Path to the directory containing jailbreak YAML files
        api_key (str): Azure Content Safety API key
    
    Returns:
        dict: Statistics about the evaluation results
    """
    results = []
    stats = {"total": 0, "flagged": 0, "classifications": Counter()}
    
    # Get all YAML files in the directory
    yaml_files = [f for f in os.listdir(jailbreak_dir) if f.endswith('.yaml') and not f == 'README.md']
    stats["total"] = len(yaml_files)
    
    print(f"Found {len(yaml_files)} jailbreak prompts to evaluate")
    
    # Process each file
    for filename in tqdm(yaml_files, desc="Evaluating prompts"):
        file_path = os.path.join(jailbreak_dir, filename)
        yaml_data = load_yaml_file(file_path)
        
        if not yaml_data or 'prompt' not in yaml_data:
            print(f"Skipping {filename}: Invalid format or missing prompt")
            continue
        
        prompt = yaml_data['prompt']
        title = yaml_data.get('title', filename)
        
        # Call the API to shield the prompt
        response = shield_prompt(api_key, user_prompt=prompt)
        
        if not response:
            print(f"Failed to evaluate {filename}")
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
            "filename": filename,
            "title": title,
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
    
    # Default jailbreak directory path
    jailbreak_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                                "data", "human-set1", "jailbreak")
    
    # Check if directory exists
    if not os.path.isdir(jailbreak_dir):
        print(f"Error: Jailbreak directory not found at {jailbreak_dir}")
        sys.exit(1)
    
    # Evaluate the prompts
    results, stats = evaluate_jailbreak_prompts(jailbreak_dir, api_key)
    
    # Print statistics
    print("\n=== Evaluation Results ===")
    print(f"Total prompts evaluated: {stats['total']}")
    print(f"Prompts flagged: {stats['flagged']} ({stats['flagged']/stats['total']*100:.2f}%)")
    print(f"Prompts considered safe: {stats['classifications']['safe']} ({stats['classifications']['safe']/stats['total']*100:.2f}%)")
    
    # Save detailed results to a file
    output_file = "jailbreak_evaluation_results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nDetailed results saved to {output_file}")

if __name__ == "__main__":
    main() 