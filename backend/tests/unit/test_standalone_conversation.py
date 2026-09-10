"""Unit tests for standalone conversation domain ownership (ADR 0011).

Authenticated conversations are owned directly by users with an optional
workspace association. No hidden or default workspace is created. Guest
durable conversation is excluded from this slice.
"""

import pytest

from types import SimpleNamespace

from backend.conversations.models import (
    Conversation,
    ConversationCreate,
    ConversationValidationError,
)
from backend.conversations.service import (
    ConversationService,
    WorkspaceNotFoundError,
)
from backend.workspaces.models import RetentionState

OWNER = "user_owner"
OTHER_OWNER = "user_other"
OWNED_WORKSPACE = "tw_owned"
FOREIGN_WORKSPACE = "tw_foreign"
HIDDEN_WORKSPACE = "tw_hidden"

EXPECTED_WORKSPACE_NOT_FOUND = "The parent workspace does not exist."


class FakeWorkspaceRepository:
    def __init__(self):
        self._workspaces = {
            OWNED_WORKSPACE: SimpleNamespace(
                workspace_id=OWNED_WORKSPACE,
                owner_user_id=OWNER,
                retention_state=RetentionState.ACTIVE,
            ),
            FOREIGN_WORKSPACE: SimpleNamespace(
                workspace_id=FOREIGN_WORKSPACE,
                owner_user_id=OTHER_OWNER,
                retention_state=RetentionState.ACTIVE,
            ),
            HIDDEN_WORKSPACE: SimpleNamespace(
                workspace_id=HIDDEN_WORKSPACE,
                owner_user_id=OWNER,
                retention_state=RetentionState.DELETION_REQUESTED,
            ),
        }
        self.calls = []

    def get(self, workspace_id):
        self.calls.append(("get", workspace_id))
        return self._workspaces.get(workspace_id)


class FakeConversationRepository:
    def __init__(self):
        self.conversations = {}
        self.calls = []

    def create(self, conversation):
        self.calls.append(("create", conversation.conversation_id))
        self.conversations[conversation.conversation_id] = conversation
        return conversation

    def get(self, conversation_id):
        self.calls.append(("get", conversation_id))
        return self.conversations.get(conversation_id)

    def list_by_workspace(self, workspace_id, include_deletion=False):
        self.calls.append(("list_by_workspace", workspace_id))
        return tuple(
            c for c in self.conversations.values() if c.workspace_id == workspace_id
        )

    def list_by_owner(self, owner_user_id, include_deletion=False):
        self.calls.append(("list_by_owner", owner_user_id))
        return tuple(
            c for c in self.conversations.values() if c.owner_user_id == owner_user_id
        )


@pytest.fixture
def workspaces():
    return FakeWorkspaceRepository()


@pytest.fixture
def repository():
    return FakeConversationRepository()


@pytest.fixture
def service(repository, workspaces):
    return ConversationService(
        conversation_repository=repository, workspace_repository=workspaces
    )


# 1. Owner is required; workspace is optional.


def test_create_requires_owner_user_id():
    with pytest.raises((ConversationValidationError, TypeError)):
        ConversationCreate(workspace_id=None)


@pytest.mark.parametrize("value", ["", "   ", None, 7])
def test_create_rejects_blank_owner(value):
    with pytest.raises((ConversationValidationError, TypeError)):
        ConversationCreate(owner_user_id=value, workspace_id=None)


def test_create_allows_standalone_without_workspace(service, repository):
    conversation = service.create_conversation(
        ConversationCreate(owner_user_id=OWNER, workspace_id=None)
    )

    assert isinstance(conversation, Conversation)
    assert conversation.owner_user_id == OWNER
    assert conversation.workspace_id is None
    assert repository.conversations[conversation.conversation_id] == conversation


def test_standalone_create_creates_no_hidden_workspace(service, workspaces):
    service.create_conversation(
        ConversationCreate(owner_user_id=OWNER, workspace_id=None, title="Solo trip")
    )

    # No workspace lookup or creation for a standalone conversation: the
    # workspace association stays absent rather than inventing a parent.
    assert workspaces.calls == []


# 2. Valid workspace compatibility: matching owner + workspace succeeds.


def test_create_with_valid_workspace_and_matching_owner_succeeds(service):
    conversation = service.create_conversation(
        ConversationCreate(owner_user_id=OWNER, workspace_id=OWNED_WORKSPACE)
    )

    assert conversation.owner_user_id == OWNER
    assert conversation.workspace_id == OWNED_WORKSPACE


# 3. Owner/workspace mismatch is rejected without disclosing content.


def test_create_with_mismatched_owner_and_workspace_is_rejected(service, repository):
    with pytest.raises(WorkspaceNotFoundError) as excinfo:
        service.create_conversation(
            ConversationCreate(owner_user_id=OTHER_OWNER, workspace_id=OWNED_WORKSPACE)
        )

    assert str(excinfo.value) == EXPECTED_WORKSPACE_NOT_FOUND
    assert repository.conversations == {}


def test_create_with_missing_workspace_is_rejected(service, repository):
    with pytest.raises(WorkspaceNotFoundError) as excinfo:
        service.create_conversation(
            ConversationCreate(owner_user_id=OWNER, workspace_id="tw_missing")
        )

    assert str(excinfo.value) == EXPECTED_WORKSPACE_NOT_FOUND
    assert repository.conversations == {}


def test_create_with_deletion_hidden_workspace_is_rejected(service, repository):
    with pytest.raises(WorkspaceNotFoundError) as excinfo:
        service.create_conversation(
            ConversationCreate(owner_user_id=OWNER, workspace_id=HIDDEN_WORKSPACE)
        )

    assert str(excinfo.value) == EXPECTED_WORKSPACE_NOT_FOUND
    assert repository.conversations == {}


def test_workspace_rejections_are_indistinguishable(service, repository):
    """Missing, foreign, and deletion-hidden workspaces fail identically.

    HTTP status/body parity for these cases belongs to the later API child;
    this slice pins only the service-layer exception class and message.
    """
    observed = []
    for owner_user_id, workspace_id in (
        (OWNER, "tw_missing"),
        (OTHER_OWNER, OWNED_WORKSPACE),
        (OWNER, HIDDEN_WORKSPACE),
    ):
        with pytest.raises(WorkspaceNotFoundError) as excinfo:
            service.create_conversation(
                ConversationCreate(
                    owner_user_id=owner_user_id, workspace_id=workspace_id
                )
            )
        observed.append(str(excinfo.value))

    assert observed[0] == EXPECTED_WORKSPACE_NOT_FOUND
    assert observed[1] == observed[0]
    assert observed[2] == observed[0]
    assert repository.conversations == {}


# 4. Owned list/get behavior isolates owners.


def test_owned_list_returns_only_owned_conversations(service):
    solo = service.create_conversation(
        ConversationCreate(owner_user_id=OWNER, workspace_id=None)
    )
    bound = service.create_conversation(
        ConversationCreate(owner_user_id=OWNER, workspace_id=OWNED_WORKSPACE)
    )
    foreign = service.create_conversation(
        ConversationCreate(owner_user_id=OTHER_OWNER, workspace_id=FOREIGN_WORKSPACE)
    )

    listed = service.list_conversations_by_owner(OWNER)

    assert solo in listed
    assert bound in listed
    assert foreign not in listed
    assert isinstance(listed, tuple)


def test_owned_get_returns_owned_and_hides_foreign(service):
    owned = service.create_conversation(
        ConversationCreate(owner_user_id=OWNER, workspace_id=None)
    )
    foreign = service.create_conversation(
        ConversationCreate(owner_user_id=OTHER_OWNER, workspace_id=FOREIGN_WORKSPACE)
    )

    assert service.get_conversation_for_owner(owned.conversation_id, OWNER) == owned
    assert service.get_conversation_for_owner(foreign.conversation_id, OWNER) is None
    assert service.get_conversation_for_owner("cv_missing", OWNER) is None
