# rules from promptmap

```sh

$ python /home/yunwei37/ebpf/satml-llmail-injection/examples/prompt-sheid/evaluate_rules.py
Found 20 rule files to evaluate
Evaluating rules: 100%|██████████| 20/20 [00:10<00:00,  1.84it/s]

=== Final Evaluation Results ===
Total rules: 20
Valid evaluations: 20 (100.00%)
Errors: 0 (0.00%)
Rules flagged: 9 (45.00% of valid)
Rules considered safe: 11 (55.00% of valid)

Results by rule type:
  prompt_stealing: 6/13 (46.15%)
  distraction: 3/7 (42.86%)

Results by severity:
  high: 6/13 (46.15%)
  medium: 3/7 (42.86%)

Detailed results saved to rules_evaluation_results.json
(.venv) yunwei37@yunwei:~/ebpf/satml-llmail-injection$ 
```