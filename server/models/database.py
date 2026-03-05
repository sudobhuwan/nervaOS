"""
NervaOS License Server - Database Models

SQLAlchemy models for:
- Users (admin accounts)
- Licenses (activation keys)
- Activations (device bindings)
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

# Database URL (SQLite for development, PostgreSQL for production)
DATABASE_URL = "sqlite+aiosqlite:///./nervaos_licenses.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class User(Base):
    """Admin user accounts"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    name = Column(String(255))
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    licenses = relationship("License", back_populates="owner")


class License(Base):
    """Software licenses"""
    __tablename__ = "licenses"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), unique=True, nullable=False, index=True)
    
    # License details
    license_type = Column(String(50), default="standard")  # standard, pro, enterprise
    max_activations = Column(Integer, default=3)
    current_activations = Column(Integer, default=0)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_revoked = Column(Boolean, default=False)
    revoke_reason = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # None = lifetime
    
    # Owner
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    owner = relationship("User", back_populates="licenses")
    
    # Relationships
    activations = relationship("Activation", back_populates="license")


class Activation(Base):
    """Device activations (HWID bindings)"""
    __tablename__ = "activations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    license_id = Column(Integer, ForeignKey("licenses.id"), nullable=False)
    
    # Hardware identification
    hwid = Column(String(128), nullable=False)  # Hardware ID hash
    machine_name = Column(String(255), nullable=True)
    os_info = Column(String(255), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    activated_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    license = relationship("License", back_populates="activations")


async def init_db():
    """Initialize the database"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database initialized")


async def get_session() -> AsyncSession:
    """Get a database session"""
    async with async_session() as session:
        yield session
