from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from sqlalchemy import func
import string
import random

# Association table for room membership
room_members = db.Table('room_members',
    db.Column('room_id', db.Integer, db.ForeignKey('room.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    current_streak = db.Column(db.Integer, default=0)
    longest_streak = db.Column(db.Integer, default=0)
    daily_goal_minutes = db.Column(db.Integer, default=60)
    last_study_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    created_rooms = db.relationship('Room', backref='creator', lazy=True, foreign_keys='Room.creator_id')
    study_sessions = db.relationship('StudySession', backref='user', lazy=True)
    progress = db.relationship('UserProgress', backref='user', lazy=True)
    notes = db.relationship('Note', backref='author', lazy=True)
    
    def get_today_study_time(self):
        today = date.today()
        sessions = StudySession.query.filter(
            StudySession.user_id == self.id,
            func.date(StudySession.start_time) == today
        ).all()
        return sum(session.duration_minutes for session in sessions if session.duration_minutes)
    
    def get_today_minutes(self):
        return self.get_today_study_time()
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'current_streak': self.current_streak,
            'longest_streak': self.longest_streak,
            'daily_goal_minutes': self.daily_goal_minutes
        }

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.String(8), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(256))
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    members = db.relationship('User', secondary=room_members, backref='rooms')
    topics = db.relationship('Topic', backref='room', lazy=True, cascade='all, delete-orphan')
    notes = db.relationship('Note', backref='room', lazy=True, cascade='all, delete-orphan')
    
    @staticmethod
    def generate_room_id():
        while True:
            room_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if not Room.query.filter_by(room_id=room_id).first():
                return room_id
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'room_id': self.room_id,
            'name': self.name,
            'creator_id': self.creator_id,
            'member_count': len(list(self.members))
        }

class Topic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    order_index = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    subtopics = db.relationship('Subtopic', backref='topic', lazy=True, cascade='all, delete-orphan')

class Subtopic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    estimated_time = db.Column(db.Integer, nullable=False)  # in minutes
    topic_id = db.Column(db.Integer, db.ForeignKey('topic.id'), nullable=False)
    order_index = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    progress = db.relationship('UserProgress', backref='subtopic', lazy=True)
    study_sessions = db.relationship('StudySession', backref='subtopic', lazy=True)

class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subtopic_id = db.Column(db.Integer, db.ForeignKey('subtopic.id'), nullable=False)
    status = db.Column(db.String(20), default='not_started')  # not_started, in_progress, completed
    total_time_spent = db.Column(db.Integer, default=0)  # in minutes
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Ensure unique progress per user per subtopic
    __table_args__ = (db.UniqueConstraint('user_id', 'subtopic_id'),)

class StudySession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subtopic_id = db.Column(db.Integer, db.ForeignKey('subtopic.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)
    
    def set_duration(self, duration_seconds):
        self.duration_minutes = max(1, duration_seconds // 60)  # Minimum 1 minute
        if self.start_time:
            self.end_time = datetime.utcnow()

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'content': self.content,
            'author_name': self.author.username,
            'created_at': self.created_at.isoformat(),
            'room_id': self.room_id
        }