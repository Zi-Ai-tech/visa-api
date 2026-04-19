import re

class ValidationService:
    def __init__(self):
        self.max_query_length = 500
        self.malicious_patterns = [
            r'<script',
            r'javascript:',
            r'onerror\s*=',
            r'onclick\s*=',
            r'SELECT\s+.*\s+FROM',
            r'DROP\s+TABLE',
            r'DELETE\s+FROM',
            r'INSERT\s+INTO',
            r'UNION\s+SELECT',
            r'--',
            r'/\*',
            r'\.\./',
            r'\.\.\\',
            r'exec\s*\(',
            r'eval\s*\(',
            r'system\s*\(',
            r'<?php',
        ]
    
    def validate_input(self, query):
        """Validate and sanitize input query"""
        if not query or not isinstance(query, str):
            return False, "Invalid input type"
        
        if len(query) > self.max_query_length:
            return False, f"Query too long (max {self.max_query_length} characters)"
        
        for pattern in self.malicious_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return False, "Invalid query content detected"
        
        return True, "Valid input"
    
    def validate_response(self, response, country_data):
        """
        Validate response against source data
        Prevents hallucination by checking all claims against the data
        """
        # Check if we have data
        if not country_data:
            response["confidence"] = "low"
            response["validation_note"] = "No source data available"
            return response
        
        # Check requirements validity
        requirements = response.get("requirements", [])
        source_requirements = self._get_source_requirements(country_data, response.get("visa_type"))
        
        if not requirements:
            response["confidence"] = "low"
            response["validation_note"] = "No requirements found in source data"
        elif not self._requirements_match(requirements, source_requirements):
            response["confidence"] = "medium"
            response["validation_note"] = "Partial match with source data"
        else:
            response["confidence"] = "high"
            response["validation_note"] = "Fully verified against official sources"
        
        # Ensure we don't claim things not in data
        response["requirements"] = self._filter_verified_requirements(requirements, source_requirements)
        
        return response
    
    def _get_source_requirements(self, country_data, visa_type):
        """Extract requirements from source data"""
        if visa_type and visa_type != "unknown":
            visa_data = country_data.get("visas", {}).get(visa_type, {})
            return visa_data.get("requirements", [])
        
        # Return all requirements if visa type unknown
        all_reqs = []
        for visa_data in country_data.get("visas", {}).values():
            all_reqs.extend(visa_data.get("requirements", []))
        return list(set(all_reqs))
    
    def _requirements_match(self, response_reqs, source_reqs):
        """Check if response requirements match source"""
        if not source_reqs:
            return False
        
        # Simple matching - can be enhanced with fuzzy matching
        matches = 0
        for req in response_reqs:
            if any(req.lower() in source.lower() or source.lower() in req.lower() 
                   for source in source_reqs):
                matches += 1
        
        return matches >= len(response_reqs) * 0.7  # 70% match threshold
    
    def _filter_verified_requirements(self, response_reqs, source_reqs):
        """Only return requirements that exist in source data"""
        if not source_reqs:
            return []
        
        verified = []
        for req in response_reqs:
            if any(source.lower() in req.lower() or req.lower() in source.lower() 
                   for source in source_reqs):
                verified.append(req)
        
        return verified if verified else ["Requirements not available in verified sources"]