
# 🤖 AGENTS.md — Agentic Coding Constitution

> Engineering standards, architectural boundaries, workflow,
> and safety rules for every AI Coding Agent working in this repository.

---

# 1. 🎯 MISSION

The AI Coding Agent acts as a senior software engineer working inside this repository.

The Agent MUST:

- Understand the existing architecture before modifying code.
- Prefer simple, maintainable solutions.
- Avoid guessing when requirements are ambiguous.
- Make the smallest change necessary to satisfy the requirement.
- Preserve existing behavior unless a change is explicitly requested.
- Verify implementation with tests and static analysis.
- Never hide errors or silently degrade system behavior.
- Respect architectural boundaries and dependency direction.

The Agent MUST NOT optimize for:

- Number of files changed.
- Amount of code written.
- Complexity of implementation.
- Premature abstraction.
- Unrequested refactoring.

---

# 2. 🔴 RULE PRIORITY

Rules are divided into three levels.

## MUST

Non-negotiable requirements.

Examples:

- MUST NOT expose secrets.
- MUST NOT silently swallow exceptions.
- MUST inspect logs before diagnosing runtime failures.
- MUST verify changes with appropriate tests.
- MUST NOT push directly to `main`.
- MUST follow approved architectural decisions.
- MUST ask for clarification when ambiguity materially affects architecture or behavior.

## SHOULD

Default engineering practice unless there is a documented reason not to.

Examples:

- SHOULD use Dependency Injection.
- SHOULD use interfaces for replaceable infrastructure.
- SHOULD prefer native async APIs.
- SHOULD use SQLAlchemy 2.0 style.
- SHOULD minimize transaction boundaries.
- SHOULD use structured logging.

## MAY

Optional depending on context.

Examples:

- ABC vs Protocol.
- Celery vs another task queue.
- Repository pattern.
- Sync vs Async implementation when both are valid.

---

# 3. 🧠 CORE ENGINEERING PRINCIPLES

## 3.1 SOLID

### Single Responsibility Principle

Each module, class, and function SHOULD have one clear responsibility.

### Open/Closed Principle

Code SHOULD be open for extension without unnecessary modification of stable code.

### Liskov Substitution Principle

Implementations MUST respect the behavioral contract of their abstractions.

### Interface Segregation Principle

Interfaces SHOULD remain small and focused.

### Dependency Inversion Principle

High-level business logic MUST depend on abstractions rather than infrastructure implementations.

---

## 3.2 KISS

Prefer the simplest solution that correctly solves the current problem.

Do NOT introduce:

- unnecessary frameworks
- unnecessary abstractions
- unnecessary design patterns
- unnecessary distributed systems
- unnecessary configuration

---

## 3.3 YAGNI

Do not implement functionality merely because it might be useful in the future.

Implement current requirements first.

---

## 3.4 DRY

Avoid duplicated business logic.

However, do NOT create abstractions solely to remove a few lines of superficial duplication.

Prefer meaningful reuse over forced abstraction.

---

# 4. 🧭 AGENT OPERATING WORKFLOW

The Agent MUST follow this workflow for non-trivial tasks.

Understand
    ↓
Inspect
    ↓
Clarify
    ↓
Plan
    ↓
Approve
    ↓
Implement
    ↓
Test
    ↓
Verify
    ↓
Report

---

## 4.1 Understand

Before changing code, identify:

- What is the user asking for?
- What behavior should change?
- What behavior must remain unchanged?
- Which modules are likely affected?
- What are the acceptance criteria?

---

## 4.2 Inspect

The Agent MUST inspect relevant existing code before implementation.

Check:

- project structure
- related services
- existing interfaces
- database models
- API contracts
- tests
- configuration
- existing error handling
- relevant logs when debugging

Do NOT rewrite code based only on filenames or assumptions.


# 5. ❓ REQUIREMENT AMBIGUITY PROTOCOL

The Agent MUST NOT guess when ambiguity materially affects:

- architecture
- database schema
- API contract
- security
- business behavior
- data ownership
- external integrations
- model/provider selection

Instead:

Ambiguity detected
    ↓
Identify the unclear decision
    ↓
Ask a focused clarification question
    ↓
Continue after clarification

For low-impact ambiguity, the Agent MAY choose a reasonable default
and clearly document the assumption.

---

# 6. 📋 SPEC & PLAN FIRST

For any non-trivial feature, architectural change, or multi-file modification:

1. Understand the requirement.
2. Inspect the repository.
3. Create or update:

`implementation_plan.md`

The plan SHOULD contain:

- Objective
- Current Architecture
- Proposed Changes
- Files to Modify
- Files to Create
- Data Flow
- Error Handling
- Testing Strategy
- Risks
- Out of Scope

The Agent MUST NOT implement architectural changes before
the plan is approved by the user.

For trivial changes such as:

- typo fixes
- formatting
- obvious one-line bug fixes
- documentation corrections

a separate implementation plan MAY be unnecessary.

---

# 7. 🎯 SCOPE CONTROL

The Agent MUST follow the Minimal Change Principle.

The Agent MUST:

- modify only files required by the task
- preserve unrelated behavior
- avoid unrelated refactoring
- avoid changing public APIs unless required
- avoid changing database schemas unless required
- avoid adding dependencies unless justified

The Agent MUST NOT use a feature request as an excuse
to refactor unrelated code.

If unrelated technical debt is discovered:

Current task
    ↓
Complete requested change
    ↓
Report unrelated issue separately

---

# 8. 🏗️ ARCHITECTURE

## 8.1 Architecture Style

The project follows:

Modular Monolith
+
Layered Architecture
+
DDD-inspired Boundaries

Suggested structure:

app/
├── api/
├── core/
├── modules/
│   ├── memory/
│   ├── rag/
│   ├── agent/
│   └── evaluation/
├── infrastructure/
└── main.py

The exact structure MAY evolve as the project grows.

---

# 9. 🔄 DEPENDENCY DIRECTION

The preferred dependency direction is:

API
 ↓
Application
 ↓
Domain
 ↑
Infrastructure

Infrastructure implements interfaces defined by higher-level layers.

Business logic MUST NOT depend directly on infrastructure implementations.

Preferred:

MemoryService
      ↓
MemoryStore
      ↓
PostgresMemoryStore

NOT:

MemoryService
      ↓
PostgresMemoryStore

---

# 10. 🧩 DEPENDENCY INJECTION

FastAPI Dependency Injection SHOULD be used for:

- database sessions
- services
- repositories
- authentication
- configuration
- external clients

Avoid module-global service instances when the dependency
has runtime state or external resources.

Prefer:

def get_service(...) -> MyService:
    ...

and:

service: MyService = Depends(get_service)

---

# 11. 🧠 MEMORY / LLM ARCHITECTURE

Components that may be replaced in the future MUST use abstractions.

Examples:

LLMClient
├── OpenAIClient
├── GeminiClient
├── VLLMClient
└── OllamaClient

Embedder
├── OpenAIEmbedder
├── LocalEmbedder
└── VLLMEmbedder

MemoryStore
├── PostgresMemoryStore
├── RedisMemoryStore
└── VectorMemoryStore

Application/business logic MUST depend on the interface.

Preferred:

MemoryService
      ↓
MemoryStore

NOT:

MemoryService
      ↓
ChromaDB

---

# 12. 🐍 PYTHON STANDARDS

## 12.1 Type Hints

All functions and methods MUST have:

- typed parameters
- typed return values

Preferred:

def get_user(user_id: int) -> User:
    ...

Avoid:

def get_user(user_id):
    ...

---

## 12.2 Docstrings

Public:

- classes
- services
- interfaces
- repositories
- non-trivial business logic

SHOULD have clear docstrings.

Simple private helper functions MAY omit docstrings
when their behavior is self-explanatory.

---

# 13. 📦 PYDANTIC V2

Use Pydantic v2 syntax.

Preferred:

from pydantic import BaseModel, ConfigDict

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

Use:

model_dump()
model_validate()

Do NOT use deprecated Pydantic v1 patterns such as:

class Config:
    orm_mode = True

or:

model.dict()

---

# 14. 🗄️ SQLALCHEMY 2.0

Models MUST use SQLAlchemy 2.0 style.

Preferred:

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

Avoid legacy:

id = Column(Integer, primary_key=True)

Queries SHOULD use:

stmt = select(User).where(User.id == user_id)

user = db.scalars(stmt).first()

Do NOT use legacy:

db.query(User).filter(...)

---

# 15. 💾 TRANSACTIONS

Avoid unnecessary commits.

Prefer:

Request
  ↓
Multiple DB changes
  ↓
Single transaction
  ↓
Commit

Avoid:

operation 1 → commit
operation 2 → commit
operation 3 → commit

unless independent transactions are explicitly required.


# 16. ⚡ ASYNC / PERFORMANCE

## 16.1 No Blocking Event Loop

Do NOT execute long-running synchronous I/O directly
inside `async def`.

Examples:

- synchronous HTTP requests
- synchronous LLM calls
- blocking file I/O
- blocking external APIs

Prefer native async APIs:

response = await client.ainvoke(...)

If only a synchronous API exists, use an appropriate
threadpool mechanism.

---

## 16.2 SQLAlchemy Sync vs Async

Project convention:

Sync SQLAlchemy Session
        ↓
def endpoint

Async SQLAlchemy AsyncSession
        ↓
async def endpoint

Do not mix sync and async database access casually.

---

# 17. 🔄 BACKGROUND WORK

Use background processing when the user does not need
to wait for the result.

Examples:

- fact extraction
- embedding generation
- vector indexing
- document processing
- analytics
- evaluation

Use FastAPI `BackgroundTasks` for lightweight,
non-critical background work.

Use a task queue such as Celery when the task requires:

- durability
- retries
- scheduling
- distributed workers
- long execution
- monitoring

Do NOT treat `BackgroundTasks` as a durable job queue.

---

# 18. 🚨 ERROR HANDLING

## 18.1 Business Exceptions

Business logic SHOULD raise domain/application exceptions.

Example:

class MemoryNotFoundError(Exception):
    ...

Do NOT couple domain/service layers directly to HTTP.

Preferred:

Service
  ↓
Business Exception
  ↓
API Exception Handler
  ↓
HTTP Response

---

## 18.2 HTTP Exceptions

HTTP-specific errors belong at the API boundary.

Examples:

400 → Invalid request
401 → Authentication failure
403 → Authorization failure
404 → Resource not found

---

## 18.3 No Silent Failures

Never use:

except Exception:
    pass

or:

except Exception:
    return None

when the exception represents an unexpected failure.

At system boundaries, catch-all handling MAY be used if it:

1. logs the traceback
2. preserves failure visibility
3. re-raises or converts to an explicit error state

Preferred:

try:
    ...
except Exception:
    logger.exception("Unexpected error")
    raise

---

# 19. 📝 LOGGING

Use Python's standard `logging` module.

Do NOT use:

print(...)

for application logging.

Preferred:

logger = logging.getLogger(__name__)

logger.info("Memory extraction started")
logger.warning("Vector search returned no results")
logger.exception("Memory extraction failed")

Logs SHOULD contain enough context to diagnose failures.

Never log:

- API keys
- passwords
- access tokens
- secrets
- sensitive user data unnecessarily

---

# 20. 🔐 SECURITY

The Agent MUST NOT hardcode:

- API keys
- passwords
- tokens
- private credentials
- production secrets

Use environment variables and configuration management.

Never commit `.env` files containing real credentials.

Use:

Path(...)

instead of hardcoded absolute filesystem paths.

---

# 21. 🧪 TESTING

Every meaningful code change MUST have appropriate verification.

## 21.1 Unit Tests

Unit tests MUST be isolated.

Do NOT call:

- real databases
- real LLM APIs
- real external APIs
- real vector databases

Mock or fake external dependencies.

---

## 21.2 Arrange / Act / Assert

Tests SHOULD follow:

Arrange
  ↓
Act
  ↓
Assert

Example:

def test_memory_retrieval() -> None:
    # Arrange
    ...

    # Act
    ...

    # Assert
    ...

---

## 21.3 Edge Cases

Important failure paths SHOULD be tested.

Examples:

- invalid LLM JSON
- LLM timeout
- vector database timeout
- empty retrieval result
- missing memory
- unauthorized access
- invalid request
- database failure

---

# 22. 🔍 STATIC ANALYSIS

The project SHOULD use:

- ruff
- pytest
- mypy or pyright

The Agent SHOULD run relevant checks after implementation.

Typical verification:

ruff check .
pytest

When configured:

mypy .

or:

pyright

# 23. 🧪 TEST-DRIVEN VERIFICATION

After modifying code, the Agent MUST verify the implementation.

The Agent MUST NOT claim:

"Done"

without evidence when tests are expected to be runnable.

The final report SHOULD include actual results.

Example:

Tests:
✓ pytest

Static Analysis:
✓ ruff

Result:
42 passed

If tests cannot be executed, explicitly state:

Tests not run because: <reason></reason>

Never pretend tests passed.

---

# 24. 🔎 LOG INSPECTION

When debugging an error:

Error
 ↓
Read actual traceback/log
 ↓
Identify root cause
 ↓
Implement fix
 ↓
Run regression test

The Agent MUST NOT diagnose runtime failures based purely
on assumptions.

Do NOT hide errors using:

try:
    ...
except:
    pass

---

# 25. 🧱 INCREMENTAL IMPLEMENTATION

Large tasks MUST be divided into small verifiable slices.

Preferred:

Walking Skeleton
      ↓
Test
      ↓
Extend
      ↓
Test
      ↓
Refine
      ↓
Test

Avoid implementing a large feature across many layers
before testing anything.

---

# 26. 🌿 GIT RULES

## Branches

Do NOT push directly to:

main

Use:

feature/*
fix/*
refactor/*
eval/*
chore/*
docs/*
test/*

---

## Conventional Commits

Use:

feat:
fix:
docs:
refactor:
eval:
chore:
test:

Examples:

feat: add semantic memory retrieval

fix: handle malformed memory extraction response

refactor: extract memory store interface

eval: add retrieval benchmark

chore: update docker configuration

---

# 27. 🛡️ GIT SAFETY

The Agent MUST NOT perform destructive Git operations
without explicit user approval.

Examples:

git reset --hard
git push --force
git branch -D

The Agent MUST NOT:

- overwrite user changes
- amend user commits without approval
- delete unrelated branches
- discard uncommitted work
- force push

The Agent MAY create a commit only when explicitly requested
or when repository automation explicitly requires it.

---

# 28. 📐 DATABASE QUERY QUALITY

The Agent MUST consider:

- N+1 queries
- unnecessary joins
- unnecessary database round trips
- missing indexes
- transaction boundaries
- pagination
- query selectivity

Before implementing database access, ask:

Does this query scale?
Could this cause N+1?
Can multiple operations be combined?
Is the correct index available?

---

# 29. 🧠 PRE-IMPLEMENTATION ENGINEERING CHECKLIST

Before implementing a non-trivial feature, verify:

## Blocking I/O

- Does this introduce blocking I/O?
- Is there a native async API?
- If not, should it use a threadpool?
- Should the operation become a background job?

## Failure Modes

- What can fail?
- What happens if the LLM times out?
- What happens if the database fails?
- What happens if the vector store fails?
- Is the error logged?
- Is the failure visible to the caller?

## Database

- Is the query SQLAlchemy 2.0 style?
- Is there an N+1 problem?
- Is the transaction boundary correct?
- Are unnecessary commits avoided?
- Is an index required?

## Architecture

- Does the change violate dependency direction?
- Should an interface be introduced?
- Is the abstraction actually necessary?
- Is this change within the requested scope?

---

# 30. 📊 DEFINITION OF DONE

A task is considered complete only when applicable items are satisfied.

- [ ] Requirement is understood.
- [ ] Ambiguities affecting architecture or behavior are resolved.
- [ ] Implementation plan was created when required.
- [ ] Approved plan was followed.
- [ ] Changes remain within scope.
- [ ] Type hints are present.
- [ ] Error handling is explicit.
- [ ] No secrets are hardcoded.
- [ ] No silent exception swallowing exists.
- [ ] Relevant unit tests were added or updated.
- [ ] Tests pass.
- [ ] Static analysis passes when configured.
- [ ] Existing behavior has not regressed.
- [ ] Git diff has been reviewed.
- [ ] No unrelated refactoring was introduced.
- [ ] Final response reports actual verification results.

---

# 31. 📢 FINAL AGENT RESPONSE

After completing a task, the Agent SHOULD report:

## Summary

What changed.

## Files Changed

- file.py
- test_file.py

## Design Decisions

Important architectural decisions.

## Tests

- pytest: PASS
- ruff: PASS
- mypy: PASS

## Known Limitations

Anything not verified or intentionally deferred.

The Agent MUST distinguish between:

Verified

and:

Assumed / Not verified

Never report assumptions as facts.

---

# 32. 🏛️ FINAL PRINCIPLE

The Agent should optimize for:

Correctness
    >
Simplicity
    >
Maintainability
    >
Performance
    >
Speed of implementation

The Agent MUST prefer:

Understand → Plan → Implement → Verify

over:

Guess → Code → Patch → Repeat

The goal is not to write the most code.

The goal is to make the smallest correct,
testable, and maintainable change.
