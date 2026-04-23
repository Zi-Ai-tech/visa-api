import redis
import json
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import os

class UserService:
    def __init__(self):
        """Initialize user service with Redis for session storage"""
        self.redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        self.session_timeout = 86400  # 24 hours
    
    def get_user_id(self, session_id: str) -> str:
        """Get or create user ID from session"""
        user_key = f"session:{session_id}"
        user_id = self.redis_client.get(user_key)
        
        if not user_id:
            # Create new user
            user_id = hashlib.md5(session_id.encode()).hexdigest()
            self.redis_client.setex(user_key, self.session_timeout, user_id)
            self._initialize_user_profile(user_id)
        
        return user_id.decode('utf-8') if isinstance(user_id, bytes) else user_id
    
    def _initialize_user_profile(self, user_id: str):
        """Initialize a new user profile"""
        profile = {
            "created_at": datetime.now().isoformat(),
            "total_queries": 0,
            "preferred_countries": [],
            "preferred_visa_types": [],
            "interests": [],
            "notification_preferences": {
                "email": None,
                "updates": True
            }
        }
        self.redis_client.setex(
            f"user:{user_id}:profile",
            self.session_timeout * 30,  # 30 days
            json.dumps(profile)
        )
    
    def add_to_history(self, user_id: str, query: str, response: Dict[str, Any]):
        """Add query to user history"""
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "country": response.get("country"),
            "visa_type": response.get("visa_type"),
            "response_summary": response.get("summary", "")
        }
        
        # Add to history list (keep last 50)
        history_key = f"user:{user_id}:history"
        self.redis_client.lpush(history_key, json.dumps(history_entry))
        self.redis_client.ltrim(history_key, 0, 49)
        self.redis_client.expire(history_key, self.session_timeout * 30)
        
        # Update profile statistics
        self._update_user_profile(user_id, response)
    
    def _update_user_profile(self, user_id: str, response: Dict[str, Any]):
        """Update user profile based on interactions"""
        profile_key = f"user:{user_id}:profile"
        profile_json = self.redis_client.get(profile_key)
        
        if profile_json:
            profile = json.loads(profile_json)
            profile["total_queries"] += 1
            
            # Update preferred countries
            country = response.get("country")
            if country and country not in profile["preferred_countries"]:
                profile["preferred_countries"].append(country)
                # Keep only last 5
                profile["preferred_countries"] = profile["preferred_countries"][-5:]
            
            # Update preferred visa types
            visa_type = response.get("visa_type")
            if visa_type and visa_type not in profile["preferred_visa_types"]:
                profile["preferred_visa_types"].append(visa_type)
                profile["preferred_visa_types"] = profile["preferred_visa_types"][-5:]
            
            self.redis_client.setex(profile_key, self.session_timeout * 30, json.dumps(profile))
    
    def get_user_history(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get user's query history"""
        history_key = f"user:{user_id}:history"
        history = self.redis_client.lrange(history_key, 0, limit - 1)
        
        return [json.loads(h) for h in history]
    
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """Get user profile"""
        profile_key = f"user:{user_id}:profile"
        profile_json = self.redis_client.get(profile_key)
        
        if profile_json:
            return json.loads(profile_json)
        return {}
    
    def update_preferences(self, user_id: str, preferences: Dict[str, Any]):
        """Update user preferences"""
        profile_key = f"user:{user_id}:profile"
        profile_json = self.redis_client.get(profile_key)
        
        if profile_json:
            profile = json.loads(profile_json)
            profile.update(preferences)
            self.redis_client.setex(profile_key, self.session_timeout * 30, json.dumps(profile))
    
    def get_similar_users(self, user_id: str, limit: int = 5) -> List[str]:
        """Find users with similar interests (for recommendations)"""
        profile = self.get_user_profile(user_id)
        if not profile:
            return []
        
        # Simple similarity based on preferred countries and visa types
        pattern = f"user:*:profile"
        similar_users = []
        
        for key in self.redis_client.scan_iter(match=pattern):
            other_id = key.decode('utf-8').split(':')[1]
            if other_id != user_id:
                other_profile_json = self.redis_client.get(key)
                if other_profile_json:
                    other_profile = json.loads(other_profile_json)
                    # Calculate similarity score
                    score = 0
                    for country in profile.get("preferred_countries", []):
                        if country in other_profile.get("preferred_countries", []):
                            score += 1
                    for visa_type in profile.get("preferred_visa_types", []):
                        if visa_type in other_profile.get("preferred_visa_types", []):
                            score += 1
                    
                    if score > 0:
                        similar_users.append((other_id, score))
        
        # Sort by score and return top users
        similar_users.sort(key=lambda x: x[1], reverse=True)
        return [user_id for user_id, _ in similar_users[:limit]]
    
    def get_popular_queries(self, visa_type: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most frequent queries (for suggestions)"""
        # This would typically use aggregation, simplified version here
        pattern = f"user:*:history"
        all_queries = []
        
        for key in self.redis_client.scan_iter(match=pattern):
            history = self.redis_client.lrange(key, 0, -1)
            for h in history:
                query_data = json.loads(h)
                if not visa_type or query_data.get("visa_type") == visa_type:
                    all_queries.append(query_data.get("query"))
        
        # Count frequencies
        from collections import Counter
        query_counts = Counter(all_queries)
        
        # Return most common
        return [{"query": q, "count": c} for q, c in query_counts.most_common(limit)]