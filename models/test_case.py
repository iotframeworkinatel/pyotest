"""
Data models for the IoT Test Case Generator.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
import uuid


@dataclass
class TestCase:
    test_id: str
    test_name: str
    description: str
    protocol: str
    port: int
    target_ip: str
    vulnerability_type: str
    owasp_iot_category: str
    severity: str  # "critical", "high", "medium", "low", "info"
    test_steps: list[str] = field(default_factory=list)
    expected_result: str = ""
    payloads: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    auth_required: bool = False
    tags: list[str] = field(default_factory=list)
    risk_score: Optional[float] = None
    is_recommended: bool = False
    test_origin: str = "registry"         # "registry" | "llm"
    pytest_code: Optional[str] = None     # LLM tests carry their own standalone code

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TestCase":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TestSuite:
    suite_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    devices: list[dict] = field(default_factory=list)
    test_cases: list[TestCase] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def total_tests(self) -> int:
        return len(self.test_cases)

    @property
    def protocols(self) -> list[str]:
        return sorted(set(tc.protocol for tc in self.test_cases))

    @property
    def recommended_count(self) -> int:
        return sum(1 for tc in self.test_cases if tc.is_recommended)

    def to_dict(self) -> dict:
        return {
            "suite_id": self.suite_id,
            "name": self.name,
            "created_at": self.created_at,
            "devices": self.devices,
            "test_cases": [tc.to_dict() for tc in self.test_cases],
            "metadata": self.metadata,
            "total_tests": self.total_tests,
            "protocols": self.protocols,
            "recommended_count": self.recommended_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestSuite":
        test_cases = [TestCase.from_dict(tc) for tc in data.get("test_cases", [])]
        return cls(
            suite_id=data.get("suite_id", str(uuid.uuid4())[:8]),
            name=data.get("name", ""),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            devices=data.get("devices", []),
            test_cases=test_cases,
            metadata=data.get("metadata", {}),
        )
