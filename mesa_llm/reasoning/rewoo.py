from typing import TYPE_CHECKING

from mesa_llm.reasoning.reasoning import Plan, Reasoning

if TYPE_CHECKING:
    from mesa_llm.llm_agent import LLMAgent


class ReWOOReasoning(Reasoning):
    """
    ReWOO is a reasoning approach that creates a plan that can be executed without needing new observations.
    """

    def __init__(self, agent: "LLMAgent"):
        super().__init__(agent=agent)
        self.remaining_tool_calls = 0  # Initialize remaining tool calls
        self.current_plan = None

    def plan(self, prompt: str) -> Plan:
        """
        Plan the next (ReWOO) action based on the current observation and the agent's memory.
        """

        # If we have remaining tool calls, skip observation and plan generation
        if self.remaining_tool_calls > 0:
            index_of_tool = (
                self.current_plan.tool_calls.length() - self.remaining_tool_calls
            )
            self.remaining_tool_calls -= 1
            tool_call = [self.current_plan.tool_calls[index_of_tool]]
            current_plan = self.current_plan
            current_plan.tool_calls = tool_call
            return Plan(llm_plan=current_plan, step=10, ttl=1)  # change step

        obs = self.agent.generate_obs()
        llm = self.agent.llm
        memory = self.agent.memory
        long_term_memory = memory.format_long_term()
        short_term_memory = memory.format_short_term()

        system_prompt = f"""
        You are an autonomous agent that creates multi-step plans without re-observing during execution.
        Using the ReWOO (Reasoning WithOut Observation) approach, you will create a comprehensive plan
        that anticipates multiple steps ahead based on your current observation and memory.

        ---

        # Long-Term Memory
        {long_term_memory}

        ---

        # Short-Term Memory (Recent History)
        {short_term_memory}

        ---

        # Current Observation
        {obs}

        ---

        # Instructions
        Create a detailed multi-step plan that can be executed without needing new observations.
        Your plan should anticipate likely scenarios and include contingencies.

        Determine the optimal number of steps (1-5) based on the complexity of the task and available tools.
        Use this format:


            "plan": "Describe your overall strategy and reasoning",
            "step_1": "First action with expected outcome",
            "step_2": "Second action building on Step 1 (optional)",
            "step_3": "Third action if needed (optional)",
            "step_4": "Fourth action if needed (optional)",
            "step_5": "Final action if needed (optional)",
            "contingency": "What to do if things don't go as expected"


        Only include the steps you need (step_1 is required, step_2 through step_5 are optional).
        Set unused step fields to null. The plan should be comprehensive enough to execute
        for multiple simulation steps without requiring new environmental observations.
        Refer to available tools when planning actions.

        ---
        """

        llm.set_system_prompt(system_prompt)
        rsp = llm.generate(
            prompt=prompt,
            tool_schema=self.agent.tool_manager.get_all_tools_schema(),
            tool_choice="none",
        )

        memory.add_to_memory(type="Plan", content=rsp.choices[0].message.content)

        rewoo_plan = self.execute_tool_call(rsp.choices[0].message.content)

        # Count the number of tool calls in the response and set remaining_tool_calls
        if hasattr(rewoo_plan, "tool_calls"):
            self.remaining_tool_calls = len(rewoo_plan.tool_calls)
            print(
                "############################################################",
                self.remaining_tool_calls,
            )
        else:
            self.remaining_tool_calls = 0
        self.current_plan = rewoo_plan

        # --------------------------------------------------
        # Recording hook for plan event
        # --------------------------------------------------
        if self.agent.recorder is not None:
            self.agent.recorder.record_event(
                event_type="plan",
                content={"plan": str(rewoo_plan)},
                agent_id=self.agent.unique_id,
            )

        return rewoo_plan
