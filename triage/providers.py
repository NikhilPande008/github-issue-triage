"""Typed provider-neutral contracts; adapters must preserve provenance."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol

@dataclass(frozen=True)
class ProviderCapabilities:
    structured_output: bool; token_reporting: bool; cost_reporting: bool; cancellation: bool; sandbox_compatible: bool; embedding: bool
@dataclass(frozen=True)
class ProviderUsage:
    input_tokens:int|None=None; output_tokens:int|None=None; cached_input_tokens:int|None=None; cost_usd:float|None=None; cost_status:str="UNSUPPORTED"
@dataclass(frozen=True)
class ProviderResult:
    provider:str; model:str; purpose:str; schema_version:str; payload:Any; usage:ProviderUsage; latency_ms:int|None=None; attempt:int=1; request_id:str|None=None; failure_category:str|None=None
class ExtractionProvider(Protocol):
    identifier:str; capabilities:ProviderCapabilities
    def extract(self,system_prompt:str,user_prompt:str)->Any:...
class ClassificationProvider(Protocol):
    identifier:str; capabilities:ProviderCapabilities
    def classify(self,system_prompt:str,evidence_prompt:str)->Any:...
class InvestigationAgentProvider(Protocol):
    identifier:str; capabilities:ProviderCapabilities
    def run_attempt(self,*args,**kwargs):...

OPENAI_CAPABILITIES=ProviderCapabilities(True,True,True,False,False,False)
CODEX_CAPABILITIES=ProviderCapabilities(False,False,False,False,True,False)
def validate_provider_selection(extraction:str,classification:str,agent:str,embedding:str|None)->None:
    supported={"openai"};
    if extraction not in supported: raise ValueError(f"Unsupported extraction provider '{extraction}'; supported: openai")
    if classification not in supported: raise ValueError(f"Unsupported classification provider '{classification}'; supported: openai")
    if agent not in {"codex","claude_code"}: raise ValueError(f"Unsupported investigation-agent provider '{agent}'; supported: codex, claude_code")
    if embedding not in {None,"openai"}: raise ValueError(f"Unsupported embedding provider '{embedding}'; supported: openai")
