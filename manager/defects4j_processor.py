import os
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Optional
from tqdm import tqdm
import shutil

class Defects4JProcessor:
    def __init__(self, config: Dict):
        self.config = config
        self.defects4j_path = Path(config['defects4j']['base_path']).expanduser()
        self.checkout_dir = Path(config['defects4j']['checkout_dir'])
        self.checkout_dir.mkdir(parents=True, exist_ok=True)
        
        os.environ["PATH"] += os.pathsep + str(self.defects4j_path / 'framework' / 'bin')
        os.environ["TZ"] = "America/Los_Angeles"

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
                raise Exception("Defects4J not properly configured in PATH or installation error.")
            logging.info("Defects4J installation verified")
        except Exception as e:
            logging.error(f"Defects4J verification failed: {e}")
            raise

    def get_project_bugs(self, project: str) -> List[int]:
        """Get list of bug IDs for a project"""
        try:
            result = subprocess.run(
                ['defects4j', 'bids', '-p', project],
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8'
            )
            if result.returncode == 0:
                bug_ids = [int(bid.strip()) for bid in result.stdout.strip().split('\n') if bid.strip()]
                
                max_bugs = self.config['defects4j'].get('max_bugs_per_project')
                if max_bugs:
                    return bug_ids[:max_bugs]
                return bug_ids
            return []
        except Exception as e:
            logging.error(f"Error getting bugs for {project}: {e}")
            return []

    def checkout_bug(self, project: str, bug_id: int, version: str = 'b') -> Optional[Path]:
        """Checkout a specific bug version (b=buggy, f=fixed)"""
        checkout_path = self.checkout_dir / f"{project}_{bug_id}{version}"

        if checkout_path.exists():
            logging.info(f"Bug {project}-{bug_id}{version} already checked out")
            return checkout_path

        try:
            logging.info(f"Checking out {project}-{bug_id}{version} to {checkout_path}...")
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
                logging.info(f"Checked out {project}-{bug_id}{version}")
                return checkout_path
            else:
                logging.error(f"Checkout failed for {project}-{bug_id}{version}: {result.stderr}")
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
            if result.returncode != 0:
                logging.warning(f"Compilation failed for {checkout_path.name}: {result.stderr}")
            return result.returncode == 0
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
                'stdout': result.stdout,
                'stderr': result.stderr
            }
        except Exception as e:
            logging.error(f"Test execution error in {checkout_path.name}: {e}")
            return {'error': str(e)}

    def export_metadata(self, checkout_path: Path) -> Dict:
        """Export bug metadata from a checked-out directory"""
        metadata = {}
        properties = ['classes.modified', 'tests.trigger', 'dir.src.classes']

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
                    logging.warning(f"Could not export '{prop}' for {checkout_path.name}")
            except Exception as e:
                logging.error(f"Error exporting '{prop}' for {checkout_path.name}: {e}")
                metadata[prop] = []
        return metadata

    def generate_diff(self, project: str, bug_id: int) -> Optional[str]:
        """Generate diff between buggy and fixed versions"""
        buggy_path = self.checkout_dir / f"{project}_{bug_id}b"
        fixed_path = self.checkout_dir / f"{project}_{bug_id}f"

        if not buggy_path.exists() or not fixed_path.exists():
            logging.error(f"Cannot generate diff for {project}-{bug_id}: missing checkout directories")
            return None

        try:
            result = subprocess.run(
                ['git', 'diff', '--no-index', str(buggy_path), str(fixed_path)],
                capture_output=True,
                text=True,
                timeout=60,
                encoding='utf-8',
                errors='ignore'
            )
            if result.returncode in [0, 1]:
                return result.stdout
            else:
                logging.error(f"git diff failed: {result.stderr}")
                return None
        except Exception as e:
            logging.error(f"Error generating diff: {e}")
            return None

    def _find_and_copy_files(self, modified_classes: List[str], src_dir: Path, dest_dir: Path, suffix: str):
        """
        Finds modified class files in common Java source dirs and copies them.
        """
        common_src_dirs = ['src/main/java', 'src/java', 'src', 'source']
        found_count = 0
        
        for class_name in modified_classes:
            relative_path = class_name.replace('.', '/') + ".java"
            found = False
            
            for common_dir in common_src_dirs:
                src_file = src_dir / common_dir / relative_path
                if src_file.exists():
                    dest_file = dest_dir / f"{class_name}_{suffix}.java"
                    shutil.copy(src_file, dest_file)
                    found = True
                    break
            
            if not found:
                found_files = list(src_dir.rglob(relative_path))
                if found_files:
                    src_file = found_files[0]
                    dest_file = dest_dir / f"{class_name}_{suffix}.java"
                    shutil.copy(src_file, dest_file)
                    found = True
                else:
                    logging.warning(f"Could not find file for class '{class_name}' in {src_dir}")
            
            if found:
                found_count += 1
        
        return found_count


    def process_project(self, project: str):
        """Process all bugs for a project"""
        logging.info(f"Processing project: {project}")
        bug_ids = self.get_project_bugs(project)

        processed_count = 0
        for bug_id in tqdm(bug_ids, desc=f"Processing {project}"):
            buggy_path = self.checkout_bug(project, bug_id, 'b')
            if not buggy_path:
                continue

            fixed_path = self.checkout_bug(project, bug_id, 'f')
            if not fixed_path:
                continue

            buggy_compiled = self.compile_bug(buggy_path)
            fixed_compiled = self.compile_bug(fixed_path)

            buggy_metadata = self.export_metadata(buggy_path)
            fixed_metadata = self.export_metadata(fixed_path)

            diff = self.generate_diff(project, bug_id)
            
            bug_source_dir = self.checkout_dir / f"{project}_{bug_id}_source"
            bug_source_dir.mkdir(parents=True, exist_ok=True)

            modified_classes = buggy_metadata.get('classes.modified', [])
            if not modified_classes:
                 logging.warning(f"No modified classes found for {project}-{bug_id}b. Skipping file copy.")
                 continue 

            self._find_and_copy_files(
                modified_classes, 
                buggy_path, 
                bug_source_dir, 
                "buggy"
            )
            
            self._find_and_copy_files(
                modified_classes, 
                fixed_path, 
                bug_source_dir, 
                "fixed"
            )

            bug_data = {
                'project': project,
                'bug_id': bug_id,
                'buggy_compiled': buggy_compiled,
                'fixed_compiled': fixed_compiled,
                'buggy_metadata': buggy_metadata,
                'fixed_metadata': fixed_metadata,
                'diff': diff,
                'source_files_path': str(bug_source_dir)
            }

            output_file = self.checkout_dir / f"{project}_{bug_id}_metadata.json"
            with open(output_file, 'w') as f:
                json.dump(bug_data, f, indent=2)

            processed_count += 1
                
        logging.info(f"Processed {processed_count} bugs for {project}")
        return processed_count

    def process_all_projects(self):
        """Process all configured projects"""
        total_processed = 0
        for project in self.config['defects4j']['projects']:
            total_processed += self.process_project(project)
        logging.info(f"Total Defects4J bugs processed: {total_processed}")


def main():
    import yaml

    with open('config/config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    processor = Defects4JProcessor(config)
    processor.process_all_projects()

if __name__ == '__main__':
    main()