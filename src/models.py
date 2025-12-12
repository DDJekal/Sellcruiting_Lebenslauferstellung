"""Pydantic models for the protocol filling system."""
from enum import Enum
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field


class PromptType(str, Enum):
    """Types of prompts that can be inferred."""
    YES_NO = "yes_no"
    YES_NO_WITH_DETAILS = "yes_no_with_details"
    TEXT = "text"
    TEXT_LIST = "text_list"
    NUMBER = "number"
    DATE = "date"
    ROUTING_RULE = "routing_rule"
    INFO = "info"
    RECRUITER_INSTRUCTION = "recruiter_instruction"


class ShadowType(BaseModel):
    """Inferred type for a prompt (Shadow-Type)."""
    prompt_id: int
    inferred_type: PromptType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: Optional[str] = None


class Evidence(BaseModel):
    """Evidence from transcript supporting an answer."""
    span: str = Field(description="Text snippet from transcript")
    turn_index: int = Field(description="Index of turn in transcript")
    speaker: Optional[str] = Field(default=None, description="Speaker (A or B)")


class PromptAnswer(BaseModel):
    """Answer for a single prompt."""
    checked: Optional[bool] = Field(default=None, description="For yes/no prompts")
    value: Optional[Union[str, List[str]]] = Field(default=None, description="For text/list prompts")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: List[Evidence] = Field(default_factory=list)
    notes: Optional[str] = None


class FilledPrompt(BaseModel):
    """A filled prompt with inferred type and answer."""
    id: int
    question: str
    inferred_type: PromptType
    answer: PromptAnswer


class FilledPage(BaseModel):
    """A page with filled prompts."""
    id: int
    name: str
    prompts: List[FilledPrompt]


class FilledProtocol(BaseModel):
    """Complete filled protocol."""
    protocol_id: int
    protocol_name: str
    pages: List[FilledPage]
    extracted_extras: Dict[str, Any] = Field(default_factory=dict)


# Mandanten-Config Models

class HeuristicRule(BaseModel):
    """Heuristic rule for type inference."""
    pattern: str
    type: PromptType
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)


class MustCriterion(BaseModel):
    """Must-have criterion that needs to be fulfilled."""
    prompt_id: int
    expected: bool
    error_msg: str


class RoutingCondition(BaseModel):
    """Condition for routing rule."""
    prompt: int
    field: str  # "checked" or "value"
    operator: str  # "==", "!=", "contains", "not_contains"
    value: Any


class RoutingAction(BaseModel):
    """Action to take when routing condition is met."""
    checked: Optional[bool] = None
    value: Optional[str] = None
    notes: Optional[str] = None


class RoutingRule(BaseModel):
    """Routing rule for automatic prompt filling."""
    rule_id: str
    target_prompt: int
    conditions: List[RoutingCondition]
    action: RoutingAction


class ImplicitDefaultAnswer(BaseModel):
    """Default answer to apply when prompt not explicitly mentioned."""
    checked: Optional[bool] = None
    value: Optional[str] = None
    confidence: float = 0.8
    notes: str = ""


class ImplicitDefault(BaseModel):
    """Rule for implicitly filling prompts that were not explicitly discussed."""
    prompt_id: int
    reasoning: str
    default_answer: ImplicitDefaultAnswer


class MandantenConfig(BaseModel):
    """Configuration for a Mandant (client)."""
    mandant_id: str
    protokoll_template_id: int
    heuristic_rules: List[HeuristicRule] = Field(default_factory=list)
    info_page_names: List[str] = Field(default_factory=list)
    grounding: Dict[str, Any] = Field(default_factory=dict)
    aida_phase_mapping: Dict[str, List[int]] = Field(default_factory=dict)
    must_criteria: List[MustCriterion] = Field(default_factory=list)
    routing_rules: List[RoutingRule] = Field(default_factory=list)
    implicit_defaults: List[ImplicitDefault] = Field(default_factory=list)


# Resume/CV Models (for structured output)

class Experience(BaseModel):
    """Work experience entry."""
    id: int
    start: Optional[str] = Field(default=None, description="Start date (YYYY-MM-DD)")
    end: Optional[str] = Field(default=None, description="End date (YYYY-MM-DD) or None if current")
    company: Optional[str] = Field(default=None, description="Company name or None if unknown")
    tasks: str = Field(default="", description="Description of tasks and responsibilities")


class Education(BaseModel):
    """Education/training entry."""
    id: int
    end: Optional[str] = Field(default=None, description="Completion date (YYYY-MM-DD)")
    company: Optional[str] = Field(default=None, description="Institution or organization")
    description: str = Field(default="", description="Degree, qualification, or course name")


class Resume(BaseModel):
    """Resume/CV data structure."""
    id: int
    preferred_contact_time: Optional[str] = None
    preferred_workload: Optional[str] = None
    willing_to_relocate: Optional[str] = None
    earliest_start: Optional[str] = None
    current_job: Optional[str] = None
    motivation: Optional[str] = None
    expectations: Optional[str] = None
    start: Optional[str] = None
    applicant_id: int
    experiences: List[Experience] = Field(default_factory=list)
    educations: List[Education] = Field(default_factory=list)


class Applicant(BaseModel):
    """Applicant personal data."""
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    postal_code: Optional[str] = None


class ApplicantResume(BaseModel):
    """Complete applicant profile with resume."""
    applicant: Applicant
    resume: Resume