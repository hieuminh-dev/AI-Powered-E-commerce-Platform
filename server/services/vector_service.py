import importlib
import logging
import os
import traceback
from typing import Any, Dict, List, Optional

from flask import current_app
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class VectorService:
    """Service for managing vector embeddings and similarity search with Pinecone"""

    def __init__(self):
        self.model = None
        self.index = None
        self.initialized = False
        self._pc = None
        self._pc_variant: Optional[str] = None
        self._init_error: Optional[str] = None
        self._active_index_name: Optional[str] = None

    def initialize(self):
        """Initialize embedding model and Pinecone"""
        try:
            logger.info("Vector service initialization started")
            model_name = current_app.config.get(
                "EMBEDDING_MODEL", "all-MiniLM-L6-v2"
            )

            # Load embedding model
            self.model = SentenceTransformer(model_name)
            logger.info("Embedding model loaded: %s", model_name)

            # Load config
            cfg_index = None
            cfg_api = None
            try:
                cfg_index = os.getenv("PINECONE_INDEX_NAME") or current_app.config.get("PINECONE_INDEX_NAME")
                cfg_api = os.getenv("PINECONE_API_KEY") or current_app.config.get("PINECONE_API_KEY")
                cfg_env = os.getenv("PINECONE_ENVIRONMENT") or current_app.config.get("PINECONE_ENVIRONMENT")   
                source = "current_app.config"
            except Exception:
                cfg_index = None
                cfg_api = None
                cfg_env = None
                source = "no_app_context"

            # fallback .env
            if not cfg_index or not cfg_api:
                try:
                    load_dotenv()
                except Exception:
                    pass

                env_index = os.getenv("PINECONE_INDEX_NAME")
                env_api = os.getenv("PINECONE_API_KEY")
                env_env = os.getenv("PINECONE_ENVIRONMENT")

                if not cfg_index and env_index:
                    cfg_index = env_index
                    source = "env"
                if not cfg_api and env_api:
                    cfg_api = env_api
                    source = "env"
                if not cfg_env and env_env:
                    cfg_env = env_env

            index_name = cfg_index
            api_key = cfg_api

            logger.debug(
                f"Config source={source} "
                f"PINECONE_INDEX_NAME={index_name} "
                f"PINECONE_API_KEY={'SET' if api_key else 'MISSING'} "
                f"PINECONE_ENVIRONMENT={cfg_env}"
            )

            if not api_key or not index_name:
                self._init_error = (
                    "PINECONE_API_KEY or PINECONE_INDEX_NAME missing"
                )
                logger.warning("%s -> Pinecone disabled", self._init_error)
                self.index = None
                self.initialized = True
                return

            # import pinecone
            pinecone = importlib.import_module("pinecone")
            logger.info(
                "Pinecone module loaded: version=%s file=%s",
                getattr(pinecone, "__version__", "unknown"),
                getattr(pinecone, "__file__", "unknown"),
            )

            indexes = []
            chosen_index = None

            # === ONLY Pinecone v3 ===
            if hasattr(pinecone, "Pinecone"):
                try:
                    try:
                        pc = pinecone.Pinecone(api_key=api_key, environment=cfg_env)
                    except TypeError:
                        pc = pinecone.Pinecone(api_key=api_key)

                    self._pc = pc
                    self._pc_variant = "new"

                    index_list = pc.list_indexes()

                    if hasattr(index_list, "names"):
                        indexes = index_list.names()
                    elif isinstance(index_list, (list, tuple)):
                        indexes = list(index_list)
                    else:
                        indexes = list(index_list)

                except Exception as e:
                    self._init_error = f"Failed to initialize Pinecone client: {e}"
                    logger.error(self._init_error)
                    logger.debug(traceback.format_exc())
            else:
                self._init_error = (
                    "Installed pinecone package does not expose Pinecone class (v3+ required)"
                )
                logger.error(self._init_error)

            if self._pc is None:
                logger.warning(
                    "Pinecone client unavailable; running without semantic search. reason=%s",
                    self._init_error or "unknown",
                )
                self.index = None
                self.initialized = True
                return

            logger.info(f"Resolved Pinecone index name from config: '{index_name}'")
            logger.info(f"Pinecone indexes available: {repr(indexes)}")

            # chọn index
            if index_name in indexes:
                chosen_index = index_name
            else:
                candidates = [
                    i for i in indexes
                    if index_name.lower() in i.lower()
                    or i.lower().startswith(index_name.lower())
                ]
                if candidates:
                    chosen_index = candidates[0]
                    logger.warning(
                        f"Pinecone index '{index_name}' not found; fallback to '{chosen_index}'"
                    )
                elif indexes:
                    chosen_index = indexes[0]
                    logger.warning(
                        f"Pinecone index '{index_name}' not found; fallback to first '{chosen_index}'"
                    )
                else:
                    self._init_error = (
                        f"Pinecone index '{index_name}' does not exist and no indexes available"
                    )
                    logger.error(self._init_error)
                    self.index = None
                    self.initialized = True
                    return

            # tạo index client (v3 ONLY)
            try:
                self.index = self._pc.Index(chosen_index)
                self._active_index_name = chosen_index
                self._init_error = None
                logger.info(
                    f"Pinecone connected to index: {chosen_index} (v3 client)"
                )

                try:
                    stats = self.get_index_stats()
                    logger.info(f"Initial index stats: {stats}")
                except Exception:
                    logger.debug("Could not fetch initial index stats")

            except Exception as e:
                self._init_error = f"Failed to create index client: {e}"
                logger.error(self._init_error)
                logger.debug(traceback.format_exc())
                self.index = None

            self.initialized = True

            logger.info(
                "Vector service initialized (model loaded, Pinecone available=%s, active_index=%s, init_error=%s)",
                "yes" if self.index else "no",
                self._active_index_name,
                self._init_error,
            )

        except Exception as e:
            logger.error(f"Failed to initialize vector service: {str(e)}")
            logger.debug(traceback.format_exc())
            raise

    def generate_embedding(self, text: str) -> List[float]:
        if not self.initialized:
            self.initialize()

        embedding = self.model.encode(text)
        return embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)

    def upsert_product_embedding(
        self, product_id: str, text: str, metadata: Dict[str, Any] = None
    ):
        if not self.initialized:
            self.initialize()

        if not self.index:
            logger.warning("Pinecone index not available")
            return

        embedding = self.generate_embedding(text)

        vector_data = {
            "id": product_id,
            "values": embedding,
            "metadata": metadata or {},
        }

        self.index.upsert(vectors=[vector_data])
        logger.info(f"Upserted embedding for product: {product_id}")

    def search_similar_products(
        self,
        query_text: str,
        top_k: int = 10,
        filter_dict: Dict[str, Any] = None,
    ) -> List[Dict[str, Any]]:

        if not self.initialized:
            self.initialize()

        if not self.index:
            logger.info(
                "Skipping semantic search: Pinecone index unavailable (init_error=%s)",
                self._init_error,
            )
            return []

        query_embedding = self.generate_embedding(query_text)

        search_kwargs = {
            "vector": query_embedding,
            "top_k": top_k,
            "include_metadata": True,
            "include_values": False,
        }

        if filter_dict:
            search_kwargs["filter"] = filter_dict

        results = self.index.query(**search_kwargs)

        return [
            {
                "id": m.id,
                "score": m.score,
                "metadata": m.metadata or {},
            }
            for m in getattr(results, "matches", []) or []
        ]

    def delete_product_embedding(self, product_id: str):
        if not self.initialized:
            self.initialize()

        if self.index:
            self.index.delete(ids=[product_id])

    def get_index_stats(self) -> Dict[str, Any]:
        if not self.initialized or not self.index:
            logger.debug(
                "Index stats unavailable (initialized=%s, has_index=%s, init_error=%s)",
                self.initialized,
                bool(self.index),
                self._init_error,
            )
            return {}

        try:
            describe_fn = getattr(self.index, "describe_index_stats", None)
            if not callable(describe_fn):
                logger.error(
                    "Index stats function unavailable: index_type=%s has_describe=%s describe_callable=%s",
                    type(self.index).__name__,
                    hasattr(self.index, "describe_index_stats"),
                    callable(describe_fn),
                )
                return {}
            return describe_fn()
        except Exception as e:
            logger.exception("Failed to get index stats: %s", e)
            return {}

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "initialized": self.initialized,
            "pinecone_available": bool(self.index),
            "pc_variant": self._pc_variant,
            "active_index_name": self._active_index_name,
            "init_error": self._init_error,
        }

    def batch_upsert_products(
        self,
        products: List[Dict[str, Any]],
        batch_size: int = 100,
    ):
        if not self.initialized:
            self.initialize()

        if not self.index:
            return

        vectors = []

        for product in products:
            embedding = self.generate_embedding(product["text"])

            vectors.append(
                {
                    "id": product["id"],
                    "values": embedding,
                    "metadata": product.get("metadata", {}),
                }
            )

            if len(vectors) >= batch_size:
                self.index.upsert(vectors=vectors)
                vectors = []

        if vectors:
            self.index.upsert(vectors=vectors)

        logger.info(f"Batch upserted {len(products)} products")