"""
NervaOS Web Search Integration
Enables web search with AI-powered result summarization.
"""

import logging
import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass
import json

logger = logging.getLogger('nerva-websearch')

try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False
    logger.warning("ddgs not installed. Run: pip install ddgs")


@dataclass
class SearchResult:
    """Represents a web search result"""
    title: str
    url: str
    snippet: str
    
    def to_dict(self):
        return {
            'title': self.title,
            'url': self.url,
            'snippet': self.snippet
        }


class WebSearchEngine:
    """Web search with AI summarization"""
    
    def __init__(self, ai_client=None):
        self.ai_client = ai_client
        self.ddgs = DDGS() if DDGS_AVAILABLE else None
    
    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """
        Search the web for a query.
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            
        Returns:
            List of SearchResult objects
        """
        if not DDGS_AVAILABLE:
            logger.error("DuckDuckGo search not available")
            return []
        
        try:
            logger.info(f"Web search: {query}")
            
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: list(self.ddgs.text(query, max_results=max_results))
            )
            
            search_results = []
            for r in results:
                search_results.append(SearchResult(
                    title=r.get('title', ''),
                    url=r.get('href', ''),
                    snippet=r.get('body', '')
                ))
            
            logger.info(f"Found {len(search_results)} results")
            return search_results
            
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return []
    
    async def search_and_summarize(self, query: str, max_results: int = 5) -> Dict[str, any]:
        """
        Search the web and provide an AI summary.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            Dict with 'results' and 'summary'
        """
        results = await self.search(query, max_results)
        
        if not results:
            return {
                'results': [],
                'summary': 'No results found.'
            }
        
        # If AI client available, generate summary
        summary = ""
        if self.ai_client:
            try:
                # Prepare context for AI
                results_text = "\n\n".join([
                    f"**{i+1}. {r.title}**\n{r.snippet}\nURL: {r.url}"
                    for i, r in enumerate(results)
                ])
                
                summary_prompt = f"""You searched for: "{query}"

Here are the top search results:

{results_text}

Please provide a concise summary (2-3 sentences) of what these results tell us about "{query}". 
Focus on the key information and insights."""
                
                summary = await self.ai_client.ask(summary_prompt, {})
                
            except Exception as e:
                logger.error(f"Failed to generate summary: {e}")
                summary = "Summary generation failed."
        else:
            summary = f"Found {len(results)} results for '{query}'"
        
        return {
            'results': results,
            'summary': summary
        }
    
    async def quick_answer(self, question: str) -> str:
        """
        Get a quick answer to a question by searching and summarizing.
        
        Args:
            question: Question to answer
            
        Returns:
            AI-generated answer based on search results
        """
        results = await self.search(question, max_results=3)
        
        if not results or not self.ai_client:
            return "Unable to find an answer."
        
        try:
            # Prepare context
            context = "\n\n".join([
                f"Source {i+1}: {r.title}\n{r.snippet}"
                for i, r in enumerate(results)
            ])
            
            answer_prompt = f"""Question: {question}

I found these sources:

{context}

Based on these sources, please provide a clear, concise answer to the question. 
If the sources don't contain enough information, say so.
Cite sources by number (e.g., "According to Source 1...")."""
            
            answer = await self.ai_client.ask(answer_prompt, {})
            return answer
            
        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            return "Failed to generate answer."
    
    def is_available(self) -> bool:
        """Check if web search is available"""
        return DDGS_AVAILABLE
