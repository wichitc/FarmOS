from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AIModelOut(BaseModel):
    id: str
    code: str
    name: str
    task_type: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ModelVersionOut(BaseModel):
    id: str
    model_id: str
    version: str
    status: str
    implementation_ref: str
    training_dataset_ref: Optional[str] = None
    metrics: dict
    released_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PredictionOut(BaseModel):
    id: str
    model_version_id: str
    entity_type: str
    entity_id: str
    input_ref: dict
    output: dict
    confidence: Optional[float] = None
    predicted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PredictionFeedbackCreate(BaseModel):
    status: str
    corrected_value: Optional[dict] = None
    notes: Optional[str] = None


class PredictionFeedbackOut(BaseModel):
    id: str
    prediction_id: str
    status: str
    corrected_value: Optional[dict] = None
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AgentActionPropose(BaseModel):
    agent_code: str
    action_type: str
    requested_level: str = "L1"
    entity_type: str
    entity_id: str
    farm_id: Optional[str] = None
    rationale: str
    input_context: dict = {}


class AgentActionOut(BaseModel):
    id: str
    agent_code: str
    action_type: str
    level: str
    entity_type: str
    entity_id: str
    farm_id: Optional[str] = None
    rationale: str
    input_context: dict
    status: str
    workflow_instance_id: Optional[str] = None
    policy_grant_id: Optional[str] = None
    result: Optional[dict] = None
    executed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ApprovalDecisionRequest(BaseModel):
    reason: Optional[str] = None


class AgentActionExecuteRequest(BaseModel):
    confirmed: bool = False
    result: dict = {}


class AgentPolicyGrantCreate(BaseModel):
    action_type: str
    notes: Optional[str] = None


class AgentPolicyGrantOut(BaseModel):
    id: str
    action_type: str
    is_active: bool
    granted_by: Optional[str] = None
    granted_at: datetime
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CopilotAskRequest(BaseModel):
    farm_id: Optional[str] = None
    question: str
    conversation_id: Optional[str] = None


class CopilotAskResponse(BaseModel):
    conversation_id: str
    answer: str
    citations: list[dict]
