import os
import openai
import subprocess

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

print('Getting environment variables')
api_key = get_env_var("OPENAI_API_KEY")
organization = get_env_var("OPENAI_ORG")

print('Running git diff --cached')
result = run_subprocess('git diff --cached')
if not result:
    result = run_subprocess('git diff')
if not result:
    print('No result, running git diff')
    raise Exception('No diff')

print('Calling OpenAI')
openai.organization = organization
openai.api_key = api_key
text = 'Suggest me a few good commit messages for my commit following conventional commit (<type>: <subject>). \n' + result
response = openai.Completion.create(
  model="text-davinci-003",
  prompt=text,
  temperature=0.7,
  max_tokens=100,
  top_p=1,
  frequency_penalty=0.0,
  presence_penalty=0.0
)
for choice in response['choices']:
    print(choice['text'])