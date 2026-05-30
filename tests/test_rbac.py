"""
Tests for RBAC (Role-Based Access Control) system.
"""

import pytest


class TestRoles:
    """Test role definitions and hierarchy."""

    def test_role_enum_values(self):
        """All expected roles exist."""
        from app.core.security.rbac import Role
        assert Role.ADMIN == "admin"
        assert Role.ANALYST == "analyst"
        assert Role.VIEWER == "viewer"
        assert Role.AUDITOR == "auditor"

    def test_clearance_level_enum(self):
        """Clearance levels are defined."""
        from app.core.security.rbac import ClearanceLevel
        assert hasattr(ClearanceLevel, "PUBLIC")
        assert hasattr(ClearanceLevel, "INTERNAL")
        assert hasattr(ClearanceLevel, "CONFIDENTIAL")
        assert hasattr(ClearanceLevel, "SECRET")


class TestAccessContext:
    """Test AccessContext model."""

    def test_access_context_creation(self):
        """AccessContext is created with valid parameters."""
        from app.core.security.rbac import AccessContext, ClearanceLevel, Role
        ctx = AccessContext(
            user_id="u1",
            role=Role.ANALYST,
            department="legal",
            clearance=ClearanceLevel.SECRET,
        )
        assert ctx.user_id == "u1"
        assert ctx.role == Role.ANALYST
        assert ctx.department == "legal"

    def test_access_context_admin(self):
        """Admin context has highest privileges."""
        from app.core.security.rbac import AccessContext, ClearanceLevel, Role
        ctx = AccessContext(
            user_id="admin-1",
            role=Role.ADMIN,
            department="legal",
            clearance=ClearanceLevel.SECRET,
        )
        assert ctx.role == Role.ADMIN
        assert ctx.clearance == ClearanceLevel.SECRET


class TestRBACService:
    """Test RBAC service logic."""

    def test_rbac_service_exists(self):
        """RBAC service singleton is importable."""
        from app.core.security.rbac import rbac_service
        assert rbac_service is not None

    def test_build_cypher_filter(self):
        """Cypher filter generation produces valid output."""
        from app.core.security.rbac import (
            AccessContext, ClearanceLevel, Role, rbac_service,
        )
        ctx = AccessContext(
            user_id="u1",
            role=Role.VIEWER,
            department="legal",
            clearance=ClearanceLevel.CONFIDENTIAL,
        )
        if hasattr(rbac_service, "build_cypher_filter"):
            result = rbac_service.build_cypher_filter(ctx)
            assert isinstance(result, str)

    def test_clearance_ordering(self):
        """Clearance levels have a logical ordering."""
        from app.core.security.rbac import ClearanceLevel
        levels = [
            ClearanceLevel.PUBLIC,
            ClearanceLevel.INTERNAL,
            ClearanceLevel.CONFIDENTIAL,
            ClearanceLevel.SECRET,
        ]
        assert len(set(levels)) == 4
        assert ClearanceLevel.PUBLIC < ClearanceLevel.SECRET

    def test_node_access_granted_same_clearance(self):
        """User with CONFIDENTIAL clearance accesses CONFIDENTIAL node."""
        from app.core.security.rbac import (
            AccessContext, ClearanceLevel, NodeAccessPolicy, Role, rbac_service,
        )
        ctx = AccessContext(user_id="u1", role=Role.ANALYST, department="legal", clearance=ClearanceLevel.CONFIDENTIAL)
        policy = NodeAccessPolicy(node_id="n1", required_clearance=ClearanceLevel.CONFIDENTIAL, allowed_departments=["legal"])
        assert rbac_service.check_node_access(ctx, policy) is True

    def test_node_access_denied_clearance(self):
        """User with INTERNAL clearance is DENIED access to SECRET node."""
        from app.core.security.rbac import (
            AccessContext, ClearanceLevel, NodeAccessPolicy, Role, rbac_service,
        )
        ctx = AccessContext(user_id="u2", role=Role.VIEWER, department="hr", clearance=ClearanceLevel.INTERNAL)
        policy = NodeAccessPolicy(node_id="n2", required_clearance=ClearanceLevel.SECRET, allowed_departments=["all"])
        assert rbac_service.check_node_access(ctx, policy) is False

    def test_node_access_denied_department(self):
        """User from HR is DENIED access to LEGAL-only node."""
        from app.core.security.rbac import (
            AccessContext, ClearanceLevel, NodeAccessPolicy, Role, rbac_service,
        )
        ctx = AccessContext(user_id="u3", role=Role.ANALYST, department="hr", clearance=ClearanceLevel.CONFIDENTIAL)
        policy = NodeAccessPolicy(node_id="n3", required_clearance=ClearanceLevel.PUBLIC, allowed_departments=["legal"])
        assert rbac_service.check_node_access(ctx, policy) is False

    def test_node_access_denied_role(self):
        """Viewer is DENIED when only Analyst role is allowed."""
        from app.core.security.rbac import (
            AccessContext, ClearanceLevel, NodeAccessPolicy, Role, rbac_service,
        )
        ctx = AccessContext(user_id="u4", role=Role.VIEWER, department="all", clearance=ClearanceLevel.INTERNAL)
        policy = NodeAccessPolicy(node_id="n4", required_clearance=ClearanceLevel.PUBLIC, allowed_roles=[Role.ANALYST])
        assert rbac_service.check_node_access(ctx, policy) is False

    def test_admin_bypass_all_restrictions(self):
        """Admin bypasses all restrictions regardless of clearance/department."""
        from app.core.security.rbac import (
            AccessContext, ClearanceLevel, NodeAccessPolicy, Role, rbac_service,
        )
        ctx = AccessContext(user_id="admin", role=Role.ADMIN, department="legal", clearance=ClearanceLevel.PUBLIC)
        policy = NodeAccessPolicy(node_id="n5", required_clearance=ClearanceLevel.SECRET, allowed_departments=["finance"], allowed_roles=[])
        assert rbac_service.check_node_access(ctx, policy) is True

    def test_filter_nodes_filters_by_access(self):
        """filter_nodes removes inaccessible nodes."""
        from app.core.security.rbac import (
            AccessContext, ClearanceLevel, NodeAccessPolicy, Role, rbac_service,
        )
        ctx = AccessContext(user_id="u5", role=Role.VIEWER, department="legal", clearance=ClearanceLevel.INTERNAL)
        nodes = [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}]
        policies = {
            "n1": NodeAccessPolicy(node_id="n1", required_clearance=ClearanceLevel.PUBLIC, allowed_departments=["all"]),
            "n2": NodeAccessPolicy(node_id="n2", required_clearance=ClearanceLevel.SECRET, allowed_departments=["all"]),
            "n3": NodeAccessPolicy(node_id="n3", required_clearance=ClearanceLevel.PUBLIC, allowed_departments=["finance"]),
        }
        filtered = rbac_service.filter_nodes(ctx, nodes, policies)
        assert len(filtered) == 1
        assert filtered[0]["id"] == "n1"

    def test_build_cypher_filter_non_admin(self):
        """Cypher filter includes clearance and department constraints for non-admin."""
        from app.core.security.rbac import (
            AccessContext, ClearanceLevel, Role, rbac_service,
        )
        ctx = AccessContext(user_id="u6", role=Role.VIEWER, department="legal", clearance=ClearanceLevel.CONFIDENTIAL)
        result = rbac_service.build_cypher_filter(ctx)
        assert "clearance_level" in result
        assert "department" in result

    def test_build_cypher_filter_admin_empty(self):
        """Admin gets empty filter (no restrictions)."""
        from app.core.security.rbac import (
            AccessContext, ClearanceLevel, Role, rbac_service,
        )
        ctx = AccessContext(user_id="admin", role=Role.ADMIN, department="all", clearance=ClearanceLevel.SECRET)
        result = rbac_service.build_cypher_filter(ctx)
        assert result == ""