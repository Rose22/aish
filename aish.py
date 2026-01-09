#!/bin/env python

# ----------
# SETTINGS

substitutions = {
    "ls": "ls --color",
}

check_prompt = [{"role": "system", "content": "say hi"}]

# --------
# IMPORTS
import yaml
import os
import platform
import sys
import subprocess
import signal
import traceback
import prompt_toolkit
import glob
import datetime
import colored
import openai

from pygments.lexers.shell import BashLexer

# --------
# UTILITY FUNCTIONS

dir_cache = {}

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
            return None
        case "exit":
            exit()
            return None

    # substitute certain commands for different ones
    for orig, subst in substitutions.items():
        for index, word in enumerate(cmd_split):
            if orig.lower() == word.lower():
                cmd_split[index] = subst

    cmd = " ".join(cmd_split)

    return cmd

def ai_connect(config):
    print_color("Connecting to AI..", colored.Fore.sky_blue_1)
    client = openai.OpenAI(base_url=config.data.get("api_url"), api_key=config.data.get("api_key"))

    try:
        client.chat.completions.create(
            model=config.data.get("api_model"),
            messages=check_prompt
        )

        print_color("Connected!", colored.Fore.green)
        return client

    except Exception as e:
        print_color(f"Failed to connect to AI! error: {e}", colored.Fore.red)
        print("Falling back to normal shell. Type 'connect' to reconnect. Type 'settings' to edit your settings.")

        return None

def recursive_list(root_dir=".", max_depth=5):
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
        try:
            with os.scandir(current_path) as folder:
                for file in folder:
                    items.append(file.path)
                    if file.is_dir() and current_depth < max_depth:
                        _list_items(file.path, current_depth + 1)
        except:
            # Skip inaccessible things
            pass
    
    _list_items(root_dir, 0)  # Start at depth 0 (root)
    return items

def get_dir_list(path):
    """
        caches recursive lists in memory so they don't need to keep being re-fetched
    """

    if path not in dir_cache:
        dir_cache[path] = recursive_list(path)
    return dir_cache[path]

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
        commands = ("help", "settings", "config", "connect", "disconnect", "auto", "hide")

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

class Config:
    path = f"{os.path.expanduser('~')}/.aish.conf"
    default_data = {
        "api_url": "http://localhost:12434/v1",
        "api_key": "key_here",
        "api_model": "qwen3",
        "autoconnect": True,
        "show_intro": True,
        "intro": f"Welcome to AI.sh! type 'help' for help. Type 'settings' to edit the configuration file. Use 'auto' to engage automatic mode.\nThe AI.sh configuration file is here: {path}\nPlease edit the configuration file to suit your preferences, and to set up the AI connection!",
        "prompt": """
You are AI.sh, an AI shell assistant. You live in a linux shell, helping the user convert natural language into CLI commands.

Based on the description of the command given, generate the command. Output only the command and nothing else. Output only one line.
Make sure to escape characters when appropriate. Do not wrap the command in quotes.

When executing a command that must run as system administrator, prepend "sudo" to the command.
You must ALWAYS refuse to execute commands that will harm the user's system.

ALWAYS answer with a command. Prefer commands over natural language statements. If you absolutely must answer with a statement instead, for example if the user asks a question that cannot be answered with a command, wrap that statement in an echo statement.
"""
    }

    def __init__(self):
        self.first_run = False
        if not os.path.exists(self.path):
            self.first_run = True
        self.data = {}

    def write_defaults(self):
        with open(self.path, 'w') as f:
            # default config data
            f.write(yaml.dump(self.default_data))
        return True

    def load(self):
        if not os.path.exists(self.path):
            self.data = self.default_data
            return False

        try:
            with open(self.path, 'r') as f:
                self.data = yaml.safe_load(f)
        except Exception as e:
            print_color(f"warning: config wasn't loaded (error: {e}).\ndefaulting to default settings.", colored.Fore.red)
            self.data = self.default_data

    def launch_editor(self):
        while True:
            os.system(f"{os.environ.get('EDITOR', 'nano')} {self.path}")
            try:
                with open(self.path, 'r') as f:
                    self.data = yaml.safe_load(f)
                print("Config file was valid. Your settings have been saved and loaded into the current session!")

                return True
            except:
                print("Your config isn't valid. Press Enter to go back into the editor and edit it again!")
                input()

# load config
config = Config()
config.load()

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
client = None

if config.data.get("show_intro"):
    print_color(config.data.get("intro"), colored.Fore.yellow)

skip_ai_connect = False
if config.first_run:
    config.write_defaults()
    if prompt_toolkit.shortcuts.confirm("Would you like to set up the configuration now?"):
        config.launch_editor()
    else:
        print("Okay. You can launch the editor at any time by typing 'settings' or 'config'.")
        print("Once you've set things up, type 'connect' to connect to the AI.")
        skip_ai_connect = True

if not skip_ai_connect and config.data.get("autoconnect"):
    client = ai_connect(config)
    if client:
        using_ai = True

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
        path_display = os.getcwd().replace(os.path.expanduser("~"), "~")

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
            case "auto":
                if not auto:
                    if confirm(f"{colored.Fore.red}Warning: automatic mode will run the AI's suggested commands without your confirmation! Are you sure{colored.Style.reset}"):
                        auto = toggle_bool(auto, "automatic command execution")
                    hide_cmd = False
                else:
                    auto = toggle_bool(auto, "automatic command execution")
            case "hide":
                if not auto:
                    print("turn on automatic execution first with 'auto'")
                    continue

                hide_cmd = toggle_bool(hide_cmd, "command hiding")
            case "settings":
                config.launch_editor()
            case "config":
                config.launch_editor()
            case "connect":
                if using_ai:
                    print("already connected!")
                    continue

                client = ai_connect(config)
                if client:
                    using_ai = True
            case "disconnect":
                if not using_ai:
                    print("already disconnected!")
                    continue

                using_ai = False
                print_color("disconnected", colored.Fore.sky_blue_1)
            case "help":
                print("""
exit:       exit the shell
settings:   edit the settings
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
                # parse one-word commands
                if len(cmd_split) == 1:
                    match cmd_split[0]:
                        case "cd":
                            os.chdir(os.path.expanduser("~"))
                            continue

                # recursively retrieve the file structure from the current directory and use it to find and target any paths the user has specified with a @
                activated_target = False
                dir_tree = False
                relevant_paths = []
                for index, word in enumerate(cmd_split):
                    if word[0] == "@":
                        if not activated_target:
                            activated_target = True

                        print(f"{colored.Fore.sky_blue_1}>> targeting {word[1:]}{colored.Style.reset}")
                        if not dir_tree:
                            dir_tree = get_dir_list(os.getcwd())

                        found_items = []
                        for item in dir_tree:
                            if word[1:] in os.path.basename(item):
                                if os.path.isdir(item):
                                    # add trailing slash
                                    item += "/"

                                found_items.append(item)
                                relevant_paths.append(item)

                        if not found_items:
                            print(f"No paths found for {word}")
                            continue

                        if not using_ai:
                            # if AI is disconnected, let the user decide the best path
                            choices = [(choice, choice) for choice in found_items]

                            cmd_split[index] = prompt_toolkit.shortcuts.choice(
                                message=f"Please choose a target for {word}:",
                                options=choices,
                                default=word
                            )
                            continue

                if activated_target and not relevant_paths:
                    print("No files or folders found")
                    continue

                # re-join modified command
                cmd = " ".join(cmd_split)

                if not using_ai:
                    # just execute the command like a normal shell
                    cmd = process_cmd(cmd)
                    if cmd:
                        subprocess.run(cmd, env=env_vars, shell=True, text=True)
                    continue

                if relevant_paths:
                    # let the AI decide the best path
                    relevant_paths = f"\nYou can find target files at one of these paths: {relevant_paths}"

                prompt = [
                    {
                        "role": "system",
                        "content": f"You are currently in directory `{os.getcwd()}`.\nUser's home directory is `{os.path.expanduser('~')}`.\n{relevant_paths}\nEnvironment variables: {env_vars_display}\nThe current date is {datetime.datetime.now().strftime('%b %d %Y %H:%M:%S')}.\nFiles in current directory: {os.listdir()}.\nSystem information: {sys_info}"
                    },
                    {
                        "role": "system",
                        "content": config.data.get("prompt")
                    },
                    {
                        "role": "user",
                        "content": cmd
                    }
                ]

                try:
                    stream = client.chat.completions.create(
                        model=config.data.get("api_model"),
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
                    continue

                skip_confirm = False

                # check generated command for unsafe instructions
                unsafe = False
                for word in ai_cmd_split:
                    if word.lower() in ("rm", "del", "delete", "-delete", "--delete", "remove", "-r", "-rf", "dd", "wipe", "shred", "mkfs", "format", "fdisk", "parted", "sh", "bash", "zsh", "csh", "fish", "reboot", "shutdown", "poweroff", "halt"):
                        unsafe = True

                if unsafe:
                    if hide_cmd:
                        print_color(f">> {ai_cmd}", colored.Fore.red)

                    if not confirm(f"{colored.Fore.red}Warning: Generated command contains potentially unsafe instructions! Are you sure?{colored.Style.reset}"):
                        continue

                # ask for extra confirmation if the command is a sudo command
                if ai_cmd_split[0].lower() in ("sudo", "su"):
                    if hide_cmd:
                        print(f">> {ai_cmd}")

                    if not confirm(f"{colored.Fore.red}really execute as root{colored.Style.reset}"):
                        continue

                    skip_confirm = True

                if not auto and not skip_confirm:
                    if not prompt_toolkit.shortcuts.confirm("execute?"):
                        continue

                # finally, after all those safety checks, go ahead and execute
                ai_cmd = process_cmd(ai_cmd)
                if ai_cmd:
                    subprocess.run(ai_cmd, env=env_vars, shell=True, text=True)
    except KeyboardInterrupt:
        continue
    except Exception as e:
        print_color(f"error: {e}", colored.Fore.red)
        traceback.print_exc()
        pass
    finally:
        print()
