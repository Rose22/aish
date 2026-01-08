#!/bin/env python

# ----------
# SETTINGS
api_url = "http://localhost:5001/v1"
api_key = "dummy"

ai_prompt = """
You are AIsh, an AI shell assistant. You live in a linux shell, helping the user convert natural language into CLI commands.
Based on the description of the command given, generate the command. Output only the command and nothing else. Output only one line.
Make sure to escape characters when appropriate. Do not wrap the command in quotes.

When executing a command that must run as system administrator, prepend "sudo" to the command.
You must ALWAYS refuse to execute commands that will harm the user's system.

ALWAYS answer with a command. Prefer commands over natural language statements. If you absolutely must answer with a statement instead, for example if the user asks a question that cannot be answered with a command, wrap that statement in an echo statement.
"""

substitutions = {
    "ls": "ls --color",
}

check_prompt = [{"role": "system", "content": "say hi"}]

# --------
# IMPORTS
import os
import platform
import sys
import subprocess
import signal
import readline
import platform
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

def toggle_bool(thebool, description="feature"):
    if thebool:
        thebool = False
        print(f"{colored.Fore.sky_blue_1}{description}{colored.Style.reset} turned off")
    else:
        thebool = True
        print(f"{colored.Fore.sky_blue_1}{description}{colored.Style.reset} turned on")

    return thebool

def print_color(message, color, **kwargs):
    print(f"{color}{message}{colored.Style.reset}", *kwargs)

def process_cmd(cmd):
    cmd_split = cmd.split(" ")

    # process any special commands
    match cmd_split[0].lower():
        case "cd":
            # actually change directory
            target_path = os.path.expanduser(" ".join(cmd_split[1:]))
            os.chdir(target_path)
            return False
        case "exit":
            exit()

    # substitute certain commands for different ones
    for orig, subst in substitutions.items():
        for index, word in enumerate(cmd_split):
            if orig.lower() == word.lower():
                cmd_split[index] = subst

    cmd = " ".join(cmd_split)

    return cmd
import os

def recursive_list(root_dir=".", max_depth=3):
    """
    Recursively list files and directories up to max_depth levels deep.
    
    Args:
        root_dir (str): The root directory path.
        max_depth (int): Maximum depth to traverse (default is 3).
        
    Returns:
        list: List of full paths (strings) for files and directories.
    """
    items = []
    
    def _list_items(current_path, current_depth):
        #if current_depth > max_depth:
        #    return
        
        try:
            for item in os.listdir(current_path):
                item_path = os.path.join(current_path, item)
                items.append(item_path)  # Add the path regardless of type
                
                # If it's a directory, go deeper (if allowed)
                if os.path.isdir(item_path) and current_depth < max_depth:
                    _list_items(item_path, current_depth + 1)
                    
        except PermissionError:
            # Skip inaccessible directories
            pass
    
    _list_items(root_dir, 0)  # Start at depth 0 (root)
    return items

# --------
# INITIALIZATION

# disable the Ctrl+C command so that the user can cancel running commands
def signal_handler(sig, frame):
    pass
signal.signal(signal.SIGINT, signal_handler)

# enable tab completion
readline.parse_and_bind("tab: complete")

using_ai = False
auto = False
hide_cmd = False

sys_info = {
    "os": platform.system(),
    "os_release": platform.release(),
    "platform": platform.platform(),
    "architecture": platform.machine() if platform.machine() else "unknown",
    "hostname": platform.node(),
    "system_root": os.listdir("/"),
}

# -------------
# MAIN PROGRAM
client = openai.OpenAI(base_url=api_url, api_key=api_key)

print_color("Welcome to AIsh! type 'help' for help. Use 'auto' to engage automatic mode.", colored.Fore.yellow)

print_color("Connecting to AI..", colored.Fore.sky_blue_1)
try:
    client.chat.completions.create(
        model="model",
        messages=check_prompt
    )
    using_ai = True

    print_color("Connected!", colored.Fore.green)
except Exception as e:
    print_color(f"Failed to connect to AI! error: {e}", colored.Fore.red)
    print("normal shell mode engaged")

while True:
    try:
        print()

        path_display = os.getcwd().replace(os.path.expanduser("~"), "~")
        shell_prompt = f"{colored.Fore.green}AI" if using_ai else f"{colored.Fore.sky_blue_1}shell"
        shell_prompt += colored.Style.reset
        shell_prompt += f" ({path_display})"

        cmd = input(f"{shell_prompt}> ")
        cmd_split = cmd.split(" ")

        match cmd:
            case "exit":
                exit()
                break
            case "auto":
                auto = toggle_bool(auto, "automatic command execution")
                if not auto:
                    hide_cmd = False
            case "hide":
                if not auto:
                    print("turn on automatic execution first with 'auto'")
                    continue

                hide_cmd = toggle_bool(hide_cmd, "command hiding")
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
                    print_color("connected", colored.Fore.green)
                except Exception as e:
                    print_color(f"Failed to connect to AI! error: {e}", colored.Fore.red)
                    continue
            case "disconnect":
                if not using_ai:
                    print("already disconnected!")

                using_ai = False
                print_color("disconnected", colored.Fore.sky_blue_1)
            case "help":
                print("""
    exit:       exit the shell
    auto:       toggle auto execution mode (WARNING: dangerous! disables confirmation before running suggested commands. will still ask for confirmation when running root commands)
    hide:       toggle command hiding (hides generated commands prior to running them)
    connect:    reconnect to the AI in case a disconnection occured
    disconnect: disconnect from the AI, switch to an AI-less shell
    help:       display help

    Type what you want the shell to do, then press enter. The AI will then generate a shell command and ask you if you want to run it.
    You can also just type normal shell commands, which will run if the AI doesn't modify the command.

    You can find and target files within the current folder (even nested folders) by prepending the filename with a '@'. Example: cat @aish.py will search for the file and then read it.
    """.strip())
            case "":
                pass
            case _:
                if not using_ai:
                    # just execute the command like a normal shell
                    os.system(cmd)
                    continue

                # recursively retrieve the file structure from the current directory and use it to find and target any paths the user has specified with a @
                dir_tree = False
                relevant_paths = []
                for word in cmd_split:
                    if word[0] == "@":
                        print(f"{colored.Fore.sky_blue_1}>> targeting {word[1:]}{colored.Style.reset}")
                        if not dir_tree:
                            dir_tree = recursive_list(".", max_depth=3)

                        for item in dir_tree:
                            if word[1:] in item:
                                relevant_paths.append(item)

                if relevant_paths:
                    relevant_paths = f"\nYou can find target files at one of these paths: {relevant_paths}"

                prompt = [
                    {
                        "role": "system",
                        "content": f"You are currently in directory `{os.getcwd()}`.\nUser's home directory is `{os.path.expanduser('~')}`.\n{relevant_paths}\nThe current date is {datetime.datetime.now().strftime('%b %d %Y %H:%M:%S')}.\nFiles in current directory: {os.listdir()}.\nSystem information: {sys_info}"
                    },
                    {
                        "role": "system",
                        "content": ai_prompt
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
                    print_color(f"Failed to connect to AI! error: {e}", colored.Fore.red)
                    using_ai = False

                    print("use `connect` to reconnect to the AI when ready.")
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
    except Exception as e:
        print_color(f"error: {e}", colored.Fore.red)
        pass
