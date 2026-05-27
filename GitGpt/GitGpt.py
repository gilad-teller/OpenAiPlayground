import os
import openai
import subprocess
import json
import pyperclip
import re

def run_subprocess(command):
    result = subprocess.run(command, capture_output=True, text=True, shell=True)
    if result.stderr and not result.stdout:
        raise Exception('{} returned error'.format(command), result.stderr)
    return result.stdout

def get_env_var(name):
    env_var = os.getenv(name)
    if not env_var:
        raise Exception('No {} environment variable'.format(name))
    return env_var

def get_current_branch_name():
    try:
        branch = run_subprocess('git rev-parse --abbrev-ref HEAD').strip()
        return branch
    except Exception:
        return None

def extract_ticket_from_text(text: str):
    if not text:
        return None
    m = re.search(r'([A-Z]{2,}-\d+)', text)
    return m.group(1) if m else None

def call_openai(messages):
    response = openai.chat.completions.create(
      model="gpt-4o",
      response_format = { "type": "json_object" },
      messages = messages
    )
    return response

def extract_suggestions(response):
    firstChoice = response.choices[0].message.content
    try:
        startJson = firstChoice.index('[')
        endJson = firstChoice.rindex(']') + 1
        jsonResult = firstChoice[startJson:endJson]
        parsedJson = json.loads(jsonResult)
        try:
            suggestions = []
            for s in parsedJson:
                suggestions.append("{}: {}".format(s["type"], s["subject"]))
            return suggestions
        except:
            return parsedJson
    except:
        print("\nCan't find suggestions. The response was:")
        print(firstChoice)
        raise

def sanitize_for_powershell_single_quoted(s: str) -> str:
    # Replace CR/LF with spaces, trim, and escape single quotes by doubling
    s = s.replace('\r', ' ').replace('\n', ' ').strip()
    return s.replace("'", "''")

print('Getting environment variables')
api_key = get_env_var("OPENAI_API_KEY")
organization = get_env_var("OPENAI_ORG")
openai.organization = organization
openai.api_key = api_key

print('Running git diff --cached')
result = run_subprocess('git diff --cached')
if not result:
    print('No result, running git diff')
    result = run_subprocess('git diff')
if not result:
    raise Exception('No diff')

print('Calling OpenAI')
messages = [
    {"role": "system", "content": "You are a helpful assistant, and an expert in creating git commit messages."},
    {"role": "user", "content": "Suggest me a few good commit messages for my commit following conventional commit (<type>: <subject>). Return all suggestions as json array. \n" + result}
]
response = call_openai(messages)
messages.append(response.choices[0].message.content)
suggestions = []
try:
    suggestions.extend(extract_suggestions(response))
except:
    print("Calling OpenAI")
    messages.append({"role": "user", "content": "I couldn't parse the json you sent. Pleaese fix it."})
    response = call_openai(messages)
    messages.append(response['choices'][0]['message'])
    suggestions.extend(extract_suggestions(response))

ind = 1
for s in suggestions:
    print("{}. {}".format(ind, s))
    ind += 1

selections = input("Selection: ").split()

selections = [int(num) - 1 for num in selections]
selected_messages = [suggestions[i] for i in selections]

# Try to extract ticket from current branch name before asking
extracted_ticket = extract_ticket_from_text(get_current_branch_name())
if extracted_ticket:
    ticket_input = input("Ticket ({}): ".format(extracted_ticket)).strip()
    ticket = extracted_ticket if ticket_input == "" else ticket_input
else:
    ticket = input("Ticket: ").strip()
commitMessage = ""
if not selected_messages:
    raise Exception('No selections provided')

# Build commit command with multiple -m flags, using single quotes for PowerShell safety
first_raw = ("{} {}".format(ticket, selected_messages[0]) if ticket else selected_messages[0])
first_message = sanitize_for_powershell_single_quoted(first_raw)
parts = ["git commit -am '{}'".format(first_message)]
for msg in selected_messages[1:]:
    parts.append("-m '{}'".format(sanitize_for_powershell_single_quoted(msg)))
commitMessage = ' '.join(parts)
pyperclip.copy(commitMessage)
print("{} was copied to clipboard".format(commitMessage))