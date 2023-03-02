import os
import openai
import subprocess
import json

def copy_to_clip(text):
    command = 'echo {}|clip'.format(text.strip())
    subprocess.check_call(command, shell=True)

def run_subprocess(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.stderr:
        raise Exception('{} returned error'.format(command), result.stderr)
    return result.stdout

def get_env_var(name):
    env_var = os.getenv(name)
    if not env_var:
        raise Exception('No {} environment variable'.format(name))
    return env_var

def call_openai(prompt):
    response = openai.Completion.create(
      model="text-davinci-003",
      prompt=prompt,
      temperature=0.7,
      max_tokens=100,
      top_p=1,
      frequency_penalty=0.0,
      presence_penalty=0.0
    )
    return response

def extract_suggestions(response):
    firstChoice = response['choices'][0]['text']
    startJson = firstChoice.index('[')
    endJson = firstChoice.rindex(']') + 1
    jsonResult = firstChoice[startJson:endJson]
    return json.loads(jsonResult)

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
prompt = 'Suggest me a few good commit messages for my commit following conventional commit (<type>: <subject>). Return all suggestions as json array. \n' + result
response = call_openai(prompt)
suggestions = extract_suggestions(response)

print("0. Get more suggestions")
ind = 1
for s in suggestions:
    print("{}. {}".format(ind, s))
    ind += 1

selection = int(input("Selection: "))

if selection == 0:
    print("Calling OpenAI")
    second_response = call_openai(prompt + response['choices'][0]['text'] + "\nGive me a few more suggestions")
    new_suggestions = extract_suggestions(second_response)
    suggestions.extend(new_suggestions)
    for s in new_suggestions:
        print("{}. {}".format(ind, s))
        ind += 1
    selection = int(input("Selection: "))

ticket = input("Ticket: ")
commitMessage = ""
if ticket:
    commitMessage = 'git commit -am "{} {}"'.format(ticket, suggestions[selection - 1])
else:
    commitMessage = 'git commit -am "{}"'.format(suggestions[selection - 1])
copy_to_clip(commitMessage)
print("{} was copied to clipboard".format(commitMessage))