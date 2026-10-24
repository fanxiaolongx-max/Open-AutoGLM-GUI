"""Public automation request schemas shared by the API and its OpenAPI document."""
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class AutomationStep(BaseModel):
    content: str = Field(min_length=1)
    timeout: float = Field(default=180, ge=1, le=3600)
    repeatable: bool = False
    retry_once: bool = False
    acceptance: Optional[str | dict] = None


class DeviceSequenceStep(BaseModel):
    device_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    timeout: float = Field(default=180, ge=1, le=3600)


class RecipeParameter(BaseModel):
    name: str = Field(min_length=1)
    type: Literal['text', 'number', 'date', 'time', 'enum'] = 'text'
    default: Any = None
    options: Optional[list] = None


class RecipeDefinition(BaseModel):
    format_version: int = 1
    name: str = Field(min_length=1)
    description: str = ''
    parameters: list[RecipeParameter] = Field(default_factory=list)
    steps: list[AutomationStep] = Field(min_length=1, max_length=100)
    target_app: Optional[str] = None
    acceptance: Optional[str | dict] = None
    archived: bool = False


class TriggerDefinition(BaseModel):
    name: str = ''
    kind: Literal['online', 'charging', 'recipe_completed']
    device_id: str = Field(min_length=1)
    recipe_id: str = Field(min_length=1)
    revision: Optional[int] = Field(default=None, ge=1)
    parameters: dict = Field(default_factory=dict)
    source_recipe: Optional[str] = None
    enabled: bool = True
    cooldown: int = Field(default=300, ge=0)
