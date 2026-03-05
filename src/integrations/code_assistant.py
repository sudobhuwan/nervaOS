"""
NervaOS Code Assistant
Provides code analysis, git integration, and development tools.
"""

import logging
import subprocess
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import re

logger = logging.getLogger('nerva-code')


@dataclass
class GitStatus:
    """Git repository status"""
    branch: str
    staged: List[str]
    unstaged: List[str]
    untracked: List[str]
    ahead: int
    behind: int
    
    def to_dict(self):
        return {
            'branch': self.branch,
            'staged': self.staged,
            'unstaged': self.unstaged,
            'untracked': self.untracked,
            'ahead': self.ahead,
            'behind': self.behind
        }


@dataclass
class ProjectInfo:
    """Project information"""
    name: str
    path: str
    language: str
    framework: Optional[str]
    files_count: int
    
    def to_dict(self):
        return {
            'name': self.name,
            'path': self.path,
            'language': self.language,
            'framework': self.framework,
            'files_count': self.files_count
        }


class CodeAssistant:
    """AI-powered code assistant with git integration"""
    
    def __init__(self, ai_client=None):
        self.ai_client = ai_client
        self.current_project = None
    
    def get_git_status(self, path: str = None) -> Optional[GitStatus]:
        """Get git status for a repository"""
        if not path:
            path = os.getcwd()
        
        try:
            # Check if it's a git repo
            result = subprocess.run(
                ['git', 'rev-parse', '--is-inside-work-tree'],
                cwd=path,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return None
            
            # Get branch name
            branch_result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=path,
                capture_output=True,
                text=True
            )
            branch = branch_result.stdout.strip()
            
            # Get status
            status_result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=path,
                capture_output=True,
                text=True
            )
            
            staged = []
            unstaged = []
            untracked = []
            
            for line in status_result.stdout.splitlines():
                if not line:
                    continue
                
                status_code = line[:2]
                filename = line[3:]
                
                if status_code[0] in ['M', 'A', 'D', 'R', 'C']:
                    staged.append(filename)
                if status_code[1] in ['M', 'D']:
                    unstaged.append(filename)
                if status_code == '??':
                    untracked.append(filename)
            
            # Get ahead/behind
            ahead = 0
            behind = 0
            try:
                rev_result = subprocess.run(
                    ['git', 'rev-list', '--left-right', '--count', f'{branch}...@{{u}}'],
                    cwd=path,
                    capture_output=True,
                    text=True
                )
                if rev_result.returncode == 0:
                    counts = rev_result.stdout.strip().split()
                    if len(counts) == 2:
                        ahead = int(counts[0])
                        behind = int(counts[1])
            except:
                pass
            
            return GitStatus(
                branch=branch,
                staged=staged,
                unstaged=unstaged,
                untracked=untracked,
                ahead=ahead,
                behind=behind
            )
            
        except Exception as e:
            logger.error(f"Failed to get git status: {e}")
            return None
    
    def get_git_log(self, path: str = None, n: int = 5) -> List[Dict[str, str]]:
        """Get recent git commits"""
        if not path:
            path = os.getcwd()
        
        try:
            result = subprocess.run(
                ['git', 'log', f'-{n}', '--pretty=format:%h|%an|%ar|%s'],
                cwd=path,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return []
            
            commits = []
            for line in result.stdout.splitlines():
                parts = line.split('|', 3)
                if len(parts) == 4:
                    commits.append({
                        'hash': parts[0],
                        'author': parts[1],
                        'time': parts[2],
                        'message': parts[3]
                    })
            
            return commits
            
        except Exception as e:
            logger.error(f"Failed to get git log: {e}")
            return []
    
    def detect_project(self, path: str = None) -> Optional[ProjectInfo]:
        """Detect project type and framework"""
        if not path:
            path = os.getcwd()
        
        path_obj = Path(path)
        
        # Detect language and framework
        language = "Unknown"
        framework = None
        
        # Check for Python
        if (path_obj / 'requirements.txt').exists() or (path_obj / 'setup.py').exists():
            language = "Python"
            if (path_obj / 'manage.py').exists():
                framework = "Django"
            elif (path_obj / 'app.py').exists() or (path_obj / 'application.py').exists():
                framework = "Flask"
            elif (path_obj / 'pyproject.toml').exists():
                framework = "Poetry"
        
        # Check for Node.js
        elif (path_obj / 'package.json').exists():
            language = "JavaScript/TypeScript"
            try:
                import json
                with open(path_obj / 'package.json') as f:
                    pkg = json.load(f)
                    deps = pkg.get('dependencies', {})
                    
                    if 'react' in deps:
                        framework = "React"
                    elif 'vue' in deps:
                        framework = "Vue.js"
                    elif 'next' in deps:
                        framework = "Next.js"  
                    elif 'express' in deps:
                        framework = "Express.js"
            except:
                pass
        
        # Check for Go
        elif (path_obj / 'go.mod').exists():
            language = "Go"
        
        # Check for Rust
        elif (path_obj / 'Cargo.toml').exists():
            language = "Rust"
        
        # Count files
        files_count = sum(1 for _ in path_obj.rglob('*') if _.is_file())
        
        return ProjectInfo(
            name=path_obj.name,
            path=str(path_obj),
            language=language,
            framework=framework,
            files_count=files_count
        )
    
    async def explain_code(self, code: str, language: str = None) -> str:
        """Explain code using AI"""
        if not self.ai_client:
            return "AI client not available"
        
        try:
            prompt = f"""Explain this code clearly and concisely:

```{language or 'code'}
{code}
```

Provide:
1. What it does (1-2 sentences)
2. Key logic/algorithms
3. Any potential issues or improvements

Keep it brief and clear."""
            
            explanation = await self.ai_client.ask(prompt, {})
            return explanation
            
        except Exception as e:
            logger.error(f"Failed to explain code: {e}")
            return f"Failed to explain code: {str(e)}"
    
    async def find_bugs(self, code: str, language: str = None) -> str:
        """Find potential bugs in code"""
        if not self.ai_client:
            return "AI client not available"
        
        try:
            prompt = f"""Analyze this {language or 'code'} for bugs and issues:

```{language or 'code'}
{code}
```

List:
1. Bugs (syntax, logic, runtime errors)
2. Security issues
3. Performance problems
4. Best practice violations

Be specific and concise."""
            
            analysis = await self.ai_client.ask(prompt, {})
            return analysis
            
        except Exception as e:
            logger.error(f"Failed to analyze code: {e}")
            return f"Failed to analyze code: {str(e)}"
    
    def get_diff(self, path: str = None, file: str = None) -> str:
        """Get git diff"""
        if not path:
            path = os.getcwd()
        
        try:
            cmd = ['git', 'diff']
            if file:
                cmd.append(file)
            
            result = subprocess.run(
                cmd,
                cwd=path,
                capture_output=True,
                text=True
            )
            
            return result.stdout
            
        except Exception as e:
            logger.error(f"Failed to get diff: {e}")
            return f"Error: {str(e)}"
