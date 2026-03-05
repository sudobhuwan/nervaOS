"""
NervaOS Smart Search - Lightweight Content Search
Memory-safe file indexing and search.
"""

import json
import logging
import mimetypes
import os
import re
import subprocess
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger('nerva-search')


@dataclass
class FileIndex:
    """Represents an indexed file"""
    path: str
    filename: str
    size: int
    modified: datetime
    file_type: str
    mime_type: str
    content_preview: str = ""
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    def to_dict(self):
        d = asdict(self)
        d['modified'] = self.modified.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: Dict):
        data['modified'] = datetime.fromisoformat(data['modified'])
        if 'tags' not in data:
            data['tags'] = []
        return cls(**data)


class SmartSearchEngine:
    """Memory-safe file search engine"""

    def __init__(self, ai_client=None, index_path: Path = None):
        self.ai_client = ai_client
        self.index_path = index_path or (Path.home() / '.config' / 'nervaos' / 'search_index.json')
        # Keep for compatibility/cleanup from previous versions.
        self.chunk_index_path = self.index_path.with_name('search_chunks.json')
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove legacy heavy chunk cache from older versions.
        try:
            if self.chunk_index_path.exists():
                self.chunk_index_path.unlink()
        except OSError:
            pass

        self.file_index: Dict[str, FileIndex] = {}

        self.search_paths = [
            Path.home(),
            Path.home() / '.local' / 'share' / 'applications',
            Path('/usr/share/applications'),
            Path('/usr/local/share/applications'),
        ]

        self.excluded_dirs = {
            '.cache', '.git', '.hg', '.svn', '__pycache__', 'node_modules', 'venv', '.venv',
            '.npm', '.cargo', '.rustup', '.android', '.Trash', 'Trash',
            'snap', '.local/share/Trash', '.var', '.mozilla',
        }

        self.max_index_file_size = 25 * 1024 * 1024
        self.preview_chars = 4000
        self.max_indexed_files = 30000

        self.indexed_extensions = {
            '.txt', '.md', '.pdf', '.doc', '.docx', '.odt',
            '.py', '.js', '.html', '.css', '.java', '.cpp', '.c',
            '.json', '.xml', '.yaml', '.yml', '.csv', '.xls', '.xlsx',
            '.desktop', '.conf', '.ini', '.log', '.sh', '.bash', '.zsh',
        }

        self._load_index()
        logger.info("Smart search initialized with %d indexed files", len(self.file_index))

    def _load_index(self):
        if self.index_path.exists():
            try:
                with open(self.index_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                changed = False
                for file_id, file_data in data.items():
                    fi = FileIndex.from_dict(file_data)
                    if fi.content_preview and len(fi.content_preview) > self.preview_chars:
                        fi.content_preview = fi.content_preview[:self.preview_chars]
                        changed = True
                    self.file_index[file_id] = fi

                if len(self.file_index) > self.max_indexed_files:
                    trimmed = sorted(
                        self.file_index.items(),
                        key=lambda kv: kv[1].modified,
                        reverse=True
                    )[:self.max_indexed_files]
                    self.file_index = dict(trimmed)
                    changed = True

                if changed:
                    self._save_index()

                logger.info("Loaded %d files from index", len(self.file_index))
            except Exception as e:
                logger.error("Failed to load search index: %s", e)

    def _save_index(self):
        try:
            data = {file_id: file.to_dict() for file_id, file in self.file_index.items()}
            with open(self.index_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save search index: %s", e)

    def _tokenize(self, text: str) -> Set[str]:
        return {t for t in re.findall(r"[a-zA-Z0-9_]{3,}", text.lower())}

    def _extract_text_for_indexing(self, file_path: Path, file_ext: str, max_chars: Optional[int] = None) -> str:
        limit = max_chars or self.preview_chars
        try:
            if file_ext in {'.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.xml', '.yaml', '.yml', '.ini', '.conf', '.log', '.sh', '.bash', '.zsh', '.csv'}:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read(limit)
            if file_ext == '.pdf':
                result = subprocess.run(
                    ['pdftotext', str(file_path), '-'],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return result.stdout[:limit]
        except Exception:
            return ""
        return ""

    def _categorize_file(self, ext: str, mime_type: str) -> str:
        categories = {
            'document': {'.txt', '.md', '.pdf', '.doc', '.docx', '.odt'},
            'code': {'.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.sh', '.bash', '.zsh'},
            'data': {'.json', '.xml', '.yaml', '.yml', '.csv', '.ini', '.conf', '.log'},
            'spreadsheet': {'.xls', '.xlsx'},
        }
        for category, exts in categories.items():
            if ext in exts:
                return category
        if mime_type and mime_type.startswith('text/'):
            return 'document'
        return 'other'

    def _extract_tags(self, filename: str, content: str) -> List[str]:
        tags = []
        parts = filename.lower().replace('_', ' ').replace('-', ' ').split()
        tags.extend([p for p in parts if len(p) > 2])
        if content:
            keywords = ['invoice', 'receipt', 'tax', 'report', 'contract', 'resume', 'budget', 'meeting', 'presentation']
            low = content.lower()
            for keyword in keywords:
                if keyword in low:
                    tags.append(keyword)
        return list(set(tags))

    def index_directories(self, paths: List[Path] = None, update_existing: bool = True):
        if paths is None:
            paths = self.search_paths

        indexed_count = 0
        for search_path in paths:
            if not search_path.exists():
                continue

            logger.info("Indexing: %s", search_path)
            for root, dirs, files in os.walk(search_path):
                root_path = Path(root)
                dirs[:] = [
                    d for d in dirs
                    if d not in self.excluded_dirs
                    and not str((root_path / d)).startswith('/proc')
                    and not str((root_path / d)).startswith('/sys')
                    and not str((root_path / d)).startswith('/dev')
                ]

                for filename in files:
                    if filename.startswith('.'):
                        continue

                    file_path = Path(root) / filename
                    file_ext = file_path.suffix.lower()
                    if file_ext not in self.indexed_extensions:
                        continue

                    try:
                        if not os.access(file_path, os.R_OK):
                            continue
                        file_id = hashlib.md5(str(file_path).encode()).hexdigest()
                        if file_id in self.file_index and not update_existing:
                            continue
                        stat = file_path.stat()
                        if stat.st_size > self.max_index_file_size:
                            continue
                        modified = datetime.fromtimestamp(stat.st_mtime)

                        if file_id in self.file_index:
                            if self.file_index[file_id].modified >= modified:
                                continue

                        if len(self.file_index) >= self.max_indexed_files and file_id not in self.file_index:
                            continue

                        mime_type, _ = mimetypes.guess_type(str(file_path))
                        content_preview = self._extract_text_for_indexing(file_path, file_ext, self.preview_chars)
                        file_type = self._categorize_file(file_ext, mime_type or '')

                        self.file_index[file_id] = FileIndex(
                            path=str(file_path),
                            filename=filename,
                            size=stat.st_size,
                            modified=modified,
                            file_type=file_type,
                            mime_type=mime_type or 'unknown',
                            content_preview=content_preview,
                            tags=self._extract_tags(filename, content_preview),
                        )
                        indexed_count += 1
                    except Exception as e:
                        logger.error("Failed to index %s: %s", file_path, e)

        if indexed_count > 0:
            self._save_index()
            logger.info("Indexed %d files", indexed_count)
        return indexed_count

    def _score(self, file: FileIndex, query_text: str, terms: Set[str]) -> int:
        score = 0
        filename = file.filename.lower()
        content = (file.content_preview or '').lower()
        tags = " ".join(file.tags).lower() if file.tags else ""

        if query_text and query_text in filename:
            score += 15
        if query_text and query_text in content:
            score += 12
        for term in terms:
            if term in filename:
                score += 8
            if term in tags:
                score += 5
            if term in content:
                score += 4
        if query_text and query_text in file.file_type:
            score += 2
        return score

    def _build_snippet(self, content: str, query_text: str, terms: Set[str]) -> str:
        if not content:
            return ""
        text = " ".join(content.split())
        low = text.lower()
        pos = -1
        if query_text:
            pos = low.find(query_text)
        if pos == -1:
            for term in terms:
                pos = low.find(term)
                if pos != -1:
                    break
        if pos == -1:
            return text[:220]
        start = max(0, pos - 90)
        end = min(len(text), pos + 170)
        return text[start:end]

    def search(self, query: str, max_results: int = 10) -> List[FileIndex]:
        query_text = query.lower().strip()
        terms = self._tokenize(query_text)
        results = []
        for file in self.file_index.values():
            sc = self._score(file, query_text, terms)
            if sc > 0:
                results.append((sc, file))
        results.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in results[:max_results]]

    def search_with_snippets(self, query: str, max_results: int = 10) -> List[Dict[str, str]]:
        query_text = query.lower().strip()
        terms = self._tokenize(query_text)
        scored = []
        for file in self.file_index.values():
            sc = self._score(file, query_text, terms)
            if sc > 0:
                scored.append((sc, file))
        scored.sort(key=lambda x: x[0], reverse=True)

        out = []
        for sc, fi in scored[:max_results]:
            snippet = self._build_snippet(fi.content_preview or '', query_text, terms)
            out.append({
                'path': fi.path,
                'filename': fi.filename,
                'score': str(sc),
                'snippet': snippet,
            })
        return out

    async def smart_search(self, natural_query: str, max_results: int = 10) -> List[FileIndex]:
        logger.info("Smart search: %s", natural_query)

        if self.ai_client:
            try:
                prompt = f"Analyze this query and output JSON with keys: keywords (list), file_type (string). Query: {natural_query}"
                response = await self.ai_client.ask(prompt, {})
                match = re.search(r'\{.*\}', response, re.DOTALL)
                if match:
                    params = json.loads(match.group())
                    keywords = params.get('keywords', []) or []
                    file_type = (params.get('file_type') or '').lower()
                    q = " ".join([natural_query] + [str(k) for k in keywords])
                    ranked = self.search(q, max_results=max_results * 2)
                    if file_type:
                        ranked = sorted(
                            ranked,
                            key=lambda f: (1 if f.file_type == file_type else 0),
                            reverse=True,
                        )
                    return ranked[:max_results]
            except Exception as e:
                logger.error("AI search failed: %s", e)

        return self.search(natural_query, max_results)

    def get_file_content(self, file_path: str, max_chars: int = 5000) -> Optional[str]:
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            return self._extract_text_for_indexing(path, path.suffix.lower(), max_chars)
        except Exception as e:
            logger.error("Failed to get content for %s: %s", file_path, e)
            return None

    def add_search_path(self, path: Path):
        if path not in self.search_paths:
            self.search_paths.append(path)
            logger.info("Added search path: %s", path)

    def remove_search_path(self, path: Path):
        if path in self.search_paths:
            self.search_paths.remove(path)
            logger.info("Removed search path: %s", path)

    def clear_index(self):
        self.file_index.clear()
        self._save_index()
        try:
            if self.chunk_index_path.exists():
                self.chunk_index_path.unlink()
        except OSError:
            pass
        logger.info("Search index cleared")
