#!/usr/bin/env python3
import os
import sys
import json
import argparse
import requests
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# OpenAI configuration
openai_api_key = os.getenv('OPENAI_API_KEY')
model_name = os.getenv('OPENAI_MODEL_NAME', 'gpt-4o')
temperature = float(os.getenv('OPENAI_TEMPERATURE', '0.7'))
client = OpenAI()

# Azure Content Safety configuration
azure_api_key = os.getenv("AZURE_CONTENT_SAFETY_KEY")

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

def generate_response(messages, model=model_name, temp=temperature):
    """Send the conversation to OpenAI's API and get the response."""
    if model.startswith("gemini"):
        # Use Gemini API
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_api_key}"
        headers = {
            'Content-Type': 'application/json'
        }
        
        # Convert OpenAI message format to Gemini format
        gemini_messages = []
        for msg in messages:
            gemini_messages.append({
                "parts": [{"text": msg["content"]}]
            })
        
        data = {
            "contents": gemini_messages,
            "generationConfig": {
                "temperature": temp
            }
        }
        
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response_json = response.json()
        
        if 'candidates' in response_json and len(response_json['candidates']) > 0:
            return response_json['candidates'][0]['content']['parts'][0]['text']
        else:
            # Check for specific error types
            if 'promptFeedback' in response_json and 'blockReason' in response_json['promptFeedback']:
                block_reason = response_json['promptFeedback']['blockReason']
                if block_reason == 'PROHIBITED_CONTENT':
                    raise Exception(f"Gemini API error: Content was blocked due to prohibited content")
            # Generic error
            raise Exception(f"Gemini API error: {response_json}")
    else:
        # Use OpenAI API
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temp
        )
        return str(completion.choices[0].message.content)

def main():
    parser = argparse.ArgumentParser(description="Interactive chat with AI using prompt shielding")
    parser.add_argument("--no-shield", action="store_true", help="Disable prompt shielding")
    parser.add_argument("--model", type=str, help="Override the model name from environment")
    parser.add_argument("--temperature", type=float, help="Override the temperature from environment")
    args = parser.parse_args()
    
    # Override settings if provided
    current_model = args.model if args.model else model_name
    current_temp = args.temperature if args.temperature is not None else temperature
    
    # Check for API keys
    if not openai_api_key and not os.getenv('GEMINI_API_KEY'):
        print("Error: No API key found. Please set OPENAI_API_KEY or GEMINI_API_KEY in your .env file.")
        sys.exit(1)
    
    if not args.no_shield and not azure_api_key:
        print("Warning: No Azure Content Safety API key found. Prompt shielding will be disabled.")
        print("Set AZURE_CONTENT_SAFETY_KEY in your .env file to enable prompt shielding.")
        args.no_shield = True
    
    # Initialize conversation history
    conversation = []
    system_message = {"role": "system", "content": "You are a helpful assistant."}
    conversation.append(system_message)
    
    print(f"Chat with {current_model} (temperature: {current_temp})")
    print("Type 'exit', 'quit', or press Ctrl+C to end the conversation.")
    print("Type 'clear' to start a new conversation.")
    print()
    
    try:
        while True:
            # Get user input
            user_input = input("You: ")
            
            # Check for exit commands
            if user_input.lower() in ["exit", "quit"]:
                break
            
            # Check for clear command
            if user_input.lower() == "clear":
                conversation = [system_message]
                print("Conversation cleared.")
                continue
            
            # Apply prompt shielding if enabled
            if not args.no_shield:
                shield_result = shield_prompt(azure_api_key, user_input)
                if shield_result:
                    # Check for attack detection
                    attack_detected = False
                    if "userPromptAnalysis" in shield_result and shield_result["userPromptAnalysis"].get("attackDetected", False):
                        attack_detected = True
                    elif "documentsAnalysis" in shield_result:
                        for doc_analysis in shield_result["documentsAnalysis"]:
                            if doc_analysis.get("attackDetected", False):
                                attack_detected = True
                                break
                    
                    if attack_detected:
                        print("\n⚠️  ALERT: Potential prompt injection attempt detected and mitigated! ⚠️")
                    
                    if "shieldedPrompt" in shield_result:
                        shielded_prompt = shield_result["shieldedPrompt"]
                        if shielded_prompt != user_input:
                            print("Note: Your prompt was modified for safety.")
                        user_input = shielded_prompt
            
            # Add user message to conversation
            conversation.append({"role": "user", "content": user_input})
            
            try:
                # Get AI response
                ai_response = generate_response(conversation, current_model, current_temp)
                
                # Print AI response
                print("\nAssistant:", ai_response, "\n")
                
                # Add AI response to conversation history
                conversation.append({"role": "assistant", "content": ai_response})
                
            except Exception as e:
                print(f"Error: {e}")
                # Remove the last user message to avoid repeating it
                conversation.pop()
    
    except KeyboardInterrupt:
        print("\nExiting chat...")
    
    print("Goodbye!")

if __name__ == "__main__":
    main() 