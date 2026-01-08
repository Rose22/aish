#!/bin/env python

# ----------
# SETTINGS
api_url = "http://localhost:5001/v1"
api_key = "dummy"

ai_prompt = """
You live in a linux shell, helping the user convert natural language into CLI commands.
Based on the description of the command given, generate the command. Output only the command and nothing else. Output only one line.
Make sure to escape characters when appropriate. Do not wrap the command in quotes.

When executing a command that must run as system administrator, prepend "sudo" to the command.

ALWAYS answer with a command. Prefer commands over natural language statements. If you absolutely must answer with a statement instead, for example if the user asks a question that cannot be answered with a command, wrap that statement in an echo statement.
"""

substitutions = {
    "ls": "ls --color",
}

check_prompt = [{"role": "system", "content": "say hi"}]

# --------
# IMPORTS
import os
import sys
import subprocess
import signal
import readline
import platform
import distro
import datetime
import colored
import openai

# --------
# UTILITY FUNCTIONS

def confirm(prompt):
    while True:
        confirmation = input(f"{prompt}? (Y/n)> ").lower()
        if confirmation in ("y", "yes"):
            return True
        elif confirmation in ("n", "no"):
            return False
        else:
            print("please answer yes or no")

def toggle_bool(thebool):
    if thebool:
        thebool = False
    else:
        thebool = True

    return thebool

def process_cmd(cmd):
    cmd_split = cmd.split(" ")

    # process any special commands
    match cmd_split[0].lower():
        case "cd":
            # actually change directory
            os.chdir(" ".join(cmd_split[1:]))
            return False

    # substitute certain commands for different ones
    for orig, subst in substitutions.items():
        for index, word in enumerate(cmd_split):
            if orig.lower() == word.lower():
                cmd_split[index] = subst

    cmd = " ".join(cmd_split)

    return cmd

# disable the Ctrl+C command so that the user can cancel running commands
def signal_handler(sig, frame):
    pass
signal.signal(signal.SIGINT, signal_handler)

using_ai = False
auto = False
hide_cmd = False

# -------------
# MAIN PROGRAM
client = openai.OpenAI(base_url=api_url, api_key=api_key)

print("Welcome to AI Shell! type 'help' for help. Use 'auto' to engage automatic mode.")

print("Connecting to AI..")
try:
    client.chat.completions.create(
        model="model",
        messages=check_prompt
    )
    using_ai = True

    print("Connected!")
except Exception as e:
    print(f"{colored.Fore.orange}Failed to connect to AI! error: {e}{colored.Style.reset}")
    print("normal shell mode engaged")

while True:
    print()

    shell_prompt = f"{colored.Fore.green}AI" if using_ai else f"{colored.Fore.sky_blue_1}shell"
    shell_prompt += colored.Style.reset

    cmd = input(f"{shell_prompt}> ")
    cmd_split = cmd.split(" ")

    match cmd:
        case "exit":
            exit()
            break
        case "auto":
            auto = toggle_bool(auto)
            state = "on" if auto else "off"

            print(f"automatic execution turned {state}")

            if auto:
                if confirm(f"{colored.Fore.red}Also hide commands before running them (DANGEROUS){colored.Style.reset}"):
                    hide_cmd = True
            else:
                hide_cmd = False

        case "connect":
            if using_ai:
                print("already connected!")
                continue

            try:
                client.chat.completions.create(
                    model="model",
                    messages=check_prompt
                )
                using_ai = True
            except Exception as e:
                print(f"failed to connect to AI! error: {e}")
                continue
        case "disconnect":
            if not using_ai:
                print("already disconnected!")

            using_ai = False
        case "help":
            print("""
exit:       exit the shell
auto:       turn on auto execution mode (WARNING: dangerous! disables confirmation before running suggested commands. will still ask for confirmation when running root commands)
connect:    reconnect to the AI in case a disconnection occured
disconnect: disconnect from the AI, switch to an AI-less shell
help:       display help

Type what you want the shell to do, then press enter. The AI will then generate a shell command and ask you if you want to run it.
You can also just type normal shell commands, which will run if the AI doesn't modify the command.
""")
        case "":
            pass
        case _:
            if not using_ai:
                # just execute the command like a normal shell
                os.system(cmd)
                continue

            prompt = [
                {
                    "role": "system",
                    "content": ai_prompt
                },
                {
                    "role": "system",
                    "content": f"User's OS: {platform.system()} ({distro.info().get('id')}). You are currently in directory `{os.getcwd()}`. User's home directory is `{os.path.expanduser('~')}`. The current date is {datetime.datetime.now()}. Files in current directory: {os.listdir()}"
                },
                {
                    "role": "user",
                    "content": cmd
                }
            ]

            try:
                stream = client.chat.completions.create(
                    model="model",
                    messages=prompt,
                    stream=True
                )

                # stream llm's response
                chunks = []
                if not hide_cmd:
                    print(f"{colored.Fore.sky_blue_1}>> ", end="")
                for chunk in stream:
                    chunk_s = chunk.choices[0].delta.content
                    chunks.append(chunk_s)

                    if not hide_cmd:
                        print(chunk_s, end="", flush=True)
                if not hide_cmd:
                    print(colored.Style.reset)

                ai_cmd = "".join(chunks)
                ai_cmd_split = ai_cmd.split(" ")
            except Exception as e:
                print(f"failed to connect to AI! error: {e}")
                using_ai = False
                continue

            env_vars = os.environ.copy()

            if ai_cmd.lower().strip() == cmd.lower().strip():
                # just run it if it's the same as what the user typed - it's probably a shell command the user entered

                ai_cmd = process_cmd(ai_cmd)
                if ai_cmd:
                    subprocess.run(ai_cmd, env=env_vars, shell=True, text=True)
            else:
                if ai_cmd_split[0].lower() in ("sudo", "su"):
                    if hide_cmd:
                        print(f">> {ai_cmd}")

                    if not confirm(f"{colored.Fore.red}really execute as root{colored.Style.reset}"):
                        continue

                if not auto:
                    if not confirm(f"{colored.Fore.green}execute{colored.Style.reset}"):
                        continue

                ai_cmd = process_cmd(ai_cmd)
                if ai_cmd:
                    subprocess.run(ai_cmd, env=env_vars, shell=True, text=True)
