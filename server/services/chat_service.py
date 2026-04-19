import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import or_

from flask import current_app
# Import AgentType from possible locations for compatibility across langchain versions
try:
    from langchain.agents import AgentType, initialize_agent
except Exception:
    try:
        # newer/langchain layout
        from langchain.agents.agent_types import AgentType
        from langchain.agents import initialize_agent
    except Exception:
        # Fallback: initialize_agent may still be available
        try:
            from langchain.agents import initialize_agent
            AgentType = None
        except Exception:
            initialize_agent = None
            AgentType = None
try:
    from langchain.memory import ConversationBufferWindowMemory
except Exception:
    try:
        from langchain.memory.chat_memory import ConversationBufferWindowMemory
    except Exception:
        # Minimal fallback implementation used when langchain memory is unavailable.
        class ConversationBufferWindowMemory:
            def __init__(self, k=10, return_messages=True, memory_key="chat_history"):
                self.k = k
                self.return_messages = return_messages
                self.memory_key = memory_key
                self.buffer = []

            def load_memory_variables(self, inputs):
                return {self.memory_key: self.buffer}

            def save_context(self, inputs, outputs):
                # store as simple strings for compatibility
                user = inputs.get("input") if isinstance(inputs, dict) else str(inputs)
                bot = outputs if isinstance(outputs, str) else str(outputs)
                if user:
                    self.buffer.append(user)
                if bot:
                    self.buffer.append(bot)
try:
    from langchain.schema import AIMessage, HumanMessage, SystemMessage
except Exception:
    AIMessage = None
    HumanMessage = None
    SystemMessage = None

try:
    from langchain.tools import Tool
except Exception:
    # Minimal fallback Tool class
    class Tool:
        def __init__(self, name: str, description: str, func):
            self.name = name
            self.description = description
            self.func = func

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:
    ChatGoogleGenerativeAI = None
try:
    from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
except Exception:
    ChatGoogleGenerativeAIError = Exception
try:
    from langchain_groq import ChatGroq
except Exception:
    ChatGroq = None
from models.chat_session import ChatSession
from models.message import Message
from models.product import Product

from .cart_service import CartService
from .product_service import ProductService
from .vector_service import VectorService

logger = logging.getLogger(__name__)


class ChatService:
    """Enhanced chat service with LangChain and Gemini integration"""

    def __init__(self):
        self.llm = None
        self.vector_service = VectorService()
        self.product_service = ProductService()
        self.cart_service = CartService()
        self.memory_sessions = {}
        self.initialized = False
        self._llm_retry_after_ts = 0.0
        self._llm_provider: Optional[str] = None

    @staticmethod
    def _is_llm_rate_limited(err_text: str) -> bool:
        if not err_text:
            return False
        upper = err_text.upper()
        return (
            "429" in err_text
            or "RESOURCE_EXHAUSTED" in upper
            or "RATE_LIMIT" in upper
        )

    @property
    def llm_provider(self) -> Optional[str]:
        """Active LLM backend when `self.llm` is set: groq, gemini, or None."""
        return self._llm_provider

    def initialize(self):
        """Initialize LangChain components"""
        try:
            logger.info("Chat service initialization started")

            self.llm = None
            self._llm_provider = None

            groq_key = current_app.config.get("GROQ_API_KEY")
            if ChatGroq and groq_key:
                try:
                    self.llm = ChatGroq(
                        api_key=groq_key,
                        model=current_app.config.get(
                            "GROQ_MODEL", "llama-3.1-8b-instant"
                        ),
                        temperature=0.7,
                        max_tokens=1024,
                        max_retries=1,
                    )
                    self._llm_provider = "groq"
                    logger.info("LLM enabled: Groq (%s)", current_app.config.get("GROQ_MODEL"))
                except Exception as e:
                    logger.warning("ChatGroq initialization failed: %s", e)

            if self.llm is None and ChatGoogleGenerativeAI and current_app.config.get(
                "GOOGLE_API_KEY"
            ):
                self.llm = ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash",
                    google_api_key=current_app.config["GOOGLE_API_KEY"],
                    temperature=0.7,
                    max_tokens=1000,
                    max_retries=1,
                    convert_system_message_to_human=True,
                )
                self._llm_provider = "gemini"
                logger.info("LLM enabled: Gemini (gemini-2.0-flash)")

            if self.llm is None:
                logger.warning(
                    "No LLM configured; set GROQ_API_KEY and/or GOOGLE_API_KEY. "
                    "Chat will use keyword/vector fallback only."
                )

            # initialize vector service (embedding model) - may work without Pinecone
            try:
                self.vector_service.initialize()
                logger.info(
                    "Vector diagnostics after init: %s",
                    self.vector_service.get_diagnostics(),
                )
            except Exception as e:
                logger.warning(f"Vector service failed to initialize: {e}")

            self.initialized = True
            logger.info("Chat service initialized (LLM %s)", "enabled" if self.llm else "disabled")

        except Exception as e:
            logger.error(f"Failed to initialize chat service: {str(e)}")
            raise

    def get_or_create_memory(self, session_id: str) -> ConversationBufferWindowMemory:
        """Get or create memory for a chat session"""
        if session_id not in self.memory_sessions:
            self.memory_sessions[session_id] = ConversationBufferWindowMemory(
                k=10,
                return_messages=True,
                memory_key="chat_history",
            )
        return self.memory_sessions[session_id]

    def create_tools(self) -> List[Tool]:
        """Create tools for the LangChain agent"""
        tools = [
            Tool(
                name="search_products",
                description="Find products using semantic search. Input: search query (str).",
                func=self._search_products_tool,
            ),
            Tool(
                name="filter_products",
                description="Filter products. Input: JSON string with keys: category, subcategory, brand, min_price, max_price, min_rating, in_stock_only, features (list), search_query, limit.",
                func=self._filter_products_tool,
            ),
            Tool(
                name="get_product_details",
                description="Get product details. Input: product ID (str).",
                func=self._get_product_details_tool,
            ),
            Tool(
                name="get_recommendations",
                description="Get recommendations. Input: product ID (str) or preference description (str).",
                func=self._get_recommendations_tool,
            ),
            Tool(
                name="add_to_cart",
                description="Add a product to the user's cart. Input: JSON string with keys: product_id (str), quantity (int, optional, default 1).",
                func=self._add_to_cart_tool,
            ),
        ]
        return tools

    def _search_products_tool(self, query: str) -> str:
        """Tool function for semantic product search"""
        try:
            similar_products = self.vector_service.search_similar_products(
                query, top_k=6
            )

            if not similar_products:
                return json.dumps(
                    {
                        "message": "No products found for the given query.",
                        "product_ids": [],
                    }
                )

            product_ids = [p["id"] for p in similar_products]
            products = Product.query.filter(Product.id.in_(product_ids)).all()

            result = "Found the following products:\n"
            for product in products:
                result += f"- {product.name} by {product.brand} - ${product.price}\n"
                result += f"  {product.description[:100]}...\n"

            return json.dumps({"message": result, "product_ids": product_ids})

        except Exception as e:
            logger.error(f"Error in search_products_tool: {str(e)}")
            return json.dumps(
                {
                    "message": "Error occurred while searching for products.",
                    "product_ids": [],
                }
            )

    def _filter_products_tool(self, filter_json: str) -> str:
        """Tool function for filtering products"""
        try:
            filters = json.loads(filter_json)
            products = Product.search_by_filters(**filters)

            if not products:
                return json.dumps(
                    {
                        "message": "No products found matching the specified filters.",
                        "product_ids": [],
                    }
                )

            result = f"Found {len(products)} products matching your criteria:\n"
            for product in products[:5]:
                result += f"- {product.name} by {product.brand} - ${product.price}\n"

            product_ids = [product.id for product in products[:5]]
            return json.dumps({"message": result, "product_ids": product_ids})

        except Exception as e:
            logger.error(f"Error in filter_products_tool: {str(e)}")
            return json.dumps(
                {
                    "message": "Error occurred while filtering products.",
                    "product_ids": [],
                }
            )

    def _get_product_details_tool(self, product_id: str) -> str:
        """Tool function for getting product details"""
        try:
            product = Product.query.get(product_id.strip())
            if not product:
                return "Product not found."

            result = "Product Details:\n"
            result += f"Name: {product.name}\n"
            result += f"Brand: {product.brand}\n"
            result += f"Price: ${product.price}\n"
            result += f"Rating: {product.rating}/5 ({product.review_count} reviews)\n"
            result += f"Description: {product.description}\n"
            result += f"Features: {', '.join(product.get_features())}\n"
            result += f"Stock: {product.stock} available\n"

            return result

        except Exception as e:
            logger.error(f"Error in get_product_details_tool: {str(e)}")
            return "Error occurred while getting product details."

    def _get_recommendations_tool(self, input_text: str) -> str:
        """Tool function for getting product recommendations"""
        try:
            product = Product.query.get(input_text.strip())

            if product:
                similar_products = self.vector_service.search_similar_products(
                    product.get_search_text(), top_k=4
                )
                similar_ids = [
                    p["id"] for p in similar_products if p["id"] != product.id
                ]
                recommendations = Product.query.filter(
                    Product.id.in_(similar_ids)
                ).all()
            else:
                similar_products = self.vector_service.search_similar_products(
                    input_text, top_k=4
                )
                similar_ids = [p["id"] for p in similar_products]
                recommendations = Product.query.filter(
                    Product.id.in_(similar_ids)
                ).all()

            if not recommendations:
                return "No recommendations found."

            result = "Here are some recommendations:\n"
            for rec in recommendations:
                result += f"- {rec.name} by {rec.brand} - ${rec.price}\n"

            return result

        except Exception as e:
            logger.error(f"Error in get_recommendations_tool: {str(e)}")
            return "Error occurred while getting recommendations."

    def _add_to_cart_tool(self, input_json: str) -> str:
        """Tool function to add a product to the user's cart"""
        try:
            # Log the input for debugging
            logger.info(f"add_to_cart_tool input: {input_json}")
            
            data = json.loads(input_json)
            product_id = data.get("product_id")
            quantity = data.get("quantity", 1)
            user_id = data.get("user_id", "guest_user")

            logger.info(f"Parsed data: product_id={product_id}, quantity={quantity}, user_id={user_id}")

            if not product_id:
                return json.dumps(
                    {"message": "Missing product_id for add to cart.", "success": False}
                )

            # If product_id looks like a product name, try to find the actual product
            if len(product_id) < 32 or " " in product_id:
                logger.info(f"Searching for product by name: {product_id}")
                # Search for product by name (case-insensitive)
                product = Product.query.filter(
                    Product.name.ilike(f"%{product_id}%")
                ).first()
                
                if product:
                    logger.info(f"Found product: {product.name} with ID: {product.id}")
                    product_id = product.id
                else:
                    logger.warning(f"Product not found: {product_id}")
                    return json.dumps(
                        {
                            "message": f"Product '{product_id}' not found.",
                            "success": False,
                        }
                    )

            # Add to cart using the cart service
            logger.info(f"Adding to cart: user_id={user_id}, product_id={product_id}, quantity={quantity}")
            result = self.cart_service.add_to_cart(user_id, product_id, quantity)
            logger.info(f"Cart service result: {result}")
            
            # Check if the cart service returned an error
            if not result.get("success", True):
                return json.dumps(result)
            
            # Get product details for response
            product = Product.query.get(product_id)
            if not product:
                return json.dumps(
                    {
                        "message": f"Product with ID {product_id} not found.",
                        "success": False,
                    }
                )

            success_response = {
                "message": f"Added {quantity} x {product.name} to your cart.",
                "success": True,
                "product": {
                    "id": product.id,
                    "name": product.name,
                    "price": product.price,
                },
                "quantity": quantity,
            }
            
            logger.info(f"Returning success response: {success_response}")
            return json.dumps(success_response)
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in add_to_cart_tool: {str(e)}")
            logger.error(f"Input that caused error: {repr(input_json)}")
            return json.dumps(
                {"message": "Invalid JSON format in request.", "success": False}
            )
        except Exception as e:
            logger.error(f"Error in add_to_cart_tool: {str(e)}")
            return json.dumps(
                {"message": "Error occurred while adding to cart.", "success": False}
            )

    def _extract_product_names_from_text(self, text: str) -> list:
        """Extract product names from the message text by matching against all product names in the database."""
        product_names = []
        all_products = Product.query.all()
        for product in all_products:
            if product.name in text:
                product_names.append(product.name)
        return product_names

    def _detect_fallback_intent(self, text: str) -> str:
        normalized = (text or "").strip().lower()
        if not normalized:
            return "empty"

        greeting_words = ["chào", "hello", "hi", "xin chào", "hey"]
        recommend_words = ["gợi ý", "đề xuất", "recommend", "suggest"]
        product_words = [
            "mua",
            "tìm",
            "sản phẩm",
            "điện thoại",
            "laptop",
            "tai nghe",
            "iphone",
            "samsung",
            "sony",
            "bose",
            "giá",
        ]

        if any(word in normalized for word in greeting_words) and not any(
            word in normalized for word in product_words
        ):
            return "greeting_only"

        if any(word in normalized for word in recommend_words):
            return "recommendation"

        return "product_search"

    def _compose_fallback_product_reply(
        self, user_message: str, products: List[Product], source: str
    ) -> str:
        intent = self._detect_fallback_intent(user_message)
        if intent == "recommendation":
            intro = "Mình gợi ý nhanh cho bạn vài sản phẩm đáng cân nhắc:"
        elif intent == "product_search":
            intro = "Mình đã tìm được một số sản phẩm phù hợp với nhu cầu của bạn:"
        else:
            intro = "Mình có vài sản phẩm bạn có thể tham khảo:"

        lines = [intro]
        for product in products[:6]:
            lines.append(f"- {product.name} ({product.brand}) - ${product.price}")

        if source == "keyword":
            lines.append(
                "Nếu bạn muốn chính xác hơn, bạn nói thêm mức giá, thương hiệu hoặc mục đích sử dụng nhé."
            )
        else:
            lines.append(
                "Bạn muốn mình lọc tiếp theo giá, thương hiệu hay loại sản phẩm không?"
            )

        return "\n".join(lines)

    def process_message(
        self, session_id: str, user_message: str, user_id: str = None
    ) -> Dict[str, Any]:
        """Process user message and generate AI response"""
        if not self.initialized:
            self.initialize()

        try:
            chat_session = ChatSession.query.get(session_id)
            if not chat_session:
                chat_session = ChatSession(id=session_id, user_id=user_id)
                from app import db

                db.session.add(chat_session)
                db.session.commit()

            user_msg = Message(
                id=str(uuid.uuid4()),
                chat_session_id=session_id,
                content=user_message,
                is_bot=False,
            )
            from app import db

            db.session.add(user_msg)

            memory = self.get_or_create_memory(session_id)
            chat_history = []
            if hasattr(memory, "buffer"):
                for msg in memory.buffer:
                    if hasattr(msg, "content"):
                        chat_history.append(msg.content)
                    elif isinstance(msg, str):
                        chat_history.append(msg)

            tools = self.create_tools()

            # Use LLM directly when available; no dependency on legacy initialize_agent APIs.
            llm_temporarily_blocked = time.time() < self._llm_retry_after_ts
            if self.llm is not None and not llm_temporarily_blocked:
                try:
                    logger.info(
                        "Using direct LLM handler (provider=%s)",
                        self._llm_provider or "unknown",
                    )
                    prompt = (
                        "Bạn là trợ lý mua sắm tiếng Việt thân thiện. "
                        "Trả lời tự nhiên, ngắn gọn, ưu tiên gợi ý rõ ràng theo nhu cầu user. "
                        "Nếu user chào hỏi, hãy chào lại thân thiện và hỏi nhu cầu mua sắm."
                    )
                    if SystemMessage and HumanMessage:
                        llm_response = self.llm.invoke(
                            [
                                SystemMessage(content=prompt),
                                HumanMessage(content=user_message),
                            ]
                        )
                    else:
                        llm_response = self.llm.invoke(
                            f"{prompt}\n\nNgười dùng: {user_message}"
                        )

                    llm_text = getattr(llm_response, "content", llm_response)
                    if isinstance(llm_text, list):
                        llm_text = "\n".join([str(x) for x in llm_text if x])
                    llm_text = str(llm_text).strip()
                    result = {"output": llm_text or "Mình đang sẵn sàng hỗ trợ bạn chọn sản phẩm."}
                except ChatGoogleGenerativeAIError as e:
                    err_text = str(e)
                    if self._is_llm_rate_limited(err_text):
                        self._llm_retry_after_ts = time.time() + 120
                        logger.warning(
                            "Gemini rate/quota error. Temporarily disabling LLM for 120s."
                        )
                    else:
                        logger.warning("Direct Gemini handler failed: %s", err_text)
                    result = None
                except Exception as e:
                    err_text = str(e)
                    if self._is_llm_rate_limited(err_text):
                        self._llm_retry_after_ts = time.time() + 120
                        logger.warning(
                            "LLM rate/quota error (provider=%s). Cooldown 120s.",
                            self._llm_provider,
                        )
                    else:
                        logger.warning("Direct LLM handler failed: %s", err_text)
                    result = None
            elif self.llm is not None and llm_temporarily_blocked:
                remaining = int(max(0, self._llm_retry_after_ts - time.time()))
                logger.info(
                    "Skipping LLM call during cooldown after rate/quota error (%ss remaining)",
                    remaining,
                )
                result = None
            else:
                result = None

            # If LLM is unavailable (or failed), use semantic-search fallback handler.
            if result is None:
                logger.info(
                    "Using fallback chat handler (llm_available=%s)",
                    self.llm is not None,
                )
                intent = self._detect_fallback_intent(user_message)
                logger.info("Fallback intent detected: %s", intent)

                if intent in ["empty", "greeting_only"]:
                    result = {
                        "output": (
                            "Chào bạn. Mình có thể giúp bạn tìm sản phẩm theo nhu cầu, "
                            "ví dụ: 'tôi muốn tai nghe chống ồn dưới 2 triệu' hoặc 'gợi ý điện thoại chụp ảnh tốt'."
                        )
                    }
                else:
                    result = None

                if result is None:
                    # Ensure vector service is initialized / re-check the index before searching
                    try:
                        if not getattr(self.vector_service, "index", None):
                            logger.info(
                                "Vector index not present, attempting re-initialize. diagnostics_before=%s",
                                self.vector_service.get_diagnostics(),
                            )
                            try:
                                self.vector_service.initialize()
                                logger.info(
                                    "Vector diagnostics after re-init: %s",
                                    self.vector_service.get_diagnostics(),
                                )
                            except Exception as e_init:
                                logger.warning(f"Re-initializing vector service failed: {e_init}")

                        similar = self.vector_service.search_similar_products(user_message, top_k=6)
                        logger.info(
                            "Fallback semantic search completed: query_len=%s result_count=%s",
                            len(user_message or ""),
                            len(similar),
                        )
                    except Exception:
                        logger.exception("Error while performing semantic search")
                        similar = []

                    if similar:
                        product_ids = [p["id"] for p in similar]
                        products = Product.query.filter(Product.id.in_(product_ids)).all()
                        result = {
                            "output": self._compose_fallback_product_reply(
                                user_message, products, source="semantic"
                            )
                        }
                    else:
                        # No semantic results: fallback to DB keyword search before generic reply.
                        terms = [t.strip() for t in (user_message or "").split() if len(t.strip()) >= 2]
                        keyword_products = []
                        if terms:
                            try:
                                conditions = []
                                for term in terms[:6]:
                                    like_term = f"%{term}%"
                                    conditions.extend(
                                        [
                                            Product.name.ilike(like_term),
                                            Product.description.ilike(like_term),
                                            Product.brand.ilike(like_term),
                                            Product.category.ilike(like_term),
                                        ]
                                    )
                                keyword_products = (
                                    Product.query.filter(or_(*conditions))
                                    .limit(6)
                                    .all()
                                )
                                logger.info(
                                    "Keyword fallback search completed: terms=%s result_count=%s",
                                    terms[:6],
                                    len(keyword_products),
                                )
                            except Exception:
                                logger.exception("Keyword fallback search failed")

                        if keyword_products:
                            result = {
                                "output": self._compose_fallback_product_reply(
                                    user_message, keyword_products, source="keyword"
                                )
                            }
                        else:
                            # No semantic and no keyword result — fallback generic reply
                            logger.warning(
                                "No semantic result and no keyword result; returning generic fallback"
                            )
                            message_text = (
                                "Mình chưa tìm thấy sản phẩm phù hợp ngay lúc này. "
                                "Bạn thử nói rõ hơn giúp mình về loại sản phẩm, tầm giá hoặc thương hiệu nhé."
                            )
                            result = {"output": message_text}

                        logger.warning(
                            "Fallback semantic search returned no results; diagnostics=%s",
                            self.vector_service.get_diagnostics(),
                        )
            ai_response = (
                result["output"] if isinstance(result, dict) and "output" in result else result
            )

            product_ids = []
            if isinstance(result, dict) and "intermediate_steps" in result:
                for step in result["intermediate_steps"]:
                    tool_name = (
                        getattr(step[0], "tool", None)
                        if hasattr(step[0], "tool")
                        else None
                    )
                    tool_output = step[1]
                    if tool_name in ["search_products", "filter_products"]:
                        try:
                            parsed = json.loads(tool_output)
                            ids = parsed.get("product_ids", [])
                            if ids:
                                product_ids.extend(ids)
                        except Exception:
                            pass
            product_ids = list(dict.fromkeys(product_ids))

            message_text = ai_response
            if not product_ids:
                try:
                    parsed = json.loads(ai_response)
                    message_text = parsed.get("message", ai_response)
                    product_ids = parsed.get("product_ids", [])
                except Exception:
                    pass

            if not product_ids:
                product_names = self._extract_product_names_from_text(message_text)
                if product_names:
                    product_ids = [
                        p.id
                        for p in Product.query.filter(
                            Product.name.in_(product_names)
                        ).all()
                    ]

            ai_msg = Message(
                id=str(uuid.uuid4()),
                chat_session_id=session_id,
                content=message_text,
                is_bot=True,
                message_type="product" if product_ids else "text",
                products=product_ids,
            )
            db.session.add(ai_msg)
            db.session.commit()

            products = []
            if product_ids:
                products = [
                    Product.query.get(pid).to_dict()
                    for pid in product_ids
                    if Product.query.get(pid)
                ]

            return {
                "id": ai_msg.id,
                "content": message_text,
                "isBot": True,
                "timestamp": ai_msg.created_at.isoformat(),
                "products": products,
                "type": ai_msg.message_type,
            }

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            error_msg = Message(
                id=str(uuid.uuid4()),
                chat_session_id=session_id,
                content="I'm sorry, I encountered an error. Please try again.",
                is_bot=True,
            )
            from app import db

            db.session.add(error_msg)
            db.session.commit()
            return {
                "id": error_msg.id,
                "content": error_msg.content,
                "isBot": True,
                "timestamp": error_msg.created_at.isoformat(),
                "products": [],
                "type": "text",
            }

    def _extract_product_ids_from_response(self, response: str) -> List[str]:
        """Extract product IDs from AI response (basic implementation)"""

        product_ids = []

        return product_ids

    def get_chat_history(
        self, session_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get chat history for a session"""
        try:
            messages = (
                Message.query.filter_by(chat_session_id=session_id)
                .order_by(Message.created_at.asc())
                .limit(limit)
                .all()
            )

            return [msg.to_dict(include_product_details=True) for msg in messages]

        except Exception as e:
            logger.error(f"Error getting chat history: {str(e)}")
            return []

    def clear_session_memory(self, session_id: str):
        """Clear memory for a specific session"""
        if session_id in self.memory_sessions:
            del self.memory_sessions[session_id]
