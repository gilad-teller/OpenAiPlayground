import os
import openai
import subprocess

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise Exception('No OPENAI_API_KEY environment variable')

organization = os.getenv("OPENAI_ORG")
if not api_key:
    raise Exception('No OPENAI_ORG environment variable')


result = subprocess.run('git diff --cached', capture_output=True, text=True)
if result.stderr:
    raise Exception('git diff --cached returned error', result.stderr)

openai.organization = organization
openai.api_key = api_key
text = 'Suggest me a few good commit messages for my commit following conventional commit (<type>: <subject>). \n' + result.stdout
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