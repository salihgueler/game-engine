"""Pydantic schemas for request/response validation."""
import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from src.models.models import SUPPORTED_CODE_LANGUAGES


class QuestionBankCreate(BaseModel):
    name: str


class QuestionBankUpdate(BaseModel):
    name: Optional[str] = None


class CodeVariantInput(BaseModel):
    """One per-language variant of a Coding question (admin authoring)."""

    language: str
    starter_code: Optional[str] = None
    code_sample_input: Optional[str] = None
    code_sample_output: Optional[str] = None
    code_hidden_input: Optional[str] = None
    code_hidden_output: Optional[str] = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, v):
        normalized = (v or "").lower().strip()
        if normalized not in SUPPORTED_CODE_LANGUAGES:
            raise ValueError(
                f"language must be one of {list(SUPPORTED_CODE_LANGUAGES)}"
            )
        return normalized


class QuestionCreate(BaseModel):
    category: str
    difficulty: str
    description: str
    correct_answer: str
    hint: Optional[str] = None
    options: Optional[list[str]] = None
    code_programming_language: Optional[str] = None
    code_sample_input: Optional[str] = None
    code_sample_output: Optional[str] = None
    code_hidden_input: Optional[str] = None
    code_hidden_output: Optional[str] = None
    code_variants: Optional[list[CodeVariantInput]] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        allowed = {"Coding", "General", "MultipleChoice"}
        if v not in allowed:
            raise ValueError(f"category must be one of {allowed}")
        return v

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v):
        allowed = {"Easy", "Moderate", "Hard"}
        if v not in allowed:
            raise ValueError(f"difficulty must be one of {allowed}")
        return v


class QuestionUpdate(BaseModel):
    category: Optional[str] = None
    difficulty: Optional[str] = None
    description: Optional[str] = None
    correct_answer: Optional[str] = None
    hint: Optional[str] = None
    options: Optional[list[str]] = None
    code_programming_language: Optional[str] = None
    code_sample_input: Optional[str] = None
    code_sample_output: Optional[str] = None
    code_hidden_input: Optional[str] = None
    code_hidden_output: Optional[str] = None
    code_variants: Optional[list[CodeVariantInput]] = None


class AnswerSubmit(BaseModel):
    answer: str
    # Optional language selection for Coding questions with multiple variants.
    language: Optional[str] = None


class ConfigUpdate(BaseModel):
    value: str


class QuestionImport(BaseModel):
    questions: list[QuestionCreate]


class BankAssignQuestions(BaseModel):
    question_ids: list[int]


class EventCreate(BaseModel):
    name: str
    theme: str
    question_bank_id: int
    custom_welcome_text: Optional[str] = None
    survey_link: Optional[str] = None
    code_expiry: Optional[datetime] = None


class EventUpdate(BaseModel):
    name: Optional[str] = None
    theme: Optional[str] = None
    question_bank_id: Optional[int] = None
    custom_welcome_text: Optional[str] = None
    survey_link: Optional[str] = None
    code_expiry: Optional[datetime] = None


class PlayerCreate(BaseModel):
    name: str
    avatar: str
    preferred_coding_language: str
    difficulty: str

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v):
        allowed = {"Easy", "Moderate", "Hard"}
        if v not in allowed:
            raise ValueError(f"difficulty must be one of {allowed}")
        return v


class GameEnd(BaseModel):
    score: int
    time_taken_seconds: int
