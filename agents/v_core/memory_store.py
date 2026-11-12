import os
import uuid
from datetime import datetime, timezone
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from google import genai
from dotenv import load_dotenv

load_dotenv()

COLLECTION_NAME = "v_tactical_memory"

class TacticalMemory:
    def __init__(self, host: str = "", port: int = 6333):
        qdrant_host = host or os.getenv("QDRANT_HOST", "")
        if qdrant_host and qdrant_host != "localhost":
            self.client = QdrantClient(host=qdrant_host, port=port)
        else:
            local_path = os.getenv("QDRANT_LOCAL_PATH", "C:/v_core_data/qdrant_storage")
            os.makedirs(local_path, exist_ok=True)
            self.client = QdrantClient(path=local_path)
        
        # Instanciación segura del nuevo SDK
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("Missing GEMINI_API_KEY in .env file")
        self.genai_client = genai.Client(api_key=api_key)

    def _ensure_collection(self, vector_size: int) -> None:
        collections = [c.name for c in self.client.get_collections().collections]
        if COLLECTION_NAME in collections:
            info = self.client.get_collection(COLLECTION_NAME)
            current_size = info.config.params.vectors.size
            if current_size != vector_size:
                self.client.delete_collection(COLLECTION_NAME)
                collections.remove(COLLECTION_NAME)

        if COLLECTION_NAME not in collections:
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def _get_embedding(self, text: str) -> list[float]:
        try:
            # Sintaxis del SDK v0.8.0+
            response = self.genai_client.models.embed_content(
                model="text-embedding-001",
                contents=text,
            )
            vector = response.embeddings[0].values
            self._ensure_collection(len(vector))
            return vector
        except Exception as e:
            raise RuntimeError(f"Fallo al generar embedding: {str(e)}")

    def store_memory(self, text: str, category: str = "general") -> str:
        vector = self._get_embedding(text)
        point_id = str(uuid.uuid4())
        payload = {
            "text": text,
            "category": category,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )
        return point_id

    def recall_memories(self, query: str, limit: int = 4) -> list[str]:
        query_vector = self._get_embedding(query)
        if hasattr(self.client, "query_points"):
            res = self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                limit=limit,
            )
            hits = res.points
        else:
            hits = self.client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                limit=limit,
            )
        return [hit.payload["text"] for hit in hits if hit.score and hit.score > 0.45]