#!/usr/bin/env python3
"""Claude OS Worker Agent — calls Claude API in an agentic loop to execute tasks."""

import json
import os
import subprocess
import sys

import anthropic


def run_command(command: str, workdir: str = None) -> dict:
    """Execute a shell command and return stdout/stderr."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=workdir or os.getcwd(),
        )
        return {
            "stdout": result.stdout[-4000:]
            if len(result.stdout) > 4000
            else result.stdout,
            "stderr": result.stderr[-2000:]
            if len(result.stderr) > 2000
            else result.stderr,
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": "Command timed out after 300s",
            "exit_code": 124,
        }


TOOLS = [
    {
        "name": "run_command",
        "description": "Execute a shell command. Use for git, file operations, builds, tests, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "workdir": {
                    "type": "string",
                    "description": "Working directory (optional)",
                },
            },
            "required": ["command"],
        },
    },
]


def main():
    task_id = os.environ.get("TASK_ID", "unknown")
    task_title = os.environ.get("TASK_TITLE", "")
    task_description = os.environ.get("TASK_DESCRIPTION", "")
    target_repo = os.environ.get("TARGET_REPO", "")
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

    system_prompt = f"""You are Claude OS Worker, an autonomous agent executing tasks on a Kubernetes cluster.

Your task: {task_title}
Description: {task_description}
Target repo: {target_repo or 'None (general task)'}
Working directory: /workspace{'/repo' if target_repo else ''}

You have access to run shell commands. The environment has git, python3, curl, jq, and gh (GitHub CLI) available.
If the task involves a repo, it has already been cloned to /workspace/repo.

Execute the task step by step. When done, output a clear summary of what you accomplished.
If you need to create a PR, use `gh pr create`. If you need to commit, use git commit.
Be thorough but efficient. If you encounter an error, try to fix it."""

    messages = [
        {
            "role": "user",
            "content": f"Execute this task: {task_title}\n\n{task_description}",
        }
    ]
    total_tokens = 0
    max_tokens = int(os.environ.get("MAX_TOKENS_PER_JOB", "200000"))
    max_iterations = 50

    for iteration in range(max_iterations):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        total_tokens += response.usage.input_tokens + response.usage.output_tokens

        # Check if we should stop
        if response.stop_reason == "end_turn":
            for block in response.content:
                if block.type == "text":
                    print(f"\n=== Task Result ===\n{block.text}")
            break

        # Process tool calls
        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        tool_results = []
        for block in assistant_content:
            if block.type == "tool_use":
                print(
                    f"[iter {iteration}] Running: {block.input.get('command', '')[:100]}"
                )
                result = run_command(
                    block.input["command"], block.input.get("workdir")
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    }
                )
            elif block.type == "text" and block.text:
                print(f"[iter {iteration}] {block.text[:200]}")

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        if total_tokens > max_tokens:
            print(f"Token budget exceeded ({total_tokens}/{max_tokens}), stopping.")
            break

    # Write usage stats for the controller to read
    stats = {
        "task_id": task_id,
        "total_tokens": total_tokens,
        "iterations": iteration + 1,
    }
    with open("/workspace/task-stats.json", "w") as f:
        json.dump(stats, f)

    print(f"\nTotal tokens used: {total_tokens}")


if __name__ == "__main__":
    main()
