# Lua Discord Bot

A Discord bot that safely executes untrusted Lua code using Docker sandboxing and Lupa.

## Features

- **Safe Execution**: Runs Lua code in a Docker container with limited resources
- **Sandboxed Environment**: Only allows safe Lua functions (no file I/O, network, or system access)
- **Timeout Protection**: 3-second execution limit
- **Memory Limits**: 128MB memory constraint
- **Easy Usage**: Wrap code in `%'` and `'%` or use `!lua` command

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create `.env` file with your Discord bot token:
   ```
   DISCORD_BOT_TOKEN=your_bot_token_here
   ```

3. Build Docker image:
   ```bash
   docker build -t lua-bot .
   ```

4. Run the bot:
   ```bash
   python bot.py
   ```

## Usage

### In Discord Messages
Wrap Lua code in `%'` and `'%`:
```
%'print("Hello, World!")'%
```

### Using Commands
```
!lua print("Hello, World!")
!help_lua
```

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
- Execution timeout
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
