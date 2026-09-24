from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import ModelId

Subject = Literal["數學", "國語", "英文", "自然", "社會", "其他"]
Grade = Literal["國小低年級", "國小中年級", "國小高年級", "國中", "高中"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Observation(StrictModel):
    question: str = Field(max_length=3000)
    student_answer: str = Field(max_length=2000)
    subject: Subject
    concept: str = Field(max_length=200)
    confidence: float = Field(ge=0, le=1)
    quality: Literal["clear", "blurred", "occluded", "no_question", "multiple_questions"]
    clarification: str = Field(max_length=500)


class ObserveRequest(StrictModel):
    model: ModelId | None = None
    image: str = Field(max_length=4_000_000)
    subject: Subject = "數學"
    grade: Grade = "國小高年級"


class TutorRequest(StrictModel):
    model: ModelId | None = None
    question: str = Field(min_length=1, max_length=3000)
    student_answer: str = Field(default="", max_length=2000)
    subject: Subject = "數學"
    grade: Grade = "國小高年級"
    image: str | None = Field(default=None, max_length=4_000_000)
    confirmed: bool = False
    hint_level: int = Field(default=1, ge=1, le=3)
    demo: bool = False


class Exercise(StrictModel):
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=1000)
    explanation: str = Field(min_length=1, max_length=1500)


class TutorAnalysis(StrictModel):
    verdict: Literal["correct", "needs_work", "in_progress", "uncertain"]
    confidence: float = Field(ge=0, le=1)
    concept: str = Field(max_length=200)
    feedback: str = Field(max_length=1000)
    hints: list[str] = Field(min_length=2, max_length=2)
    explanation: str = Field(max_length=2000)
    exercises: list[Exercise] = Field(min_length=1, max_length=3)
