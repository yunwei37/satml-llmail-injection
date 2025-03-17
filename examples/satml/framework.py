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
    def __init__(self, api_key: str = None, api_server: str = "https://llmailinject.azurewebsites.net"):
        """Initialize the evaluation framework."""
        # Load API key from .env if not provided
        if api_key is None:
            load_dotenv()
            api_key = os.getenv("LLMAIL_INJECTION")
            
        if not api_key:
            raise ValueError("API key not provided and not found in .env file")
            
        self.client = CompetitionClient(api_key, api_server)
        self.base_path = Path(os.path.dirname(os.path.abspath(__file__)))
        self.prompts_dir = self.base_path / "prompts"
        self.records_dir = self.base_path / "records"
        self.levels_file = self.base_path / "level_config.json"
        
        # Ensure the records directory exists
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
    
    def evaluate_prompt_against_level(self, prompt: Dict, level: Dict, 
                                      timeout: int = 300, poll_interval: int = 30) -> Dict:
        """
        Evaluate a single prompt against a single level.
        
        Args:
            prompt: The prompt configuration
            level: The level configuration
            timeout: Maximum time to wait for job completion (in seconds)
            poll_interval: Time between job status checks (in seconds)
            
        Returns:
            result: Dictionary containing the evaluation result
        """
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
                     timeout: int = 300, poll_interval: int = 30):
        """
        Evaluate all specified prompts against all specified levels.
        
        Args:
            level_ids: List of level IDs to evaluate (None for all)
            prompt_ids: List of prompt IDs to evaluate (None for all)
            timeout: Maximum time to wait for job completion (in seconds)
            poll_interval: Time between job status checks (in seconds)
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
        
        for prompt in prompts_to_evaluate:
            prompt_results = []
            
            for level in levels_to_evaluate:
                result = self.evaluate_prompt_against_level(
                    prompt=prompt,
                    level=level,
                    timeout=timeout,
                    poll_interval=poll_interval
                )
                prompt_results.append(result)
            
            # Save results for this prompt
            self._save_prompt_results(prompt, prompt_results)


def main():
    """Main function to run the evaluation framework."""
    parser = argparse.ArgumentParser(description="Evaluate prompts against LLM Mail Injection defenses")
    parser.add_argument('--level', type=str, nargs='+', default='level1m',
                        help='Specific level IDs to evaluate (default: all levels)')
    parser.add_argument('--prompt', type=str, nargs='+', 
                        help='Specific prompt IDs to evaluate (default: all prompts)')
    parser.add_argument('--timeout', type=int, default=300, 
                        help='Maximum time to wait for job completion (in seconds)')
    parser.add_argument('--poll-interval', type=int, default=30, 
                        help='Time between job status checks (in seconds)')
    
    args = parser.parse_args()
    
    # Create the evaluation framework
    try:
        framework = EvaluationFramework()
        
        # Run evaluations
        framework.evaluate_all(
            level_ids=args.level,
            prompt_ids=args.prompt,
            timeout=args.timeout,
            poll_interval=args.poll_interval
        )
        
    except Exception as e:
        print(f"Error running evaluation framework: {e}")


if __name__ == "__main__":
    main() 