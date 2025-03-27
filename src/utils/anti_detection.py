import time
import random
import logging
from datetime import datetime, timedelta
import json
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class SessionManager:
    """Manages browser session behavior to avoid detection"""
    
    def __init__(self, session_file_path="session_data.json"):
        self.session_file = Path(session_file_path)
        self.session_data = self._load_session_data()
        self.request_times = []
        self.total_requests_today = self._get_requests_today()
        
    def _load_session_data(self):
        if not self.session_file.exists():
            return {"last_session": None, "daily_requests": {}, "sites_visited": {}}
        try:
            with open(self.session_file, 'r') as f:
                return json.load(f)
        except:
            return {"last_session": None, "daily_requests": {}, "sites_visited": {}}
            
    def _save_session_data(self):
        with open(self.session_file, 'w') as f:
            json.dump(self.session_data, f)
            
    def _get_requests_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return self.session_data["daily_requests"].get(today, 0)
        
    def start_session(self):
        """Start a new browsing session with natural timing"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        last_session = self.session_data["last_session"]
        
        # If we had a recent session, add a natural break
        if last_session:
            last_time = datetime.strptime(last_session, "%Y-%m-%d %H:%M:%S")
            time_since_last = datetime.now() - last_time
            
            if time_since_last < timedelta(hours=1):
                # Very short break - might look suspicious
                natural_break = random.uniform(15, 45)
                logger.info(f"Taking a short {natural_break:.1f}s break between sessions")
                #TODO: Change back
                #time.sleep(natural_break)
        
        self.session_data["last_session"] = now
        self._save_session_data()
        logger.info(f"Started new browsing session at {now}")
        
    def record_request(self, url):
        """Record a request to help manage rate limiting"""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        
        # Add to request times for rate limiting
        self.request_times.append(now)
        
        # Clean old requests (older than 1 hour)
        self.request_times = [t for t in self.request_times 
                              if (now - t).total_seconds() < 3600]
        
        # Update daily counts
        if today not in self.session_data["daily_requests"]:
            self.session_data["daily_requests"][today] = 0
        self.session_data["daily_requests"][today] += 1
        self.total_requests_today += 1
        
        # Track site-specific visits
        domain = url.split("//")[-1].split("/")[0]
        if domain not in self.session_data["sites_visited"]:
            self.session_data["sites_visited"][domain] = 0
        self.session_data["sites_visited"][domain] += 1
        
        # Save updated data
        if random.random() < 0.2:  # Don't save every time to reduce I/O
            self._save_session_data()
            
    def should_rate_limit(self):
        """Check if we should limit our request rate"""
        # Count requests in last minute
        now = datetime.now()
        recent_requests = sum(1 for t in self.request_times 
                            if (now - t).total_seconds() < 60)
        
        # Natural browsing rarely exceeds 12 requests per minute
        return recent_requests > 12
        
    def get_next_request_delay(self):
        """Get a natural delay for the next request"""
        if self.should_rate_limit():
            # We're requesting too fast, slow down significantly
            return random.uniform(5, 15)
            
        # Normal varying delay between requests
        if random.random() < 0.7:
            # Most requests have short delays
            return random.uniform(1, 4)
        else:
            # Occasional longer pauses
            return random.uniform(4, 10)
            
    def should_end_session(self):
        """Check if we should end the current session with more natural behavior"""
        # Don't make too many requests in one day
        if self.total_requests_today > 300:
            return True
            
        # Check time of day - normal users don't browse jobs at 3am
        hour = datetime.now().hour
        if 1 <= hour <= 5:  # Very late night/early morning
            # Lower threshold during abnormal hours
            return self.total_requests_today > 100
            
        # Check session duration - normal users don't browse for 8 hours straight
        if self.session_data["last_session"]:
            last_time = datetime.strptime(self.session_data["last_session"], "%Y-%m-%d %H:%M:%S")
            session_duration = (datetime.now() - last_time).total_seconds() / 3600  # hours
            if session_duration > 3:  # More than 3 hours in one session is suspicious
                return True
                
        return False

class UserAgentRotator:
    """Provides realistic, modern user agents that rotate naturally"""
    
    def __init__(self):
        # List of common modern user agents
            # Chrome on Windows
            #"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            #"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            # Firefox on Windows
            #"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
            # Edge on Windows
            #"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
        self.desktop_agents = [
            # Chrome on macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            # Firefox on macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
            # Safari on macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        ]
        
        # Keep track of used agents to avoid immediate repeats
        self.used_agents = []
        
    def get_random_agent(self):
        """Get a random user agent, avoiding recent ones"""
        available_agents = [a for a in self.desktop_agents if a not in self.used_agents]
        
        # If all have been used, reset
        if not available_agents:
            self.used_agents = []
            available_agents = self.desktop_agents
            
        agent = random.choice(available_agents)
        self.used_agents.append(agent)
        
        # Only remember the last few to avoid repeating recent ones
        if len(self.used_agents) > len(self.desktop_agents) // 2:
            self.used_agents.pop(0)
            
        return agent