#!/usr/bin/env python3
import os
import json
import glob
import time
import datetime
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Union
from dotenv import load_dotenv

# Import the CompetitionClient from the runner.py file
from runner import CompetitionClient, Job

class EvaluationFramework:
    def __init__(self, api_key: str = None, api_server: str = "https://llmailinject.azurewebsites.net",
                 prompts_dir: Optional[str] = None, records_dir: Optional[str] = None):
        """Initialize the evaluation framework."""
        # Load API key from .env if not provided
        if api_key is None:
            load_dotenv()
            api_key = os.getenv("LLMAIL_INJECTION")
            
        if not api_key:
            raise ValueError("API key not provided and not found in .env file")
            
        self.client = CompetitionClient(api_key, api_server)
        self.base_path = Path(os.path.dirname(os.path.abspath(__file__)))
        
        # Use provided paths or default paths
        self.prompts_dir = Path(prompts_dir) if prompts_dir else self.base_path / "prompts"
        self.records_dir = Path(records_dir) if records_dir else self.base_path / "records"
        self.levels_file = self.base_path / "level_config.json"
        
        # Ensure the directories exist
        os.makedirs(self.prompts_dir, exist_ok=True)
        os.makedirs(self.records_dir, exist_ok=True)
        
        # Load levels and prompts
        self.levels = self._load_levels()
        self.prompts = self._load_prompts()
        
    def _load_levels(self) -> List[Dict]:
        """Load levels from the level configuration file."""
        try:
            with open(self.levels_file, 'r') as f:
                data = json.load(f)
                return data.get('levels', [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading levels: {e}")
            return []
    
    def _load_prompts(self) -> List[Dict]:
        """Load prompts from the prompts directory."""
        prompts = []
        for prompt_file in glob.glob(str(self.prompts_dir / "*.json")):
            try:
                with open(prompt_file, 'r') as f:
                    prompt = json.load(f)
                    prompts.append(prompt)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                print(f"Error loading prompt file {prompt_file}: {e}")
        return prompts

    def has_existing_result(self, prompt_id: str, level_id: str) -> bool:
        """
        Check if a result already exists for this prompt and level combination.
        
        Args:
            prompt_id: ID of the prompt
            level_id: ID of the level
            
        Returns:
            bool: True if a successful result exists, False otherwise
        """
        record_file = self.records_dir / f"{prompt_id}_results.json"
        
        if not record_file.exists():
            return False
            
        try:
            with open(record_file, 'r') as f:
                existing_results = json.load(f)
                
            # Check if this level has already been evaluated
            if 'results' in existing_results and level_id in existing_results['results']:
                result = existing_results['results'][level_id]
                # Only consider completed evaluations with successful status as existing
                if result.get('status') == 'completed' and 'error' not in result:
                    print(f"Skipping already completed evaluation for prompt '{prompt_id}' and level '{level_id}'")
                    return True
                elif result.get('status') == 'error':
                    print(f"Previous attempt for prompt '{prompt_id}' and level '{level_id}' had an error. Retrying...")
                    # If the error was a rate limit, we should print a message about waiting
                    if 'error' in result and 'rate limit' in result['error'].lower():
                        print("This was previously rate limited. Make sure enough time has passed before retrying.")
                    return False
                    
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Error checking existing results: {e}")
            
        return False
    
    def evaluate_prompt_against_level(self, prompt: Dict, level: Dict, 
                                      timeout: int = 300, poll_interval: int = 30,
                                      skip_existing: bool = False) -> Dict:
        """
        Evaluate a single prompt against a single level.
        
        Args:
            prompt: The prompt configuration
            level: The level configuration
            timeout: Maximum time to wait for job completion (in seconds)
            poll_interval: Time between job status checks (in seconds)
            skip_existing: Whether to skip evaluation if result already exists
            
        Returns:
            result: Dictionary containing the evaluation result
            
        Raises:
            Exception: If a rate limit error occurs, so the calling function can handle retries
        """
        # Check if we should skip this evaluation
        if skip_existing and self.has_existing_result(prompt['id'], level['id']):
            # Load the existing result
            record_file = self.records_dir / f"{prompt['id']}_results.json"
            with open(record_file, 'r') as f:
                existing_results = json.load(f)
            return existing_results['results'][level['id']]
        
        print(f"Testing prompt '{prompt['name']}' against level '{level['name']}'")
        
        try:
            # Create a job
            job = self.client.create_job(
                scenario=level["scenario"],
                subject=prompt["subject"],
                body=prompt["body"]
            )
            
            print(f"Job created with ID: {job.job_id}")
            
            # Wait for the job to complete or timeout
            start_time = time.time()
            while not job.is_completed and (time.time() - start_time) < timeout:
                print(f"Waiting for job to complete... (elapsed: {int(time.time() - start_time)}s)")
                time.sleep(poll_interval)
                job = self.client.get_job(job.job_id)
            
            # Check if we timed out
            if not job.is_completed:
                print(f"Job timed out after {timeout} seconds")
                result = {
                    "status": "timeout",
                    "level_id": level["id"],
                    "level_name": level["name"],
                    "job_id": job.job_id,
                    "team_id": job.team_id,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "elapsed_time": timeout,
                    "output": None,
                    "objectives": None,
                    "result_string": "TIMEOUT"
                }
            else:
                elapsed_time = time.time() - start_time
                print(f"Job completed in {elapsed_time:.2f} seconds")
                
                # Format the result string as requested
                if job.output and job.objectives:
                    result_string = f"{job.output} ({json.dumps(job.objectives)})"
                else:
                    result_string = "No result"
                
                result = {
                    "status": "completed",
                    "level_id": level["id"],
                    "level_name": level["name"],
                    "job_id": job.job_id,
                    "team_id": job.team_id,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "elapsed_time": elapsed_time,
                    "output": job.output,
                    "objectives": job.objectives,
                    "result_string": result_string
                }
                
                print(f"Result for level {level['id']}: {result_string}")
            
            return result
        
        except Exception as e:
            error_message = str(e).lower()
            
            # For rate limit errors, raise the exception to allow retry mechanism to work
            if "rate limit" in error_message or "exceeded" in error_message:
                print(f"Rate limit error detected: {e}")
                raise
            
            # For other errors, handle them here
            print(f"Error during evaluation: {e}")
            result = {
                "status": "error",
                "level_id": level["id"],
                "level_name": level["name"],
                "job_id": None,
                "team_id": None,
                "timestamp": datetime.datetime.now().isoformat(),
                "elapsed_time": None,
                "output": None,
                "objectives": None,
                "error": str(e),
                "result_string": f"ERROR: {str(e)}"
            }
            return result
    
    def _save_prompt_results(self, prompt: Dict, results: List[Dict]):
        """
        Save all results for a single prompt to a JSON file.
        
        Args:
            prompt: The prompt configuration
            results: List of results for this prompt across all levels
        """
        # Create the record file path
        record_file = self.records_dir / f"{prompt['id']}_results.json"
        
        # Load existing results if file exists
        existing_results = {}
        if record_file.exists():
            try:
                with open(record_file, 'r') as f:
                    existing_results = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                print(f"Error loading existing results: {e}")
                existing_results = {}
        
        # Initialize the record structure if needed
        if 'prompt' not in existing_results:
            existing_results['prompt'] = prompt
        
        if 'results' not in existing_results:
            existing_results['results'] = {}
            
        # Add or update results for each level
        for result in results:
            level_id = result['level_id']
            existing_results['results'][level_id] = result
        
        # Save the updated results
        try:
            with open(record_file, 'w') as f:
                json.dump(existing_results, f, indent=2)
            print(f"Results for prompt '{prompt['name']}' saved to {record_file}")
        except Exception as e:
            print(f"Error saving results: {e}")
    
    def evaluate_all(self, level_ids: Optional[List[str]] = None, 
                     prompt_ids: Optional[List[str]] = None,
                     timeout: int = 300, poll_interval: int = 30,
                     skip_existing: bool = True):
        """
        Evaluate all specified prompts against all specified levels.
        
        Args:
            level_ids: List of level IDs to evaluate (None for all)
            prompt_ids: List of prompt IDs to evaluate (None for all)
            timeout: Maximum time to wait for job completion (in seconds)
            poll_interval: Time between job status checks (in seconds)
            skip_existing: Whether to skip evaluations if results already exist
        """
        # Filter levels if level_ids is provided
        levels_to_evaluate = self.levels
        if level_ids:
            levels_to_evaluate = [level for level in self.levels if level['id'] in level_ids]
        
        # Filter prompts if prompt_ids is provided
        prompts_to_evaluate = self.prompts
        if prompt_ids:
            prompts_to_evaluate = [prompt for prompt in self.prompts if prompt['id'] in prompt_ids]
        
        print(f"Starting evaluation of {len(prompts_to_evaluate)} prompts against {len(levels_to_evaluate)} levels")
        print(f"Prompt directory: {self.prompts_dir}")
        print(f"Records directory: {self.records_dir}")
        print(f"Skip existing results: {skip_existing}")
        
        # Add a delay between submissions to avoid rate limits
        submission_delay = 10  # seconds
        
        for prompt in prompts_to_evaluate:
            prompt_results = []
            
            for level in levels_to_evaluate:
                # Try to evaluate with up to 3 retries on rate limit errors
                max_retries = 3
                retry_count = 0
                retry_delay = 60  # seconds
                
                while retry_count <= max_retries:
                    try:
                        result = self.evaluate_prompt_against_level(
                            prompt=prompt,
                            level=level,
                            timeout=timeout,
                            poll_interval=poll_interval,
                            skip_existing=skip_existing
                        )
                        prompt_results.append(result)
                        
                        # If we get here without an exception, break the retry loop
                        break
                    except Exception as e:
                        error_message = str(e)
                        if "rate limit" in error_message.lower() and retry_count < max_retries:
                            retry_count += 1
                            wait_time = retry_delay * retry_count
                            print(f"Rate limit hit. Waiting {wait_time} seconds before retry {retry_count}/{max_retries}...")
                            time.sleep(wait_time)
                        else:
                            # Create an error result
                            result = {
                                "status": "error",
                                "level_id": level["id"],
                                "level_name": level["name"],
                                "job_id": None,
                                "team_id": None,
                                "timestamp": datetime.datetime.now().isoformat(),
                                "elapsed_time": None,
                                "output": None,
                                "objectives": None,
                                "error": error_message,
                                "result_string": f"ERROR: {error_message}"
                            }
                            prompt_results.append(result)
                            break
                
                # Add a delay between submissions to avoid hitting rate limits
                if len(levels_to_evaluate) > 1 or len(prompts_to_evaluate) > 1:
                    print(f"Waiting {submission_delay} seconds before next submission to avoid rate limits...")
                    time.sleep(submission_delay)
            
            # Save results for this prompt
            self._save_prompt_results(prompt, prompt_results)


def main():
    """Main function to run the evaluation framework."""
    parser = argparse.ArgumentParser(description="Evaluate prompts against LLM Mail Injection defenses")
    parser.add_argument('--level', type=str, nargs='+', default='level1m',
                        help='Specific level IDs to evaluate (default: level1m)')
    parser.add_argument('--prompt', type=str, nargs='+', 
                        help='Specific prompt IDs to evaluate (default: all prompts)')
    parser.add_argument('--pattern', type=str, 
                        help='Filter prompts by pattern (e.g., "token*" for all prompts starting with "token")')
    parser.add_argument('--timeout', type=int, default=300, 
                        help='Maximum time to wait for job completion (in seconds)')
    parser.add_argument('--poll-interval', type=int, default=30, 
                        help='Time between job status checks (in seconds)')
    parser.add_argument('--base-dir', type=str, default=None, 
                        help='Directory containing prompt files and evaluation records')
    parser.add_argument('--skip-existing', action='store_true', default=True,
                        help='Skip evaluations if results already exist')
    
    args = parser.parse_args()
    
    # Create the evaluation framework
    try:
        if args.base_dir:
            prompts_dir = os.path.join(args.base_dir, "prompts")
            records_dir = os.path.join(args.base_dir, "records")
        else:
            prompts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
            records_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "records")
        framework = EvaluationFramework(
            prompts_dir=prompts_dir,
            records_dir=records_dir
        )
        
        # Filter prompt IDs by pattern if provided
        prompt_ids = args.prompt
        if args.pattern and not args.prompt:
            import fnmatch
            # Filter prompts by pattern
            matching_prompts = [prompt['id'] for prompt in framework.prompts 
                               if fnmatch.fnmatch(prompt['id'], args.pattern)]
            if matching_prompts:
                print(f"Found {len(matching_prompts)} prompts matching pattern '{args.pattern}': {', '.join(matching_prompts)}")
                prompt_ids = matching_prompts
            else:
                print(f"No prompts found matching pattern '{args.pattern}'")
                return
        
        # Run evaluations
        framework.evaluate_all(
            level_ids=args.level,
            prompt_ids=prompt_ids,
            timeout=args.timeout,
            poll_interval=args.poll_interval,
            skip_existing=args.skip_existing
        )
        
    except Exception as e:
        print(f"Error running evaluation framework: {e}")


if __name__ == "__main__":
    main() 