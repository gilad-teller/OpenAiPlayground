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

def call_openai(messages):
    response = openai.chat.completions.create(
      model="gpt-4o",
      messages = messages,
      stream=True
    )
    return response

print('Getting environment variables')
api_key = get_env_var("OPENAI_API_KEY")
organization = get_env_var("OPENAI_ORG")
openai.organization = organization
openai.api_key = api_key

base_branch = input("Base branch: ")
compare_branch = input("Compare branch: ")
diff_command = f'git diff {base_branch}..{compare_branch}'

print(f'Running {diff_command}')
result = run_subprocess(diff_command)
if not result:
    raise Exception('No diff')

print('Calling OpenAI')
messages = [
    {"role": "system", "content": "You are a helpful assistant, and an expert in reviewing code."},
    {"role": "user", "content": f"Please use this git diff in order to review my code. Looks for potential bugs, unhandled edge case, etc. \n {result}"}
]
response = call_openai(messages)
print(f"\nChatGPT: ", end ='')
chatResponse = ''
for chunk in response:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end ='')
        chatResponse += chunk.choices[0].delta.content
messages.append({ 'role': 'assistant', 'content': chatResponse })
userInput = input(f"\n\nUser: ")

while userInput:
    messages.append({"role": "user", "content": userInput})
    response = call_openai(messages)
    print(f"\nChatGPT: ", end ='')
    chatResponse = ''
    for chunk in response:
        if chunk.choices[0].delta.content is not None:
            print(chunk.choices[0].delta.content, end ='')
            chatResponse += chunk.choices[0].delta.content
    messages.append({ 'role': 'assistant', 'content': chatResponse })
    userInput = input(f"\n\nUser: ")
