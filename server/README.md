# E-commerce + AI Chatbot Backend API

AI chatbot with vector search capabilities, LangChain integration, and Google Gemini support. Provides advanced product search, recommendations, and order management, cart management.

## Features

### **Assistant for Order Management and Advanced Search**

- Advanced product searches, comparisons, cart operations, and recommendations based on user intent
- Powered by Google Gemini Flash 2.0 for deep, contextual conversations
- Maintains conversation history and user preferences across multiple interactions

### **Advanced Vector Search**

- Pinecone-powered vector database for understanding product relationships and user intent
- Sentence Transformer models convert product descriptions into meaningful vector representations
- AI analyzes user behavior patterns and preferences for personalized suggestions
- Finds products similar to user preferences even without exact keyword matches

### **E-commerce Engine**

- Multi-dimensional search by price, brand, specifications, ratings, and availability
- Persistent shopping carts with automatic price updates
- User-friendly product comparisons and recommendations

## Setup

Prerequisites

- Python 3.12+
- Pinecone account and API key
- Google AI Studio API key (optional if using Groq)
- Groq API key (optional; when set, used instead of Gemini for chat)

Environment Setup

```bash
uv venv
source venv/bin/activate
uv sync

cp .env.example .env
GROQ_API_KEY=your-groq-api-key-here
# Optional: defaults to llama-3.1-8b-instant
GROQ_MODEL=llama-3.1-8b-instant
GOOGLE_API_KEY=your-google-api-key-here
PINECONE_API_KEY=your-pinecone-api-key-here
PINECONE_INDEX_NAME=ecommerce-chatbot-1
JWT_SECRET_KEY=your-jwt-secret-key-here
PORT=5001
```

### DB & Pinecone Setup

```bash
flask db upgrade

# sample data
python -m scripts.index_all_products
```

### Run the Application

```bash
python run.py
```

By default the app uses port `5001` to avoid common conflicts with Docker/WSL on `5000`.
If the configured port is busy, `run.py` will auto-select the next available port and log it.

## API Endpoints

### Authentication

- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login
- `POST /api/auth/refresh` - Refresh access token
- `GET /api/auth/me` - Get current user info
- `PUT /api/auth/preferences` - Update user preferences
- `POST /api/auth/deactivate` - Deactivate user account

### Products

- `GET /api/products/` - Get products with filtering
- `GET /api/products/<id>` - Get specific product
- `POST /api/products/search` - Advanced semantic search
- `GET /api/products/recommendations` - Get recommendations
- `GET /api/products/categories` - Get all categories
- `GET /api/products/brands` - Get all brands
- `GET /api/products/stats` - Get product statistics
- `POST /api/products/` - Create new product (Admin)
- `PUT /api/products/<id>` - Update product (Admin)
- `DELETE /api/products/<id>` - Delete product (Admin)

### Cart Management

- `GET /api/cart/<user_id>` - Get user's cart
- `POST /api/cart/add` - Add item to cart
- `DELETE /api/cart/remove` - Remove item from cart
- `PUT /api/cart/update` - Update cart item quantity
- `DELETE /api/cart/clear` - Clear entire cart

### User Likes & Favorites

- `POST /api/likes/toggle` - Toggle like/unlike product
- `GET /api/likes/user/<user_id>` - Get user's liked products
- `GET /api/likes/product/<product_id>` - Get product like count
- `POST /api/likes/check` - Check if user likes specific product
- `GET /api/likes/popular` - Get most popular/liked products

### Chat

- `POST /api/chat/message` - Send message to chatbot
- `GET /api/chat/history/<session_id>` - Get chat history
- `GET /api/chat/sessions` - Get user's chat sessions
- `DELETE /api/chat/sessions/<id>` - Delete chat session
- `POST /api/chat/sessions/<id>/clear` - Clear chat history
- `GET /api/chat/health` - Check chat service health

### System

- `GET /api/health` - API health check

## Database Models

### User

- **Authentication & Security**: Email/password authentication with bcrypt hashing
- **User Preferences**: JSON-stored preferences (favorite categories, price ranges, brands)
- **Profile Management**: Name, email, account status, timestamps
- **Relationships**: One-to-many with chat sessions, cart items, and user likes
- **JWT Integration**: Secure token-based authentication support

### Product

- **Core Information**: Name, description, pricing (current/original), category hierarchy
- **Inventory Management**: Stock levels, availability status, sale indicators
- **Brand & Rating**: Brand information, user ratings, review counts
- **Rich Media**: Image URLs, feature lists (JSON-stored)
- **Search Optimization**: Full-text search indexes on key fields
- **Vector Integration**: Embedding IDs for semantic search capabilities

### Cart

- **Shopping Cart**: User-specific cart items with quantity management
- **Relationships**: Links users to products with quantity tracking
- **Timestamps**: Creation and update tracking for cart persistence
- **Unique Constraints**: User-product relationship management

### UserLike (Favorites)

- **User Preferences**: Track user likes/favorites for products
- **Relationship Management**: Many-to-many user-product relationships
- **Unique Constraints**: Prevents duplicate likes per user-product pair
- **Analytics Ready**: Supports popularity tracking and recommendations

### ChatSession

- **Conversation Management**: User-specific chat session tracking
- **Session Metadata**: Creation timestamps, session identification
- **User Association**: Links to user accounts for personalized experiences
- **Message Relationships**: One-to-many with individual messages

### Message

- **Chat History**: Individual chat messages with content and metadata
- **Product Integration**: Links messages to relevant products
- **Message Types**: Support for different message types and formats
- **Session Tracking**: Associates messages with specific chat sessions

## Services Architecture

### VectorService

- **Pinecone Integration**: Cloud-based vector database management
- **Embedding Generation**: Sentence Transformer model integration for product vectorization
- **Semantic Search**: Advanced similarity matching and product discovery
- **Batch Operations**: Efficient bulk indexing and search operations
- **Vector Management**: Embedding storage, retrieval, and similarity calculations

### ChatService

- **LangChain Orchestration**: Advanced conversation flow management with memory
- **Google Gemini Integration**: State-of-the-art AI model with 1M token context
- **Intelligent Tool Calling**: Dynamic product search, filtering, and recommendations
- **Session Management**: Persistent conversation history and context preservation
- **Multi-Modal Support**: Text processing with context-aware responses

### ProductService

- **CRUD Operations**: Complete product lifecycle management
- **Advanced Search**: Multi-dimensional filtering (price, brand, category, rating)
- **Recommendation Engine**: AI-powered product suggestions based on user behavior
- **Inventory Management**: Stock tracking, availability checks, pricing updates
- **Embedding Integration**: Automatic vector generation for semantic search

### AuthService

- **JWT Authentication**: Secure token-based authentication with refresh tokens
- **User Management**: Registration, login, profile updates, account deactivation
- **Preference Handling**: User-specific settings and behavioral preferences
- **Security Validation**: Password hashing, token verification, session management
- **Authorization**: Role-based access control and permission management

### CartService

- **Shopping Cart Management**: Add, remove, update cart items with quantity control
- **Cart Persistence**: User-specific cart storage with automatic updates
- **Product Integration**: Real-time product data synchronization
- **Quantity Validation**: Stock availability checks and quantity limits
- **Cart Operations**: Bulk operations, cart clearing, and item management

### LikeService

- **User Preferences**: Like/unlike functionality for products
- **Favorites Management**: User-specific product favorites tracking
- **Social Features**: Popular products identification and trending analysis
- **Recommendation Support**: Like-based product suggestions
- **Analytics Integration**: User behavior tracking for personalization

## Development

### Adding New Products

```python
from services.product_service import ProductService

product_service = ProductService()
product_data = {
    'name': 'New Product',
    'description': 'Product description',
    'price': 299.99,
    'category': 'Electronics',
    'subcategory': 'Smartphones',
    'brand': 'Brand Name',
    'features': ['Feature 1', 'Feature 2']
}

product = product_service.create_product(product_data)
```

following this, you can index the product in Pinecone:

```bash
python -m scripts.index_all_products
```

### Vector Search

```python
from services.vector_service import VectorService

vector_service = VectorService()
vector_service.initialize()

# Search for similar products
results = vector_service.search_similar_products(
    "gaming laptop with RTX graphics",
    top_k=10
)
```

### Log Files

- `logs/ecommerce_chatbot.log` - Application logs
- Rotating file handler (10MB max, 10 backups)
- Console and file output

### Health Checks

- `/api/health` - Basic API health
- `/api/chat/health` - Chat service health
- Vector database statistics
- Service initialization status

## Troubleshooting

### Common Issues

1. **Pinecone Connection Error**

   - Verify API key and environment
   - Check network connectivity
   - Ensure index exists

2. **Google AI API Error**

   - Verify API key
   - Check quota limits
   - Ensure proper model access

3. **Database Migration Issues**

   - Delete migration files and reinitialize
   - Check database permissions
   - Verify SQLAlchemy models

4. **Memory Issues**
   - Monitor conversation memory usage
   - Clear old sessions periodically
   - Optimize embedding storage

## Contributing

1. Fork the repository
2. Create a branch
3. Make your changes
4. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
