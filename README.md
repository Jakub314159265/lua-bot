# Lua Discord Bot

A Discord bot that runs Lua code safely using Docker and Lupa.

## Features

- Runs Lua code in a sandbox (no file/network/system access)
- 5 second timeout, 128MB memory limit
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
3. Start the bot:
   ```
   python bot.py
   ```

## Usage

- Inline: Wrap code in  ` %```lua ... ``` `
- Command: `~ print("Hello, World!")`

## Example

```
%```lua
print("Hello, World!")
print(math.pi)
print(string.upper("lua"))
%```
```

## Security

- Docker sandbox: no network, no files, limited memory/CPU, short timeout
- Only safe Lua libraries are available
## Available Lua Functions

- **Math**: `math.abs`, `math.sin`, `math.cos`, etc.
- **String**: `string.find`, `string.gsub`, `string.sub`, etc.
- **Table**: `table.insert`, `table.remove`, `table.sort`, etc.
- **Basic**: `print`, `tonumber`, `tostring`, `pairs`, `ipairs`, etc.

## Security

- Runs in isolated Docker container
- No network access
- No file system access
- Limited memory and CPU
- Execution timeout = 5s
- Sandboxed Lua environment

## Examples

```lua
%'
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
end
'%
```
