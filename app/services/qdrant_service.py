import os
import hashlib
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from sentence_transformers import SentenceTransformer
import numpy as np

class QdrantService:
    def __init__(self):
        """Initialize Qdrant client and embedding model"""
        self.client = QdrantClient(
            url=os.getenv("QDRANT_URL"),
            api_key=os.getenv("QDRANT_API_KEY")
    )
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.collection_name = "visa_information"
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Ensure collection exists"""
        collections = self.client.get_collections().collections
        if not any(c.name == self.collection_name for c in collections):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=384,  # all-MiniLM-L6-v2 dimension
                    distance=Distance.COSINE
                )
            )
    
    def index_document(self, document: Dict[str, Any], doc_id: Optional[str] = None):
        """Index a document for semantic search"""
        if not doc_id:
            doc_id = hashlib.md5(str(document).encode()).hexdigest()
        
        # Create text representation for embedding
        text = f"{document.get('title', '')} {document.get('content', '')} {document.get('country', '')} {document.get('visa_type', '')}"
        
        # Generate embedding
        embedding = self.embedding_model.encode(text).tolist()
        
        # Store in Qdrant
        point = PointStruct(
            id=doc_id,
            vector=embedding,
            payload=document
        )
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )
        
        return doc_id
    
    def semantic_search(self, query: str, country: Optional[str] = None, 
                       visa_type: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Perform semantic search"""
        # Generate query embedding
        query_embedding = self.embedding_model.encode(query).tolist()
        
        # Build filter if needed
        filter_conditions = []
        if country:
            filter_conditions.append({
                "key": "country",
                "match": {"value": country}
            })
        if visa_type:
            filter_conditions.append({
                "key": "visa_type",
                "match": {"value": visa_type}
            })
        
        search_result = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=limit,
            query_filter={
                "must": filter_conditions
            } if filter_conditions else None
        )
        
        return [hit.payload for hit in search_result]
    
    def batch_index(self, documents: List[Dict[str, Any]]):
        """Batch index multiple documents"""
        points = []
        for doc in documents:
            doc_id = hashlib.md5(str(doc).encode()).hexdigest()
            text = f"{doc.get('title', '')} {doc.get('content', '')} {doc.get('country', '')} {doc.get('visa_type', '')}"
            embedding = self.embedding_model.encode(text).tolist()
            
            points.append(PointStruct(
                id=doc_id,
                vector=embedding,
                payload=doc
            ))
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
    
    def get_similar_documents(self, doc_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Get documents similar to a given document"""
        # Get the document vector first
        points = self.client.retrieve(
            collection_name=self.collection_name,
            ids=[doc_id]
        )
        
        if not points:
            return []
        
        vector = points[0].vector
        
        # Search for similar documents
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=vector,
            limit=limit + 1  # +1 to exclude the original
        )
        
        # Filter out the original document
        return [hit.payload for hit in results if hit.id != doc_id]