"""
QODO INTEGRATION
File: scripts/qodo_integration.py

Wrapper for the Qodo (Codium) CLI tool to generate code reviews.
Assumes 'qodo' is installed and accessible in the system PATH.
"""

import subprocess
import logging
import json
import os
from pathlib import Path
from typing import Dict, Optional

class QodoClient:
    """
    Wrapper for the Qodo (Codium) CLI tool to generate code reviews.
    Assumes 'qodo' is installed and accessible in the system PATH.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._verify_installation()

    def _verify_installation(self):
        """Check if qodo CLI is installed."""
        try:
            result = subprocess.run(['qodo', '--help'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.logger.info("✓ Qodo CLI found and accessible")
            else:
                self.logger.warning("Qodo CLI returned error. Install with: pip install qodo-cli")
        except FileNotFoundError:
            self.logger.warning("Qodo CLI executable not found in PATH. Install with: pip install qodo-cli")
        except Exception as e:
            self.logger.warning(f"Could not verify Qodo: {e}")

    def review_file(self, file_path: str) -> Optional[Dict]:
        """
        Runs 'qodo review' on a specific file.
        
        Args:
            file_path: Path to the code file to review.
            
        Returns:
            Dict containing the review output or None if failed.
        """
        if not os.path.exists(file_path):
            self.logger.error(f"File not found: {file_path}")
            return None

        try:
            # Run the review command
            cmd = ['pr-agent', 'review', file_path, '--output', 'json']
            
            self.logger.info(f"Running Qodo on: {file_path}")
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=120  # 2 minute timeout per file
            )

            if result.returncode == 0:
                return {
                    "raw_output": result.stdout,
                    "tool": "qodo-cli",
                    "status": "success",
                    "file_path": file_path
                }
            else:
                self.logger.error(f"Qodo failed on {file_path}: {result.stderr}")
                return {
                    "raw_output": result.stderr,
                    "tool": "qodo-cli",
                    "status": "failed",
                    "file_path": file_path
                }

        except subprocess.TimeoutExpired:
            self.logger.error(f"Qodo timed out on {file_path}")
            return {
                "error": "timeout", 
                "status": "failed",
                "file_path": file_path
            }
        except Exception as e:
            self.logger.error(f"Error running Qodo: {e}")
            return {
                "error": str(e), 
                "status": "failed",
                "file_path": file_path
            }

    def review_code_string(self, code: str, language: str = "python") -> Optional[Dict]:
        """
        Reviews code by writing it to a temp file and running qodo on it.
        
        Args:
            code: Code content as string
            language: Programming language (python, java, etc.)
            
        Returns:
            Dict containing the review output or None if failed.
        """
        # Create temp file with appropriate extension
        ext_map = {
            'python': '.py',
            'java': '.java',
            'javascript': '.js',
            'typescript': '.ts',
            'cpp': '.cpp',
            'c': '.c'
        }
        
        ext = ext_map.get(language.lower(), '.txt')
        temp_file = Path(f"/tmp/qodo_review_{hash(code)}{ext}")
        
        try:
            # Write code to temp file
            with open(temp_file, 'w') as f:
                f.write(code)
            
            # Review the temp file
            result = self.review_file(str(temp_file))
            
            return result
            
        finally:
            # Clean up temp file
            if temp_file.exists():
                temp_file.unlink()


# Test block
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test 1: Create a dummy file to test
    test_file = Path("test_qodo.py")
    with open(test_file, "w") as f:
        f.write("""def add(a, b):
    \"\"\"Add two numbers\"\"\"
    return a - b  # BUG: Should be a + b
    
def process_data(data):
    result = []
    for item in data:
        if item is None:  # Potential bug - no null handling
            result.append(item.upper())  # Will crash
    return result
""")
    
    client = QodoClient()
    print("Testing Qodo on file:")
    result = client.review_file(str(test_file))
    print(json.dumps(result, indent=2))
    
    # Clean up
    test_file.unlink()
