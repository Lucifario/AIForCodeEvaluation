"""
CODE CHUNKER
File: scripts/code_chunker.py

Splits source code into semantic chunks (functions/classes) to fit LLM context windows.
Optimized for Python (AST) and Java (Brace counting).
"""

import ast
import logging
import re
from typing import List, Dict, Optional

class CodeChunker:
    """
    Splits source code into semantic chunks (functions/classes) to fit LLM context windows.
    Currently optimized for Python (AST) and Java (Regex/Brace counting).
    """

    def __init__(self, max_lines: int = 100):
        self.max_lines = max_lines
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def chunk_python(code: str, max_lines: int = 100) -> List[Dict]:
        """
        Uses Python's AST to extract functions and classes.
        
        Args:
            code: Python source code as string
            max_lines: Maximum lines per chunk
            
        Returns:
            List of chunks with metadata
        """
        chunks = []
        try:
            tree = ast.parse(code)
            lines = code.splitlines()

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    # Get start and end lines
                    start = node.lineno - 1
                    end = node.end_lineno if node.end_lineno else len(lines)
                    
                    # Extract source segment
                    segment_lines = lines[start:end]
                    chunk_content = "\n".join(segment_lines)
                    
                    chunks.append({
                        "type": type(node).__name__,
                        "name": getattr(node, 'name', 'unknown'),
                        "start_line": start + 1,
                        "end_line": end,
                        "lines": end - start,
                        "content": chunk_content,
                        "language": "python"
                    })
        
        except SyntaxError as e:
            logging.warning(f"Python Syntax Error during chunking: {e}. Falling back to file-level.")
            return [{
                "type": "file",
                "name": "full_file",
                "start_line": 1,
                "end_line": len(code.splitlines()),
                "lines": len(code.splitlines()),
                "content": code,
                "language": "python"
            }]
        
        except Exception as e:
            logging.error(f"Chunking error: {e}")
            return [{
                "type": "file",
                "name": "full_file",
                "content": code,
                "language": "python"
            }]
        
        # If no chunks found, return entire file
        if not chunks:
            return [{
                "type": "file",
                "name": "full_file",
                "lines": len(code.splitlines()),
                "content": code,
                "language": "python"
            }]
            
        return chunks

    @staticmethod
    def chunk_java(code: str, max_lines: int = 100) -> List[Dict]:
        """
        Uses regex and brace-counting to extract methods and classes for Java.
        
        Args:
            code: Java source code as string
            max_lines: Maximum lines per chunk
            
        Returns:
            List of chunks with metadata
        """
        chunks = []
        lines = code.splitlines()
        
        # Find all methods and classes using regex
        # Pattern: (public|private|protected)? (static)? (synchronized)? <return_type> <method_name>(...) {
        method_pattern = r'(public|private|protected)?\s*(static)?\s*(synchronized)?\s*[\w<>[\],\s]+\s+(\w+)\s*\([^)]*\)\s*(\{|throws)'
        class_pattern = r'(public|private)?\s*class\s+(\w+)'
        
        try:
            # Find class definitions
            for match in re.finditer(class_pattern, code):
                start_pos = match.start()
                class_name = match.group(2)
                
                # Find the opening brace
                brace_start = code.find('{', match.end())
                if brace_start == -1:
                    continue
                
                # Count braces to find the end
                brace_count = 0
                start_line = code[:brace_start].count('\n')
                
                for i, char in enumerate(code[brace_start:]):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_line = code[:brace_start + i].count('\n')
                            class_content = code[brace_start:brace_start + i + 1]
                            
                            chunks.append({
                                "type": "class",
                                "name": class_name,
                                "start_line": start_line + 1,
                                "end_line": end_line + 1,
                                "lines": end_line - start_line + 1,
                                "content": class_content,
                                "language": "java"
                            })
                            break
            
            # Find method definitions
            for match in re.finditer(method_pattern, code):
                method_name = match.group(4)
                brace_pos = code.find('{', match.end())
                
                if brace_pos == -1:
                    continue
                
                # Count braces
                brace_count = 0
                start_line = code[:brace_pos].count('\n')
                
                for i, char in enumerate(code[brace_pos:]):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_line = code[:brace_pos + i].count('\n')
                            method_content = code[brace_pos:brace_pos + i + 1]
                            
                            chunks.append({
                                "type": "method",
                                "name": method_name,
                                "start_line": start_line + 1,
                                "end_line": end_line + 1,
                                "lines": end_line - start_line + 1,
                                "content": method_content,
                                "language": "java"
                            })
                            break
        
        except Exception as e:
            logging.error(f"Java chunking error: {e}")
        
        # If no chunks found, return whole file
        if not chunks:
            return [{
                "type": "file",
                "name": "full_file",
                "lines": len(lines),
                "content": code,
                "language": "java"
            }]
        
        return chunks

    @staticmethod
    def get_chunks(code: str, language: str, max_lines: int = 100) -> List[Dict]:
        """
        Get chunks for any supported language.
        
        Args:
            code: Source code as string
            language: Programming language (python, java, etc.)
            max_lines: Maximum lines per chunk
            
        Returns:
            List of code chunks
        """
        if language.lower() in ['python', 'py']:
            return CodeChunker.chunk_python(code, max_lines)
        
        elif language.lower() in ['java']:
            return CodeChunker.chunk_java(code, max_lines)
        
        else:
            # Fallback for unknown languages - return whole file
            return [{
                "type": "file",
                "name": "full_file",
                "content": code,
                "language": language,
                "lines": len(code.splitlines())
            }]


# Test block
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test Python chunking
    python_code = """
def add(a, b):
    \"\"\"Add two numbers\"\"\"
    return a + b

def multiply(x, y):
    \"\"\"Multiply two numbers\"\"\"
    return x * y

class Calculator:
    def __init__(self):
        self.value = 0
    
    def compute(self, a, b, op):
        if op == 'add':
            return self.add(a, b)
        elif op == 'mul':
            return self.multiply(a, b)
    
    def add(self, a, b):
        return a + b
    
    def multiply(self, a, b):
        return a * b
"""
    
    print("Python Chunks:")
    chunks = CodeChunker.get_chunks(python_code, 'python')
    for chunk in chunks:
        print(f"  - {chunk['type']}: {chunk['name']} ({chunk['lines']} lines)")
    
    # Test Java chunking
    java_code = """
public class Calculator {
    private int value;
    
    public Calculator() {
        this.value = 0;
    }
    
    public int add(int a, int b) {
        return a + b;
    }
    
    public int multiply(int x, int y) {
        return x * y;
    }
}
"""
    
    print("\nJava Chunks:")
    chunks = CodeChunker.get_chunks(java_code, 'java')
    for chunk in chunks:
        print(f"  - {chunk['type']}: {chunk['name']} ({chunk['lines']} lines)")
