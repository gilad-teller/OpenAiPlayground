import os
import json
import re
import subprocess
import pyperclip
from typing import List, Tuple, Optional

# OpenAI client (modern SDK)
try:
    from openai import OpenAI
except ImportError:
    raise ImportError("Please install/upgrade the OpenAI Python SDK: pip install --upgrade openai")

MODELS = ["gpt-4o", "gpt-5"]

def run_subprocess(args: List[str], cwd: Optional[str] = None) -> str:
    """Run a subprocess command with arg list; raise on non-zero exit."""
    result = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{result.stderr.strip()}")
    return result.stdout

def get_env_var(name: str, required: bool = True) -> Optional[str]:
    val = os.getenv(name)
    if required and not val:
        raise Exception(f"No {name} environment variable")
    return val

def get_current_branch_name() -> Optional[str]:
    try:
        return run_subprocess(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
    except Exception:
        return None

def extract_ticket_from_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    m = re.search(r'([A-Z]{2,}-\d+)', text)
    return m.group(1) if m else None

def initialize_openai() -> OpenAI:
    # Organization is optional; API key is required
    api_key = get_env_var("OPENAI_API_KEY", required=True)
    organization = get_env_var("OPENAI_ORG", required=False)
    if organization:
        return OpenAI(api_key=api_key, organization=organization)
    return OpenAI(api_key=api_key)

# -------- File discovery and binary filtering (no staging) --------

def get_changed_files() -> List[Tuple[str, str]]:
    """
    Returns list of (path, kind) where kind in {"added_untracked","added","modified"}.
    Based on 'git status --porcelain' across index (staged) and worktree (unstaged).
    """
    out = run_subprocess(["git", "status", "--porcelain"])
    files: List[Tuple[str, str]] = []
    seen = set()
    for line in out.splitlines():
        if not line.strip():
            continue
        x = line[0:1]
        y = line[1:2]
        path = line[3:].strip()
        kind: Optional[str] = None
        if x == "?" and y == "?":
            kind = "added_untracked"
        elif "A" in (x + y):
            kind = "added"
        elif "M" in (x + y):
            kind = "modified"
        if kind and path not in seen:
            files.append((path, kind))
            seen.add(path)
    return files

def is_probably_text(data: bytes) -> bool:
    if not data:
        return True
    if b"\0" in data:
        return False
    # Printable ASCII + common whitespace
    printable = set(range(32, 127)) | {9, 10, 13}
    nontext = sum(1 for b in data if b not in printable)
    return (nontext / len(data)) < 0.30

def is_binary_untracked(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        return not is_probably_text(chunk)
    except Exception:
        # If unreadable, treat as binary to be safe
        return True

def is_binary_in_diff(path: str, staged: bool) -> bool:
    """
    Use 'git diff --numstat' to detect binary for tracked files.
    Returns True if the diff shows '-' '-' for this path.
    """
    args = ["git", "diff", "--numstat"]
    if staged:
        args.insert(2, "--cached")
    args += ["--", path]
    out = run_subprocess(args)
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2].strip() == path:
            return parts[0] == "-" and parts[1] == "-"
    return False

def partition_files_excluding_binaries(files: List[Tuple[str, str]]) -> Tuple[List[str], List[str]]:
    """
    Returns (text_files, binary_files) from the provided file list.
    - For untracked: content heuristic
    - For tracked: look at staged and unstaged diffs via numstat
    """
    text_files: List[str] = []
    binary_files: List[str] = []
    for path, kind in files:
        if kind == "added_untracked":
            if is_binary_untracked(path):
                binary_files.append(path)
            else:
                text_files.append(path)
        else:
            # tracked path: check both unstaged and staged diffs for binary-ness
            is_bin = is_binary_in_diff(path, staged=False) or is_binary_in_diff(path, staged=True)
            if is_bin:
                binary_files.append(path)
            else:
                text_files.append(path)
    return text_files, binary_files

# -------- Diff construction (no staging side-effects) --------

def git_diff_single(path: str, staged: bool) -> str:
    args = ["git", "diff", "--no-color", "--unified=0", "--diff-filter=AM", "--", path]
    if staged:
        args.insert(2, "--cached")
    return run_subprocess(args).strip()

def synthetic_add_diff(path: str) -> str:
    """
    Build a unified diff for a new untracked text file, treating all lines as added.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except Exception as e:
        raise RuntimeError(f"Failed reading new file for diff: {path}\n{e}")
    added_count = len(lines)
    header = f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{max(1, added_count)} @@"
    body = "\n".join("+" + line for line in lines) if lines else "+\n"
    return f"{header}\n{body}"

def build_combined_diff(files: List[Tuple[str, str]], include_paths: List[str]) -> str:
    """
    For each included path:
      - Append unstaged diff (if any)
      - Append staged diff (if any)
      - For untracked new, append synthetic diff
    """
    chunks: List[str] = []
    include_set = set(include_paths)
    for path, kind in files:
        if path not in include_set:
            continue
        if kind == "added_untracked":
            chunks.append(synthetic_add_diff(path))
        else:
            unstaged = git_diff_single(path, staged=False)
            if unstaged:
                chunks.append(unstaged)
            staged = git_diff_single(path, staged=True)
            if staged:
                chunks.append(staged)
    return "\n".join(c for c in chunks if c).strip()

# -------- OpenAI prompt, call and parsing --------

def make_messages(diff_text: str):
    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "commit_suggestions",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "suggestions": {
                        "type": "array",
                        "minItems": 5,
                        "maxItems": 5,
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["feat", "fix", "refactor", "perf", "docs", "chore", "test", "build", "ci"]
                                },
                                "subject": {
                                    "type": "string",
                                    "minLength": 10,
                                    "maxLength": 72
                                }
                            },
                            "required": ["type", "subject"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["suggestions"],
                "additionalProperties": False
            }
        }
    }

    system_msg = {
        "role": "system",
        "content": (
            "You are a helpful assistant and expert in Conventional Commits. "
            "Return exactly 5 suggestions as JSON matching the provided schema."
        ),
    }
    user_msg = {
        "role": "user",
        "content": (
            "Generate exactly 5 Conventional Commit suggestions.\n"
            "- Format: { \"suggestions\": [ { \"type\": \"<type>\", \"subject\": \"<subject>\" }, ... ] }\n"
            "- Allowed types: feat, fix, refactor, perf, docs, chore, test, build, ci\n"
            "- Subject: imperative, concise, 50–72 chars, no trailing period\n"
            "- Prefer logic changes over style/test/doc-only changes\n"
            "- If only cosmetic changes exist, propose the closest meaningful summary\n"
            "Here is the combined diff (staged + unstaged + new files):\n"
            f"{diff_text}"
        ),
    }
    return schema, [system_msg, user_msg]

def call_openai_and_extract(client: OpenAI, model: str, messages: list, schema: dict) -> List[str]:
    # Known models that allow non-default temperature
    MODELS_ALLOW_TEMP = {"gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"}

    def create_request(allow_temp: bool, rf_mode: str):
        # rf_mode: "schema" -> use provided JSON schema; "object" -> generic json_object
        kwargs = {
            "model": model,
            "messages": messages,
        }
        if rf_mode == "schema":
            kwargs["response_format"] = schema
        else:
            kwargs["response_format"] = {"type": "json_object"}
        if allow_temp:
            kwargs["temperature"] = 0.2
        return client.chat.completions.create(**kwargs)

    allow_temp = model in MODELS_ALLOW_TEMP
    rf_mode = "schema"
    try:
        resp = create_request(allow_temp, rf_mode)
    except Exception as e:
        emsg = str(e)
        # Retry without temperature if rejected
        if "param': 'temperature'" in emsg or "Only the default (1) value is supported" in emsg or "unsupported_value" in emsg and "temperature" in emsg:
            try:
                resp = create_request(False, rf_mode)
            except Exception as e2:
                emsg2 = str(e2)
                # If response_format schema is rejected, fall back to json_object
                if "response_format" in emsg2 or "invalid_request_error" in emsg2:
                    resp = create_request(False, "object")
                else:
                    raise
        # If response_format schema is rejected initially, fall back to json_object
        elif "response_format" in emsg or "invalid_request_error" in emsg:
            try:
                resp = create_request(allow_temp, "object")
            except Exception as e3:
                # Final attempt without temperature + json_object
                resp = create_request(False, "object")
        else:
            raise

    assistant_content = resp.choices[0].message.content
    messages.append({"role": "assistant", "content": assistant_content})

    def parse_suggestions(text: str) -> List[str]:
        data = json.loads(text)
        # Expect either the strict schema or a plain object that still has suggestions
        if isinstance(data, dict) and "suggestions" in data and isinstance(data["suggestions"], list):
            return [f"{s['type']}: {s['subject']}" for s in data["suggestions"]]
        # If model returned an array directly, accept it
        if isinstance(data, list):
            return [f"{s['type']}: {s['subject']}" for s in data]
        raise ValueError("JSON does not contain 'suggestions' array")

    try:
        return parse_suggestions(assistant_content)
    except Exception:
        # Single structured retry asking for valid JSON only; avoid temp for max compatibility
        messages.append({"role": "user", "content": "The previous reply was not valid JSON per schema. Please resend valid JSON only."})
        try:
            resp2 = client.chat.completions.create(
                model=model,
                response_format=schema,
                messages=messages,
            )
        except Exception:
            # Fallback to json_object if schema is not supported on this model
            resp2 = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=messages,
            )
        assistant_content2 = resp2.choices[0].message.content
        messages.append({"role": "assistant", "content": assistant_content2})
        return parse_suggestions(assistant_content2)

# -------- Commit message helpers --------

def sanitize_for_powershell_single_quoted(s: str) -> str:
    s = s.replace("\r", " ").replace("\n", " ").strip()
    return s.replace("'", "''")

def build_commit_command(ticket: str, selected_messages: List[str]) -> str:
    if not selected_messages:
        raise Exception("No selections provided")
    first_raw = (f"{ticket} {selected_messages[0]}" if ticket else selected_messages[0])
    first_message = sanitize_for_powershell_single_quoted(first_raw)
    parts = [f"git commit -am '{first_message}'"]
    for msg in selected_messages[1:]:
        parts.append(f"-m '{sanitize_for_powershell_single_quoted(msg)}'")
    return " ".join(parts)

# -------- Main flow (no staging side-effects) --------

def main():
    client = initialize_openai()

    # 1) Gather changes without staging anything
    files = get_changed_files()
    if not files:
        raise Exception("No added or modified files found (staged or unstaged).")

    # 2) Exclude binaries
    text_files, binary_files = partition_files_excluding_binaries(files)

    # 3) Show user: New vs Changed, ignoring binaries. Gate on Enter/Ctrl+C
    new_files = [p for (p, k) in files if k == "added_untracked" and p in text_files]
    changed_files = [p for (p, k) in files if k in ("modified", "added") and p in text_files]

    print("\nNew files (included):" if new_files else "\nNew files (none):")
    for p in new_files:
        print(f"  - {p}")

    print("\nChanged files (included):" if changed_files else "\nChanged files (none):")
    for p in changed_files:
        print(f"  - {p}")

    if binary_files:
        print("\nBinary files (ignored):")
        for p in binary_files:
            print(f"  - {p}")

    # Require Enter to continue or Ctrl+C to quit
    input("\nPress Enter to continue, or Ctrl+C to abort... ")

    include_paths = new_files + changed_files
    if not include_paths:
        raise Exception("No text files to include in diff after filtering.")

    # 4) Build combined diff (unstaged + staged + synthetic for new)
    diff_text = build_combined_diff(files, include_paths)

    # 5) Call OpenAI; allow repeated re-runs with progressively better models
    model_index = 0
    schema, messages = make_messages(diff_text)
    print(f"\nCalling OpenAI ({MODELS[model_index]})...")
    suggestions = call_openai_and_extract(client, MODELS[model_index], messages, schema)

    while True:
        for i, s in enumerate(suggestions, start=1):
            print(f"{i}. {s}")

        user_input = input("\nType 'r' to re-run, or select suggestions (e.g., '1' or '1 3'): ").strip()
        if user_input.lower() == "r":
            model_index = min(model_index + 1, len(MODELS) - 1)
            print(f"Re-running with {MODELS[model_index]}...")
            suggestions = call_openai_and_extract(client, MODELS[model_index], messages, schema)
            continue

        selections = user_input.split()
        if selections:
            break

        print("Please enter 'r' to re-run or one or more suggestion numbers.")

    # 6) Selection + optional ticket + commit command copied to clipboard
    idx = [int(num) - 1 for num in selections]
    selected_messages = [suggestions[i] for i in idx]

    ticket_default = extract_ticket_from_text(get_current_branch_name())
    if ticket_default:
        ticket_input = input(f"Ticket ({ticket_default}): ").strip()
        ticket = ticket_default if ticket_input == "" else ticket_input
    else:
        ticket = input("Ticket: ").strip()

    commit_cmd = build_commit_command(ticket, selected_messages)
    pyperclip.copy(commit_cmd)
    print(f"\n{commit_cmd} was copied to clipboard")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted by user.")