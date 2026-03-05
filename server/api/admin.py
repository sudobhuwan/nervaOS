"""
NervaOS License Server - Admin API

Admin-only endpoints for:
- License generation
- User management
- Analytics
"""

from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import get_session, License, User, Activation
from .auth import get_admin_user
from .licenses import generate_license_key

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────────────────────────────────────

class LicenseCreate(BaseModel):
    license_type: str = "standard"
    max_activations: int = 3
    expires_days: Optional[int] = None  # None = lifetime
    owner_id: Optional[int] = None


class LicenseResponse(BaseModel):
    id: int
    key: str
    license_type: str
    max_activations: int
    current_activations: int
    is_active: bool
    is_revoked: bool
    created_at: datetime
    expires_at: Optional[datetime]


class BatchLicenseCreate(BaseModel):
    count: int
    license_type: str = "standard"
    max_activations: int = 3
    expires_days: Optional[int] = None


class DashboardStats(BaseModel):
    total_licenses: int
    active_licenses: int
    total_activations: int
    total_users: int
    licenses_by_type: dict
    recent_activations: int


class UserAdmin(BaseModel):
    id: int
    email: str
    name: Optional[str]
    is_admin: bool
    is_active: bool
    created_at: datetime
    license_count: int


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard & Analytics
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session)
):
    """Get dashboard statistics"""
    # Total licenses
    total_licenses = await db.scalar(select(func.count(License.id)))
    
    # Active licenses
    active_licenses = await db.scalar(
        select(func.count(License.id)).where(
            License.is_active == True,
            License.is_revoked == False
        )
    )
    
    # Total activations
    total_activations = await db.scalar(
        select(func.count(Activation.id)).where(Activation.is_active == True)
    )
    
    # Total users
    total_users = await db.scalar(select(func.count(User.id)))
    
    # Licenses by type
    result = await db.execute(
        select(License.license_type, func.count(License.id))
        .group_by(License.license_type)
    )
    licenses_by_type = {row[0]: row[1] for row in result.fetchall()}
    
    # Recent activations (last 24 hours)
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_activations = await db.scalar(
        select(func.count(Activation.id)).where(
            Activation.activated_at >= yesterday
        )
    )
    
    return DashboardStats(
        total_licenses=total_licenses or 0,
        active_licenses=active_licenses or 0,
        total_activations=total_activations or 0,
        total_users=total_users or 0,
        licenses_by_type=licenses_by_type,
        recent_activations=recent_activations or 0
    )


# ─────────────────────────────────────────────────────────────────────────────
# License Management
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/licenses", response_model=LicenseResponse)
async def create_license(
    data: LicenseCreate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session)
):
    """Create a new license"""
    expires_at = None
    if data.expires_days:
        expires_at = datetime.utcnow() + timedelta(days=data.expires_days)
    
    license = License(
        key=generate_license_key(),
        license_type=data.license_type,
        max_activations=data.max_activations,
        expires_at=expires_at,
        owner_id=data.owner_id
    )
    db.add(license)
    await db.commit()
    await db.refresh(license)
    
    return LicenseResponse(
        id=license.id,
        key=license.key,
        license_type=license.license_type,
        max_activations=license.max_activations,
        current_activations=license.current_activations,
        is_active=license.is_active,
        is_revoked=license.is_revoked,
        created_at=license.created_at,
        expires_at=license.expires_at
    )


@router.post("/licenses/batch", response_model=List[LicenseResponse])
async def create_batch_licenses(
    data: BatchLicenseCreate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session)
):
    """Create multiple licenses at once"""
    if data.count > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 100 licenses per batch"
        )
    
    expires_at = None
    if data.expires_days:
        expires_at = datetime.utcnow() + timedelta(days=data.expires_days)
    
    licenses = []
    for _ in range(data.count):
        license = License(
            key=generate_license_key(),
            license_type=data.license_type,
            max_activations=data.max_activations,
            expires_at=expires_at
        )
        db.add(license)
        licenses.append(license)
    
    await db.commit()
    
    return [
        LicenseResponse(
            id=lic.id,
            key=lic.key,
            license_type=lic.license_type,
            max_activations=lic.max_activations,
            current_activations=lic.current_activations,
            is_active=lic.is_active,
            is_revoked=lic.is_revoked,
            created_at=lic.created_at,
            expires_at=lic.expires_at
        )
        for lic in licenses
    ]


@router.get("/licenses", response_model=List[LicenseResponse])
async def list_licenses(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100),
    active_only: bool = False,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session)
):
    """List all licenses with pagination"""
    query = select(License).offset(skip).limit(limit).order_by(License.created_at.desc())
    
    if active_only:
        query = query.where(License.is_active == True, License.is_revoked == False)
    
    result = await db.execute(query)
    licenses = result.scalars().all()
    
    return [
        LicenseResponse(
            id=lic.id,
            key=lic.key,
            license_type=lic.license_type,
            max_activations=lic.max_activations,
            current_activations=lic.current_activations,
            is_active=lic.is_active,
            is_revoked=lic.is_revoked,
            created_at=lic.created_at,
            expires_at=lic.expires_at
        )
        for lic in licenses
    ]


@router.post("/licenses/{license_id}/revoke")
async def revoke_license(
    license_id: int,
    reason: str = "Revoked by admin",
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session)
):
    """Revoke a license"""
    result = await db.execute(
        select(License).where(License.id == license_id)
    )
    license = result.scalar_one_or_none()
    
    if not license:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License not found"
        )
    
    license.is_revoked = True
    license.revoke_reason = reason
    await db.commit()
    
    return {"success": True, "message": "License revoked"}


# ─────────────────────────────────────────────────────────────────────────────
# User Management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserAdmin])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session)
):
    """List all users"""
    result = await db.execute(
        select(User).offset(skip).limit(limit).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    
    user_list = []
    for user in users:
        # Count licenses for each user
        license_count = await db.scalar(
            select(func.count(License.id)).where(License.owner_id == user.id)
        )
        
        user_list.append(UserAdmin(
            id=user.id,
            email=user.email,
            name=user.name,
            is_admin=user.is_admin,
            is_active=user.is_active,
            created_at=user.created_at,
            license_count=license_count or 0
        ))
    
    return user_list


@router.post("/users/{user_id}/toggle-admin")
async def toggle_admin(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session)
):
    """Toggle admin status for a user"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.is_admin = not user.is_admin
    await db.commit()
    
    return {"success": True, "is_admin": user.is_admin}
