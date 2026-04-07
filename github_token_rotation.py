"""
GitHub Token Rotation System
Manages multiple GitHub tokens to increase rate limit from 5,000/h to 20,000/h
"""

import os
import requests
import time
import logging
from datetime import datetime
from typing import List, Dict
from dotenv import load_dotenv

# Load environment variables with override
load_dotenv('.env', override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [github] %(message)s")
logger = logging.getLogger("github_rotation")

class GitHubTokenManager:
    """Manages rotation of multiple GitHub tokens."""
    
    def __init__(self):
        self.tokens = self._load_tokens()
        self.current_token_index = 0
        self.token_stats = {token: {'remaining': 5000, 'reset_time': 0} for token in self.tokens}
        logger.info(f"Initialized with {len(self.tokens)} GitHub tokens")
    
    def _load_tokens(self) -> List[str]:
        """Load GitHub tokens from environment variables."""
        tokens = []
        
        # Primary token
        primary = os.getenv('GITHUB_TOKEN')
        if primary:
            tokens.append(primary)
        
        # Additional tokens (to be added by Anders)
        for i in range(2, 5):  # GITHUB_TOKEN_2, GITHUB_TOKEN_3, GITHUB_TOKEN_4
            token = os.getenv(f'GITHUB_TOKEN_{i}')
            if token:
                tokens.append(token)
        
        if not tokens:
            raise ValueError("No GitHub tokens found in environment variables")
            
        return tokens
    
    def get_next_token(self) -> str:
        """Get next available token with rate limit capacity."""
        # Try each token starting from current index
        for i in range(len(self.tokens)):
            token_index = (self.current_token_index + i) % len(self.tokens)
            token = self.tokens[token_index]
            
            # Check if token has capacity
            if self.token_stats[token]['remaining'] > 10:  # Keep buffer
                self.current_token_index = token_index
                return token
            
            # Check if reset time has passed
            if time.time() > self.token_stats[token]['reset_time']:
                logger.info(f"Token {token_index + 1} rate limit reset")
                self.token_stats[token]['remaining'] = 5000
                self.current_token_index = token_index
                return token
        
        # All tokens exhausted - use current and log warning
        logger.warning("All tokens exhausted, using current token anyway")
        return self.tokens[self.current_token_index]
    
    def update_rate_limit(self, token: str, response: requests.Response):
        """Update rate limit stats from API response headers."""
        if response.headers.get('X-RateLimit-Remaining'):
            remaining = int(response.headers['X-RateLimit-Remaining'])
            reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
            
            self.token_stats[token] = {
                'remaining': remaining,
                'reset_time': reset_time
            }
            
            if remaining < 100:
                logger.warning(f"Token {self.tokens.index(token) + 1} low: {remaining} requests remaining")
    
    def get_headers(self) -> Dict[str, str]:
        """Get headers with current token."""
        token = self.get_next_token()
        return {
            'Authorization': f'token {token}',
            'User-Agent': 'AgentIndex/1.0 (https://agentcrawl.dev)',
            'Accept': 'application/vnd.github.v3+json'
        }
    
    def make_request(self, url: str, params: dict = None) -> requests.Response:
        """Make GitHub API request with automatic token rotation."""
        max_retries = len(self.tokens)
        
        for attempt in range(max_retries):
            token = self.get_next_token()
            headers = {
                'Authorization': f'token {token}',
                'User-Agent': 'AgentIndex/1.0 (https://agentcrawl.dev)',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            try:
                response = requests.get(url, params=params, headers=headers)
                self.update_rate_limit(token, response)
                
                if response.status_code == 403 and 'rate limit' in response.text.lower():
                    logger.warning(f"Rate limit hit on token {self.tokens.index(token) + 1}, rotating...")
                    self.token_stats[token]['remaining'] = 0
                    continue
                
                response.raise_for_status()
                return response
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed on token {self.tokens.index(token) + 1}: {e}")
                if attempt == max_retries - 1:
                    raise
                continue
        
        raise Exception("All tokens failed")
    
    def get_status(self) -> Dict:
        """Get current status of all tokens."""
        status = {}
        for i, token in enumerate(self.tokens):
            stats = self.token_stats[token]
            status[f"token_{i+1}"] = {
                'remaining': stats['remaining'],
                'reset_time': datetime.fromtimestamp(stats['reset_time']).isoformat() if stats['reset_time'] else None,
                'active': i == self.current_token_index
            }
        
        return status

# Global token manager instance
token_manager = None

def get_token_manager() -> GitHubTokenManager:
    """Get global token manager instance."""
    global token_manager
    if token_manager is None:
        token_manager = GitHubTokenManager()
    return token_manager

if __name__ == "__main__":
    # Test token rotation
    try:
        manager = GitHubTokenManager()
        print(f"Loaded {len(manager.tokens)} tokens")
        
        # Test API call
        response = manager.make_request("https://api.github.com/rate_limit")
        print(f"Rate limit test: {response.status_code}")
        print(f"Current status: {manager.get_status()}")
        
    except Exception as e:
        print(f"Error: {e}")
        print("\\nTo enable token rotation, add to .env:")
        print("GITHUB_TOKEN_2=ghp_...")
        print("GITHUB_TOKEN_3=ghp_...")  
        print("GITHUB_TOKEN_4=ghp_...")