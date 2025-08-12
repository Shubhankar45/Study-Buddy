from flask import render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import app, db
from models import User, Room, Topic, Subtopic, UserProgress, StudySession, Note
from datetime import datetime
import json

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return render_template('register.html')
        
        user = User()
        user.username = username
        user.email = email
        user.password_hash = generate_password_hash(password)
        
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        flash('Registration successful!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    created_rooms = current_user.created_rooms
    joined_rooms = current_user.rooms
    return render_template('dashboard.html', 
                         created_rooms=created_rooms, 
                         joined_rooms=joined_rooms)

@app.route('/create_room', methods=['GET', 'POST'])
@login_required
def create_room():
    if request.method == 'POST':
        room_name = request.form['room_name']
        password = request.form['password']
        
        room = Room()
        room.room_id = Room.generate_room_id()
        room.name = room_name
        room.password_hash = generate_password_hash(password)
        room.creator_id = current_user.id
        
        db.session.add(room)
        db.session.flush()  # Get the room ID
        
        # Add creator as member
        room.members.append(current_user)
        db.session.commit()
        
        flash(f'Room created successfully! Room ID: {room.room_id}', 'success')
        return redirect(url_for('room', room_id=room.room_id))
    
    return render_template('create_room.html')

@app.route('/join_room', methods=['GET', 'POST'])
@login_required
def join_room():
    if request.method == 'POST':
        room_id = request.form['room_id'].upper()
        password = request.form['password']
        
        room = Room.query.filter_by(room_id=room_id).first()
        
        if not room:
            flash('Room not found', 'error')
            return render_template('join_room.html')
        
        if not check_password_hash(room.password_hash, password):
            flash('Incorrect password', 'error')
            return render_template('join_room.html')
        
        if current_user not in room.members:
            room.members.append(current_user)
            db.session.commit()
            flash('Successfully joined the room!', 'success')
        
        return redirect(url_for('room', room_id=room_id))
    
    return render_template('join_room.html')

@app.route('/room/<room_id>')
@login_required
def room(room_id):
    room = Room.query.filter_by(room_id=room_id).first_or_404()
    
    if current_user not in room.members:
        flash('You are not a member of this room', 'error')
        return redirect(url_for('dashboard'))
    
    topics = Topic.query.filter_by(room_id=room.id).order_by(Topic.order_index).all()
    members = room.members
    notes = Note.query.filter_by(room_id=room.id).order_by(Note.created_at.desc()).all()
    
    # Get user progress for all subtopics
    user_progress = {}
    topic_times = {}
    
    for topic in topics:
        topic_actual = 0
        topic_estimated = 0
        completed_count = 0
        total_count = 0
        
        for subtopic in topic.subtopics:
            total_count += 1
            topic_estimated += subtopic.estimated_time
            
            progress = UserProgress.query.filter_by(
                user_id=current_user.id,
                subtopic_id=subtopic.id
            ).first()
            
            if progress:
                user_progress[subtopic.id] = progress
                topic_actual += progress.total_time_spent
                if progress.status == 'completed':
                    completed_count += 1
            
        topic_times[topic.id] = {
            'actual': topic_actual,
            'estimated': topic_estimated,
            'completed_count': completed_count,
            'total_count': total_count
        }
    
    is_creator = current_user.id == room.creator_id
    
    return render_template('room.html', 
                         room=room, 
                         topics=topics, 
                         members=members, 
                         notes=notes,
                         user_progress=user_progress,
                         topic_times=topic_times,
                         is_creator=is_creator)

@app.route('/update_daily_goal', methods=['POST'])
@login_required
def update_daily_goal():
    daily_goal = int(request.form['daily_goal'])
    current_user.daily_goal_minutes = daily_goal
    db.session.commit()
    flash('Daily goal updated successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/room/<room_id>/syllabus', methods=['POST'])
@login_required
def update_syllabus(room_id):
    room = Room.query.filter_by(room_id=room_id).first_or_404()
    
    if current_user.id != room.creator_id:
        flash('Only the room creator can update the syllabus', 'error')
        return redirect(url_for('room', room_id=room_id))
    
    try:
        syllabus_data = json.loads(request.form['syllabus_data'])
        
        # Clear existing topics
        for topic in room.topics:
            db.session.delete(topic)
        
        # Add new topics
        for topic_index, topic_data in enumerate(syllabus_data):
            topic = Topic()
            topic.name = topic_data['name']
            topic.room_id = room.id
            topic.order_index = topic_index
            
            db.session.add(topic)
            db.session.flush()  # Get the topic ID
            
            for subtopic_index, subtopic_data in enumerate(topic_data['subtopics']):
                subtopic = Subtopic()
                subtopic.name = subtopic_data['name']
                subtopic.estimated_time = int(subtopic_data['time'])
                subtopic.topic_id = topic.id
                subtopic.order_index = subtopic_index
                
                db.session.add(subtopic)
        
        db.session.commit()
        flash('Syllabus updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Error updating syllabus', 'error')
        app.logger.error(f"Syllabus update error: {e}")
    
    return redirect(url_for('room', room_id=room_id))

@app.route('/room/<room_id>/notes', methods=['POST'])
@login_required
def add_note(room_id):
    room = Room.query.filter_by(room_id=room_id).first_or_404()
    
    if current_user not in room.members:
        flash('You are not a member of this room', 'error')
        return redirect(url_for('dashboard'))
    
    content = request.form['content'].strip()
    if content:
        note = Note()
        note.content = content
        note.room_id = room.id
        note.author_id = current_user.id
        
        db.session.add(note)
        db.session.commit()
        
        flash('Note added successfully!', 'success')
    
    return redirect(url_for('room', room_id=room_id))

@app.route('/api/timer/start', methods=['POST'])
@login_required
def start_timer():
    data = request.get_json()
    subtopic_id = data.get('subtopic_id')
    
    subtopic = Subtopic.query.get_or_404(subtopic_id)
    room = subtopic.topic.room
    
    if current_user not in room.members:
        return jsonify({'error': 'Not authorized'}), 403
    
    # Get or create user progress
    progress = UserProgress.query.filter_by(
        user_id=current_user.id,
        subtopic_id=subtopic_id
    ).first()
    
    if not progress:
        progress = UserProgress()
        progress.user_id = current_user.id
        progress.subtopic_id = subtopic_id
        db.session.add(progress)
    
    progress.status = 'in_progress'
    
    # Create new study session
    session_obj = StudySession()
    session_obj.user_id = current_user.id
    session_obj.subtopic_id = subtopic_id
    
    db.session.add(session_obj)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'session_id': session_obj.id,
        'start_time': session_obj.start_time.isoformat()
    })

@app.route('/api/timer/stop', methods=['POST'])
@login_required
def stop_timer():
    data = request.get_json()
    session_id = data.get('session_id')
    duration_seconds = data.get('duration_seconds', 0)
    
    session_obj = StudySession.query.get_or_404(session_id)
    
    if session_obj.user_id != current_user.id:
        return jsonify({'error': 'Not authorized'}), 403
    
    # Update session
    session_obj.end_time = datetime.utcnow()
    session_obj.duration_minutes = max(1, round(duration_seconds / 60))
    
    # Update user progress
    progress = UserProgress.query.filter_by(
        user_id=current_user.id,
        subtopic_id=session_obj.subtopic_id
    ).first()
    
    if progress:
        progress.total_time_spent += session_obj.duration_minutes
        progress.status = 'in_progress'
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'duration_minutes': session_obj.duration_minutes,
        'total_time': progress.total_time_spent if progress else 0
    })

@app.route('/api/progress/complete', methods=['POST'])
@login_required
def mark_complete():
    data = request.get_json()
    subtopic_id = data.get('subtopic_id')
    
    subtopic = Subtopic.query.get_or_404(subtopic_id)
    room = subtopic.topic.room
    
    if current_user not in room.members:
        return jsonify({'error': 'Not authorized'}), 403
    
    # Get or create user progress
    progress = UserProgress.query.filter_by(
        user_id=current_user.id,
        subtopic_id=subtopic_id
    ).first()
    
    if not progress:
        progress = UserProgress()
        progress.user_id = current_user.id
        progress.subtopic_id = subtopic_id
        db.session.add(progress)
    
    progress.status = 'completed'
    progress.completed_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'status': progress.status
    })
