#!/bin/env python

# ----------
# SETTINGS
api_url = "http://localhost:5001/v1"
api_key = "dummy"

ai_prompt = """
You are AI.sh, an AI shell assistant. You live in a linux shell, helping the user convert natural language into CLI commands.
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
import prompt_toolkit
import glob
import platform
import datetime
import colored
import openai

from pygments.lexers.shell import BashLexer

# --------
# UTILITY FUNCTIONS

def confirm(prompt):
    while True:
        confirmation = input(f"{prompt}? (y/n)> ").lower()
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
    cmd = cmd.strip("`")
    cmd_split = cmd.split(" ")

    # process any special commands
    match cmd_split[0].lower():
        case "cd":
            # actually change directory
            target_path = os.path.expanduser(" ".join(cmd_split[1:]))

            # default to home dir upon "cd" command without a target dir
            if not target_path:
                target_path = os.path.expanduser("~")

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

class TabCompleter(prompt_toolkit.completion.Completer):
    def get_completions(self, document, complete_event):
        completion_style = "bg:ansiblack fg:ansiwhite"

        text = document.text_before_cursor
        words = text.strip().split()

        # List of available commands (case-insensitive)
        commands = ("help", "connect", "disconnect", "auto", "hide")

        # Suggest commands if first word is empty or not a path
        if not words or (len(words) == 1 and not words[0].startswith('.') and not words[0].startswith(os.path.sep)):
            for cmd in commands:
                if cmd.lower().startswith(text.lower()):
                    yield prompt_toolkit.completion.Completion(cmd, start_position=-len(text), style=completion_style)

            if len(words) == 0:
                return

        # Try to do file completion on the last word
        base_path = os.getcwd()
        try:
            # Determine what we're completing
            if len(words) > 0:
                last_word = words[-1]
            else:
                last_word = ""

            # If there's no text or only whitespace, suggest current directory
            if len(text) == 0 or text.isspace():
                matches = os.listdir(base_path)
                start_pos = 0
            else:
                # Check if the user typed a space after the last word → suggests files in current dir
                if text.endswith(' '):
                    # User has typed a space → treat as starting a new filename
                    matches = os.listdir(base_path)
                    start_pos = 0
                else:
                    # Otherwise, try to glob based on partial path
                    if last_word.startswith('/') or last_word.startswith('~'):
                        path_to_search = os.path.expanduser(last_word)
                    else:
                        path_to_search = os.path.join(base_path, last_word)

                    matches = []
                    pattern = f"{path_to_search}*"
                    for f in glob.glob(pattern):
                        if os.path.isdir(f) or os.path.isfile(f):
                            # Show only basename if it's in current directory
                            if os.path.dirname(f) == base_path:
                                f = os.path.basename(f)

                            matches.append(f.replace(os.path.expanduser("~"), "~"))

                    start_pos = -len(last_word)

            # add trailing slash to directories
            for index, match in enumerate(matches):
                if os.path.isdir(match):
                    matches[index] = match+"/"

            # Yield all matching completions
            for match in matches:
                yield prompt_toolkit.completion.Completion(match, start_position=start_pos, style=completion_style)
        
        except Exception as e:
            pass

using_ai = False
auto = False
hide_cmd = False

# get most important env variables
env_vars_to_pass_on = (
    "USER",
    "HOME",
    "PATH",
    "TERM",
    "COLORTERM",
    "LANG",
    "EDITOR",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CURRENT_DESKTOP",
)
env_vars_display = {}
for key, value in os.environ.items():
    if key in env_vars_to_pass_on:
        env_vars_display[key] = value

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

print_color("Welcome to AI.sh! type 'help' for help. Use 'auto' to engage automatic mode.", colored.Fore.yellow)

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
    print("Normal shell mode engaged. Type 'connect' to reconnect.")

prompt_style = prompt_toolkit.styles.Style.from_dict({
    'connected': 'fg:ansigreen',
    'disconnected': 'fg:skyblue',
    'reset': 'fg:default',
})

session = prompt_toolkit.PromptSession(
    completer=prompt_toolkit.completion.ThreadedCompleter(
        TabCompleter()
    ),
    history=prompt_toolkit.history.FileHistory(os.path.expanduser("~/.aish_history")),
    auto_suggest=prompt_toolkit.auto_suggest.AutoSuggestFromHistory(),
    style=prompt_style,
    complete_style=prompt_toolkit.shortcuts.CompleteStyle.COLUMN,
    complete_while_typing=False
)

env_vars = os.environ.copy()

while True:
    try:
        print()

        path_display = os.getcwd().replace(os.path.expanduser("~"), "~")
        # shell_prompt = f"{colored.Fore.green}AI.sh" if using_ai else f"{colored.Fore.sky_blue_1}sh"
        # shell_prompt += colored.Style.reset
        # shell_prompt += f" ({path_display})"

        # Build prompt text using HTML formatting
        display_name = "<connected>AI.sh</connected>" if using_ai else "<disconnected>sh</disconnected>"
        shell_prompt = prompt_toolkit.formatted_text.HTML(
            f"{display_name} ({path_display})> "
        )

        #cmd = session.prompt(shell_prompt, lexer=prompt_toolkit.lexers.PygmentsLexer(BashLexer))
        # lexer disabled for now
        cmd = session.prompt(shell_prompt)
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
                    print("Normal shell mode engaged. Type 'connect' to reconnect.")
                    continue
            case "disconnect":
                if not using_ai:
                    print("already disconnected!")
                    continue

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

                if not using_ai:
                    # just execute the command like a normal shell

                    # support basic file targeting
                    if relevant_paths:
                        for path in relevant_paths:
                            print(path)
                        # dont execute the command if files were targeted with @
                        continue

                    cmd = process_cmd(cmd)
                    if cmd:
                        subprocess.run(cmd, env=env_vars, shell=True, text=True)
                    continue

                if relevant_paths:
                    relevant_paths = f"\nYou can find target files at one of these paths: {relevant_paths}"

                prompt = [
                    {
                        "role": "system",
                        "content": f"You are currently in directory `{os.getcwd()}`.\nUser's home directory is `{os.path.expanduser('~')}`.\n{relevant_paths}\nEnvironment variables: {env_vars_display}\nThe current date is {datetime.datetime.now().strftime('%b %d %Y %H:%M:%S')}.\nFiles in current directory: {os.listdir()}.\nSystem information: {sys_info}"
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
                        if chunk_s:
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

                if ai_cmd.lower().strip() == cmd.lower().strip():
                    # just run it if it's the same as what the user typed - it's probably a shell command the user entered

                    ai_cmd = process_cmd(ai_cmd)
                    if ai_cmd:
                        subprocess.run(ai_cmd, env=env_vars, shell=True, text=True)
                else:
                    proceed = False

                    if ai_cmd_split[0].lower() in ("sudo", "su"):
                        if hide_cmd:
                            print(f">> {ai_cmd}")

                        if not confirm(f"{colored.Fore.red}really execute as root{colored.Style.reset}"):
                            continue

                        proceed = True

                    if not auto and not proceed:
                        if not prompt_toolkit.shortcuts.confirm(f"execute?"):
                            continue

                    ai_cmd = process_cmd(ai_cmd)
                    if ai_cmd:
                        subprocess.run(ai_cmd, env=env_vars, shell=True, text=True)
    except KeyboardInterrupt:
        continue
    except Exception as e:
        print_color(f"error: {e}", colored.Fore.red)
        pass
