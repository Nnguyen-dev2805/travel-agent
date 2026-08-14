"""Pydantic schemas for Authentication API requests and responses."""

from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    """Schema for user registration request."""

    email: EmailStr = Field(..., json_schema_extra={"example": "user@travel.vn"})
    password: str = Field(..., min_length=6, json_schema_extra={"example": "password123"})
    full_name: Optional[str] = Field(None, json_schema_extra={"example": "Nguyễn Văn A"})


class UserLoginRequest(BaseModel):
    """Schema for user login request."""

    email: EmailStr = Field(..., json_schema_extra={"example": "user@travel.vn"})
    password: str = Field(..., json_schema_extra={"example": "password123"})


class MemoryConsentUpdate(BaseModel):
    """Schema for updating memory consent."""
    
    memory_enabled: bool = Field(..., description="Whether the user allows AI to remember facts.")


class TokenResponse(BaseModel):
    """Schema for authentication token response."""

    access_token: str = Field(..., json_schema_extra={"example": "eyJhbGciOiJIUzI1NiIsInR5cCI6..."})
    token_type: str = Field("bearer", json_schema_extra={"example": "bearer"})


class UserResponse(BaseModel):
    """Schema for user public profile response."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., json_schema_extra={"example": 1})
    email: str = Field(..., json_schema_extra={"example": "user@travel.vn"})
    full_name: Optional[str] = Field(None, json_schema_extra={"example": "Nguyễn Văn A"})
    is_active: bool = Field(True, json_schema_extra={"example": True})
    memory_enabled: bool = Field(True, json_schema_extra={"example": True})
