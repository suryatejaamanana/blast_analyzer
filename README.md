# blast_analyzer

Static blast radius analyzer for Python codebases.

## What it does

- Parses Python source into a directed dependency graph.
- Accepts structured change intent.
- Computes direct and indirect impacts.
- Produces explainable JSON and Markdown reports.

## Change intent format

```json
{
  "change_type": "api_modification",
  "target": "post_user",
  "modification": "add_optional_field"
}
```

Supported `change_type` values:

- `api_modification`
- `function_logic_change`
- `validation_rule_change`
- `refactor_shared_method`
- `data_model_change`

## Run

```bash
python3 blast_analyzer.py \
  --project-path project \
  --intent-json '{"change_type":"function_logic_change","target":"create_user","modification":"adjust validation flow"}'
```

Or with a file:

```bash
python3 blast_analyzer.py --project-path project --intent-file intent.json
```

Outputs:

- `blast_report.json`
- `blast_report.md`

## Test

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```
