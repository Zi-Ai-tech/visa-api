class RAGService:
    def __init__(self):
        pass
    
    def build_context(self, country_data, visa_type):
        """
        Build context based on visa type
        Returns only relevant information from the data layer
        """
        context = {
            "country": country_data.get("country", "Unknown"),
            "last_updated": country_data.get("last_updated", "Unknown"),
            "sources": country_data.get("sources", [])
        }
        
        # Get visa-specific data
        visas = country_data.get("visas", {})
        
        if visa_type == "unknown":
            # Return summary of all visa types
            context["visa_types_available"] = list(visas.keys())
            context["message"] = "Please specify visa type for detailed requirements"
            context["requirements"] = []
            context["processing_time"] = "Varies by visa type"
        else:
            # Return specific visa type data
            visa_data = visas.get(visa_type, {})
            context.update({
                "visa_type": visa_type,
                "requirements": visa_data.get("requirements", []),
                "documents": visa_data.get("documents", []),
                "processing_time": visa_data.get("processing_time", "Contact embassy"),
                "fees": visa_data.get("fees", "Contact embassy for current fees"),
                "validity": visa_data.get("validity", "Varies by visa type"),
                "ielts_required": visa_data.get("ielts_required", False),
                "ielts_note": visa_data.get("ielts_note", ""),
                "interview_required": visa_data.get("interview_required", False),
                "biometrics_required": visa_data.get("biometrics_required", False)
            })
            
            # Add Pakistani-specific requirements if available
            pakistani_special = visa_data.get("pakistani_special", {})
            if pakistani_special:
                context["pakistani_special"] = pakistani_special
        
        return context
    
    def get_relevant_requirements(self, context, intent):
        """Extract most relevant requirements based on intent"""
        requirements = context.get("requirements", [])
        
        # Prioritize based on intent
        if intent.get("is_urgent"):
            # Highlight processing time for urgent queries
            return {
                "priority": "urgent",
                "processing_time": context.get("processing_time", "Unknown"),
                "key_requirements": requirements[:3]  # Top 3 requirements
            }
        
        if intent.get("needs_fee_info"):
            return {
                "priority": "fee",
                "fees": context.get("fees", "Contact embassy"),
                "additional_costs": self._get_additional_costs(context)
            }
        
        return {
            "priority": "standard",
            "all_requirements": requirements
        }
    
    def _get_additional_costs(self, context):
        """Extract additional costs from context"""
        costs = []
        
        if context.get("biometrics_required"):
            costs.append("Biometrics fee may apply")
        
        if context.get("interview_required"):
            costs.append("Interview scheduling fee may apply")
        
        return costs if costs else ["No additional costs identified"]