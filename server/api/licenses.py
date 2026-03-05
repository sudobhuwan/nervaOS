"""
NervaOS License Server - License API Routes

Endpoints for:
- License validation
- Device activation
- License status check
"""

import secrets
import hashlib
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import get_session, License, Activation

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────────────────────────────────────

class ActivationRequest(BaseModel):
    """Request to activate a license"""
    license_key: str
    hwid: str
    machine_name: Optional[str] = None
    os_info: Optional[str] = None


class ActivationResponse(BaseModel):
    """Response from activation"""
    success: bool
    message: str
    license_type: Optional[str] = None
    expires_at: Optional[datetime] = None


class ValidationRequest(BaseModel):
    """Request to validate a license"""
    license_key: str
    hwid: str


class ValidationResponse(BaseModel):
    """Response from validation"""
    valid: bool
    message: str
    license_type: Optional[str] = None
    expires_at: Optional[datetime] = None


class LicenseStatus(BaseModel):
    """License status information"""
    is_valid: bool
    license_type: str
    max_activations: int
    current_activations: int
    expires_at: Optional[datetime]
    is_expired: bool


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def generate_license_key() -> str:
    """Generate a unique license key in format: XXXXX-XXXXX-XXXXX-XXXXX"""
    parts = []
    for _ in range(4):
        part = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(5))
        parts.append(part)
    return '-'.join(parts)


def hash_hwid(hwid: str) -> str:
    """Hash the hardware ID for storage"""
    return hashlib.sha256(hwid.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/activate", response_model=ActivationResponse)
async def activate_license(
    request: ActivationRequest,
    db: AsyncSession = Depends(get_session)
):
    """
    Activate a license on a new device.
    
    This binds the license key to the device's hardware ID (HWID).
    """
    # Find the license
    result = await db.execute(
        select(License).where(License.key == request.license_key)
    )
    license = result.scalar_one_or_none()
    
    if not license:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid license key"
        )
    
    # Check if license is active
    if not license.is_active or license.is_revoked:
        return ActivationResponse(
            success=False,
            message="License has been revoked or deactivated"
        )
    
    # Check expiration
    if license.expires_at and license.expires_at < datetime.utcnow():
        return ActivationResponse(
            success=False,
            message="License has expired"
        )
    
    # Check activation limit
    if license.current_activations >= license.max_activations:
        return ActivationResponse(
            success=False,
            message=f"Maximum activations ({license.max_activations}) reached"
        )
    
    # Hash the HWID
    hwid_hash = hash_hwid(request.hwid)
    
    # Check if already activated on this device
    existing = await db.execute(
        select(Activation).where(
            Activation.license_id == license.id,
            Activation.hwid == hwid_hash
        )
    )
    
    if existing.scalar_one_or_none():
        # Already activated - just update last_seen
        return ActivationResponse(
            success=True,
            message="License already activated on this device",
            license_type=license.license_type,
            expires_at=license.expires_at
        )
    
    # Create new activation
    activation = Activation(
        license_id=license.id,
        hwid=hwid_hash,
        machine_name=request.machine_name,
        os_info=request.os_info
    )
    db.add(activation)
    
    # Increment activation count
    license.current_activations += 1
    
    await db.commit()
    
    return ActivationResponse(
        success=True,
        message="License activated successfully",
        license_type=license.license_type,
        expires_at=license.expires_at
    )


@router.post("/validate", response_model=ValidationResponse)
async def validate_license(
    request: ValidationRequest,
    db: AsyncSession = Depends(get_session)
):
    """
    Validate a license for a specific device.
    
    Returns whether the license is valid and active for this HWID.
    """
    # Find the license
    result = await db.execute(
        select(License).where(License.key == request.license_key)
    )
    license = result.scalar_one_or_none()
    
    if not license:
        return ValidationResponse(
            valid=False,
            message="Invalid license key"
        )
    
    # Check if license is active
    if not license.is_active or license.is_revoked:
        return ValidationResponse(
            valid=False,
            message="License has been revoked"
        )
    
    # Check expiration
    if license.expires_at and license.expires_at < datetime.utcnow():
        return ValidationResponse(
            valid=False,
            message="License has expired"
        )
    
    # Check if activated on this device
    hwid_hash = hash_hwid(request.hwid)
    result = await db.execute(
        select(Activation).where(
            Activation.license_id == license.id,
            Activation.hwid == hwid_hash,
            Activation.is_active == True
        )
    )
    activation = result.scalar_one_or_none()
    
    if not activation:
        return ValidationResponse(
            valid=False,
            message="License not activated on this device"
        )
    
    # Update last_seen
    activation.last_seen = datetime.utcnow()
    await db.commit()
    
    return ValidationResponse(
        valid=True,
        message="License valid",
        license_type=license.license_type,
        expires_at=license.expires_at
    )


@router.get("/status/{license_key}", response_model=LicenseStatus)
async def get_license_status(
    license_key: str,
    db: AsyncSession = Depends(get_session)
):
    """Get the status of a license"""
    result = await db.execute(
        select(License).where(License.key == license_key)
    )
    license = result.scalar_one_or_none()
    
    if not license:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License not found"
        )
    
    is_expired = False
    if license.expires_at:
        is_expired = license.expires_at < datetime.utcnow()
    
    return LicenseStatus(
        is_valid=license.is_active and not license.is_revoked and not is_expired,
        license_type=license.license_type,
        max_activations=license.max_activations,
        current_activations=license.current_activations,
        expires_at=license.expires_at,
        is_expired=is_expired
    )


@router.post("/deactivate")
async def deactivate_device(
    request: ValidationRequest,
    db: AsyncSession = Depends(get_session)
):
    """Deactivate a license from a device"""
    # Find the license
    result = await db.execute(
        select(License).where(License.key == request.license_key)
    )
    license = result.scalar_one_or_none()
    
    if not license:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid license key"
        )
    
    # Find and deactivate the activation
    hwid_hash = hash_hwid(request.hwid)
    result = await db.execute(
        select(Activation).where(
            Activation.license_id == license.id,
            Activation.hwid == hwid_hash
        )
    )
    activation = result.scalar_one_or_none()
    
    if not activation:
        return {"success": False, "message": "Device not found"}
    
    # Deactivate
    activation.is_active = False
    license.current_activations = max(0, license.current_activations - 1)
    
    await db.commit()
    
    return {"success": True, "message": "Device deactivated"}
