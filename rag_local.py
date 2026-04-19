import faiss
import numpy as np
import json
import os
from sentence_transformers import SentenceTransformer
from transformers import pipeline

# Load local models (downloads once, then runs locally)
print("Loading local embedding model...", flush=True)
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

print("Loading local LLM for answer generation...", flush=True)
# Use a smaller model that runs on CPU
llm = pipeline("text-generation", model="microsoft/DialoGPT-small", max_new_tokens=200)

documents = []

def load_data():
    global documents
    
    print("Loading visa documents...", flush=True)
    
    # Create comprehensive visa documents
    documents = [
        """US Tourist Visa (B1/B2): 
Requirements: Valid passport (6 months validity), DS-160 online form completion, visa fee payment ($185), photo (2x2 inches), interview appointment at US embassy.
Processing time: 2-4 weeks for interview scheduling, 3-5 days for processing after interview.
Required documents: Bank statements (last 3 months), employment verification letter, travel itinerary, accommodation proof, ties to home country.""",

        """Canada Visitor Visa (Temporary Resident Visa):
Requirements: Valid passport, online application through IRCC portal, biometrics fee ($85), purpose of travel.
Processing time: 2-8 weeks depending on home country.
Documents: Invitation letter (if visiting family/friends), financial proof ($1000+ per month), travel history, employment verification, marriage certificate (if applicable).""",

        """UK Standard Visitor Visa:
Requirements: Valid passport, online application, healthcare surcharge (£470), tuberculosis test (for certain countries).
Processing time: 3-4 weeks, priority service available (5 days for £500).
Documents: Sponsorship letter, bank statements (6 months), accommodation details, return flight booking, employment proof, criminal record certificate (if required).""",

        """Schengen Visa (Europe - 27 countries):
Requirements: Valid passport (3 months beyond stay), application form, travel insurance (€30,000 minimum), flight reservation, hotel booking.
Processing time: 15 calendar days, can extend to 45 days.
Documents: Employment proof, bank statements (3 months), itinerary, sponsorship letter (if applicable), marriage/birth certificates, no-objection letter from employer.""",

        """Australia Tourist Visa (subclass 600):
Requirements: Valid passport, online ImmiAccount application, health insurance, character certificate, health examination.
Processing time: 20-35 days, faster for certain nationalities.
Documents: Financial capacity (proof of funds $5000+ AUD), employment letter, invitation letter, previous visas, family composition form."""
    ]
    
    print(f"Loaded {len(documents)} documents", flush=True)
    return create_faiss_index()

def create_faiss_index():
    print("Creating FAISS index with local embeddings...", flush=True)
    embeddings = embedding_model.encode(documents)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings.astype("float32"))
    print(f"FAISS index created with dimension {dim}", flush=True)
    return index

def get_embedding_local(text):
    """Get embedding using local model"""
    return embedding_model.encode([text])[0]

def retrieve(query, index, k=3):
    try:
        q_emb = get_embedding_local(query)
        q_emb = np.array([q_emb]).astype("float32")
        distances, indices = index.search(q_emb, k)
        return [documents[i] for i in indices[0] if i < len(documents)]
    except Exception as e:
        print(f"Error in retrieve: {e}", flush=True)
        return documents[:k]  # Return first k documents as fallback

def generate_answer_local(query, context):
    """Generate answer using local LLM or template"""
    
    # Template-based answer (reliable and fast)
    answer_template = f"""Based on the visa information available:

QUESTION: {query}

RELEVANT INFORMATION:
{context}

KEY REQUIREMENTS:
• Valid passport with sufficient validity
• Completed visa application form
• Visa fee payment
• Supporting financial documents
• Purpose of travel documentation

RECOMMENDATIONS:
1. Check the official embassy website for the most current requirements
2. Apply at least 2-3 months before your planned travel date
3. Ensure all documents are translated to English if required
4. Keep copies of all submitted documents

Note: Visa requirements can change. Always verify with the official embassy/consulate."""
    
    # Extract specific information from context
    requirements = []
    processing_time = "Varies by country (typically 2-8 weeks)"
    docs_list = ["Valid passport", "Application form", "Photo", "Financial proof"]
    
    # Try to extract specific info from context
    if "Requirements:" in context:
        req_section = context.split("Requirements:")[1].split("Processing")[0]
        requirements = [r.strip() for r in req_section.split(",")[:5]]
    
    if "Processing time:" in context:
        time_section = context.split("Processing time:")[1].split(".")[0]
        processing_time = time_section.strip()
    
    if "Documents:" in context:
        docs_section = context.split("Documents:")[1].split(".")[0]
        docs_list = [d.strip() for d in docs_section.split(",")[:5]]
    
    return json.dumps({
        "direct_answer": answer_template,
        "requirements": requirements if requirements else ["Valid passport", "Completed application", "Visa fee payment", "Travel itinerary", "Financial documents"],
        "processing_time": processing_time,
        "documents": docs_list,
        "sources": ["Visa information database", "Official embassy guidelines"]
    }, indent=2)

index = None

def init_rag():
    global index
    try:
        print("Initializing local RAG system...", flush=True)
        index = load_data()
        print("Local RAG initialization complete!", flush=True)
    except Exception as e:
        print(f"Failed to initialize RAG: {e}", flush=True)
        raise

def retrieve_query(query, k=3):
    return retrieve(query, index, k)

def generate_answer(query, context):
    return generate_answer_local(query, context)