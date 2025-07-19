# Lua Discord Bot

A Discord bot that runs Lua code safely using Podman and Lupa.

## Features

- Runs Lua code in a sandbox (no file/network/system access)
- 10 second timeout (can be changed by `TIMEOUT` constant), 64MB memory limit
- Supports most standard Lua functions: math, string, table, coroutine, utf8, print

## Setup

1. Install requirements:
   ```
   pip install -r requirements.txt
   ```
2. Add your Discord bot token to `.env`:
   ```
   DISCORD_BOT_TOKEN=your_token_here
   ```
3. Install Podman (if not yet installed):
   ```bash
   # On Ubuntu/Debian
   sudo apt install podman
   
   # On Fedora/RHEL
   sudo dnf install podman
   
   # On Arch Linux
   sudo pacman -S podman
   ```

4. It is recommended to build the Podman image manually by running:
   ```bash
   podman build -t lua-bot-p-img .
   ```

5. Start the bot:
   ```
   python bot.py
   ```

## Usage

- Wrap code in  ` %```<code> ``` `
- or: `~~ <code>`
- `~help` for help

## Example of `~~` usage

```lua
~~print("Hello, World!")
print(math.pi)
print(string.upper("lua"))
```

## Available Lua Functions

- **Math**: `math.abs`, `math.sin`, `math.cos`, etc.
- **String**: `string.find`, `string.gsub`, `string.sub`, etc.
- **Table**: `table.insert`, `table.remove`, `table.sort`, etc.
- **Basic**: `print`, `tonumber`, `tostring`, `pairs`, `ipairs`, etc.
- `os.clock`, `os.time`, `os.date`

## Security

- Runs in isolated Podman container
- No network access
- No file system access
- Limited memory (64MB) and CPU (0.25 cores)
- Execution timeout = 10 seconds (can be changed)
- Sandboxed Lua environment with restricted functions

## Example

```lua
%```
-- Math calculations
print(math.sqrt(16))
print(math.pi)

-- String manipulation
local str = "Hello World"
print(string.upper(str))
print(string.sub(str, 1, 5))

-- Tables
local t = {1, 2, 3, 4, 5}
table.insert(t, 6)
for i, v in ipairs(t) do
    print(i, v)
end```
```

## Technical Details

- Built on Python 3.12 slim image
- Uses Lupa for Python-Lua integration
- Runs as non-root user (UID 1000) for security
- Container is read-only with no network access
- Memory and CPU limits enforced by Podman

## Invite
[here](https://discord.com/oauth2/authorize?client_id=1394401891538046976&permissions=551903422528&integration_type=0&scope=bot)
