import agent
import os

SKILL_META = {
    "name": "plan_to_tasklist",
    "description": "Takes a high-level plan, summarizes it, and converts it into a structured task list saved to the workspace.",
    "version": "1.0",
}

def run(args: str, state: dict, client) -> str:
    """
    Processes a user's provided plan (in args), summarizes it using the LLM, 
    and saves the resulting task list to the workspace directory.
    """
    if not args or not args.strip():
        return "Please provide a detailed plan for me to process."

    print("\n🧠 Analyzing your plan and generating a structured task list...")
    
    # 1. Define the prompt structure
    system_prompt = (
                """
                You are an expert Senior Python Developer and Technical Architect. Your sole function is to translate high-level business requirements into a precise, actionable technical plan. You must assume the role of the lead engineer receiving vague instructions from a non-technical stakeholder.

                Your output **must not** contain any explanations or conversational filler. It must only be the summary of the tsk to be achieved and the task list itself.

                Analyze the Stakeholder Description. Your goal is to break down the intent into discrete, sequential, and technically actionable steps required to write the code. Focus on *what* needs to be built, not *why*.

                **Output Format Rules:**
                1.  A *VERY BRIEF* description of the intent of the script/applicaiton to be developed
                2.  Use a numbered list (`1.`, `2.`, etc.).
                3.  Each step must start with an imperative verb (e.g., "Implement," "Refactor," "Create," "Handle").
                4.  Group related steps logically (e.g., Setup, Core Logic, Testing).
                """
    )

    # 2. Construct the messages for the LLM call
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Please process this plan:\n\n---PLAN---\n{args}"}
    ]

    # 3. Call the LLM to generate the structured content
    print("🤖 Calling LLM to summarize and structure the tasks...")
    try:
        text, _ = agent._stream_response(client, state["model"], messages,
                                        gen_params=state.get("gen_params") or None)
    except Exception as e:
        return f"An error occurred while calling the LLM: {e}"

    # 4. Attempt to save the generated text to a file in the workspace
    tasklist_filename = "structured_tasklist.md"
    file_path = os.path.join('workspace', tasklist_filename)

    print(f"\n💾 Attempting to save the structured task list to '{tasklist_filename}' in the workspace...")
    try:
        # The 'text' variable contains the streamed response from agent._stream_response
        # We assume that if streaming was successful, the full content is available 
        # or we use a placeholder for demonstration purposes since actual stream handling is complex.
        # For this skill, we will treat the final output of the LLM call as the content to save.

        # NOTE: In a real scenario, you would need to collect the entire streamed response 
        # into a single string before saving it. Since the provided agent API only returns 
        # (text, _) which might be the final compiled text, we use that directly.
        content_to_save = text

        with open(file_path, "w") as f:
            f.write(content_to_save)
        
        return (f"\n✅ Success! The plan has been analyzed and converted into a structured task list.\n"
                f"The file '{tasklist_filename}' has been saved to the workspace folder.")

    except Exception as e:
        # Fixing the SyntaxError issue by ensuring proper string formatting 
        # and variable usage within f-strings.
        return f"\n❌ Error saving file to workspace: {e}"
