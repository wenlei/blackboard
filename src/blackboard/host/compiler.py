import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeType(str, Enum):
    AGENT = "agent"
    BRANCH = "branch"
    MERGE = "merge"
    RETURN = "return"


@dataclass
class ASTNode:
    node_type: NodeType
    agent: str = ""
    action: str = ""
    condition: str = ""
    next_true: "ASTNode | None" = None
    next_false: "ASTNode | None" = None
    next_node: "ASTNode | None" = None
    children: list["ASTNode"] = field(default_factory=list)


def compile_psc(source: str) -> ASTNode:
    lines = [l for l in source.strip().split("\n") if l.strip() and not l.strip().startswith("WORKFLOW:")]

    if not lines:
        return ASTNode(node_type=NodeType.RETURN)

    first_node: ASTNode | None = None
    last_node: ASTNode | None = None
    branch_stack: list[ASTNode] = []
    pending_else_branch: ASTNode | None = None

    def append_node(node: ASTNode):
        nonlocal first_node, last_node, pending_else_branch
        if pending_else_branch is not None:
            if pending_else_branch.next_false is None:
                pending_else_branch.next_false = node
            else:
                cur = pending_else_branch.next_false
                while cur.next_node:
                    cur = cur.next_node
                cur.next_node = node
            last_node = node
            return

        if branch_stack:
            parent = branch_stack[-1]
            if parent.next_true is None:
                parent.next_true = node
            elif parent.next_false is None:
                parent.next_false = node
            else:
                cur = parent.next_false
                while cur.next_node:
                    cur = cur.next_node
                cur.next_node = node
        else:
            if first_node is None:
                first_node = node
            if last_node is not None:
                last_node.next_node = node
            last_node = node

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("IF "):
            condition = stripped[3:].rstrip(":")
            node = ASTNode(node_type=NodeType.BRANCH, condition=condition)
            append_node(node)
            branch_stack.append(node)
            last_node = node

        elif stripped == "ELSE:":
            pass

        elif stripped.startswith("→ RETURN"):
            node = ASTNode(node_type=NodeType.RETURN)
            append_node(node)
            if branch_stack:
                pending_else_branch = branch_stack.pop()

        elif ":" in stripped:
            parts = stripped.split(":", 1)
            agent_name = parts[0].strip()
            action = parts[1].strip() if len(parts) > 1 else ""
            node = ASTNode(node_type=NodeType.AGENT, agent=agent_name, action=action)
            append_node(node)

    last_branch = branch_stack[-1] if branch_stack else None
    if last_branch and (last_branch.next_true is None or last_branch.next_false is None):
        branch_stack.pop()

    return first_node or ASTNode(node_type=NodeType.RETURN)
