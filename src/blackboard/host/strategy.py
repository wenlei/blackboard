import logging

from blackboard.config.loader import StrategyTemplates

logger = logging.getLogger(__name__)


class StrategyGenerator:
    def __init__(self, templates: StrategyTemplates):
        self.templates = templates

    def generate(self, user_input: str, agent_roles: dict[str, str]) -> str:
        matched = self._match_template(user_input)
        if not matched:
            return self._build_general_psc(user_input, agent_roles)

        return self._build_psc_from_template(matched, agent_roles)

    def _match_template(self, user_input: str):
        input_lower = user_input.lower()
        best = None
        best_score = 0
        for tmpl in self.templates.templates:
            if not tmpl.match_keywords:
                continue
            score = sum(1 for kw in tmpl.match_keywords if kw.lower() in input_lower)
            if score > best_score:
                best_score = score
                best = tmpl
        return best

    def _build_psc_from_template(self, template, agent_roles: dict[str, str]) -> str:
        lines = [f"WORKFLOW: {template.name}"]
        # agent_roles = {role: agent_name}; build role→agent_name lookup
        available_agents = {role.lower(): agent_name for role, agent_name in agent_roles.items()}

        for step in template.steps:
            agent_name = step.agent_role
            if agent_name == "auto":
                # Use the first available agent instance name
                agent_name = list(available_agents.values())[0] if available_agents else "agent"
            else:
                # Resolve role name → instance name if mapping exists
                agent_name = available_agents.get(agent_name.lower(), agent_name)
            lines.append(f"  {agent_name.upper()}: {step.action}")

        return "\n".join(lines)

    def generate_from_template_id(self, template_id: str, agent_roles: dict[str, str]) -> str | None:
        """Return PSC for a specific template id, or None if not found."""
        tmpl = next((t for t in self.templates.templates if t.id.lower() == template_id.lower() or t.name == template_id), None)
        if not tmpl:
            return None
        return self._build_psc_from_template(tmpl, agent_roles)

    def _build_general_psc(self, user_input: str, agent_roles: dict[str, str]) -> str:
        lines = ["WORKFLOW: 通用问答"]
        if agent_roles:
            # Use instance name (value) so the executor can look up the agent by name
            first_instance = list(agent_roles.values())[0]
            lines.append(f"  {first_instance.upper()}: 回答用户问题: {user_input}")
            lines.append("  → RETURN")
        else:
            lines.append(f"  AGENT: {user_input}")
            lines.append("  → RETURN")
        return "\n".join(lines)
