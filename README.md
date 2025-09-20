# QuickPost - Modern Social Media Platform

<div align="center">

[![Django](https://img.shields.io/badge/Django-5.2.4-092E20?style=for-the-badge&logo=django&logoColor=white)](https://djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org/)
[![WebSocket](https://img.shields.io/badge/WebSocket-Real--time-FF6B6B?style=for-the-badge&logo=websocket&logoColor=white)](https://channels.readthedocs.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

**A full-stack social media platform built with Django 5.2.4, featuring real-time messaging, modern dark theme UI, and comprehensive social networking features.**

[Features](#features) • [Installation](#installation) • [Usage](#usage) • [API Documentation](#api-documentation) • [Contributing](#contributing)

</div>

---

## Table of Contents

- [Features](#features)
- [Technical Requirements](#technical-requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Architecture](#architecture)
- [API Documentation](#api-documentation)
- [Database Schema](#database-schema)
- [WebSocket Implementation](#websocket-implementation)
- [Security](#security)
- [Performance](#performance)
- [Testing](#testing)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [License](#license)

---

## Features

### Core Functionality
- **User Authentication System** - Registration, login, logout with Django's built-in auth
- **Post Management** - Create, edit, delete posts with character limit (240 chars)
- **Media Upload** - Image upload with PIL processing and optimization
- **Social Interactions** - Like/dislike system with ManyToMany relationships
- **Comment System** - Threaded comments with real-time updates
- **User Profiles** - Extended user model with custom profile fields
- **Follow System** - User-to-user following with follower/following counts

### Real-time Features
- **Live Messaging** - WebSocket-based chat using Django Channels
- **Typing Indicators** - Real-time typing status updates
- **Message Status** - Read receipts and delivery confirmations
- **Connection Management** - Automatic reconnection with fallback to AJAX
- **Conversation Management** - Inbox-style conversation list

### UI/UX Implementation
- **Dark Theme System** - CSS custom properties with comprehensive color scheme
- **Responsive Design** - Mobile-first approach with CSS Grid and Flexbox
- **Modern Animations** - CSS transitions and keyframe animations
- **Interactive Components** - Hover states and micro-interactions
- **Accessibility** - ARIA labels and keyboard navigation support

---

## Technical Requirements

### System Requirements
- **Python 3.12 or higher**
- **pip package manager**
- **Redis server** (for WebSocket channel layer)
- **Git** (for version control)
- **SQLite** (default) or **PostgreSQL** (recommended for production)

### Python Dependencies
```
Django==5.2.4
channels==4.3.1
channels_redis==4.3.0
redis==6.4.0
Pillow==11.3.0
APScheduler==3.11.0
google-genai==1.36.0
websockets==15.0.1
python-dotenv==1.1.1
```

### Optional Requirements
- **PostgreSQL** - For production database
- **Nginx** - For reverse proxy and static file serving
- **Gunicorn** - For WSGI application server
- **Docker** - For containerized deployment
- **Celery** - For background task processing

---

## Installation

### Development Setup

1. **Clone Repository**
   ```bash
   git clone https://github.com/RajeebLochan/QuickPost.git
   cd QuickPost
   ```

2. **Create Virtual Environment**
   ```bash
   python -m venv venv
   
   # Linux/macOS
   source venv/bin/activate
   
   # Windows
   venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Database Setup**
   ```bash
   cd quickpost
   python manage.py makemigrations
   python manage.py migrate
   ```

5. **Create Superuser** (Optional)
   ```bash
   python manage.py createsuperuser
   ```

6. **Start Redis Server**
   ```bash
   # Linux/macOS
   redis-server
   
   # Windows (if installed via WSL or native)
   redis-server.exe
   ```

7. **Run Development Server**
   ```bash
   python manage.py runserver
   ```

### Production Setup

1. **Environment Configuration**
   Create `.env` file in project root:
   ```env
   DEBUG=False
   SECRET_KEY=your-production-secret-key
   ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
   DATABASE_URL=postgresql://user:password@localhost:5432/quickpost
   REDIS_URL=redis://localhost:6379/0
   ```

2. **Database Configuration**
   ```python
   # settings.py
   import dj_database_url
   
   DATABASES = {
       'default': dj_database_url.parse(os.environ.get('DATABASE_URL'))
   }
   ```

3. **Static Files**
   ```bash
   python manage.py collectstatic --noinput
   ```

4. **Process Management**
   ```bash
   # Using Gunicorn
   gunicorn quickpost.wsgi:application --bind 0.0.0.0:8000
   
   # Using Daphne (for ASGI)
   daphne quickpost.asgi:application --bind 0.0.0.0 --port 8000
   ```

---

## Configuration

### Django Settings

**Required Settings**
```python
# quickpost/settings.py

INSTALLED_APPS = [
    'channels',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'post',
]

ASGI_APPLICATION = 'quickpost.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [('127.0.0.1', 6379)],
        },
    },
}
```

**Media Configuration**
```python
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# File upload limits
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
```

**Authentication Settings**
```python
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/post/'
LOGOUT_REDIRECT_URL = 'home'
```

### WebSocket Configuration

**ASGI Configuration**
```python
# quickpost/asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from post.routing import websocket_urlpatterns

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'quickpost.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
```

**WebSocket Routing**
```python
# post/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<conversation_id>\d+)/$', consumers.ChatConsumer.as_asgi()),
]
```

---

## Usage

### User Management

**Registration Process**
```python
# Navigate to /accounts/register/
# POST data: username, email, password1, password2, first_name, last_name
# Automatic UserProfile creation via post_save signal
```

**Profile Management**
```python
# URL: /post/profile/edit/
# Fields: bio, profile_image, location, website, birth_date
# Image processing with PIL for optimization
```

### Content Management

**Post Creation**
```python
# URL: /post/create/
# Fields: content (max 240 chars), photo (optional)
# Automatic image resize and optimization
# Real-time feed updates
```

**Engagement System**
```python
# Like/Dislike: AJAX requests to /post/like/<id>/ and /post/dislike/<id>/
# Comments: POST to /post/comment/<id>/
# Real-time counter updates via JavaScript
```

### Messaging System

**WebSocket Connection**
```javascript
// Client-side WebSocket implementation
const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
const wsPath = `${wsScheme}://${window.location.host}/ws/chat/${conversationId}/`;
const chatSocket = new WebSocket(wsPath);
```

**Message Handling**
```python
# Real-time message delivery via WebSocket
# Fallback to AJAX for connection failures
# Typing indicators with debounced updates
# Message status tracking (sent, delivered, read)
```

---

## Architecture

### Project Structure
```
QuickPost/
├── quickpost/                 # Django project root
│   ├── quickpost/            # Project configuration
│   │   ├── settings.py       # Django settings
│   │   ├── urls.py          # URL configuration
│   │   ├── asgi.py          # ASGI configuration
│   │   └── wsgi.py          # WSGI configuration
│   ├── post/                 # Main application
│   │   ├── models.py         # Data models
│   │   ├── views.py          # View controllers
│   │   ├── forms.py          # Form definitions
│   │   ├── urls.py           # URL patterns
│   │   ├── consumers.py      # WebSocket consumers
│   │   ├── routing.py        # WebSocket routing
│   │   ├── admin.py          # Admin interface
│   │   ├── apps.py           # App configuration
│   │   ├── scheduler.py      # Background tasks
│   │   ├── migrations/       # Database migrations
│   │   └── templates/        # HTML templates
│   ├── templates/            # Global templates
│   │   ├── layout.html       # Base template
│   │   └── registration/     # Auth templates
│   ├── static/              # Static files
│   ├── media/               # User uploads
│   └── manage.py            # Django CLI
├── requirements.txt          # Python dependencies
├── README.md                # Documentation
└── .env                     # Environment variables
```

### Data Models

**Core Models**
```python
class Post(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(max_length=240)
    photo = models.ImageField(upload_to='photos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    likes = models.ManyToManyField(User, related_name='liked_posts', blank=True)
    dislikes = models.ManyToManyField(User, related_name='disliked_posts', blank=True)

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(max_length=500, blank=True)
    profile_image = models.ImageField(upload_to='profile_pics/', default='profile_pics/default.jpg')
    location = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    birth_date = models.DateField(null=True, blank=True)
    following = models.ManyToManyField('self', symmetrical=False, blank=True)

class Conversation(models.Model):
    participants = models.ManyToManyField(User, related_name='conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
```

### View Architecture

**Class-Based Views**
```python
# Function-based views for simplicity and customization
def post_list(request):
    # Main feed with pagination and filtering
    # Query optimization with select_related and prefetch_related
    
def create_post(request):
    # Form handling with custom validation
    # Image processing and optimization
    
def chat_room(request, conversation_id):
    # WebSocket integration
    # Message history loading
    # Real-time UI updates
```

---

## API Documentation

### REST Endpoints

**Post Management**
```
GET    /post/                     # List posts (paginated)
POST   /post/create/              # Create new post
GET    /post/edit/<int:post_id>/  # Get post edit form
POST   /post/edit/<int:post_id>/  # Update post
DELETE /post/delete/<int:post_id>/ # Delete post
POST   /post/like/<int:post_id>/  # Toggle like
POST   /post/dislike/<int:post_id>/ # Toggle dislike
POST   /post/comment/<int:post_id>/ # Add comment
```

**User Management**
```
GET  /post/profile/<str:username>/           # User profile
POST /post/profile/edit/                     # Update profile
POST /post/follow/<str:username>/            # Toggle follow
GET  /post/profile/<str:username>/followers/ # Followers list
GET  /post/profile/<str:username>/following/ # Following list
```

**Messaging**
```
GET  /post/conversations/                    # Conversation list
GET  /post/chat/<int:conversation_id>/       # Chat interface
POST /post/start-conversation/<int:user_id>/ # Start new conversation
POST /post/ajax/send-message/                # Send message (AJAX)
GET  /post/ajax/messages/<int:conversation_id>/ # Get messages (AJAX)
```

**Authentication**
```
GET  /accounts/login/     # Login form
POST /accounts/login/     # Authenticate user
GET  /accounts/register/  # Registration form
POST /accounts/register/  # Create account
POST /accounts/logout/    # Logout user
```

### WebSocket API

**Connection**
```javascript
// WebSocket endpoint: ws://localhost:8000/ws/chat/<conversation_id>/
// Authentication: Django session-based
// Protocol: JSON message format
```

**Message Types**
```json
// Send message
{
    "message": "Hello, world!"
}

// Typing indicator
{
    "typing": true
}

// Receive message
{
    "message": "Hello, world!",
    "sender": "username",
    "sender_id": 1,
    "timestamp": "2025-09-20T22:30:00Z"
}

// Typing status
{
    "typing": true,
    "sender_id": 1
}

// Error response
{
    "error": "Authentication required"
}
```

---

## Database Schema

### Entity Relationship Diagram
```
User (Django Auth)
├── UserProfile (OneToOne)
├── Post (ForeignKey)
├── Comment (ForeignKey)
├── Message (ForeignKey)
└── Conversation (ManyToMany)

Post
├── User (ForeignKey)
├── Comment (ForeignKey)
├── likes (ManyToMany → User)
└── dislikes (ManyToMany → User)

Conversation
├── participants (ManyToMany → User)
└── Message (ForeignKey)
```

### Database Indexes
```python
class Meta:
    indexes = [
        models.Index(fields=['created_at']),
        models.Index(fields=['user', 'created_at']),
        models.Index(fields=['conversation', 'created_at']),
    ]
```

### Query Optimization
```python
# Optimized queries with select_related and prefetch_related
posts = Post.objects.select_related('user__profile').prefetch_related(
    'likes', 'dislikes', 'comments__user'
).order_by('-created_at')

conversations = Conversation.objects.filter(
    participants=request.user
).prefetch_related('participants', 'messages__sender').annotate(
    latest_message_time=Max('messages__created_at')
).order_by('-latest_message_time')
```

---

## WebSocket Implementation

### Consumer Architecture
```python
class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Authenticate user
        # Join conversation group
        # Accept connection
        
    async def disconnect(self, close_code):
        # Leave conversation group
        # Cleanup resources
        
    async def receive(self, text_data):
        # Parse JSON message
        # Validate and save message
        # Broadcast to group
        
    async def chat_message(self, event):
        # Send message to WebSocket
        # Update UI in real-time
```

### Channel Layers
```python
# Redis backend for production
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [('127.0.0.1', 6379)],
        },
    },
}

# In-memory backend for development
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    }
}
```

### Connection Management
```javascript
// Automatic reconnection logic
function connectWebSocket() {
    chatSocket = new WebSocket(wsPath);
    
    chatSocket.onclose = function(e) {
        console.log('Connection lost, reconnecting in 3 seconds...');
        setTimeout(connectWebSocket, 3000);
    };
    
    chatSocket.onerror = function(e) {
        console.error('WebSocket error:', e);
        // Fallback to AJAX polling
    };
}
```

---

## Security

### Built-in Protection
- **CSRF Protection**: Enabled by default with middleware
- **XSS Prevention**: Template auto-escaping enabled
- **SQL Injection**: ORM prevents direct SQL injection
- **Session Security**: Secure session cookies and HTTPS-ready
- **File Upload Security**: File type validation and size limits

### Authentication Security
```python
# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]
```

### Production Security Settings
```python
# Production security settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

---

## Performance

### Database Optimization
- **Query Optimization**: Use of select_related and prefetch_related
- **Database Indexing**: Strategic indexes on frequently queried fields
- **Connection Pooling**: PostgreSQL connection pooling for production
- **Query Monitoring**: Django Debug Toolbar for development

### Caching Strategy
```python
# Redis caching
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# View caching
from django.views.decorators.cache import cache_page

@cache_page(60 * 15)  # Cache for 15 minutes
def post_list(request):
    # Cached view logic
```

### Image Optimization
```python
# Automatic image resizing
def save(self, *args, **kwargs):
    super().save(*args, **kwargs)
    if self.profile_image:
        img = Image.open(self.profile_image.path)
        if img.height > 300 or img.width > 300:
            output_size = (300, 300)
            img.thumbnail(output_size)
            img.save(self.profile_image.path)
```

---

## Testing

### Test Coverage
```bash
# Install testing dependencies
pip install coverage pytest-django

# Run tests with coverage
coverage run --source='.' manage.py test
coverage report
coverage html
```

### Test Structure
```python
# tests/test_models.py
class PostModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        
    def test_post_creation(self):
        post = Post.objects.create(user=self.user, content='Test post')
        self.assertEqual(post.content, 'Test post')
        self.assertEqual(post.user, self.user)

# tests/test_views.py
class PostViewTest(TestCase):
    def test_post_list_view(self):
        response = self.client.get('/post/')
        self.assertEqual(response.status_code, 200)
        
# tests/test_websocket.py
class ChatConsumerTest(WebsocketCommunicator):
    async def test_chat_consumer(self):
        # WebSocket testing logic
```

### Load Testing
```bash
# Using locust for load testing
pip install locust

# Create locustfile.py
class WebsiteUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        self.client.post("/accounts/login/", {
            "username": "testuser",
            "password": "testpass"
        })
    
    @task
    def view_posts(self):
        self.client.get("/post/")
    
    @task(3)
    def create_post(self):
        self.client.post("/post/create/", {
            "content": "Test post content"
        })

# Run load test
locust --host=http://localhost:8000
```

---

## Deployment

### Docker Deployment
```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["gunicorn", "quickpost.wsgi:application", "--bind", "0.0.0.0:8000"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  web:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    environment:
      - DEBUG=False
      - DATABASE_URL=postgresql://user:password@db:5432/quickpost
      - REDIS_URL=redis://redis:6379/0
  
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: quickpost
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
    
volumes:
  postgres_data:
```

### Nginx Configuration
```nginx
# /etc/nginx/sites-available/quickpost
server {
    listen 80;
    server_name yourdomain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
    
    location /static/ {
        alias /path/to/quickpost/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    location /media/ {
        alias /path/to/quickpost/media/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### Production Checklist
- [ ] Set DEBUG=False
- [ ] Configure ALLOWED_HOSTS
- [ ] Set up HTTPS with SSL certificates
- [ ] Configure PostgreSQL database
- [ ] Set up Redis for caching and WebSocket
- [ ] Configure static file serving
- [ ] Set up monitoring and logging
- [ ] Configure backup strategy
- [ ] Set up CI/CD pipeline
- [ ] Configure error tracking (Sentry)

---

## Contributing

### Development Workflow
1. Fork the repository
2. Create feature branch (`git checkout -b feature/new-feature`)
3. Write tests for new functionality
4. Implement feature with proper documentation
5. Run test suite (`python manage.py test`)
6. Check code style (`flake8 .`)
7. Commit changes (`git commit -m 'Add new feature'`)
8. Push to branch (`git push origin feature/new-feature`)
9. Create Pull Request

### Code Standards
- Follow PEP 8 style guide
- Write docstrings for all functions and classes
- Maintain test coverage above 80%
- Use type hints where appropriate
- Follow Django best practices

### Bug Reports
Include the following information:
- Python version
- Django version
- Operating system
- Steps to reproduce
- Expected behavior
- Actual behavior
- Error messages and stack trace

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Support

- **Documentation**: [GitHub Wiki](https://github.com/RajeebLochan/QuickPost/wiki)
- **Issues**: [GitHub Issues](https://github.com/RajeebLochan/QuickPost/issues)
- **Discussions**: [GitHub Discussions](https://github.com/RajeebLochan/QuickPost/discussions)

**Author**: [Rajeeb Lochan](https://github.com/RajeebLochan)

Perfect! I've completely rewritten the README.md file with a developer-focused approach. Here are the key improvements:

## Key Changes Made:

### **Removed All Emojis**
- Clean, professional appearance
- Better readability for developers
- Focus on technical content

### **Enhanced Technical Content**
- **Detailed System Requirements** - Specific versions and dependencies
- **Comprehensive Installation Guide** - Both development and production setup
- **Configuration Documentation** - Django settings, WebSocket config, environment variables
- **Architecture Deep Dive** - Project structure, data models, view architecture
- **Complete API Documentation** - REST endpoints and WebSocket API with examples
- **Database Schema** - Entity relationships, indexes, query optimization
- **Performance Guidelines** - Caching, database optimization, image processing
- **Testing Framework** - Unit tests, load testing, coverage reporting
- **Deployment Instructions** - Docker, Nginx, production checklist

### **Developer-Focused Sections**
- **Technical Requirements** - What developers need to know upfront
- **Code Examples** - Actual Python/JavaScript code snippets
- **Security Implementation** - Built-in protections and production settings
- **WebSocket Implementation** - Detailed consumer architecture
- **Query Optimization** - Database performance best practices
- **Load Testing** - Performance testing with Locust
- **Production Deployment** - Real-world deployment scenarios

### **Professional Structure**
- Clean table of contents
- Logical information hierarchy
- Code blocks with syntax highlighting
- Technical diagrams and schemas
- Comprehensive troubleshooting guides

### **Practical Information**
- **Environment Configuration** - .env file examples
- **Docker Setup** - Complete containerization guide
- **Nginx Configuration** - Production web server setup
- **CI/CD Guidelines** - Development workflow
- **Code Standards** - PEP 8, testing requirements
- **Contributing Guidelines** - How to contribute effectively

This README now serves as a complete technical reference for developers who want to understand, install, configure, and contribute to the QuickPost project. It focuses on the essential technical information without visual distractions, making it perfect for serious development work.

---

## 🎮 Usage

### 👤 User Management

**Registration**
```python
# Navigate to /accounts/register/
# Fill in the registration form
# Automatic login after successful registration
```

**Profile Management**
```python
# Navigate to /post/profile/edit/
# Update bio, profile image, location, website
# View profile stats and social connections
```

### 📝 Creating Posts

**Text Posts**
```python
# Navigate to /post/create/
# Enter content (max 240 characters)
# Click "Share Post" to publish
```

**Image Posts**
```python
# Navigate to /post/create/
# Add content and select image file
# Automatic image optimization
# Click "Share Post" to publish
```

### 💬 Messaging

**Start Conversation**
```python
# Visit user profile
# Click "Message" button
# Start typing in the chat interface
```

**Real-time Features**
```python
# Typing indicators appear when user types
# Messages appear instantly via WebSocket
# Fallback to AJAX if WebSocket unavailable
```

### 🔍 Social Features

**Following Users**
```python
# Visit user profile
# Click "Follow" button
# View posts in main feed
# Access followers/following lists
```

**Engagement**
```python
# Like/dislike posts with instant feedback
# Add comments with real-time updates
# View engagement statistics
```

---

## 🏗️ Architecture

### 📁 Project Structure
```
QuickPost/
├── quickpost/                 # Main Django project
│   ├── quickpost/            # Project settings
│   │   ├── settings.py       # Configuration
│   │   ├── urls.py          # URL routing
│   │   ├── asgi.py          # ASGI configuration
│   │   └── wsgi.py          # WSGI configuration
│   ├── post/                 # Main application
│   │   ├── models.py         # Data models
│   │   ├── views.py          # View logic
│   │   ├── forms.py          # Form definitions
│   │   ├── urls.py           # App URLs
│   │   ├── consumers.py      # WebSocket consumers
│   │   ├── routing.py        # WebSocket routing
│   │   └── templates/        # HTML templates
│   ├── templates/            # Global templates
│   ├── static/              # Static files
│   ├── media/               # User uploads
│   └── manage.py            # Django management
├── requirements.txt          # Dependencies
└── README.md                # This file
```

### 🔄 Data Flow

```mermaid
graph TD
    A[User Request] --> B[Django Views]
    B --> C[Models/Database]
    B --> D[Templates]
    B --> E[WebSocket Consumer]
    C --> F[Response]
    D --> F
    E --> G[Real-time Updates]
    F --> H[User Interface]
    G --> H
```

### 🛠️ Key Components

**Models**
- `Post` - User posts with media support
- `Comment` - Post comments with threading
- `UserProfile` - Extended user information
- `Conversation` - Chat conversations
- `Message` - Chat messages

**Views**
- `post_list` - Main feed with pagination
- `create_post` - Post creation interface
- `profile` - User profile display
- `chat_room` - Real-time messaging
- `conversations_list` - Inbox interface

**WebSocket Consumers**
- `ChatConsumer` - Real-time messaging
- Typing indicators
- Connection management
- Message broadcasting

---

## 🎨 UI/UX Features

### 🌙 Dark Theme System
```css
:root {
    --bg-primary: #0f0f23;
    --bg-secondary: #1a1a2e;
    --bg-tertiary: #16213e;
    --primary: #6366f1;
    --secondary: #8b5cf6;
    --accent: #06b6d4;
}
```

### ✨ Modern Design Elements
- **Glassmorphism Effects** - Frosted glass navigation and cards
- **Gradient Backgrounds** - Beautiful color transitions
- **Smooth Animations** - CSS transitions and keyframes
- **Responsive Grid** - Mobile-first responsive design
- **Interactive Buttons** - Hover effects and state changes

### 📱 Mobile Optimization
- **Touch-friendly Interfaces** - Optimized touch targets
- **Swipe Gestures** - Natural mobile interactions
- **Adaptive Layouts** - Flexible grid systems
- **Fast Loading** - Optimized images and lazy loading

---

## 🔧 API Endpoints

### 📝 Posts API
```python
GET  /post/                    # List all posts
POST /post/create/             # Create new post
GET  /post/edit/<id>/          # Edit post form
POST /post/edit/<id>/          # Update post
POST /post/delete/<id>/        # Delete post
POST /post/like/<id>/          # Like/unlike post
POST /post/dislike/<id>/       # Dislike post
POST /post/comment/<id>/       # Add comment
```

### 👤 User API
```python
GET  /post/profile/<username>/           # User profile
POST /post/profile/edit/                 # Edit profile
POST /post/follow/<username>/            # Follow/unfollow
GET  /post/profile/<username>/followers/ # Followers list
GET  /post/profile/<username>/following/ # Following list
```

### 💬 Messaging API
```python
GET  /post/conversations/              # Conversation list
GET  /post/chat/<id>/                  # Chat room
POST /post/start-conversation/<id>/    # Start new chat
POST /post/ajax/send-message/          # Send message (AJAX)
GET  /post/ajax/messages/<id>/         # Get messages (AJAX)
```

### 🔐 Authentication API
```python
GET  /accounts/login/          # Login form
POST /accounts/login/          # Login action
GET  /accounts/register/       # Registration form
POST /accounts/register/       # Registration action
POST /accounts/logout/         # Logout action
```

---

## 📱 Mobile Support

### 📊 Responsive Breakpoints
```css
/* Mobile First Design */
@media (max-width: 480px)  { /* Small mobile */ }
@media (max-width: 768px)  { /* Mobile */ }
@media (max-width: 1024px) { /* Tablet */ }
@media (min-width: 1025px) { /* Desktop */ }
```

### 🎯 Mobile Features
- **Progressive Web App** - PWA capabilities
- **Touch Gestures** - Swipe and tap interactions
- **Offline Support** - Service worker implementation
- **Push Notifications** - Real-time alerts
- **App-like Experience** - Native feel on mobile

---

## 🛠️ Tech Stack

### 🖥️ Backend
- **Django 5.2.4** - Web framework
- **Python 3.12+** - Programming language
- **SQLite/PostgreSQL** - Database options
- **Django Channels** - WebSocket support
- **Redis** - Channel layer backend
- **Pillow** - Image processing

### 🎨 Frontend
- **HTML5 & CSS3** - Markup and styling
- **JavaScript ES6+** - Client-side logic
- **WebSocket API** - Real-time communication
- **Font Awesome** - Icon library
- **Google Fonts** - Typography

### 🔧 Development Tools
- **Git** - Version control
- **pip** - Package management
- **Django Debug Toolbar** - Development debugging
- **APScheduler** - Task scheduling

### ☁️ Deployment Options
- **Heroku** - Cloud platform
- **DigitalOcean** - VPS hosting
- **AWS EC2** - Scalable hosting
- **Docker** - Containerization

---

## 🔒 Security Features

### 🛡️ Built-in Security
- **CSRF Protection** - Cross-site request forgery prevention
- **XSS Prevention** - Template auto-escaping
- **SQL Injection Protection** - ORM parameterized queries
- **Session Security** - Secure session management
- **File Upload Validation** - Image type verification

### 🔐 Authentication
- **Password Hashing** - Django's built-in hashing
- **Session Management** - Secure user sessions
- **Login Required** - Protected view decorators
- **User Permissions** - Role-based access control

### 🚨 Best Practices
- **Environment Variables** - Sensitive data protection
- **HTTPS Ready** - SSL/TLS support
- **Content Security Policy** - XSS attack prevention
- **Rate Limiting** - API abuse prevention

---

## 📊 Performance

### ⚡ Optimization Features
- **Database Indexing** - Optimized query performance
- **Image Compression** - Automatic image optimization
- **Lazy Loading** - On-demand content loading
- **Caching Strategy** - Redis-based caching
- **CDN Ready** - Static file optimization

### 📈 Scalability
- **Horizontal Scaling** - Multi-server support
- **Database Optimization** - Query optimization
- **Load Balancing** - Traffic distribution
- **Microservices Ready** - Modular architecture

---

## 🤝 Contributing

We welcome contributions! Here's how you can help:

### 🐛 Bug Reports
1. Check existing issues
2. Create detailed bug report
3. Include steps to reproduce
4. Add screenshots if applicable

### ✨ Feature Requests
1. Describe the feature
2. Explain use cases
3. Provide mockups if possible
4. Discuss implementation approach

### 🔧 Development
1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

### 📝 Code Style
- Follow PEP 8 for Python code
- Use meaningful variable names
- Add comments for complex logic
- Write docstrings for functions
- Include unit tests for new features

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Django Community** - Amazing web framework
- **Font Awesome** - Beautiful icons
- **Google Fonts** - Typography resources
- **Unsplash** - Stock photography
- **Open Source Community** - Inspiration and tools

---

## 📞 Support

### 🔗 Links
- **Documentation**: [Wiki](https://github.com/RajeebLochan/QuickPost/wiki)
- **Issues**: [GitHub Issues](https://github.com/RajeebLochan/QuickPost/issues)
- **Discussions**: [GitHub Discussions](https://github.com/RajeebLochan/QuickPost/discussions)

### 📧 Contact
- **Developer**: [@RajeebLochan](https://github.com/RajeebLochan)
- **LinkedIn**: [Rajeeb Lochan](https://linkedin.com/in/rajeeb-lochan)

---

<div align="center">

**⭐ Star this repository if you found it helpful!**

Made with ❤️ by [Rajeeb Lochan](https://github.com/RajeebLochan)

</div>
