"""
PHASE 1 ORCHESTRATOR - WITH BUGSINPY
File: phase1_orchestrator_with_bugsinpy.py

Coordinates:
1. Aggressive Defects4J collection (Java bugs)
2. Aggressive GitHub PR collection (PRs)
3. Aggressive BugsInPy collection (Python bugs)
4. Real-time statistics and progress
5. Unified dataset creation
"""

import json
import logging
from pathlib import Path
from datetime import datetime
import sys

# Import from scripts
sys.path.append('scripts')
from defects4j_processor import Defects4JAggressive as Defects4JProcessor
from github_pr_miner import GitHubPRMinerAggressive
from bugsinpy_processor import BugsInPyProcessor

class Phase1OrchestratorWithBugsInPy:
    """Master orchestrator for aggressive Phase 1 data collection (with BugsInPy)"""
    
    def __init__(self, config_path: str = 'config/config.yaml'):
        import yaml
        
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'defects4j': {},
            'github': {},
            'bugsinpy': {},
            'unified_dataset': []
        }
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('phase1_orchestration.log'),
                logging.StreamHandler()
            ]
        )
        
        self.logger = logging.getLogger(__name__)
    
    def collect_defects4j(self) -> dict:
        """Run aggressive Defects4J collection"""
        
        self.logger.info("\n" + "="*70)
        self.logger.info("PHASE 1.1: DEFECTS4J AGGRESSIVE COLLECTION (Java)")
        self.logger.info("="*70)
        
        try:
            processor = Defects4JProcessor(self.config)
            samples = processor.process_all_projects()
            
            result = {
                'status': 'success',
                'samples_collected': len(samples),
                'statistics': processor.stats,
                'samples': samples
            }
            
            self.logger.info(f"✓ Defects4J: {len(samples)} total samples collected")
            return result
        
        except Exception as e:
            self.logger.error(f"✗ Defects4J collection failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
                'samples': []
            }
    
    def collect_github(self) -> dict:
        """Run aggressive GitHub PR collection"""
        
        self.logger.info("\n" + "="*70)
        self.logger.info("PHASE 1.2: GITHUB PR AGGRESSIVE COLLECTION")
        self.logger.info("="*70)
        
        try:
            token = self.config.get('github', {}).get('token')
            if not token or 'GITHUBIID' in token:
                raise Exception("GitHub token not configured")

            miner = GitHubPRMinerAggressive(token, self.config)
            samples = miner.mine_all_repositories()
            
            result = {
                'status': 'success',
                'samples_collected': len(samples),
                'statistics': miner.stats,
                'samples': samples
            }
            
            self.logger.info(f"✓ GitHub: {len(samples)} total samples collected")
            return result
        
        except Exception as e:
            self.logger.error(f"✗ GitHub collection failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
                'samples': []
            }
    
    def collect_bugsinpy(self) -> dict:
        """Run aggressive BugsInPy collection (Python)"""
        
        self.logger.info("\n" + "="*70)
        self.logger.info("PHASE 1.3: BUGSINPY AGGRESSIVE COLLECTION (Python)")
        self.logger.info("="*70)
        
        try:
            if not self.config.get('bugsinpy', {}).get('enabled', False):
                self.logger.info("BugsInPy collection disabled in config. Skipping.")
                return {
                    'status': 'skipped',
                    'samples_collected': 0,
                    'samples': []
                }
            
            processor = BugsInPyProcessor(self.config)
            samples = processor.process_all_projects()
            
            result = {
                'status': 'success' if samples else 'partial',
                'samples_collected': len(samples),
                'statistics': processor.stats,
                'samples': samples
            }
            
            if samples:
                self.logger.info(f"✓ BugsInPy: {len(samples)} total samples collected")
            else:
                self.logger.warning(f"⚠ BugsInPy: No samples collected (may not be installed)")
            
            return result
        
        except Exception as e:
            self.logger.warning(f"⚠ BugsInPy collection skipped: {e}")
            return {
                'status': 'skipped',
                'error': str(e),
                'samples': []
            }
    
    def create_unified_dataset(self, d4j_result: dict, gh_result: dict, bugsinpy_result: dict) -> list:
        """Merge all datasets into unified format"""
        
        self.logger.info("\n" + "="*70)
        self.logger.info("PHASE 1.4: CREATING UNIFIED DATASET")
        self.logger.info("="*70)
        
        unified = []
        
        # Add Defects4J samples
        d4j_samples = d4j_result.get('samples', [])
        unified.extend(d4j_samples)
        self.logger.info(f"Added {len(d4j_samples)} Defects4J samples (Java)")
        
        # Add GitHub samples
        gh_samples = gh_result.get('samples', [])
        unified.extend(gh_samples)
        self.logger.info(f"Added {len(gh_samples)} GitHub samples (Java/Python)")
        
        # Add BugsInPy samples
        bugsinpy_samples = bugsinpy_result.get('samples', [])
        if bugsinpy_samples:
            unified.extend(bugsinpy_samples)
            self.logger.info(f"Added {len(bugsinpy_samples)} BugsInPy samples (Python)")
        
        self.logger.info(f"\n✓ Total unified samples: {len(unified)}")
        
        return unified
    
    def generate_statistics_report(self):
        """Generate comprehensive statistics"""
        
        self.logger.info("\n" + "="*70)
        self.logger.info("FINAL STATISTICS REPORT")
        self.logger.info("="*70)
        
        total_samples = len(self.results['unified_dataset'])
        d4j_count = len(self.results['defects4j'].get('samples', []))
        gh_count = len(self.results['github'].get('samples', []))
        bugsinpy_count = len(self.results['bugsinpy'].get('samples', []))
        
        # Language distribution
        lang_dist = {'java': 0, 'python': 0, 'other': 0}
        for sample in self.results['unified_dataset']:
            lang = sample.get('language', 'other').lower()
            if lang in lang_dist:
                lang_dist[lang] += 1
            else:
                lang_dist['other'] += 1
        
        report = {
            'collection_timestamp': self.results['timestamp'],
            'total_samples': total_samples,
            'breakdown': {
                'defects4j': {
                    'count': d4j_count,
                    'percentage': f"{100*d4j_count/max(total_samples,1):.1f}%",
                    'language': 'Java',
                    'statistics': self.results['defects4j'].get('statistics', {})
                },
                'github': {
                    'count': gh_count,
                    'percentage': f"{100*gh_count/max(total_samples,1):.1f}%",
                    'language': 'Mixed (Java/Python)',
                    'statistics': self.results['github'].get('statistics', {})
                },
                'bugsinpy': {
                    'count': bugsinpy_count,
                    'percentage': f"{100*bugsinpy_count/max(total_samples,1):.1f}%",
                    'language': 'Python',
                    'statistics': self.results['bugsinpy'].get('statistics', {})
                }
            },
            'language_distribution': lang_dist
        }
        
        return report
    
    def save_results(self):
        """Save all results to disk"""
        
        output_base = Path(self.config['data']['output_base']) / 'phase1_results'
        output_base.mkdir(parents=True, exist_ok=True)
        
        # Save unified dataset
        unified_file = output_base / 'unified_dataset.json'
        with open(unified_file, 'w') as f:
            json.dump(self.results['unified_dataset'], f, indent=2)
        
        self.logger.info(f"✓ Saved unified dataset: {unified_file}")
        
        # Save statistics report
        report = self.generate_statistics_report()
        report_file = output_base / 'collection_statistics.json'
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.logger.info(f"✓ Saved statistics report: {report_file}")
        
        # Save detailed results
        results_file = output_base / 'detailed_results.json'
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        self.logger.info(f"✓ Saved detailed results: {results_file}")
        
        # Print summary
        self._print_summary(report, output_base)
        
        return output_base
    
    def _print_summary(self, report: dict, output_dir: Path):
        """Print a nice summary to console"""
        
        print("\n" + "="*70)
        print("PHASE 1 COLLECTION SUMMARY")
        print("="*70)
        
        print(f"\n📊 TOTAL SAMPLES COLLECTED: {report['total_samples']}")
        print(f"   Defects4J (Java): {report['breakdown']['defects4j']['count']} " +
              f"({report['breakdown']['defects4j']['percentage']})")
        print(f"   GitHub (Mixed): {report['breakdown']['github']['count']} " +
              f"({report['breakdown']['github']['percentage']})")
        print(f"   BugsInPy (Python): {report['breakdown']['bugsinpy']['count']} " +
              f"({report['breakdown']['bugsinpy']['percentage']})")
        
        print(f"\n🗣️  LANGUAGES:")
        for lang, count in report['language_distribution'].items():
            print(f"   {lang.upper()}: {count}")
        
        print(f"\n📁 OUTPUT DIRECTORY: {output_dir}")
        print("="*70 + "\n")
    
    def run(self):
        """Execute full Phase 1 orchestration"""
        
        print("\n" + "#"*70)
        print("# PHASE 1: AGGRESSIVE DATA COLLECTION ORCHESTRATION")
        print("# (Defects4J + GitHub + BugsInPy)")
        print("# Starting comprehensive dataset collection...")
        print("#"*70 + "\n")
        
        start_time = datetime.now()
        
        # Step 1: Collect Defects4J
        self.results['defects4j'] = self.collect_defects4j()
        
        # Step 2: Collect GitHub
        self.results['github'] = self.collect_github()
        
        # Step 3: Collect BugsInPy
        self.results['bugsinpy'] = self.collect_bugsinpy()
        
        # Step 4: Create unified dataset
        self.results['unified_dataset'] = self.create_unified_dataset(
            self.results['defects4j'],
            self.results['github'],
            self.results['bugsinpy']
        )
        
        # Step 5: Save results
        output_dir = self.save_results()
        
        # Final report
        duration = datetime.now() - start_time
        
        print("\n" + "#"*70)
        print("# PHASE 1 COMPLETE")
        print(f"# Duration: {duration}")
        print(f"# Total Samples: {len(self.results['unified_dataset'])}")
        print(f"# Output: {output_dir}")
        print("#"*70 + "\n")


def main():
    import sys
    
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = 'config/config.yaml'
    
    try:
        orchestrator = Phase1OrchestratorWithBugsInPy(config_path)
        orchestrator.run()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
