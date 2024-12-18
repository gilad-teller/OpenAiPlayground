import os
import openai
import subprocess
import json
import pyperclip

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

print("0. Get more suggestions")
ind = 1
for s in suggestions:
    print("{}. {}".format(ind, s))
    ind += 1

selections = input("Selection: ").split()

if selections[0] == '0':
    print("Calling OpenAI")
    messages.append({"role": "user", "content": "Give me a few more suggestions."})
    second_response = call_openai(messages)
    new_suggestions = extract_suggestions(second_response)
    suggestions.extend(new_suggestions)
    for s in new_suggestions:
        print("{}. {}".format(ind, s))
        ind += 1
    selections = input("Selection: ").split()

selections = [int(num) - 1 for num in selections]
joined_selection = ' | '.join([suggestions[i] for i in selections])

ticket = input("Ticket: ")
commitMessage = ""
if ticket:
    commitMessage = 'git commit -am "{} {}"'.format(ticket, joined_selection)
else:
    commitMessage = 'git commit -am "{}"'.format(joined_selection)
pyperclip.copy(commitMessage)
print("{} was copied to clipboard".format(commitMessage))