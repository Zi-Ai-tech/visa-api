from typing import List, Dict, Any, Optional
from datetime import datetime

class ComparisonService:
    def __init__(self):
        """Service for comparing visa information across multiple countries"""
        pass
    
    def compare_countries(self, countries_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compare visa information for multiple countries"""
        if not countries_data:
            return {"error": "No countries to compare"}
        
        comparison = {
            "countries": [data.get("country") for data in countries_data],
            "visa_types": list(set([data.get("visa_type") for data in countries_data])),
            "comparison_matrix": {},
            "recommendations": {},
            "best_for": {}
        }
        
        # Create comparison matrix
        criteria = ["fees", "processing_time", "requirements_count", "validity_days"]
        
        for criterion in criteria:
            comparison["comparison_matrix"][criterion] = {}
            for data in countries_data:
                country = data.get("country")
                if criterion == "fees":
                    value = self._extract_fee_amount(data.get("fees", ""))
                elif criterion == "processing_time":
                    value = self._extract_processing_days(data.get("processing_time_note", ""))
                elif criterion == "requirements_count":
                    value = len(data.get("requirements", []))
                elif criterion == "validity_days":
                    value = self._extract_validity_days(data.get("validity_note", ""))
                else:
                    value = None
                
                comparison["comparison_matrix"][criterion][country] = value
        
        # Generate recommendations
        comparison["recommendations"] = self._generate_recommendations(comparison["comparison_matrix"])
        
        # Find best for each category
        comparison["best_for"] = self._find_best_for_categories(comparison["comparison_matrix"], countries_data)
        
        return comparison
    
    def _extract_fee_amount(self, fee_text: str) -> Optional[float]:
        """Extract numeric fee amount from text"""
        import re
        # Look for currency amounts
        patterns = [
            r'\$(\d+(?:,\d+)*(?:\.\d+)?)',
            r'(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:USD|dollars)',
            r'(\d+(?:,\d+)*(?:\.\d+)?)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, fee_text)
            if match:
                amount = match.group(1).replace(',', '')
                try:
                    return float(amount)
                except:
                    pass
        return None
    
    def _extract_processing_days(self, time_text: str) -> Optional[int]:
        """Extract processing time in days"""
        import re
        # Look for day numbers
        patterns = [
            r'(\d+)\s*(?:days?|business days?)',
            r'(\d+)\s*-?\s*(\d+)\s*days?',  # Range
        ]
        
        for pattern in patterns:
            match = re.search(pattern, time_text.lower())
            if match:
                if len(match.groups()) == 2 and match.group(2):
                    # Return average of range
                    return (int(match.group(1)) + int(match.group(2))) // 2
                return int(match.group(1))
        return None
    
    def _extract_validity_days(self, validity_text: str) -> Optional[int]:
        """Extract validity period in days"""
        import re
        patterns = [
            r'(\d+)\s*(?:years?)',  # Convert years to days
            r'(\d+)\s*(?:months?)',  # Convert months to days
            r'(\d+)\s*(?:days?)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, validity_text.lower())
            if match:
                value = int(match.group(1))
                if 'year' in validity_text.lower():
                    return value * 365
                elif 'month' in validity_text.lower():
                    return value * 30
                else:
                    return value
        return None
    
    def _generate_recommendations(self, matrix: Dict[str, Any]) -> Dict[str, str]:
        """Generate recommendations based on comparison matrix"""
        recommendations = {}
        
        # Cheapest country
        fees = matrix.get("fees", {})
        if fees:
            cheapest = min(fees, key=lambda x: fees[x] if fees[x] is not None else float('inf'))
            recommendations["cheapest"] = cheapest
        
        # Fastest processing
        processing = matrix.get("processing_time", {})
        if processing:
            fastest = min(processing, key=lambda x: processing[x] if processing[x] is not None else float('inf'))
            recommendations["fastest"] = fastest
        
        # Least requirements
        requirements = matrix.get("requirements_count", {})
        if requirements:
            easiest = min(requirements, key=lambda x: requirements[x] if requirements[x] is not None else float('inf'))
            recommendations["easiest_requirements"] = easiest
        
        # Longest validity
        validity = matrix.get("validity_days", {})
        if validity:
            longest = max(validity, key=lambda x: validity[x] if validity[x] is not None else float('-inf'))
            recommendations["longest_validity"] = longest
        
        return recommendations
    
    def _find_best_for_categories(self, matrix: Dict[str, Any], countries_data: List[Dict[str, Any]]) -> Dict[str, str]:
        """Find best country for specific visa categories"""
        best_for = {}
        
        # Student visa
        student_data = [d for d in countries_data if d.get("visa_type") == "student"]
        if student_data:
            best_for["student"] = student_data[0].get("country")
        
        # Work visa
        work_data = [d for d in countries_data if d.get("visa_type") == "work"]
        if work_data:
            best_for["work"] = work_data[0].get("country")
        
        # Tourist visa
        tourist_data = [d for d in countries_data if d.get("visa_type") == "tourist"]
        if tourist_data:
            best_for["tourist"] = tourist_data[0].get("country")
        
        return best_for
    
    def get_country_rankings(self, countries_data: List[Dict[str, Any]], 
                            preferences: Dict[str, float]) -> List[Dict[str, Any]]:
        """Rank countries based on user preferences"""
        rankings = []
        
        for data in countries_data:
            score = 0
            country = data.get("country")
            
            # Calculate weighted score based on preferences
            if preferences.get("cost_importance", 0):
                fee = self._extract_fee_amount(data.get("fees", ""))
                if fee:
                    # Lower fee is better
                    score += preferences["cost_importance"] * (1 / (fee / 100))
            
            if preferences.get("speed_importance", 0):
                days = self._extract_processing_days(data.get("processing_time_note", ""))
                if days:
                    # Lower days is better
                    score += preferences["speed_importance"] * (1 / (days / 10))
            
            if preferences.get("requirements_importance", 0):
                req_count = len(data.get("requirements", []))
                # Fewer requirements is better
                score += preferences["requirements_importance"] * (1 / (req_count + 1))
            
            rankings.append({
                "country": country,
                "score": score,
                "visa_type": data.get("visa_type"),
                "details": data
            })
        
        # Sort by score descending
        rankings.sort(key=lambda x: x["score"], reverse=True)
        return rankings