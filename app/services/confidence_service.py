class ConfidenceService:
    def __init__(self):
        pass
    
    def calculate_confidence(self, country_data, context, intent):
        """Calculate confidence score based on multiple factors"""
        score = 0.0
        factors = []
        
        # Factor 1: Data completeness
        completeness = self._check_data_completeness(country_data, intent["visa_type"])
        score += completeness * 0.3
        factors.append(f"Data completeness: {completeness*100:.0f}%")
        
        # Factor 2: Source reliability
        source_score = self._evaluate_sources(country_data.get("sources", []))
        score += source_score * 0.25
        factors.append(f"Source reliability: {source_score*100:.0f}%")
        
        # Factor 3: Data freshness
        freshness = self._check_data_freshness(country_data.get("last_updated", ""))
        score += freshness * 0.2
        factors.append(f"Data freshness: {freshness*100:.0f}%")
        
        # Factor 4: Visa type specificity
        specificity = 1.0 if intent["visa_type"] != "unknown" else 0.5
        score += specificity * 0.15
        factors.append(f"Query specificity: {specificity*100:.0f}%")
        
        # Factor 5: Pakistani-specific data availability
        if intent["is_pakistani"]:
            has_pakistani_data = self._has_pakistani_data(country_data, intent["visa_type"])
            score += has_pakistani_data * 0.1
            factors.append(f"Pakistani-specific data: {'Yes' if has_pakistani_data else 'No'}")
        
        # Determine confidence level
        if score >= 0.8:
            level = "high"
        elif score >= 0.5:
            level = "medium"
        else:
            level = "low"
        
        return {
            "score": min(score, 1.0),
            "level": level,
            "factors": factors,
            "percentage": round(score * 100)
        }
    
    def _check_data_completeness(self, country_data, visa_type):
        """Check how complete the data is"""
        required_fields = ["country", "last_updated", "visas", "sources"]
        score = sum(1 for field in required_fields if country_data.get(field)) / len(required_fields)
        
        if visa_type != "unknown":
            visa_data = country_data.get("visas", {}).get(visa_type, {})
            visa_fields = ["requirements", "processing_time", "fees", "validity"]
            visa_score = sum(1 for field in visa_fields if visa_data.get(field)) / len(visa_fields)
            score = (score + visa_score) / 2
        
        return score
    
    def _evaluate_sources(self, sources):
        """Evaluate source reliability"""
        if not sources:
            return 0.0
        
        official_domains = ['.gov', '.gov.uk', '.gc.ca', '.gov.au', '.gouv.fr', '.go.jp', '.gov.ie']
        official_count = 0
        
        for source in sources:
            url = source.get("url", "")
            if any(domain in url for domain in official_domains):
                official_count += 1
        
        return official_count / len(sources) if sources else 0.0
    
    def _check_data_freshness(self, last_updated):
        """Check how recent the data is"""
        from datetime import datetime, timedelta
        
        if not last_updated:
            return 0.0
        
        try:
            update_date = datetime.strptime(last_updated, "%Y-%m-%d")
            days_old = (datetime.now() - update_date).days
            
            if days_old <= 30:
                return 1.0
            elif days_old <= 90:
                return 0.8
            elif days_old <= 180:
                return 0.6
            elif days_old <= 365:
                return 0.4
            else:
                return 0.2
        except:
            return 0.5
    
    def _has_pakistani_data(self, country_data, visa_type):
        """Check if Pakistani-specific data exists"""
        if visa_type != "unknown":
            visa_data = country_data.get("visas", {}).get(visa_type, {})
            return bool(visa_data.get("pakistani_special"))
        return False