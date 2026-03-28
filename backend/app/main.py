from fastapi import FastAPI
from backend.app.services.llm import ask_llm
from typing import Literal
import subprocess
import os

app = FastAPI()

# ------------------ HELPERS ------------------

def detect_intent(task: str):
    t = task.lower()

    if "nginx" in t and ("install" in t or "setup" in t or "deploy" in t):
        return "nginx_install"

    if "docker" in t and "install" in t:
        return "docker_install"

    if "create" in t and ("folder" in t or "directory" in t):
        return "create_directory"

    return "general"


def clean_yaml(text):
    return text.replace("```yaml", "").replace("```", "").strip()


def extract_variable(task: str, intent: str):
    if intent == "create_directory":
        words = task.split()
        return {"folder_name": words[-1]}
    return {}


# ------------------ CONFIG ------------------

PLAYBOOK_DIR = "backend/playbooks"


# ------------------ ROUTES ------------------

@app.get("/")
def root():
    return {"message": "AI DevOps Agent Running"}


@app.post("/deploy")
def deploy(task: str, environment: Literal["macos", "ec2"]):

    try:
        intent = detect_intent(task)

        # ------------------ ENV ------------------

        if environment == "macos":
            OS_TYPE = "macos"
            PACKAGE_MANAGER = "brew"
            ALLOW_PRIVILEGE = False
            HOST_GROUP = "webservers"

        elif environment == "ec2":
            OS_TYPE = "linux"
            PACKAGE_MANAGER = "apt"
            ALLOW_PRIVILEGE = True
            HOST_GROUP = "webservers"

        else:
            return {"error": "Invalid environment"}

        # ------------------ PATH ------------------

        path = f"{PLAYBOOK_DIR}/{environment}/{intent}.yml"

        # ------------------ LOAD OR GENERATE ------------------

        if os.path.exists(path):
            print("USING SAVED PLAYBOOK:", path)
            with open(path, "r") as f:
                template_playbook = f.read()
        else:
            print("GENERATING NEW PLAYBOOK")

            prompt = f"""
Generate a valid Ansible playbook in YAML.

- Return only YAML
- No markdown or explanations
- Start at column 0
- Use 2-space indentation
- Keep playbook minimal
- Always use ~/ for user directories

Environment:
- OS: {OS_TYPE}
- Package manager: {PACKAGE_MANAGER}
- Hosts: {HOST_GROUP}
- Privilege escalation: {"allowed" if ALLOW_PRIVILEGE else "not allowed"}

Task: {task}
"""
            template_playbook = ask_llm(prompt)
            template_playbook = clean_yaml(template_playbook)

        # ------------------ TEMPLATE → RUNTIME ------------------

        variables = extract_variable(task, intent)
        print("VARIABLES:", variables)

        playbook_runtime = template_playbook

        for key, value in variables.items():
            placeholder = "{" + key + "}"
            playbook_runtime = playbook_runtime.replace(placeholder, value)

        print("FINAL PLAYBOOK:\n", playbook_runtime)

        # ------------------ SAVE TEMP ------------------

        with open("playbook.yml", "w") as f:
            f.write(playbook_runtime)

        # ------------------ RUN ------------------

        def run():
            result = subprocess.run(
                ["ansible-playbook", "-i", "backend/inventory.ini", "playbook.yml"],
                capture_output=True,
                text=True
            )
            return result.stdout, result.stderr

        out, err = run()

        # ------------------ SUCCESS ------------------

        if "failed=0" in out or "ok=" in out:
            os.makedirs(os.path.dirname(path), exist_ok=True)

            # SAVE TEMPLATE (NOT runtime)
            with open(path, "w") as f:
                f.write(template_playbook)

            return {
                "status": "success",
                "playbook": playbook_runtime,
                "output": out,
                "error": err
            }

        # ------------------ SELF HEAL ------------------

        fix_prompt = f"""
The following Ansible playbook failed.

Playbook:
{template_playbook}

Error:
{out}
{err}

Fix the playbook.

- Return ONLY YAML
- No markdown
- No explanations
- Start at column 0
"""

        fixed_template = ask_llm(fix_prompt)
        fixed_template = clean_yaml(fixed_template)

        # apply variables again
        fixed_runtime = fixed_template

        for key, value in variables.items():
            placeholder = "{" + key + "}"
            fixed_runtime = fixed_runtime.replace(placeholder, value)

        with open("playbook.yml", "w") as f:
            f.write(fixed_runtime)

        out, err = run()

        if "failed=0" in out or "ok=" in out:
            os.makedirs(os.path.dirname(path), exist_ok=True)

            # SAVE FIXED TEMPLATE
            with open(path, "w") as f:
                f.write(fixed_template)

        return {
            "status": "fixed",
            "playbook": fixed_runtime,
            "output": out,
            "error": err
        }

    except Exception as e:
        return {"error": str(e)}