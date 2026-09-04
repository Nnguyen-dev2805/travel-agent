"""Unit tests for the local SQLite conversation repository adapter.

Per ADR 0004 this adapter and the workspace adapter share one local database
file and record independent schema versions in the registry. Per ADR 0003 SQLite
remains a local development adapter, not production storage.

Every test uses a `tmp_path` database file, so no test reads or writes the
developer database at `APP_DB_PATH`. Fixture text is synthetic Vietnamese and
English travel content and carries no secret.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.conversations.models import (
    Conversation,
    ConversationRetentionState,
    Message,
    MessageDraft,
    MessageRole,
    MessageSource,
    TraceVisibility,
    generate_conversation_id,
    generate_message_id,
)
from backend.conversations.repository import (
    ConversationAlreadyExistsError,
    ConversationStorageError,
    MessageAlreadyExistsError,
    MessageSequenceConflictError,
)
from backend.conversations.sqlite_repository import (
    SCHEMA_MODULE,
    SCHEMA_VERSION,
    SQLiteConversationRepository,
)
from backend.storage.schema_registry import SENTINEL_USER_VERSION

WORKSPACE = "tw_example"
OTHER_WORKSPACE = "tw_other"
MOMENT = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "nested" / "travel_agent.sqlite3"


@pytest.fixture
def repository(db_path: Path) -> SQLiteConversationRepository:
    return SQLiteConversationRepository(db_path=db_path)


def _conversation(**overrides) -> Conversation:
    payload = {
        "conversation_id": generate_conversation_id(),
        "workspace_id": WORKSPACE,
        "title": "Da Nang food plan",
        "created_at": MOMENT,
        "updated_at": MOMENT,
    }
    payload.update(overrides)
    return Conversation(**payload)


def _draft(conversation_id: str, **overrides) -> MessageDraft:
    payload = {
        "conversation_id": conversation_id,
        "role": MessageRole.USER,
        "content": "Nên đi Đà Nẵng vào tháng mấy?",
        "created_at": MOMENT,
    }
    payload.update(overrides)
    return MessageDraft(**payload)


def _append(
    repository: SQLiteConversationRepository, conversation_id: str, **overrides
) -> Message:
    message_id = overrides.pop("message_id", None) or generate_message_id()
    return repository.append_message(_draft(conversation_id, **overrides), message_id)


def _stored_updated_at(db_path: Path, conversation_id: str) -> str:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            "SELECT updated_at FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()[0]


def _schema_objects(db_path: Path, kind: str) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = ?", (kind,)
        ).fetchall()
    return {row[0] for row in rows}


# 1. Initialization registers the module version and creates the schema.


def test_initialization_registers_the_module_version_and_schema(
    repository, db_path: Path
):
    with sqlite3.connect(db_path) as connection:
        recorded = connection.execute(
            "SELECT version FROM schema_versions WHERE module = ?", (SCHEMA_MODULE,)
        ).fetchone()
        marker = connection.execute("PRAGMA user_version").fetchone()[0]

    assert SCHEMA_MODULE == "conversations"
    assert SCHEMA_VERSION == 1
    assert recorded is not None and recorded[0] == SCHEMA_VERSION
    assert marker == SENTINEL_USER_VERSION
    assert {"conversations", "messages"} <= _schema_objects(db_path, "table")
    assert {
        "idx_conversations_workspace",
        "idx_messages_conversation",
    } <= _schema_objects(db_path, "index")


def test_initialization_creates_the_parent_directory(db_path: Path):
    assert not db_path.parent.exists()
    SQLiteConversationRepository(db_path=db_path)
    assert db_path.exists()


def test_initialization_is_idempotent(db_path: Path):
    first = SQLiteConversationRepository(db_path=db_path)
    stored = first.create(_conversation())
    second = SQLiteConversationRepository(db_path=db_path)
    assert second.get(stored.conversation_id) == stored


# 2. Two modules coexist in one file without version contention.


def test_workspace_and_conversation_modules_share_one_database_file(db_path: Path):
    from backend.workspaces.sqlite_repository import (
        SCHEMA_MODULE as WORKSPACE_MODULE,
        SCHEMA_VERSION as WORKSPACE_VERSION,
        SQLiteWorkspaceRepository,
    )

    SQLiteWorkspaceRepository(db_path=db_path)
    conversations = SQLiteConversationRepository(db_path=db_path)
    stored = conversations.create(_conversation())

    with sqlite3.connect(db_path) as connection:
        rows = dict(
            connection.execute("SELECT module, version FROM schema_versions").fetchall()
        )
        tables = _schema_objects(db_path, "table")

    assert rows == {WORKSPACE_MODULE: WORKSPACE_VERSION, SCHEMA_MODULE: SCHEMA_VERSION}
    assert {"trip_workspaces", "conversations", "messages"} <= tables
    assert conversations.get(stored.conversation_id) == stored


def test_each_module_reads_only_its_own_registry_row(db_path: Path):
    from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

    SQLiteWorkspaceRepository(db_path=db_path)
    SQLiteConversationRepository(db_path=db_path)

    with sqlite3.connect(db_path) as connection:
        conversation_version = connection.execute(
            "SELECT version FROM schema_versions WHERE module = ?", ("conversations",)
        ).fetchone()[0]
        workspace_version = connection.execute(
            "SELECT version FROM schema_versions WHERE module = ?", ("workspaces",)
        ).fetchone()[0]

    assert conversation_version == SCHEMA_VERSION
    assert workspace_version == 1


# 3, 4 and 19. Create, read, and durability across instances.


def test_create_persists_and_returns_the_stored_record(repository):
    conversation = _conversation()
    stored = repository.create(conversation)
    assert stored == conversation
    assert repository.get(conversation.conversation_id) == conversation


def test_create_persists_an_absent_title(repository):
    conversation = _conversation(title=None)
    repository.create(conversation)
    loaded = repository.get(conversation.conversation_id)
    assert loaded is not None and loaded.title is None


def test_create_rejects_a_duplicate_identity_without_overwriting(repository):
    original = _conversation(title="Original")
    repository.create(original)
    clash = _conversation(conversation_id=original.conversation_id, title="Replacement")

    with pytest.raises(ConversationAlreadyExistsError):
        repository.create(clash)

    loaded = repository.get(original.conversation_id)
    assert loaded is not None and loaded.title == "Original"


def test_get_returns_none_when_absent(repository):
    assert repository.get("cv_does_not_exist") is None


def test_records_persist_across_repository_instances(db_path: Path):
    first = SQLiteConversationRepository(db_path=db_path)
    conversation = first.create(_conversation())
    message = _append(first, conversation.conversation_id)

    second = SQLiteConversationRepository(db_path=db_path)
    assert second.get(conversation.conversation_id) == conversation
    assert second.list_messages(conversation.conversation_id, None, 50) == (message,)


def test_timestamps_survive_the_round_trip_as_utc(repository):
    offset = timezone(timedelta(hours=7))
    local = datetime(2026, 9, 4, 19, 0, 0, tzinfo=offset)
    conversation = _conversation(created_at=local, updated_at=local)
    repository.create(conversation)

    loaded = repository.get(conversation.conversation_id)
    assert loaded is not None
    assert loaded.created_at == local
    assert loaded.created_at.utcoffset() == timedelta(0)


# 5, 6 and 7. Listing is workspace-scoped, deterministically ordered, and filtered.


def test_list_by_workspace_excludes_other_workspaces(repository):
    repository.create(_conversation(title="Mine A"))
    repository.create(_conversation(title="Mine B"))
    repository.create(_conversation(workspace_id=OTHER_WORKSPACE, title="Theirs"))

    listed = repository.list_by_workspace(WORKSPACE)
    assert {record.title for record in listed} == {"Mine A", "Mine B"}


def test_list_by_workspace_returns_an_empty_tuple_when_none_match(repository):
    repository.create(_conversation())
    listed = repository.list_by_workspace("tw_nobody")
    assert listed == ()
    assert isinstance(listed, tuple)


def test_list_orders_by_updated_at_then_created_at_then_id(repository):
    base = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
    newest = _conversation(
        title="Newest updated", created_at=base, updated_at=base + timedelta(days=2)
    )
    tie_created_later = _conversation(
        title="Tie created later",
        created_at=base + timedelta(days=1),
        updated_at=base + timedelta(days=1),
    )
    tie_created_earlier = _conversation(
        title="Tie created earlier",
        created_at=base,
        updated_at=base + timedelta(days=1),
    )
    for record in (tie_created_earlier, newest, tie_created_later):
        repository.create(record)

    listed = repository.list_by_workspace(WORKSPACE)
    assert [record.title for record in listed] == [
        "Newest updated",
        "Tie created later",
        "Tie created earlier",
    ]


def test_list_breaks_a_full_tie_by_conversation_id_ascending(repository):
    low = _conversation(conversation_id="cv_aaaa0000", title="Low id")
    high = _conversation(conversation_id="cv_zzzz9999", title="High id")
    repository.create(high)
    repository.create(low)

    listed = repository.list_by_workspace(WORKSPACE)
    assert [record.conversation_id for record in listed] == [
        "cv_aaaa0000",
        "cv_zzzz9999",
    ]


def test_list_excludes_deleted_records(repository):
    active = _conversation(title="Active")
    deleted = _conversation(
        title="Deleted", retention_state=ConversationRetentionState.DELETED
    )
    repository.create(active)
    repository.create(deleted)

    listed = repository.list_by_workspace(WORKSPACE)
    assert [record.title for record in listed] == ["Active"]
    assert repository.get(deleted.conversation_id) is not None


def test_list_includes_every_non_deleted_retention_state(repository):
    states = [
        ConversationRetentionState.ACTIVE,
        ConversationRetentionState.SUMMARIZED,
        ConversationRetentionState.ARCHIVED,
        ConversationRetentionState.DELETION_REQUESTED,
    ]
    for index, state in enumerate(states):
        repository.create(_conversation(title=f"State {index}", retention_state=state))

    listed = repository.list_by_workspace(WORKSPACE)
    assert len(listed) == len(states)


# 8 and 9. Sequence allocation starts at 1 and is per conversation.


def test_append_assigns_sequence_one_then_increments(repository):
    conversation = repository.create(_conversation())

    first = _append(repository, conversation.conversation_id, content="một")
    second = _append(repository, conversation.conversation_id, content="hai")
    third = _append(repository, conversation.conversation_id, content="ba")

    assert [first.sequence, second.sequence, third.sequence] == [1, 2, 3]
    assert first.message_id.startswith("ms_")


def test_sequences_increment_independently_per_conversation(repository):
    first_conversation = repository.create(_conversation(title="First"))
    second_conversation = repository.create(_conversation(title="Second"))

    a1 = _append(repository, first_conversation.conversation_id, content="a1")
    b1 = _append(repository, second_conversation.conversation_id, content="b1")
    a2 = _append(repository, first_conversation.conversation_id, content="a2")

    assert (a1.sequence, b1.sequence, a2.sequence) == (1, 1, 2)


def test_append_persists_governed_vocabulary_values(repository):
    conversation = repository.create(_conversation())

    stored = _append(
        repository,
        conversation.conversation_id,
        role=MessageRole.ASSISTANT,
        source=MessageSource.MODEL,
        trace_visibility=TraceVisibility.INCLUDED,
    )

    loaded = repository.list_messages(conversation.conversation_id, None, 50)[0]
    assert loaded == stored
    assert loaded.role is MessageRole.ASSISTANT
    assert loaded.source is MessageSource.MODEL
    assert loaded.trace_visibility is TraceVisibility.INCLUDED


# 10, 11 and 12. The append write is one transaction.


def test_append_advances_the_parent_updated_at(repository, db_path: Path):
    conversation = repository.create(_conversation())
    before = _stored_updated_at(db_path, conversation.conversation_id)

    later = MOMENT + timedelta(minutes=5)
    _append(repository, conversation.conversation_id, created_at=later)

    after = _stored_updated_at(db_path, conversation.conversation_id)
    assert after != before
    reloaded = repository.get(conversation.conversation_id)
    assert reloaded is not None and reloaded.updated_at == later


def test_failed_message_insert_leaves_the_parent_updated_at_unchanged(
    repository, db_path: Path
):
    """Proves the bump and the insert share one transaction.

    The adapter bumps the parent before inserting the message, so a failing
    insert must roll the bump back. A duplicate `message_id` is used to force
    the failure because it violates the message primary key.
    """
    conversation = repository.create(_conversation())
    existing = _append(repository, conversation.conversation_id, content="một")
    before = _stored_updated_at(db_path, conversation.conversation_id)

    with pytest.raises(MessageAlreadyExistsError):
        _append(
            repository,
            conversation.conversation_id,
            content="hai",
            created_at=MOMENT + timedelta(hours=1),
            message_id=existing.message_id,
        )

    assert _stored_updated_at(db_path, conversation.conversation_id) == before
    assert len(repository.list_messages(conversation.conversation_id, None, 50)) == 1


def test_duplicate_sequence_raises_a_conflict_instead_of_overwriting(
    repository, monkeypatch: pytest.MonkeyPatch
):
    """The `UNIQUE (conversation_id, sequence)` constraint is defense in depth.

    Allocation runs inside `BEGIN IMMEDIATE`, so a duplicate cannot arise from
    this adapter alone. Pinning the allocation simulates the future concurrent
    writer the constraint exists to stop.
    """
    conversation = repository.create(_conversation())
    _append(repository, conversation.conversation_id, content="một")

    monkeypatch.setattr(
        SQLiteConversationRepository,
        "_allocate_next_sequence",
        lambda self, connection, conversation_id: 1,
    )

    with pytest.raises(MessageSequenceConflictError):
        _append(repository, conversation.conversation_id, content="trùng vị trí")

    remaining = repository.list_messages(conversation.conversation_id, None, 50)
    assert [message.content for message in remaining] == ["một"]


# 13, 14, 15 and 16. History reads are ordered, paged, and conversation-scoped.


def test_list_messages_orders_by_sequence_ascending(repository):
    conversation = repository.create(_conversation())
    for content in ("một", "hai", "ba"):
        _append(repository, conversation.conversation_id, content=content)

    page = repository.list_messages(conversation.conversation_id, None, 50)
    assert [message.content for message in page] == ["một", "hai", "ba"]
    assert [message.sequence for message in page] == [1, 2, 3]


def test_list_messages_returns_only_rows_after_the_cursor(repository):
    conversation = repository.create(_conversation())
    for content in ("một", "hai", "ba"):
        _append(repository, conversation.conversation_id, content=content)

    page = repository.list_messages(conversation.conversation_id, 1, 50)
    assert [message.content for message in page] == ["hai", "ba"]


def test_list_messages_respects_the_limit_and_the_rest_stays_reachable(repository):
    conversation = repository.create(_conversation())
    for content in ("một", "hai", "ba", "bốn"):
        _append(repository, conversation.conversation_id, content=content)

    first_page = repository.list_messages(conversation.conversation_id, None, 2)
    assert [message.content for message in first_page] == ["một", "hai"]

    second_page = repository.list_messages(
        conversation.conversation_id, first_page[-1].sequence, 2
    )
    assert [message.content for message in second_page] == ["ba", "bốn"]

    third_page = repository.list_messages(
        conversation.conversation_id, second_page[-1].sequence, 2
    )
    assert third_page == ()


def test_list_messages_is_scoped_so_a_foreign_position_cannot_leak_rows(repository):
    """A cursor resolved from another conversation cannot widen the result set."""
    mine = repository.create(_conversation(title="Mine"))
    theirs = repository.create(_conversation(title="Theirs"))
    _append(repository, mine.conversation_id, content="của tôi")
    foreign = _append(repository, theirs.conversation_id, content="của họ")

    page = repository.list_messages(mine.conversation_id, None, 50)
    assert [message.content for message in page] == ["của tôi"]

    after_foreign_position = repository.list_messages(
        mine.conversation_id, foreign.sequence, 50
    )
    assert after_foreign_position == ()


def test_get_message_exposes_the_owning_conversation_for_cursor_validation(repository):
    mine = repository.create(_conversation(title="Mine"))
    theirs = repository.create(_conversation(title="Theirs"))
    foreign = _append(repository, theirs.conversation_id, content="của họ")

    loaded = repository.get_message(foreign.message_id)
    assert loaded is not None
    assert loaded.conversation_id == theirs.conversation_id
    assert loaded.conversation_id != mine.conversation_id
    assert repository.get_message("ms_absent") is None


def test_list_messages_returns_an_empty_tuple_for_a_conversation_with_no_messages(
    repository,
):
    conversation = repository.create(_conversation())
    assert repository.list_messages(conversation.conversation_id, None, 50) == ()


# 17 and 18. Stored values outside the contract fail closed.


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("role", "moderator"),
        ("source", "browser"),
        ("trace_visibility", "hidden"),
    ],
)
def test_stored_message_vocabulary_outside_the_contract_fails_closed(
    repository, db_path: Path, column: str, value: str
):
    conversation = repository.create(_conversation())
    message = _append(repository, conversation.conversation_id)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            f"UPDATE messages SET {column} = ? WHERE message_id = ?",
            (value, message.message_id),
        )

    with pytest.raises(ConversationStorageError):
        repository.list_messages(conversation.conversation_id, None, 50)


def test_stored_retention_state_outside_the_contract_fails_closed(
    repository, db_path: Path
):
    conversation = repository.create(_conversation())

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE conversations SET retention_state = ? WHERE conversation_id = ?",
            ("purged", conversation.conversation_id),
        )

    with pytest.raises(ConversationStorageError):
        repository.get(conversation.conversation_id)

    with pytest.raises(ConversationStorageError):
        repository.list_by_workspace(WORKSPACE)


@pytest.mark.parametrize("value", ["never", "2026-09-04T12:00:00"])
def test_stored_timestamp_that_is_invalid_or_naive_fails_closed(
    repository, db_path: Path, value: str
):
    conversation = repository.create(_conversation())
    message = _append(repository, conversation.conversation_id)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE conversations SET created_at = ? WHERE conversation_id = ?",
            (value, conversation.conversation_id),
        )
        connection.execute(
            "UPDATE messages SET created_at = ? WHERE message_id = ?",
            (value, message.message_id),
        )

    with pytest.raises(ConversationStorageError):
        repository.get(conversation.conversation_id)

    with pytest.raises(ConversationStorageError):
        repository.list_messages(conversation.conversation_id, None, 50)


def test_storage_error_messages_expose_no_path_sql_or_content(
    repository, db_path: Path
):
    conversation = repository.create(_conversation())
    secret_content = "Nội dung riêng tư của người dùng"
    message = _append(repository, conversation.conversation_id, content=secret_content)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE messages SET role = ? WHERE message_id = ?",
            ("moderator", message.message_id),
        )

    with pytest.raises(ConversationStorageError) as caught:
        repository.list_messages(conversation.conversation_id, None, 50)

    detail = str(caught.value)
    assert str(db_path) not in detail
    assert db_path.name not in detail
    assert secret_content not in detail
    assert "SELECT" not in detail
    assert "CREATE TABLE" not in detail


# 20. No test touches the developer's configured database path.


def test_repository_writes_only_under_the_supplied_path(db_path: Path, tmp_path: Path):
    repository = SQLiteConversationRepository(db_path=db_path)
    conversation = repository.create(_conversation())
    _append(repository, conversation.conversation_id)

    assert db_path.is_relative_to(tmp_path)
    written = {path for path in tmp_path.rglob("*") if path.is_file()}
    assert all(path.name.startswith(db_path.name) for path in written), (
        f"unexpected files written under the temporary root: {written}"
    )


def test_repository_ignores_the_configured_default_path(db_path: Path):
    from backend.app.config import settings

    repository = SQLiteConversationRepository(db_path=db_path)
    stored = repository.create(_conversation())

    assert repository.get(stored.conversation_id) == stored
    assert db_path != settings.APP_DB_PATH
