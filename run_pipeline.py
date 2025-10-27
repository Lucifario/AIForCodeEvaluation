import sys
import yaml
import logging
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).parent / 'scripts'))
from manager.github_pr_miner import GitHubPRMiner
from manager.defects4j_processor import Defects4JProcessor
from manager.synthetic_injector import SyntheticBugInjector
from manager.dataset_manager import DatasetManager

def setup_logging(config):
    """Setup logging configuration"""
    log_file = Path(config['data']['log_file'])
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )


def run_github_mining(config, manager):
    """Run GitHub PR mining"""
    logging.info("=" * 80)
    logging.info("STEP 1: Mining GitHub Pull Requests")
    logging.info("=" * 80)
    
    miner = GitHubPRMiner(config['github']['token'], config)
    pr_count = miner.mine_all_repositories()
    
    manager.log_update('github_prs', pr_count)
    logging.info(f"GitHub mining complete: {pr_count} PRs added")


def run_defects4j_processing(config, manager):
    """Run Defects4J bug processing"""
    logging.info("=" * 80)
    logging.info("STEP 2: Processing Defects4J Bugs")
    logging.info("=" * 80)
    
    processor = Defects4JProcessor(config)
    processor.process_all_projects()
    
    checkout_dir = Path(config['defects4j']['checkout_dir'])
    bug_count = len(list(checkout_dir.glob('*_metadata.json')))
    
    manager.log_update('defects4j', bug_count)
    logging.info(f"Defects4J processing complete: {bug_count} bugs processed")


def run_synthetic_injection(config, manager):
    """Run synthetic bug injection"""
    logging.info("=" * 80)
    logging.info("STEP 3: Injecting Synthetic Bugs")
    logging.info("=" * 80)
    
    injector = SyntheticBugInjector(config)
    
    defects4j_dir = Path(config['defects4j']['checkout_dir'])
    for project_dir in defects4j_dir.glob('*_f'):
        if project_dir.is_dir():
            injector.process_directory(project_dir, 'java')
    
    output_dir = Path(config['synthetic']['output_dir'])
    bug_count = len(list(output_dir.rglob('*_mutant_*')))
    
    manager.log_update('synthetic_bugs', bug_count)
    logging.info(f"Synthetic injection complete: {bug_count} bugs generated")


def main():
    parser = argparse.ArgumentParser(description='AI Code Evaluation Dataset Pipeline')
    parser.add_argument('--config', default='config/config.yaml', help='Config file path')
    parser.add_argument('--skip-github', action='store_true', help='Skip GitHub mining')
    parser.add_argument('--skip-defects4j', action='store_true', help='Skip Defects4J processing')
    parser.add_argument('--skip-synthetic', action='store_true', help='Skip synthetic injection')
    
    args = parser.parse_args()
    
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    
    setup_logging(config)
    
    logging.info("=" * 80)
    logging.info("AI CODE EVALUATION DATASET PIPELINE")
    logging.info("=" * 80)
    
    manager = DatasetManager(config)
    manager.increment_version('minor')
    
    try:
        if not args.skip_github:
            run_github_mining(config, manager)
        
        if not args.skip_defects4j:
            run_defects4j_processing(config, manager)
        
        if not args.skip_synthetic:
            run_synthetic_injection(config, manager)
        logging.info("=" * 80)
        logging.info("PIPELINE COMPLETE")
        logging.info("=" * 80)
        
        stats = manager.get_statistics()
        logging.info(f"Dataset Version: {stats['version']}")
        logging.info(f"Defects4J Bugs: {stats['defects4j_bugs']}")
        logging.info(f"GitHub PRs: {stats['github_prs']}")
        logging.info(f"Synthetic Bugs: {stats['synthetic_bugs']}")
        logging.info(f"Total Updates: {stats['total_updates']}")
        
    except Exception as e:
        logging.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
