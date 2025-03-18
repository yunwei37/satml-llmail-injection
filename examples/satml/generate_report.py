#!/usr/bin/env python3
import os
import json
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict
import pandas as pd

def load_json_files(directory):
    """Load all JSON files from the given directory."""
    results = {}
    for filename in os.listdir(directory):
        if filename.endswith('.json'):
            file_path = os.path.join(directory, filename)
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    # Extract the attack name from the filename without the _results.json suffix
                    attack_name = filename.replace('_results.json', '')
                    results[attack_name] = data
            except Exception as e:
                print(f"Error loading {filename}: {e}")
    return results

def analyze_objectives(results):
    """
    Analyze objectives completion across different attacks and levels.
    Returns data organized by objective and by level1.
    """
    # Track counts for each objective
    objective_counts = defaultdict(int)
    objective_counts_by_level = defaultdict(lambda: defaultdict(int))
    
    # Track total completed tests
    total_tests = 0
    level_counts = defaultdict(int)
    
    # Track success rates by attack type
    attack_success = defaultdict(lambda: defaultdict(int))
    
    # Iterate through all results
    for attack_name, data in results.items():
        if 'results' not in data:
            continue
            
        for level_id, level_data in data['results'].items():
            if level_data['status'] != 'completed' or level_data.get('objectives') is None:
                continue
                
            # Count this as a completed test
            total_tests += 1
            level_counts[level_id] += 1
            
            # Track objectives achieved
            for objective, achieved in level_data['objectives'].items():
                if achieved:
                    objective_counts[objective] += 1
                    objective_counts_by_level[level_id][objective] += 1
                    attack_success[attack_name][objective] += 1
    
    return {
        'objective_counts': dict(objective_counts),
        'by_level': {level: dict(objectives) for level, objectives in objective_counts_by_level.items()},
        'total_tests': total_tests,
        'level_counts': dict(level_counts),
        'attack_success': {attack: dict(objectives) for attack, objectives in attack_success.items()}
    }

def plot_objective_counts(data, output_path):
    """Create bar plots for objective counts."""
    # Plot overall objective counts
    plt.figure(figsize=(12, 6))
    objectives = list(data['objective_counts'].keys())
    counts = list(data['objective_counts'].values())
    
    # Sort by counts in descending order
    sorted_indices = np.argsort(counts)[::-1]
    objectives = [objectives[i] for i in sorted_indices]
    counts = [counts[i] for i in sorted_indices]
    
    plt.bar(objectives, counts)
    plt.title('Objective Completion Counts Across All Tests')
    plt.xlabel('Objective')
    plt.ylabel('Count')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(os.path.join(output_path, 'objective_counts.png'))
    plt.close()
    
    # Plot objective counts by level
    plt.figure(figsize=(15, 8))
    
    # Prepare data for grouped bar chart
    levels = list(data['by_level'].keys())
    all_objectives = set()
    for level_objectives in data['by_level'].values():
        all_objectives.update(level_objectives.keys())
    all_objectives = sorted(list(all_objectives))
    
    # Create DataFrame for easier plotting
    df_data = []
    for level in levels:
        level_data = data['by_level'][level]
        for objective in all_objectives:
            df_data.append({
                'Level': level,
                'Objective': objective,
                'Count': level_data.get(objective, 0)
            })
    
    df = pd.DataFrame(df_data)
    
    # Create grouped bar chart
    pivot_df = df.pivot(index='Objective', columns='Level', values='Count')
    pivot_df.plot(kind='bar', figsize=(15, 8))
    plt.title('Objective Completion by Level')
    plt.xlabel('Objective')
    plt.ylabel('Count')
    plt.legend(title='Level')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(os.path.join(output_path, 'objective_by_level.png'))
    plt.close()
    
    # Plot success rate by attack type for different objectives
    # We'll focus on the top 10 attack types with the highest success rate for any objective
    attack_success = data['attack_success']
    
    # Calculate success rate for each attack type and objective
    success_data = []
    for attack, objectives in attack_success.items():
        for objective, count in objectives.items():
            success_data.append({
                'Attack': attack,
                'Objective': objective,
                'Count': count
            })
    
    if success_data:
        success_df = pd.DataFrame(success_data)
        
        # Get top attacks for each objective
        for objective in all_objectives:
            objective_df = success_df[success_df['Objective'] == objective]
            if objective_df.empty:
                continue
                
            # Sort by count in descending order and take top 15
            top_attacks = objective_df.sort_values('Count', ascending=False).head(15)
            
            plt.figure(figsize=(12, 8))
            plt.bar(top_attacks['Attack'], top_attacks['Count'])
            plt.title(f'Top Attacks by Success Count for {objective}')
            plt.xlabel('Attack Type')
            plt.ylabel('Success Count')
            plt.xticks(rotation=90)
            plt.tight_layout()
            plt.savefig(os.path.join(output_path, f'top_attacks_{objective.replace(".", "_")}.png'))
            plt.close()

def generate_report(directory):
    """Generate a comprehensive report from JSON records."""
    print(f"Analyzing JSON files in {directory}...")
    
    # Create output directory for plots
    output_path = os.path.join(directory, 'report')
    os.makedirs(output_path, exist_ok=True)
    
    # Load all JSON files
    results = load_json_files(directory)
    print(f"Loaded {len(results)} JSON files")
    
    # Analyze objectives
    analysis = analyze_objectives(results)
    
    # Create plots
    plot_objective_counts(analysis, output_path)
    
    # Generate text report
    report_path = os.path.join(output_path, 'summary_report.md')
    with open(report_path, 'w') as f:
        f.write("# LLM Mail Injection Attacks Analysis Report\n\n")
        
        f.write("## Overall Statistics\n")
        f.write(f"Total completed tests: {analysis['total_tests']}\n")
        f.write(f"Tests by level: {json.dumps(analysis['level_counts'], indent=2)}\n\n")
        
        # Add overall charts
        f.write("![Objective Completion Counts](objective_counts.png)\n\n")
        f.write("![Objective Completion by Level](objective_by_level.png)\n\n")
        
        f.write("## Objective Completion Counts\n")
        sorted_objectives = sorted(
            analysis['objective_counts'].items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        for objective, count in sorted_objectives:
            success_rate = (count / analysis['total_tests']) * 100
            f.write(f"{objective}: {count} ({success_rate:.2f}%)\n")
        
        f.write("\n## Top Attack Types by Objective\n")
        for objective in analysis['objective_counts']:
            f.write(f"\n### {objective}\n")
            
            # Add the corresponding chart for this objective
            img_filename = f"top_attacks_{objective.replace('.', '_')}.png"
            f.write(f"![Top Attacks for {objective}]({img_filename})\n\n")
            
            # Find top attacks for this objective
            attacks_for_objective = [
                (attack, obj_counts.get(objective, 0))
                for attack, obj_counts in analysis['attack_success'].items()
                if objective in obj_counts
            ]
            
            # Sort by count in descending order and take top 10
            top_attacks = sorted(attacks_for_objective, key=lambda x: x[1], reverse=True)[:10]
            
            for attack, count in top_attacks:
                f.write(f"{attack}: {count}\n")
    
    print(f"Report generated at {output_path}")
    print(f"Summary report: {report_path}")
    print(f"Generated plots in {output_path}")

if __name__ == "__main__":
    current_dir = "/home/yunwei37/ebpf/satml-llmail-injection/examples/satml/records"
    generate_report(current_dir) 