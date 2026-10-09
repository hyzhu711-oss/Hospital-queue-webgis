from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Location(StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class QueryRequest(StrictModel):
    query: str = Field(min_length=1, max_length=4000)
    location: Location | None = None
    session_id: str | None = Field(default=None, min_length=36, max_length=36)
    reference_time: str | None = None

    @field_validator('query')
    @classmethod
    def nonblank_query(cls,value):
        if not value.strip():raise ValueError('Query cannot be blank')
        return value


class PlanSpec(StrictModel):
    intent: Literal["lookup", "nearest", "radius", "attribute", "temporal", "ranking", "comparison", "multi_step", "ambiguous", "unsupported"]
    names: list[str] = Field(default_factory=list, max_length=20)
    referent: int | None = Field(default=None, ge=1, le=20)
    radius_m: float | None = Field(default=None, gt=0, le=100000)
    hours: float = Field(default=24, gt=0, le=8784)
    min_cleanliness: float | None = Field(default=None, ge=1, le=5)
    max_queue_severity: float | None = Field(default=None, ge=1, le=5)
    max_wait_minutes: float | None = Field(default=None, ge=0, le=1440)
    limit: int = Field(default=3, ge=1, le=20)
    distance_weight: float = Field(default=1/3, ge=0, le=1)
    queue_weight: float = Field(default=1/3, ge=0, le=1)
    cleanliness_weight: float = Field(default=1/3, ge=0, le=1)


class AgentFailure(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)
