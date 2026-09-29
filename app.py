from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime

from config import config
from database import db
from models import User, Post, Comment, Notification, Message, Conversation
from auth import Auth, session_manager

# Initialize Flask app
app = Flask(__name__, static_folder='../frontend', static_url_path='')
app.config.from_object(config['development'])

# Initialize extensions
CORS(app, origins=app.config['CORS_ORIGINS'])
socketio = SocketIO(app, cors_allowed_origins=app.config['SOCKETIO_CORS_ALLOWED_ORIGINS'])

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Helper Functions
def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_file(file, folder=''):
    """Save uploaded file and return URL"""
    if not file or not allowed_file(file.filename):
        return None
    
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{filename}"
    
    # Create subfolder if needed
    upload_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
    os.makedirs(upload_path, exist_ok=True)
    
    filepath = os.path.join(upload_path, filename)
    file.save(filepath)
    
    # Determine file type
    file_type = 'image' if file.content_type.startswith('image/') else 'video'
    
    return f"/uploads/{folder}/{filename}", file_type

def create_notification(user_id, type, content, reference_id=None):
    """Create a notification and emit via WebSocket"""
    notification_id = db.create_notification(user_id, type, content, reference_id)
    
    # Emit via WebSocket
    socketio.emit('notification', {
        'id': notification_id,
        'type': type,
        'content': content,
        'reference_id': reference_id,
        'timestamp': datetime.utcnow().isoformat()
    }, room=f"user_{user_id}")
    
    return notification_id

# API Routes
@app.route('/api/register', methods=['POST'])
def register():
    """Register a new user"""
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    
    # Validate input
    if not username or not email or not password:
        return jsonify({'message': 'Missing required fields'}), 400
    
    if len(password) < 6:
        return jsonify({'message': 'Password must be at least 6 characters'}), 400
    
    # Check if user exists
    existing_user = db.get_user_by_username(username)
    if existing_user:
        return jsonify({'message': 'Username already exists'}), 400
    
    existing_email = db.get_user_by_email(email)
    if existing_email:
        return jsonify({'message': 'Email already exists'}), 400
    
    # Create user
    password_hash = Auth.hash_password(password)
    user_id = db.create_user(username, email, password_hash)
    
    # Generate token
    token = Auth.generate_token(user_id, username)
    
    # Get user data
    user_data = db.get_user_by_id(user_id)
    user = User(user_data)
    
    return jsonify({
        'message': 'User created successfully',
        'token': token,
        'user': user.to_dict(include_email=True)
    }), 201

@app.route('/api/login', methods=['POST'])
def login():
    """Login user"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'message': 'Missing username or password'}), 400
    
    # Get user
    user_data = db.get_user_by_username(username)
    if not user_data:
        return jsonify({'message': 'Invalid credentials'}), 401
    
    # Verify password
    if not Auth.verify_password(password, user_data['password']):
        return jsonify({'message': 'Invalid credentials'}), 401
    
    # Generate token
    token = Auth.generate_token(user_data['id'], user_data['username'])
    
    # Create session
    session_manager.create_session(user_data['id'], token)
    
    user = User(user_data)
    
    return jsonify({
        'token': token,
        'user': user.to_dict(include_email=True)
    })

@app.route('/api/posts', methods=['GET'])
@Auth.token_required
def get_posts():
    """Get posts with pagination"""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    user_id = request.args.get('user_id', type=int)
    
    posts_data = db.get_posts(user_id, page, limit)
    posts = []
    
    for post_data in posts_data:
        post = Post(post_data)
        post_dict = post.to_dict()
        
        # Get likes for this post
        likes = db.execute_query(
            "SELECT user_id FROM likes WHERE post_id = ?", (post.id,)
        )
        post_dict['likes'] = [like['user_id'] for like in likes]
        
        # Get comments for this post
        comments_data = db.get_comments(post.id, page=1, per_page=5)
        post_dict['comments'] = [Comment(comment).to_dict() for comment in comments_data]
        
        posts.append(post_dict)
    
    return jsonify(posts)

@app.route('/api/posts', methods=['POST'])
@Auth.token_required
def create_post():
    """Create a new post"""
    data = request.json
    content = data.get('content')
    tags = data.get('tags', [])
    media_url = data.get('media_url')
    media_type = data.get('media_type')
    
    if not content and not media_url:
        return jsonify({'message': 'Post must have content or media'}), 400
    
    # Create post
    post_id = db.create_post(
        request.current_user['id'],
        content,
        media_url,
        media_type,
        tags
    )
    
    # Create notifications for followers
    followers = db.get_followers(request.current_user['id'])
    for follower in followers:
        create_notification(
            follower['id'],
            'new_post',
            f"{request.current_user['username']} created a new post",
            post_id
        )
    
    return jsonify({'message': 'Post created', 'post_id': post_id}), 201

@app.route('/api/posts/<int:post_id>/like', methods=['POST'])
@Auth.token_required
def like_post(post_id):
    """Like a post"""
    result = db.like_post(request.current_user['id'], post_id)
    
    if result:
        # Get post owner
        post_data = db.execute_query(
            "SELECT user_id FROM posts WHERE id = ?", (post_id,)
        )
        if post_data and post_data[0]['user_id'] != request.current_user['id']:
            create_notification(
                post_data[0]['user_id'],
                'like',
                f"{request.current_user['username']} liked your post",
                post_id
            )
        
        return jsonify({'message': 'Post liked'}), 200
    
    return jsonify({'message': 'Already liked'}), 400

@app.route('/api/posts/<int:post_id>/unlike', methods=['DELETE'])
@Auth.token_required
def unlike_post(post_id):
    """Unlike a post"""
    db.unlike_post(request.current_user['id'], post_id)
    return jsonify({'message': 'Post unliked'}), 200

@app.route('/api/posts/<int:post_id>/comment', methods=['POST'])
@Auth.token_required
def add_comment(post_id):
    """Add a comment to a post"""
    data = request.json
    content = data.get('content')
    
    if not content:
        return jsonify({'message': 'Comment cannot be empty'}), 400
    
    # Add comment
    comment_id = db.add_comment(request.current_user['id'], post_id, content)
    
    # Get post owner
    post_data = db.execute_query(
        "SELECT user_id FROM posts WHERE id = ?", (post_id,)
    )
    if post_data and post_data[0]['user_id'] != request.current_user['id']:
        create_notification(
            post_data[0]['user_id'],
            'comment',
            f"{request.current_user['username']} commented on your post",
            post_id
        )
    
    return jsonify({'message': 'Comment added', 'comment_id': comment_id}), 201

@app.route('/api/posts/<int:post_id>/comments', methods=['GET'])
def get_comments(post_id):
    """Get comments for a post"""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    comments_data = db.get_comments(post_id, page, limit)
    comments = [Comment(comment).to_dict() for comment in comments_data]
    
    return jsonify(comments)

@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user_profile(user_id):
    """Get user profile"""
    user_data = db.get_user_by_id(user_id)
    if not user_data:
        return jsonify({'message': 'User not found'}), 404
    
    # Get counts
    post_count = db.execute_query(
        "SELECT COUNT(*) as count FROM posts WHERE user_id = ?", (user_id,)
    )[0]['count']
    
    followers_count = db.execute_query(
        "SELECT COUNT(*) as count FROM followers WHERE following_id = ?", (user_id,)
    )[0]['count']
    
    following_count = db.execute_query(
        "SELECT COUNT(*) as count FROM followers WHERE follower_id = ?", (user_id,)
    )[0]['count']
    
    user = User(user_data)
    user_dict = user.to_dict()
    user_dict.update({
        'post_count': post_count,
        'followers_count': followers_count,
        'following_count': following_count
    })
    
    return jsonify(user_dict)

@app.route('/api/users/profile', methods=['PUT'])
@Auth.token_required
def update_profile():
    """Update user profile"""
    data = request.json
    
    # Update user
    updated = db.update_user(
        request.current_user['id'],
        bio=data.get('bio'),
        location=data.get('location'),
        website=data.get('website'),
        avatar=data.get('avatar'),
        cover_url=data.get('cover_url')
    )
    
    if updated:
        # Get updated user data
        user_data = db.get_user_by_id(request.current_user['id'])
        user = User(user_data)
        return jsonify(user.to_dict())
    
    return jsonify({'message': 'No changes made'}), 400

@app.route('/api/users/<int:user_id>/follow', methods=['POST'])
@Auth.token_required
def follow_user(user_id):
    """Follow a user"""
    if user_id == request.current_user['id']:
        return jsonify({'message': 'Cannot follow yourself'}), 400
    
    result = db.follow_user(request.current_user['id'], user_id)
    
    if result:
        create_notification(
            user_id,
            'follow',
            f"{request.current_user['username']} started following you",
            request.current_user['id']
        )
        return jsonify({'message': 'Now following user'}), 200
    
    return jsonify({'message': 'Already following'}), 400

@app.route('/api/users/<int:user_id>/unfollow', methods=['DELETE'])
@Auth.token_required
def unfollow_user(user_id):
    """Unfollow a user"""
    db.unfollow_user(request.current_user['id'], user_id)
    return jsonify({'message': 'Unfollowed user'}), 200

@app.route('/api/users/<int:user_id>/followers', methods=['GET'])
def get_followers(user_id):
    """Get followers of a user"""
    followers_data = db.get_followers(user_id)
    followers = [User(follower).to_dict() for follower in followers_data]
    return jsonify(followers)

@app.route('/api/users/<int:user_id>/following', methods=['GET'])
def get_following(user_id):
    """Get users that a user is following"""
    following_data = db.get_following(user_id)
    following = [User(user).to_dict() for user in following_data]
    return jsonify(following)

@app.route('/api/notifications', methods=['GET'])
@Auth.token_required
def get_notifications():
    """Get user notifications"""
    notifications_data = db.get_notifications(request.current_user['id'])
    notifications = [Notification(notif).to_dict() for notif in notifications_data]
    return jsonify(notifications)

@app.route('/api/notifications/<int:notif_id>/read', methods=['PUT'])
@Auth.token_required
def mark_notification_read(notif_id):
    """Mark notification as read"""
    db.mark_notification_read(notif_id, request.current_user['id'])
    return jsonify({'message': 'Notification marked as read'}), 200

@app.route('/api/search', methods=['GET'])
def search():
    """Search users and posts"""
    query = request.args.get('q', '')
    type = request.args.get('type', 'all')
    
    if not query:
        return jsonify({'users': [], 'posts': []})
    
    results = db.search(query, type)
    
    # Format results
    formatted_results = {
        'users': [User(user).to_dict() for user in results['users']],
        'posts': []
    }
    
    for post_data in results['posts']:
        post = Post(post_data)
        post_dict = post.to_dict()
        
        # Get likes
        likes = db.execute_query(
            "SELECT user_id FROM likes WHERE post_id = ?", (post.id,)
        )
        post_dict['likes'] = [like['user_id'] for like in likes]
        
        # Get comments
        comments_data = db.get_comments(post.id, per_page=3)
        post_dict['comments'] = [Comment(comment).to_dict() for comment in comments_data]
        
        formatted_results['posts'].append(post_dict)
    
    return jsonify(formatted_results)

@app.route('/api/trending', methods=['GET'])
def get_trending():
    """Get trending posts"""
    limit = request.args.get('limit', 20, type=int)
    trending_data = db.get_trending_posts(limit)
    
    trending = []
    for post_data in trending_data:
        post = Post(post_data)
        post_dict = post.to_dict()
        
        # Get likes
        likes = db.execute_query(
            "SELECT user_id FROM likes WHERE post_id = ?", (post.id,)
        )
        post_dict['likes'] = [like['user_id'] for like in likes]
        
        # Get comments
        comments_data = db.get_comments(post.id, per_page=3)
        post_dict['comments'] = [Comment(comment).to_dict() for comment in comments_data]
        
        trending.append(post_dict)
    
    return jsonify(trending)

@app.route('/api/upload', methods=['POST'])
@Auth.token_required
def upload_file():
    """Upload a file"""
    if 'file' not in request.files:
        return jsonify({'message': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'message': 'No file selected'}), 400
    
    # Determine folder based on file type
    folder = 'images' if file.content_type.startswith('image/') else 'videos'
    
    # Save file
    url, file_type = save_file(file, folder)
    if not url:
        return jsonify({'message': 'File type not allowed'}), 400
    
    return jsonify({
        'url': url,
        'type': file_type,
        'filename': file.filename
    }), 200

@app.route('/api/messages/conversations', methods=['GET'])
@Auth.token_required
def get_conversations():
    """Get user conversations"""
    conversations_data = db.get_conversations(request.current_user['id'])
    conversations = [Conversation(conv).to_dict() for conv in conversations_data]
    return jsonify(conversations)

@app.route('/api/messages/<int:conversation_id>', methods=['GET'])
@Auth.token_required
def get_messages(conversation_id):
    """Get messages in a conversation"""
    page = request.args.get('page', 1, type=int)
    messages_data = db.get_messages(conversation_id, page)
    messages = [Message(msg).to_dict() for msg in messages_data]
    
    # Mark messages as read
    db.mark_messages_read(conversation_id, request.current_user['id'])
    
    return jsonify(messages)

@app.route('/api/messages', methods=['POST'])
@Auth.token_required
def send_message():
    """Send a message"""
    data = request.json
    conversation_id = data.get('conversation_id')
    user_id = data.get('user_id')
    content = data.get('content')
    
    if not content:
        return jsonify({'message': 'Message cannot be empty'}), 400
    
    # Get or create conversation
    if not conversation_id and user_id:
        conversation_id = db.get_or_create_conversation(
            request.current_user['id'],
            user_id
        )
    elif not conversation_id:
        return jsonify({'message': 'Invalid conversation'}), 400
    
    # Send message
    message_id = db.send_message(
        conversation_id,
        request.current_user['id'],
        content
    )
    
    # Get message data
    message_data = db.execute_query(
        "SELECT * FROM messages WHERE id = ?", (message_id,)
    )[0]
    message = Message(message_data)
    
    # Emit via WebSocket
    socketio.emit('new_message', message.to_dict(), room=f"conversation_{conversation_id}")
    
    # Create notification for other participants
    participants = db.execute_query(
        "SELECT user_id FROM conversation_participants WHERE conversation_id = ? AND user_id != ?",
        (conversation_id, request.current_user['id'])
    )
    
    for participant in participants:
        create_notification(
            participant['user_id'],
            'message',
            f"New message from {request.current_user['username']}",
            conversation_id
        )
    
    return jsonify({
        'message': 'Message sent',
        'message_id': message_id,
        'conversation_id': conversation_id
    }), 201

# Serve uploaded files
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# WebSocket events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    token = request.args.get('token')
    if token:
        payload = Auth.decode_token(token)
        if payload:
            join_room(f"user_{payload['user_id']}")
            emit('connected', {'message': 'Connected to WebSocket'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')

@socketio.on('join_conversation')
def handle_join_conversation(data):
    """Join a conversation room"""
    conversation_id = data.get('conversation_id')
    if conversation_id:
        join_room(f"conversation_{conversation_id}")

@socketio.on('leave_conversation')
def handle_leave_conversation(data):
    """Leave a conversation room"""
    conversation_id = data.get('conversation_id')
    if conversation_id:
        leave_room(f"conversation_{conversation_id}")

@socketio.on('typing')
def handle_typing(data):
    """Handle typing indicator"""
    conversation_id = data.get('conversation_id')
    user = request.current_user if hasattr(request, 'current_user') else None
    
    if conversation_id and user:
        emit('user_typing', {
            'user_id': user['id'],
            'username': user['username'],
            'is_typing': data.get('is_typing', True)
        }, room=f"conversation_{conversation_id}", include_self=False)

# Serve frontend
@app.route('/')
def serve_frontend():
    """Serve the main HTML file"""
    return send_from_directory('../frontend', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('../frontend', path)

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'message': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'message': 'Internal server error'}), 500

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000) 