# AI for Code Evaluation Pipeline

This project provides a comprehensive pipeline for evaluating AI models (specifically Large Language Models) on code review and bug detection tasks. It features an automated, renewable dataset generation process combining real-world data and academic benchmarks, followed by review generation and a novel multi-judge qualitative evaluation framework using free-tier LLMs.

## Features ✨

* **Hybrid Dataset Generation (`run_pipeline.py`)**:
    * Mines merged Pull Requests (PRs) from specified GitHub repositories.
    * Processes bugs from the Defects4J benchmark, extracting buggy/fixed code versions.
    * Includes a (currently simple) synthetic bug injector for Java code.
    * Manages dataset versioning.
* **AI Code Review Generation (`generate_ai_reviews.py`)**:
    * Uses configured free-tier LLMs (via `llm_client.py`) to generate code reviews for items in the dataset.
    * Supports multiple "generator" models defined in the config.
    * Saves reviews in a structured JSON format.
* **Multi-Judge Qualitative Evaluation (`multi_judge_evaluator.py`)**:
    * Implements a novel consensus mechanism using multiple free-tier LLMs as "judges" and one as a "meta-judge".
    * Evaluates AI-generated reviews based on criteria like Factual Correctness, Actionability, and Analytical Depth.
    * Saves detailed qualitative scores and reasoning.
* **Results Analysis (`analyze_results.py`)**:
    * Processes the qualitative evaluation outputs.
    * Calculates average scores, inter-judge agreement (Kappa, Correlation), and efficiency/error metrics.
    * Generates summary tables and visualizations (bar charts).
* **Configurable & Resilient**:
    * Uses YAML (`config.yaml`) for easy configuration of paths, models, and parameters.
    * Uses `.env` file for secure API key management.
    * Includes retry logic for API calls to handle rate limits.

---

## Setup ⚙️

1.  **Prerequisites**:
    * Python 3.10+
    * Java Development Kit (JDK) version 11
    * Git >= 1.9
    * Subversion (svn) >= 1.8
    * Perl >= 5.0.12, `cpanm`
    * Maven (if using PITest later) `brew install maven`
2.  **Clone Defects4J**: Follow the setup instructions provided previously to clone and initialize the Defects4J framework into the `defects4j/` directory. Ensure the `defects4j` command works in your terminal.
3.  **Create Virtual Environment**:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```
4.  **Install Python Dependencies**:
    ```bash
    pip install -r requirements.txt
    pip install tabulate # Needed for analyze_results.py
    ```
5.  **API Keys**: Create a `.env` file in the project root (`aiforcodeevaluation/`) and add your API keys:
    ```.env
    GROQ_API_KEY="gsk_..."
    OPENROUTER_API_KEY="sk-or-v1-..."
    # Add other keys if needed by your config
    ```
6.  **Configuration**:
    * Edit `config/config.yaml`.
    * **Crucially**, set your `github: token:`.
    * Verify `defects4j: base_path:` points to your cloned `defects4j` directory.
    * Verify the `llm_models:` section lists correct, working model IDs for Groq/OpenRouter, and assign appropriate `role`s (`generator`, `judge`, `meta-judge`).

---

## Usage 🚀

**Run scripts from the project root directory (`aiforcodeevaluation/`).**

1.  **Generate the Dataset (Run Once or Periodically)**:
    ```bash
    python3 run_pipeline.py
    ```
    * *Optional Flags*: `--skip-github`, `--skip-defects4j`, `--skip-synthetic` to run specific parts.
    * *Output*: Populates `data/defects4j_bugs/`, `data/github_prs/`, `data/synthetic_bugs/`, and updates `data/metadata/`.

2.  **Generate AI Code Reviews**:
    ```bash
    python3 scripts/generate_ai_reviews.py
    ```
    * *Requires*: Dataset generated in Step 1.
    * *Requires*: `generator` models defined in `config.yaml`.
    * *Output*: Populates `data/ai_reviews/` with JSON files containing reviews.
    * *Note*: This can take a very long time and may hit API rate limits.

3.  **Run Multi-Judge Qualitative Evaluation**:
    ```bash
    python3 scripts/multi_judge_evaluator.py
    ```
    * *Requires*: AI reviews generated in Step 2.
    * *Requires*: `judge` and `meta-judge` models defined in `config.yaml`.
    * *Output*: Populates `data/evaluation_metrics/qualitative/` with JSON files containing detailed evaluation scores and reasoning.
    * *Note*: This can also take a long time and hit API rate limits.

4.  **Analyze Qualitative Results**:
    ```bash
    python3 scripts/analyze_results.py
    ```
    * *Requires*: Evaluation results generated in Step 3.
    * *Input Directory (Default)*: `data/evaluation_metrics/qualitative/`
    * *Output*: Prints summary tables to the console and saves charts to the `charts/` directory.
    * *Optional Flags*: `--data-dir <path>`, `--output-dir <path>`, `--no-charts`.

5.  **(Optional) Automated Data Pipeline Runs**:
    * Make `setup_cron.sh` executable: `chmod +x setup_cron.sh`
    * Run it once: `./setup_cron.sh` (This sets up `run_pipeline.py` to run weekly).
    * *Note*: Ensure `schedule: enabled: true` in `config.yaml` if you want cron to run. Modify the script/cron expression as needed.

---

## Monitoring 
* **Pipeline Logs**: Check `logs/pipeline.log` for detailed output and errors from `run_pipeline.py`.
* **Evaluation Logs**: Check console output (or redirect to a file) when running `generate_ai_reviews.py` and `multi_judge_evaluator.py`.
* **Dataset Version**: See `data/metadata/dataset_version.json`.
* **Dataset Stats**: Run `python3 manager/dataset_manager.py`.