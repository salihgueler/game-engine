"""Pydantic schemas for request/response validation."""
import json
from typing import Optional

from pydantic import BaseModel, field_validator


class QuestionBankCreate(BaseModel):
    name: str


class QuestionBankUpdate(BaseModel):
    name: Optional[str] = None


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


class AnswerSubmit(BaseModel):
    answer: str


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


class EventUpdate(BaseModel):
    name: Optional[str] = None
    theme: Optional[str] = None
    question_bank_id: Optional[int] = None
    custom_welcome_text: Optional[str] = None
    survey_link: Optional[str] = None


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
