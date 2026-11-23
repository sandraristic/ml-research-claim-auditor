from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class Run(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_id: str = Field(min_length=1)
    protocol_id: str = Field(min_length=1)
    split_id: str = Field(min_length=1)
    method_id: str = Field(min_length=1)
    target_class: str = Field(min_length=1)
    fpr_limit: float = Field(ge=0, le=1)
    test_fpr: float = Field(ge=0, le=1)
    test_recall: float = Field(ge=0, le=1)
    test_positive_n: int | None = Field(default=None, ge=1)
    test_true_positives: int | None = Field(default=None, ge=0)
    test_negative_n: int | None = Field(default=None, ge=1)
    test_false_positives: int | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def check_counts(self):
        for name, num, den, metric in (
            ('recall', self.test_true_positives, self.test_positive_n, self.test_recall),
            ('fpr', self.test_false_positives, self.test_negative_n, self.test_fpr),
        ):
            if num is not None and den is None:
                raise ValueError(f'{name}: numerator provided without denominator')
            if num is not None and den is not None:
                if num > den: raise ValueError(f'{name}: numerator exceeds denominator')
                if abs(num / den - metric) > 1e-5:
                    raise ValueError(f'{name}: count-derived metric differs from reported metric')
        return self

class Manifest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['0.1'] = '0.1'
    protocol_id: str = Field(min_length=1)
    target_class: str = Field(min_length=1)
    expected_splits: dict[str, list[str]]
    expected_methods: list[str]
    fpr_limits: list[float]
    split_independence: str
    provenance: str

    @model_validator(mode='after')
    def check_expected(self):
        if not self.expected_splits or not self.expected_methods or not self.fpr_limits:
            raise ValueError('expected splits, methods and fpr_limits are required')
        if any(not v or len(v)!=len(set(v)) for v in self.expected_splits.values()):
            raise ValueError('expected splits must be nonempty and unique')
        if len(self.expected_methods)!=len(set(self.expected_methods)):
            raise ValueError('duplicate expected method')
        if any(not 0<=v<=1 for v in self.fpr_limits) or len(self.fpr_limits)!=len(set(self.fpr_limits)):
            raise ValueError('invalid or duplicate FPR limits')
        return self

class Claim(BaseModel):
    model_config = ConfigDict(extra='forbid')
    claim_type: Literal['conditional_recall_advantage', 'universal_operational_advantage']
    dataset_id: str
    protocol_id: str
    target_class: str
    baseline_method: str
    challenger_method: str
    fpr_limit: float = Field(ge=0, le=1)
    recall_margin: float = Field(default=0.0, ge=0, le=1)
    expected_split_ids: list[str] = Field(min_length=1)
