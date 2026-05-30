"""Role-Based Access Control (RBAC) for GraphRAG platform.

Implements node-level access control on the knowledge graph.
Users can only access graph nodes that match their role/department/clearance.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.core.logging import logger


class Role(str, Enum):
    """User roles with hierarchical permissions."""

    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"
    AUDITOR = "auditor"


class ClearanceLevel(int, Enum):
    """Security clearance levels (higher = more access)."""

    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    SECRET = 3


class AccessContext(BaseModel):
    """User access context for RBAC checks."""

    user_id: str
    role: Role = Role.VIEWER
    department: str = "all"  # dynamic from DB, not enum
    clearance: ClearanceLevel = ClearanceLevel.PUBLIC
    groups: list[str] = Field(default_factory=list)


class NodeAccessPolicy(BaseModel):
    """Access policy attached to a graph node."""

    node_id: str
    required_clearance: ClearanceLevel = ClearanceLevel.PUBLIC
    allowed_departments: list[str] = Field(default_factory=lambda: ["all"])
    allowed_roles: list[Role] = Field(
        default_factory=lambda: [Role.ADMIN, Role.ANALYST, Role.VIEWER, Role.AUDITOR]
    )
    owner_id: Optional[str] = None


class RBACService:
    """Service for checking node-level access permissions."""

    # Role hierarchy: higher roles inherit lower role access
    ROLE_HIERARCHY: dict[Role, int] = {
        Role.ADMIN: 100,
        Role.AUDITOR: 50,
        Role.ANALYST: 30,
        Role.VIEWER: 10,
    }

    def check_node_access(
        self, context: AccessContext, policy: NodeAccessPolicy
    ) -> bool:
        """Check if a user has access to a specific graph node."""
        # Admin bypass
        if context.role == Role.ADMIN:
            logger.debug("rbac_admin_bypass", user_id=context.user_id, node_id=policy.node_id)
            return True

        # Clearance level check
        if context.clearance.value < policy.required_clearance.value:
            logger.info(
                "rbac_denied_clearance",
                user_id=context.user_id, node_id=policy.node_id,
                user_clearance=context.clearance.name, required_clearance=policy.required_clearance.name,
            )
            return False

        # Department check
        if "all" not in policy.allowed_departments:
            if context.department not in policy.allowed_departments and context.department != "all":
                logger.info(
                    "rbac_denied_department",
                    user_id=context.user_id, node_id=policy.node_id,
                    user_department=context.department, allowed_departments=policy.allowed_departments,
                )
                return False

        # Role check
        if context.role not in policy.allowed_roles:
            logger.info(
                "rbac_denied_role",
                user_id=context.user_id, node_id=policy.node_id,
                user_role=context.role.value, allowed_roles=[r.value for r in policy.allowed_roles],
            )
            return False

        logger.debug("rbac_access_granted", user_id=context.user_id, node_id=policy.node_id)
        return True

    def filter_nodes(
        self, context: AccessContext, nodes: list[dict], policies: dict[str, NodeAccessPolicy]
    ) -> list[dict]:
        """Filter a list of graph nodes based on user access."""
        accessible = []
        for node in nodes:
            node_id = node.get("id", "")
            policy = policies.get(node_id, NodeAccessPolicy(node_id=node_id))
            if self.check_node_access(context, policy):
                accessible.append(node)

        logger.info(
            "rbac_filter_result",
            user_id=context.user_id, total_nodes=len(nodes), accessible_nodes=len(accessible),
        )
        return accessible

    def build_cypher_filter(self, context: AccessContext) -> str:
        """Generate a Cypher WHERE clause for Neo4j queries with RBAC filtering."""
        if context.role == Role.ADMIN:
            return ""

        conditions = []

        # Clearance filter
        conditions.append(
            f"(n.clearance_level IS NULL OR n.clearance_level <= {context.clearance.value})"
        )

        # Department filter
        if context.department != "all":
            conditions.append(
                f"(n.department IS NULL OR n.department = 'all' OR n.department = '{context.department}')"
            )

        return " AND ".join(conditions)


# Singleton
rbac_service = RBACService()