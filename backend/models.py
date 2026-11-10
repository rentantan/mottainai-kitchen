from __future__ import annotations

from datetime import date
from typing import Literal
from pydantic import BaseModel, Field

class PantryInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    quantity: float = Field(gt=0, le=100000)
    unit: str = Field(default="個", max_length=20)
    expiry_date: date
    category: str = Field(default="その他", max_length=30)


class PantryItemWrite(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    quantity: float = Field(gt=0, le=100000)
    unit: str = Field(default="個", max_length=20)
    expiryDate: date
    category: str = Field(default="その他", max_length=30)
    emoji: str = Field(default="🛒", max_length=8)
    note: str = Field(default="", max_length=300)


class RecipePreferences(BaseModel):
    budget_yen: Literal[300, 500, 700] = 500
    max_minutes: Literal[10, 20, 30] = 20


class SuggestRequest(BaseModel):
    pantry: list[PantryInput] = Field(default_factory=list, max_length=200)
    preferences: RecipePreferences = Field(default_factory=RecipePreferences)
    refresh_nonce: int = Field(default=0, ge=0, le=1_000_000_000)


class AuthCredentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class AuthSession(BaseModel):
    token: str
    email: str
