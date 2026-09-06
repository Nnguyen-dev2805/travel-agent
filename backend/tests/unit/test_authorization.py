"""Unit tests for R9 owner/workspace authorization helpers.

Helpers decide from resolved owner labels and the principal only: missing
and foreign resources are identical denials so errors never leak
existence across owners. No test touches a database, a provider, or the
network.
"""

import pytest

from backend.security.authorization import (
    CrossOwnerAccessError,
    OwnerForbiddenError,
    require_create_owner,
    require_workspace_owner,
    resolve_workspace_owner_id,
    scope_list_owner,
)
from backend.security.models import AuthMode, AuthenticatedPrincipal


class StubWorkspaces:
    def __init__(self, owners):
        self._owners = dict(owners)

    def get(self, workspace_id):
        from types import SimpleNamespace

        owner = self._owners.get(workspace_id)
        if owner is None:
            return None
        return SimpleNamespace(workspace_id=workspace_id, owner_user_id=owner)


def _principal(owner="owner_a", mode=AuthMode.AUTHENTICATED):
    return AuthenticatedPrincipal(
        owner_user_id=owner,
        auth_mode=mode,
        credential_label="local_token",
    )


def _compat():
    return AuthenticatedPrincipal(
        owner_user_id="local-developer",
        auth_mode=AuthMode.COMPATIBILITY,
        credential_label="none",
    )


def test_resolve_owner_returns_label_or_denies_missing():
    repos = StubWorkspaces({"tw_a": "owner_a"})

    assert resolve_workspace_owner_id("tw_a", repos) == "owner_a"
    with pytest.raises(CrossOwnerAccessError):
        resolve_workspace_owner_id("tw_missing", repos)


def test_same_owner_allowed_and_mismatch_denied():
    repos = StubWorkspaces({"tw_a": "owner_a", "tw_b": "owner_b"})

    assert require_workspace_owner("tw_a", repos, _principal("owner_a")) == "owner_a"
    with pytest.raises(CrossOwnerAccessError):
        require_workspace_owner("tw_b", repos, _principal("owner_a"))
    with pytest.raises(CrossOwnerAccessError):
        require_workspace_owner("tw_missing", repos, _principal("owner_a"))


def test_compat_mode_preserves_current_behavior():
    repos = StubWorkspaces({"tw_b": "owner_b"})

    # Compatibility performs no repository read: a missing id passes
    # through untouched so existing validation and services stay the
    # single source for those paths.
    assert require_workspace_owner("tw_b", repos, _compat()) == ""
    assert require_workspace_owner("tw_missing", repos, _compat()) == ""
    require_create_owner("anyone", _compat())
    assert scope_list_owner("anyone", _compat()) == "anyone"


def test_create_with_mismatched_body_owner_forbidden():
    require_create_owner("owner_a", _principal("owner_a"))
    with pytest.raises(OwnerForbiddenError):
        require_create_owner("owner_b", _principal("owner_a"))


def test_list_scoping_filters_or_rejects():
    assert scope_list_owner("owner_a", _principal("owner_a")) == "owner_a"
    # A missing query label still scopes to the principal, never to everyone.
    assert scope_list_owner("", _principal("owner_a")) == "owner_a"
    with pytest.raises(OwnerForbiddenError):
        scope_list_owner("owner_b", _principal("owner_a"))
