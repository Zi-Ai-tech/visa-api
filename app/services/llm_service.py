import os
from typing import List, Dict, Any, Optional
from openai import OpenAI
from anthropic import Anthropic
import json

class LLMService:
    def __init__(self):
        """Initialize LLM service with OpenAI or Anthropic"""
        self.provider = os.getenv("LLM_PROVIDER", "openai")
        
        if self.provider == "openai":
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.model = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
        elif self.provider == "anthropic":
            self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            self.model = os.getenv("LLM_MODEL", "claude-3-sonnet-20240229")
    
    def summarize_visa_info(self, visa_data: Dict[str, Any], query: str) -> str:
        """Generate a human-readable summary of visa information"""
        
        prompt = f"""
        Based on the following visa information, provide a clear, concise summary for a user asking: "{query}"
        
        Visa Information:
        Country: {visa_data.get('country', 'Unknown')}
        Visa Type: {visa_data.get('visa_type', 'Unknown')}
        Requirements: {', '.join(visa_data.get('requirements', []))}
        Fees: {visa_data.get('fees', 'Not specified')}
        Processing Time: {visa_data.get('processing_time_note', 'Not specified')}
        Validity: {visa_data.get('validity_note', 'Not specified')}
        
        Please provide a friendly, helpful summary that:
        1. Highlights the most important information first
        2. Uses simple language
        3. Includes any warnings or important notes
        4. Suggests next steps if applicable
        """
        
        if self.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300
            )
            return response.choices[0].message.content
        
        else:  # anthropic
            response = self.client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300
            )
            return response.content[0].text
    
    def compare_countries(self, countries_data: List[Dict[str, Any]], query: str) -> str:
        """Generate a comparison summary for multiple countries"""
        
        comparison_text = ""
        for data in countries_data:
            comparison_text += f"""
            {data.get('country', 'Unknown')}:
            - Visa Type: {data.get('visa_type', 'Unknown')}
            - Requirements: {', '.join(data.get('requirements', []))}
            - Fees: {data.get('fees', 'Not specified')}
            - Processing Time: {data.get('processing_time_note', 'Not specified')}
            - Validity: {data.get('validity_note', 'Not specified')}
            """
        
        prompt = f"""
        User query: "{query}"
        
        Compare the following countries' visa information:
        {comparison_text}
        
        Please provide:
        1. A brief overview of key differences
        2. Which country might be easiest/fastest/most suitable
        3. Any unique requirements per country
        4. Recommendations based on common scenarios (student, work, tourist)
        
        Keep the response helpful and actionable.
        """
        
        if self.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500
            )
            return response.choices[0].message.content
        
        else:
            response = self.client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500
            )
            return response.content[0].text
    
    def personalize_response(self, base_response: Dict[str, Any], 
                           user_history: List[Dict[str, Any]], 
                           user_preferences: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance response with personalization based on user history"""
        
        # Add personalized notes based on history
        personalized_response = base_response.copy()
        
        # Check if user has asked similar questions before
        similar_queries = [h for h in user_history if h.get('visa_type') == base_response.get('visa_type')]
        
        if similar_queries:
            personalized_response['personalized_note'] = f"You've asked about {base_response.get('visa_type')} visas before. Here's the latest information."
        
        # Add preference-based recommendations
        if user_preferences.get('preferred_countries'):
            personalized_response['recommended_countries'] = user_preferences['preferred_countries']
        
        # Generate quick action suggestions based on history
        if len(user_history) > 3:
            personalized_response['suggestions'] = [
                "Compare with other countries",
                "Check document requirements",
                "View processing time trends"
            ]
        
        return personalized_response
    
    def extract_entities(self, query: str) -> Dict[str, Any]:
        """Extract entities from user query using LLM"""
        
        prompt = f"""
        Extract the following entities from this visa-related query: "{query}"
        
        Entities to extract:
        - country (specific country name)
        - visa_type (student, work, tourist, business, family)
        - specific_requirements (ielts, toefl, bank statement, etc.)
        - urgency (urgent, normal, not specified)
        
        Return as JSON format.
        """
        
        if self.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        
        else:
            response = self.client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            # Attempt to parse JSON from response
            try:
                return json.loads(response.content[0].text)
            except:
                return {"country": None, "visa_type": None, "specific_requirements": [], "urgency": "normal"}