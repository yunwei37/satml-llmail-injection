#!/usr/bin/env python3
import os
import sys
import json
import argparse
import requests
from dotenv import load_dotenv

def shield_prompt(api_key, user_prompt=None, documents=None):
    """
    Call the Azure Content Safety API to shield a prompt.
    
    Args:
        api_key (str): The API key for Azure Content Safety
        user_prompt (str, optional): The user's prompt to be shielded
        documents (list, optional): List of documents to be analyzed
    
    Returns:
        dict: The API response
    """
    url = "https://test-prompt-sheild.cognitiveservices.azure.com/contentsafety/text:shieldPrompt?api-version=2024-09-01"
    
    headers = {
        "Ocp-Apim-Subscription-Key": api_key,
        "Content-Type": "application/json"
    }
    
    data = {}
    
    # Only include userPrompt if provided
    if user_prompt:
        data["userPrompt"] = user_prompt
    
    # Only include documents if provided
    if documents:
        data["documents"] = documents
    
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        print(response.text)
        return None
    
    return response.json()

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Shield prompts using Azure Content Safety API")
    parser.add_argument("--prompt", type=str, help="User prompt to shield")
    parser.add_argument("--document", action="append", help="Document to analyze (can be used multiple times)")
    parser.add_argument("--prompt-file", type=str, help="File containing the user prompt")
    parser.add_argument("--document-file", type=str, help="File containing documents (one per line)")
    parser.add_argument("--endpoint", type=str, help="Custom API endpoint URL")
    
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    api_key = os.getenv("AZURE_CONTENT_SAFETY_KEY")
    
    if not api_key:
        print("Error: API key not found. Please set AZURE_CONTENT_SAFETY_KEY in your .env file.")
        sys.exit(1)
    
    # Get user prompt (now optional)
    user_prompt = None
    if args.prompt:
        user_prompt = args.prompt
    elif args.prompt_file:
        try:
            with open(args.prompt_file, 'r') as f:
                user_prompt = f.read().strip()
        except Exception as e:
            print(f"Error reading prompt file: {e}")
            sys.exit(1)
    
    # Get documents (now optional)
    documents = []
    if args.document:
        documents = args.document
    elif args.document_file:
        try:
            with open(args.document_file, 'r') as f:
                documents = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"Error reading document file: {e}")
            sys.exit(1)
    
    # Ensure at least one of prompt or document is provided
    if not user_prompt and not documents:
        print("Error: Please provide at least one of --prompt, --prompt-file, --document, or --document-file")
        sys.exit(1)
    
    # Call the API
    result = shield_prompt(api_key, user_prompt, documents if documents else None)
    
    if result:
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main() 