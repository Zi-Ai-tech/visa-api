class ResponseService:
    def __init__(self):
        pass
    
    def generate_response(self, query, intent, context, country_data):
        """Generate structured response without hallucination"""
        
        response = {
            "query": query,
            "country": context.get("country"),
            "country_code": intent["country"],
            "visa_type": intent["visa_type"],
            "direct_answer": self._generate_direct_answer(intent, context),
            "requirements": context.get("requirements", []),
            "documents": context.get("documents", []),
            "processing_time": context.get("processing_time", "Contact embassy"),
            "fees": context.get("fees", "Contact embassy"),
            "validity": context.get("validity", "Varies by visa type"),
            "sources": self._format_sources(country_data.get("sources", [])),
            "disclaimer": "Only verified information from official sources is provided."
        }
        
        # Add Pakistani-specific information if applicable
        if intent["is_pakistani"]:
            pakistani_info = self._get_pakistani_info(context, intent["visa_type"])
            if pakistani_info:
                response["pakistani_special_requirements"] = pakistani_info
        
        # Add IELTS information if relevant
        ielts_info = self._get_ielts_info(context)
        if ielts_info:
            response["ielts_information"] = ielts_info
        
        return response
    
    def _generate_direct_answer(self, intent, context):
        """Generate direct answer based only on available context"""
        country = context.get("country", "this country")
        visa_type = intent["visa_type"]
        
        if visa_type == "unknown":
            available_types = context.get("visa_types_available", [])
            types_str = ", ".join(available_types) if available_types else "various"
            return (f"For {country}, visa requirements depend on the purpose of travel. "
                   f"Available visa types include: {types_str}. "
                   f"Please specify if you need a tourist, student, work, or other visa type.")
        
        # Build answer from context only
        answer_parts = [f"**{country} {visa_type.title()} Visa Information**\n"]
        
        # Processing time
        processing_time = context.get("processing_time", "Contact embassy")
        answer_parts.append(f"**Processing Time:** {processing_time}")
        
        # Key requirements summary
        requirements = context.get("requirements", [])
        if requirements:
            key_reqs = requirements[:3]  # Top 3 requirements
            answer_parts.append(f"\n**Key Requirements:**")
            for req in key_reqs:
                answer_parts.append(f"• {req}")
        
        # IELTS information
        if context.get("ielts_required") is not None:
            if context["ielts_required"]:
                note = context.get("ielts_note", "English proficiency required")
                answer_parts.append(f"\n**English Requirements:** {note}")
            else:
                answer_parts.append(f"\n**English Requirements:** IELTS not required for this visa type")
        
        # Pakistani-specific note
        if intent["is_pakistani"] and "pakistani_special" in context:
            answer_parts.append(f"\n**🇵🇰 Pakistani Nationals:** Additional requirements may apply.")
        
        return "\n".join(answer_parts)
    
    def _format_sources(self, sources):
        """Format sources with proper structure"""
        formatted = []
        for source in sources:
            formatted.append({
                "name": source.get("name", "Official Source"),
                "url": source.get("url", ""),
                "type": source.get("type", "official"),
                "last_verified": source.get("last_verified", "Unknown")
            })
        return formatted
    
    def _get_pakistani_info(self, context, visa_type):
        """Extract Pakistani-specific information"""
        pakistani_special = context.get("pakistani_special", {})
        if pakistani_special:
            return {
                "requirements": pakistani_special.get("requirements", []),
                "notes": pakistani_special.get("notes", ""),
                "additional_documents": pakistani_special.get("additional_documents", [])
            }
        return None
    
    def _get_ielts_info(self, context):
        """Extract IELTS information"""
        if context.get("ielts_required") is not None:
            return {
                "required": context["ielts_required"],
                "minimum_score": context.get("minimum_ielts_score", "Not specified"),
                "notes": context.get("ielts_note", "")
            }
        return None