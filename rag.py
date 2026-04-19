import faiss
import numpy as np
from openai import OpenAI
import os
import json
from dotenv import load_dotenv


# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    raise ValueError("OPENAI_API_KEY not found in .env file. Please add it.")

client = OpenAI(api_key=api_key)

documents = []
embeddings = []

def load_data():
    global documents, embeddings
    
    print("Loading visa documents...", flush=True)
    
    # Check if file exists
    file_path = "data/visa_docs.txt"
    if not os.path.exists(file_path):
        print(f"Warning: {file_path} not found! Using sample data.", flush=True)
        # Create sample data if file doesn't exist
        documents = [
            "US Tourist Visa (B1/B2): Requirements: Valid passport, DS-160 form, visa fee payment, photo, interview appointment. Processing time: 2-4 weeks. Required documents: Bank statements, employment letter, travel itinerary, accommodation proof.",
            "Canada Visitor Visa: Requirements: Valid passport, application form, biometrics, purpose of visit. Processing time: 2-8 weeks. Documents: Invitation letter (if applicable), financial proof, travel history, employment verification.",
            "UK Standard Visitor Visa: Requirements: Valid passport, online application, healthcare surcharge, tuberculosis test (if applicable). Processing time: 3-4 weeks. Documents: Sponsorship letter, bank statements, accommodation details, return flight booking.",
            "Schengen Visa (Europe): Requirements: Valid passport, application form, travel insurance, flight reservation, hotel booking. Processing time: 15 calendar days. Documents: Employment proof, bank statements, itinerary, sponsorship letter (if applicable).",
            "Australia Tourist Visa (subclass 600): Requirements: Valid passport, online application, health insurance, character certificate. Processing time: 20-35 days. Documents: Financial capacity proof, employment letter, invitation letter, previous visas."
        ]
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            documents = content.split("\n\n")
            documents = [doc.strip() for doc in documents if doc.strip()]
    
    print(f"Loaded {len(documents)} documents", flush=True)
    
    print("Creating embeddings...", flush=True)
    embeddings = []
    for i, doc in enumerate(documents):
        print(f"  Processing document {i+1}/{len(documents)}", flush=True)
        embeddings.append(get_embedding(doc))
    
    dim = len(embeddings[0])
    index = faiss.IndexFlatL2(dim)
    index.add(np.array(embeddings).astype("float32"))
    
    print(f"FAISS index created with dimension {dim}", flush=True)
    return index

def load_country_data(country):
    try:
        with open(f"data/{country.lower()}.json") as f:
            return json.load(f)
    except:
        return None

def get_embedding(text):
    try:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000]  # Truncate if too long
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error getting embedding: {e}", flush=True)
        raise

index = None

def init_rag():
    global index
    try:
        print("Initializing RAG system...", flush=True)
        index = load_data()
        print("RAG initialization complete!", flush=True)
    except Exception as e:
        print(f"Failed to initialize RAG: {e}", flush=True)
        raise

def retrieve(query, k=3):
    try:
        q_emb = np.array([get_embedding(query)]).astype("float32")
        distances, indices = index.search(q_emb, k)
        return [documents[i] for i in indices[0] if i < len(documents)]
    except Exception as e:
        print(f"Error in retrieve: {e}", flush=True)
        return ["No documents found"]

def generate_answer(query, context):
    from prompts import SYSTEM_PROMPT
    
    prompt = f"""
Context:
{context}

Question:
{query}

Provide answer in JSON format as specified in the system prompt.
"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error generating answer: {e}", flush=True)
        # Return a fallback JSON
        import json
        return json.dumps({
            "direct_answer": f"Based on the context: {context[:200]}...",
            "requirements": ["Check official visa website"],
            "processing_time": "Contact embassy for accurate timing",
            "documents": ["Passport", "Application form"],
            "sources": ["Visa guidelines"]
        })