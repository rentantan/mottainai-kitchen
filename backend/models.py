from __future__ import annotations

from datetime import date
from typing import Literal
from pydantic import BaseModel, Field

Category = Literal["野菜・果物", "肉・魚", "乳製品・卵", "主食・麺", "調味料", "その他"]


class PantryInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    quantity: float = Field(gt=0, le=100000)
    unit: str = Field(default="個", max_length=20)
    expiry_date: date
    category: str = Field(default="その他", max_length=30)


class PantryItemWrite(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    quantity: float = Field(gt=0, le=100000)
    unit: str = Field(default="個", min_length=1, max_length=20)
    expiryDate: date
    category: Category = "その他"
    emoji: str = Field(default="🛒", max_length=8)
    note: str = Field(default="", max_length=300)


class ConsumeRequest(BaseModel):
    # None keeps the old behaviour (use one unit).
    amount: float | None = Field(default=None, gt=0, le=100000)


class BatchConsumeEntry(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    amount: float = Field(gt=0, le=100000)


class BatchConsumeRequest(BaseModel):
    items: list[BatchConsumeEntry] = Field(min_length=1, max_length=50)


class RecipePreferences(BaseModel):
    budget_yen: Literal[300, 500, 700] = 500
    max_minutes: Literal[10, 20, 30] = 20


class SuggestRequest(BaseModel):
    pantry: list[PantryInput] = Field(default_factory=list, max_length=200)
    preferences: RecipePreferences = Field(default_factory=RecipePreferences)
    refresh_nonce: int = Field(default=0, ge=0, le=1_000_000_000)


class ShoppingItemCreate(BaseModel):
    names: list[str] = Field(min_length=1, max_length=30)


class ShoppingItemUpdate(BaseModel):
    checked: bool


class StaplesWrite(BaseModel):
    names: list[str] = Field(max_length=50)


class AuthCredentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class AuthSession(BaseModel):
    token: str
    email: str
