from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from pydantic import BaseModel, Field, StringConstraints

Category = Literal["野菜・果物", "肉・魚", "乳製品・卵", "主食・麺", "調味料", "その他"]


class PantryInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    quantity: float = Field(gt=0, le=100000)
    unit: str = Field(default="個", max_length=20)
    expiry_date: date
    category: str = Field(default="その他", max_length=30)
    frozen: bool = False


class PantryItemWrite(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    quantity: float = Field(gt=0, le=100000)
    unit: str = Field(default="個", min_length=1, max_length=20)
    expiryDate: date
    category: Category = "その他"
    emoji: str = Field(default="🛒", max_length=8)
    note: str = Field(default="", max_length=300)
    frozen: bool = False
    # Optional purchase price of the whole pack, used to show wasted food in yen.
    priceYen: int | None = Field(default=None, ge=0, le=100000)
    # Quantity when bought; the price applies to this amount. Defaults to quantity.
    purchasedQuantity: float | None = Field(default=None, gt=0, le=100000)


class RestoreRequest(BaseModel):
    """Undo a delete: re-create the item and drop the waste-log entry it produced, if any."""
    item: PantryItemWrite
    createdAt: str | None = Field(default=None, max_length=40)
    wasteId: str | None = Field(default=None, max_length=64)


class ConsumeRequest(BaseModel):
    # None keeps the old behaviour (use one unit).
    amount: float | None = Field(default=None, gt=0, le=100000)


class BatchConsumeEntry(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    amount: float = Field(gt=0, le=100000)


class BatchConsumeRequest(BaseModel):
    items: list[BatchConsumeEntry] = Field(min_length=1, max_length=50)


class UndoConsumeEntry(BaseModel):
    logId: str = Field(min_length=1, max_length=64)
    # The item as it was before "使った"; needed to bring back an item that was used up.
    item: PantryItemWrite | None = None
    createdAt: str | None = Field(default=None, max_length=40)


class UndoConsumeRequest(BaseModel):
    entries: list[UndoConsumeEntry] = Field(min_length=1, max_length=50)


class StockEntry(BaseModel):
    shoppingId: str = Field(min_length=1, max_length=64)
    item: PantryItemWrite


class StockFromShoppingRequest(BaseModel):
    """Bought items on the shopping list, registered in the fridge in one go."""
    entries: list[StockEntry] = Field(min_length=1, max_length=50)


class RecipePreferences(BaseModel):
    budget_yen: Literal[300, 500, 700] = 500
    max_minutes: Literal[10, 20, 30] = 20
    # "microwave": no stove (dorm rooms, one-burner kitchens) — microwave / kettle / rice cooker only.
    equipment: Literal["any", "microwave"] = "any"


class SuggestRequest(BaseModel):
    # The pantry is read from SQLite on the server. A "pantry" field sent by older clients
    # is ignored (pydantic drops unknown fields).
    preferences: RecipePreferences = Field(default_factory=RecipePreferences)
    # refresh=True: the user asked for different recipes under the same conditions, so skip
    # the cache and avoid the dishes in exclude_recipe_names (the ones currently shown).
    refresh: bool = False
    exclude_recipe_names: list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]] = Field(
        default_factory=list, max_length=9)


class SavedRecipeWrite(BaseModel):
    """The pantry-independent part of a recipe. Matched / missing ingredients are worked out
    again against the current fridge whenever the saved recipe is shown."""
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=300)
    minutes: int = Field(ge=1, le=180)
    difficulty: Literal["かんたん", "ふつう"] = "かんたん"
    emoji: str = Field(default="🍳", max_length=8)
    ingredients: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]] = Field(
        min_length=1, max_length=30)
    ingredientDetails: list[Annotated[str, StringConstraints(max_length=100)]] = Field(default_factory=list, max_length=30)
    steps: list[Annotated[str, StringConstraints(max_length=400)]] = Field(default_factory=list, max_length=20)
    estimatedCostYen: int | None = Field(default=None, ge=0, le=10000)
    microwaveOnly: bool = False
    source: str = Field(default="", max_length=40)


class ShoppingItemCreate(BaseModel):
    names: list[str] = Field(min_length=1, max_length=30)


class ShoppingItemUpdate(BaseModel):
    checked: bool


class StaplesWrite(BaseModel):
    names: list[str] = Field(max_length=50)


class AuthCredentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class PasswordChange(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=128)
    newPassword: str = Field(min_length=8, max_length=128)


class AccountDelete(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class AuthSession(BaseModel):
    token: str
    email: str
