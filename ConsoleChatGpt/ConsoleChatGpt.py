import os
import openai

def get_env_var(name):
    env_var = os.getenv(name)
    if not env_var:
        raise Exception('No {} environment variable'.format(name))
    return env_var

def call_openai(messages):
    response = openai.ChatCompletion.create(
      model="gpt-3.5-turbo",
      messages = messages
    )
    return response

RED = "\033[1;31m"
GREEN = "\033[0;32m"
BLUE = "\033[0;34m"
RESET = "\033[0;0m"

print('Getting environment variables')
api_key = get_env_var("OPENAI_API_KEY")
organization = get_env_var("OPENAI_ORG")
openai.organization = organization
openai.api_key = api_key

userInput = input(f"\n{BLUE}System:{RESET} ") or "You are a helpful assistant."
messages = [
    {"role": "system", "content": userInput},
]
print('You can now start chatting')
userInput = input(f"\n{RED}User:{RESET} ")
while userInput:
    messages.append({"role": "user", "content": userInput})
    response = call_openai(messages)
    chatResponse = response['choices'][0]['message']
    print(f"\n{GREEN}ChatGPT:{RESET} {chatResponse['content']}")
    messages.append(chatResponse)
    userInput = input(f"\n{RED}User:{RESET} ")