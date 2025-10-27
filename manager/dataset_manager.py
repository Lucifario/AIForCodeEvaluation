import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict


class DatasetManager:
    def __init__(self, config: Dict):
        self.config = config
        self.version_file = Path(config['data']['version_file'])
        self.version_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.version_data = self._load_version()

    def _load_version(self) -> Dict:
        """Load current version data"""
        if self.version_file.exists():
            with open(self.version_file, 'r') as f:
                return json.load(f)
        return {
            'version': '1.0.0',
            'created_at': datetime.now().isoformat(),
            'updates': []
        }

    def increment_version(self, update_type: str = 'minor'):
        """Increment version number"""
        version_parts = self.version_data['version'].split('.')
        major, minor, patch = map(int, version_parts)
        
        if update_type == 'major':
            major += 1
            minor = 0
            patch = 0
        elif update_type == 'minor':
            minor += 1
            patch = 0
        else:
            patch += 1
        
        self.version_data['version'] = f"{major}.{minor}.{patch}"

    def log_update(self, source: str, count: int, details: Dict = None):
        """Log a dataset update"""
        update_entry = {
            'timestamp': datetime.now().isoformat(),
            'source': source,
            'count': count,
            'version': self.version_data['version'],
            'details': details or {}
        }
        
        self.version_data['updates'].append(update_entry)
        self._save_version()
        
        logging.info(f"Logged update: {source} added {count} items (v{self.version_data['version']})")

    def _save_version(self):
        """Save version data to disk"""
        with open(self.version_file, 'w') as f:
            json.dump(self.version_data, f, indent=2)

    def get_statistics(self) -> Dict:
        """Get dataset statistics"""
        data_dir = Path(self.config['data']['output_base'])
        
        stats = {
            'version': self.version_data['version'],
            'defects4j_bugs': len(list((data_dir / 'defects4j_bugs').glob('*_metadata.json'))) if (data_dir / 'defects4j_bugs').exists() else 0,
            'github_prs': len(list((data_dir / 'github_prs').rglob('pr_*.json'))) if (data_dir / 'github_prs').exists() else 0,
            'synthetic_bugs': len(list((data_dir / 'synthetic_bugs').rglob('*_mutant_*'))) if (data_dir / 'synthetic_bugs').exists() else 0,
            'total_updates': len(self.version_data['updates']),
            'last_update': self.version_data['updates'][-1]['timestamp'] if self.version_data['updates'] else None
        }
        
        return stats


def main():
    import yaml
    
    with open('config/config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    manager = DatasetManager(config)
    stats = manager.get_statistics()
    
    print("\nDataset Statistics:")
    print(json.dumps(stats, indent=2))


if __name__ == '__main__':
    main()