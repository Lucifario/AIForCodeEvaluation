import os
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Optional
from tqdm import tqdm

class SyntheticBugInjector:
    def __init__(self, config: Dict):
        self.config = config
        self.output_dir = Path(config['synthetic']['output_dir'])
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def find_python_files(self, directory: Path) -> List[Path]:
        """Find all Python files in directory"""
        return list(directory.rglob('*.py'))

    def find_java_files(self, directory: Path) -> List[Path]:
        """Find all Java files in directory"""
        return list(directory.rglob('*.java'))

    def inject_python_mutations(self, source_file: Path) -> List[Dict]:
        """Inject mutations into Python file using MutPy"""
        mutations = []
        
        try:
            file_output_dir = self.output_dir / 'python' / source_file.stem
            file_output_dir.mkdir(parents=True, exist_ok=True)
            
            result = subprocess.run(
                [
                    'mut.py',
                    '--target', str(source_file),
                    '--unit-test', str(source_file.parent / 'test_*.py'),
                    '--runner', 'pytest',
                    '--report-json', str(file_output_dir / 'mutations.json')
                ],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            mutation_file = file_output_dir / 'mutations.json'
            if mutation_file.exists():
                with open(mutation_file, 'r') as f:
                    mutation_data = json.load(f)
                    mutations = mutation_data.get('mutations', [])
            
            logging.info(f"Generated {len(mutations)} mutations for {source_file.name}")
            return mutations
            
        except Exception as e:
            logging.error(f"Error injecting Python mutations: {e}")
            return []

    def inject_java_mutations(self, source_dir: Path, class_name: str) -> List[Dict]:
        """Inject mutations into Java file using PIT"""
        mutations = []
        
        try:
            output_dir = self.output_dir / 'java' / class_name
            output_dir.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    'mvn',
                    'org.pitest:pitest-maven:mutationCoverage',
                    f'-DtargetClasses={class_name}',
                    f'-DreportsDirectory={output_dir}'
                ],
                cwd=source_dir,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            return mutations
            
        except Exception as e:
            logging.error(f"Error injecting Java mutations: {e}")
            return []

    def inject_manual_bugs(self, source_file: Path) -> List[Dict]:
        """Inject predefined bug patterns manually"""
        bugs = []
        
        try:
            with open(source_file, 'r') as f:
                content = f.read()
                lines = content.split('\n')
            
            for i, line in enumerate(lines):
                if 'for i in range(' in line:
                    mutated = line.replace('range(', 'range(1, ')
                    bugs.append({
                        'type': 'off_by_one',
                        'line': i + 1,
                        'original': line,
                        'mutated': mutated
                    })
            
            for i, line in enumerate(lines):
                if 'if ' in line and '!= None' in line:
                    mutated = line.replace('!= None', '')
                    bugs.append({
                        'type': 'missing_null_check',
                        'line': i + 1,
                        'original': line,
                        'mutated': mutated
                    })
            
            for i, line in enumerate(lines):
                if 'if ' in line:
                    if ' and ' in line:
                        mutated = line.replace(' and ', ' or ')
                        bugs.append({
                            'type': 'logic_inversion',
                            'line': i + 1,
                            'original': line,
                            'mutated': mutated
                        })
            
            for idx, bug in enumerate(bugs[:self.config['synthetic']['max_mutants_per_file']]):
                mutated_file = self.output_dir / f"{source_file.stem}_mutant_{idx}{source_file.suffix}"
                mutated_lines = lines.copy()
                mutated_lines[bug['line'] - 1] = bug['mutated']
                
                with open(mutated_file, 'w') as f:
                    f.write('\n'.join(mutated_lines))
                
                bug['mutated_file'] = str(mutated_file)
            
            return bugs
            
        except Exception as e:
            logging.error(f"Error injecting manual bugs: {e}")
            return []

    def process_directory(self, source_dir: Path, language: str = 'python'):
        """Process all files in directory and inject bugs"""
        if language == 'python':
            files = self.find_python_files(source_dir)
            inject_func = self.inject_manual_bugs
        elif language == 'java':
            files = self.find_java_files(source_dir)
            inject_func = self.inject_manual_bugs
        else:
            logging.error(f"Unsupported language: {language}")
            return
        
        all_bugs = []
        for file in tqdm(files, desc=f"Injecting bugs ({language})"):
            bugs = inject_func(file)
            all_bugs.extend(bugs)
        
        summary_file = self.output_dir / f"{language}_bugs_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(all_bugs, f, indent=2)
        
        logging.info(f"Injected {len(all_bugs)} synthetic bugs for {language}")


def main():
    import yaml
    
    with open('config/config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    injector = SyntheticBugInjector(config)
    
    defects4j_dir = Path(config['defects4j']['checkout_dir'])
    for project_dir in defects4j_dir.glob('*_f'):
        if project_dir.is_dir():
            injector.process_directory(project_dir, 'java')


if __name__ == '__main__':
    main()