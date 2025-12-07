"""
PHASE 1 - AGGRESSIVE SCALING VERSION
File: defects4j_processor_aggressive_v2.py

Improvements over original:
- NO limit on bugs per project (fetch ALL available bugs)
- Parallel processing where possible
- Better error recovery and continuation
- Unified data format for easy downstream processing
- Progress tracking and statistics
"""

import os
import json
import logging
import subprocess
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from tqdm import tqdm
import shutil
from datetime import datetime
import csv

class Defects4JAggressive:
    """
    Aggressive Defects4J processor - NO LIMITS
    Collects ALL available bugs from ALL projects
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.defects4j_path = Path(config['defects4j']['base_path']).expanduser()
        self.checkout_dir = Path(config['defects4j']['checkout_dir'])
        self.checkout_dir.mkdir(parents=True, exist_ok=True)
        
        self.output_dir = Path(config['data']['output_base']) / 'defects4j_aggressive'
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Add to PATH
        os.environ["PATH"] += os.pathsep + str(self.defects4j_path / 'framework' / 'bin')
        os.environ["TZ"] = "America/Los_Angeles"
        
        # Statistics tracking
        self.stats = {
            'total_bugs_found': 0,
            'total_bugs_processed': 0,
            'total_bugs_failed': 0,
            'by_project': {}
        }
        
        self._verify_installation()
        
    def _verify_installation(self):
        """Verify Defects4J is properly installed"""
        try:
            result = subprocess.run(
                ['defects4j', 'info', '-p', 'Lang'],
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8'
            )
            
            if result.returncode != 0:
                logging.error(f"Defects4J command failed: {result.stderr}")
                raise Exception("Defects4J not properly configured")
            
            logging.info("✓ Defects4J installation verified")
        except Exception as e:
            logging.error(f"Defects4J verification failed: {e}")
            raise
    
    def get_all_projects(self) -> List[str]:
        """Get ALL available Defects4J projects (not just configured ones)"""
        try:
            result = subprocess.run(
                ['defects4j', 'info', '-p', 'all'],
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8'
            )
            
            if result.returncode == 0:
                # Parse output to extract project names
                projects = []
                for line in result.stdout.strip().split('\n'):
                    if line.strip() and not line.startswith('-'):
                        project_name = line.strip().split()[0]
                        if project_name:
                            projects.append(project_name)
                
                logging.info(f"Found {len(projects)} total projects: {projects}")
                return projects
            
            # Fallback to config
            return self.config['defects4j'].get('projects', [])
        
        except Exception as e:
            logging.warning(f"Could not get all projects: {e}. Using config.")
            return self.config['defects4j'].get('projects', [])
    
    def get_project_bugs(self, project: str) -> List[int]:
        """Get ALL bug IDs for a project (no limit)"""
        try:
            result = subprocess.run(
                ['defects4j', 'bids', '-p', project],
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8'
            )
            
            if result.returncode == 0:
                bug_ids = [
                    int(bid.strip()) 
                    for bid in result.stdout.strip().split('\n') 
                    if bid.strip()
                ]
                logging.info(f"Project {project}: {len(bug_ids)} total bugs available")
                return sorted(bug_ids)  # Sort for consistent ordering
            
            return []
        
        except Exception as e:
            logging.error(f"Error getting bugs for {project}: {e}")
            return []
    
    def checkout_bug(self, project: str, bug_id: int, version: str = 'b') -> Optional[Path]:
        """Checkout a specific bug version"""
        checkout_path = self.checkout_dir / f"{project}_{bug_id}{version}"
        
        if checkout_path.exists():
            logging.debug(f"Already checked out: {project}-{bug_id}{version}")
            return checkout_path
        
        try:
            result = subprocess.run(
                [
                    'defects4j', 'checkout',
                    '-p', project,
                    '-v', f'{bug_id}{version}',
                    '-w', str(checkout_path)
                ],
                capture_output=True,
                text=True,
                timeout=300,
                encoding='utf-8'
            )
            
            if result.returncode == 0:
                logging.debug(f"Checked out: {project}-{bug_id}{version}")
                return checkout_path
            else:
                logging.warning(f"Checkout failed: {project}-{bug_id}{version}")
                return None
        
        except Exception as e:
            logging.error(f"Error checking out {project}-{bug_id}{version}: {e}")
            return None
    
    def compile_bug(self, checkout_path: Path) -> bool:
        """Compile the checked-out bug"""
        try:
            result = subprocess.run(
                ['defects4j', 'compile'],
                cwd=checkout_path,
                capture_output=True,
                text=True,
                timeout=600,
                encoding='utf-8'
            )
            
            success = result.returncode == 0
            if not success:
                logging.debug(f"Compilation warning for {checkout_path.name}")
            return success
        
        except Exception as e:
            logging.error(f"Compilation error in {checkout_path.name}: {e}")
            return False
    
    def run_tests(self, checkout_path: Path) -> Dict:
        """Run tests and capture results"""
        try:
            result = subprocess.run(
                ['defects4j', 'test'],
                cwd=checkout_path,
                capture_output=True,
                text=True,
                timeout=1800,
                encoding='utf-8'
            )
            
            return {
                'returncode': result.returncode,
                'stdout': result.stdout[:5000],  # Limit output size
                'stderr': result.stderr[:5000]
            }
        
        except Exception as e:
            logging.error(f"Test execution error: {e}")
            return {'error': str(e)}
    
    def export_metadata(self, checkout_path: Path) -> Dict:
        """Export bug metadata"""
        metadata = {}
        properties = [
            'classes.modified',
            'tests.trigger',
            'dir.src.classes',
            'dir.bin.classes'
        ]
        
        for prop in properties:
            try:
                result = subprocess.run(
                    ['defects4j', 'export', '-p', prop],
                    cwd=checkout_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding='utf-8'
                )
                
                if result.returncode == 0:
                    metadata[prop] = result.stdout.strip().split('\n')
                else:
                    metadata[prop] = []
            
            except Exception as e:
                logging.debug(f"Could not export '{prop}': {e}")
                metadata[prop] = []
        
        return metadata
    
    def _find_and_copy_files(self, modified_classes: List[str], src_dir: Path, 
                            dest_dir: Path, suffix: str) -> int:
        """Find and copy modified class files"""
        common_src_dirs = [
            'src/main/java', 'src/java', 'src', 'source',
            'src/test/java', 'src/main', 'src/test'
        ]
        
        found_count = 0
        
        for class_name in modified_classes:
            relative_path = class_name.replace('.', '/') + ".java"
            found = False
            
            for common_dir in common_src_dirs:
                src_file = src_dir / common_dir / relative_path
                
                if src_file.exists():
                    try:
                        dest_file = dest_dir / f"{class_name}_{suffix}.java"
                        shutil.copy(src_file, dest_file)
                        found = True
                        break
                    except Exception as e:
                        logging.debug(f"Copy error: {e}")
            
            if not found:
                # Try recursive search
                try:
                    found_files = list(src_dir.rglob(relative_path))
                    if found_files:
                        dest_file = dest_dir / f"{class_name}_{suffix}.java"
                        shutil.copy(found_files[0], dest_file)
                        found = True
                except Exception as e:
                    logging.debug(f"Recursive search failed: {e}")
            
            if found:
                found_count += 1
        
        return found_count
    
    def process_bug(self, project: str, bug_id: int) -> Optional[Dict]:
        """Process a single bug - RETURNS STRUCTURED DATA"""
        try:
            # Checkout both versions
            buggy_path = self.checkout_bug(project, bug_id, 'b')
            if not buggy_path:
                return None
            
            fixed_path = self.checkout_bug(project, bug_id, 'f')
            if not fixed_path:
                return None
            
            # Compile
            buggy_compiled = self.compile_bug(buggy_path)
            fixed_compiled = self.compile_bug(fixed_path)
            
            # Export metadata
            buggy_metadata = self.export_metadata(buggy_path)
            fixed_metadata = self.export_metadata(fixed_path)
            
            # Run tests (buggy version should fail, fixed should pass)
            buggy_tests = self.run_tests(buggy_path)
            fixed_tests = self.run_tests(fixed_path)
            
            # Extract and copy source files
            bug_source_dir = self.output_dir / f"sources_{project}_{bug_id}"
            bug_source_dir.mkdir(parents=True, exist_ok=True)
            
            modified_classes = buggy_metadata.get('classes.modified', [])
            
            buggy_files_found = 0
            fixed_files_found = 0
            
            if modified_classes:
                buggy_files_found = self._find_and_copy_files(
                    modified_classes, buggy_path, bug_source_dir, "buggy"
                )
                fixed_files_found = self._find_and_copy_files(
                    modified_classes, fixed_path, bug_source_dir, "fixed"
                )
            
            # Construct unified data structure
            bug_data = {
                'id': f"{project}_{bug_id}",
                'project': project,
                'bug_id': bug_id,
                'BEFORE': {
                    'path': str(buggy_path),
                    'compiled': buggy_compiled,
                    'metadata': buggy_metadata,
                    'test_results': buggy_tests
                },
                'AFTER': {
                    'path': str(fixed_path),
                    'compiled': fixed_compiled,
                    'metadata': fixed_metadata,
                    'test_results': fixed_tests
                },
                'source_files': {
                    'directory': str(bug_source_dir),
                    'buggy_files_extracted': buggy_files_found,
                    'fixed_files_extracted': fixed_files_found,
                    'modified_classes': modified_classes
                },
                'processed_at': datetime.now().isoformat(),
                'language': 'java'  # Defects4J is Java only
            }
            
            return bug_data
        
        except Exception as e:
            logging.error(f"Error processing {project}-{bug_id}: {e}")
            return None
    
    def process_project(self, project: str) -> List[Dict]:
        """Process ALL bugs for a project"""
        logging.info(f"\n{'='*60}")
        logging.info(f"PROCESSING PROJECT: {project}")
        logging.info(f"{'='*60}")
        
        bug_ids = self.get_project_bugs(project)
        
        if not bug_ids:
            logging.warning(f"No bugs found for {project}")
            self.stats['by_project'][project] = {
                'total': 0,
                'processed': 0,
                'failed': 0
            }
            return []
        
        self.stats['total_bugs_found'] += len(bug_ids)
        self.stats['by_project'][project] = {
            'total': len(bug_ids),
            'processed': 0,
            'failed': 0
        }
        
        processed_bugs = []
        
        for bug_id in tqdm(bug_ids, desc=f"{project}", total=len(bug_ids)):
            bug_data = self.process_bug(project, bug_id)
            
            if bug_data:
                processed_bugs.append(bug_data)
                self.stats['total_bugs_processed'] += 1
                self.stats['by_project'][project]['processed'] += 1
            else:
                self.stats['total_bugs_failed'] += 1
                self.stats['by_project'][project]['failed'] += 1
        
        # Save project results
        project_output = self.output_dir / f"defects4j_{project}_samples.json"
        with open(project_output, 'w') as f:
            json.dump(processed_bugs, f, indent=2)
        
        logging.info(f"✓ Saved {len(processed_bugs)} bugs for {project}")
        
        return processed_bugs
    
    def process_all_projects(self) -> Dict:
        """Process ALL projects and ALL bugs"""
        logging.info("\n" + "="*60)
        logging.info("AGGRESSIVE DEFECTS4J DATA COLLECTION - NO LIMITS")
        logging.info("="*60)
        
        # Get all projects
        projects = self.get_all_projects()
        
        all_samples = []
        
        for project in projects:
            try:
                samples = self.process_project(project)
                all_samples.extend(samples)
            except Exception as e:
                logging.error(f"Fatal error processing {project}: {e}")
                continue
        
        # Save unified dataset
        output_file = self.output_dir / "defects4j_all_samples.json"
        with open(output_file, 'w') as f:
            json.dump(all_samples, f, indent=2)
        
        # Save statistics
        stats_file = self.output_dir / "defects4j_collection_stats.json"
        with open(stats_file, 'w') as f:
            json.dump(self.stats, f, indent=2)
        
        logging.info("\n" + "="*60)
        logging.info("COLLECTION COMPLETE")
        logging.info(f"Total Bugs Found: {self.stats['total_bugs_found']}")
        logging.info(f"Total Bugs Processed: {self.stats['total_bugs_processed']}")
        logging.info(f"Total Bugs Failed: {self.stats['total_bugs_failed']}")
        logging.info(f"Success Rate: {100*self.stats['total_bugs_processed']/max(self.stats['total_bugs_found'],1):.1f}%")
        logging.info(f"Output: {output_file}")
        logging.info("="*60 + "\n")
        
        return all_samples


def main():
    import yaml
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('defects4j_aggressive_collection.log'),
            logging.StreamHandler()
        ]
    )
    
    # Load config
    with open('config/config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Run aggressive collection
    processor = Defects4JAggressive(config)
    all_samples = processor.process_all_projects()
    
    print(f"\n✓ DEFECTS4J: Collected {len(all_samples)} total bug samples")


if __name__ == '__main__':
    main()
