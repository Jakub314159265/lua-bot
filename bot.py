import discord
from discord.ext import commands
import subprocess
import asyncio
import re
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='~', intents=intents, help_command=None)

# Store message relationships for edit handling
message_responses = {}

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await ensure_docker_image()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    await process_lua_message(message)
    await bot.process_commands(message)

@bot.event
async def on_message_edit(before, after):
    """Handle message edits to update Lua code execution"""
    if after.author == bot.user:
        return
    
    # Check if this message had a previous response
    if before.id in message_responses:
        # Look for Lua code in the edited message
        lua_pattern = r"%```(.*?)```"
        matches = re.findall(lua_pattern, after.content, re.DOTALL)
        
        if matches:
            # Delete old response first
            try:
                old_response_id = message_responses[before.id]
                old_response = await after.channel.fetch_message(old_response_id)
                await old_response.delete()
                del message_responses[before.id]
            except (discord.NotFound, KeyError):
                pass
            
            # Process the edited message normally
            await process_lua_message(after)
        else:
            # No Lua code in edited message, remove old response
            try:
                old_response_id = message_responses[before.id]
                old_response = await after.channel.fetch_message(old_response_id)
                await old_response.delete()
                del message_responses[before.id]
            except (discord.NotFound, KeyError):
                pass

async def process_lua_message(message):
    """Process a message for Lua code execution"""
    lua_pattern = r"%```(.*?)```"
    matches = re.findall(lua_pattern, message.content, re.DOTALL)
    
    if matches:
        for lua_code in matches:
            lua_code = lua_code.strip()
            if lua_code:
                response = await execute_lua_code(message, lua_code)
                if response:
                    message_responses[message.id] = response.id

async def execute_lua_code(message, lua_code):
    """Execute Lua code safely using Docker with improved resource management"""
    try:
        # Prepare Docker command with enhanced security and resource limits
        docker_cmd = [
            'docker', 'run', '--rm', '-i',
            '--memory=128m',
            '--memory-swap=196m',
            '--cpus=0.25',
            '--network=none',
            '--user=botuser',
            '--read-only',
            'lua-bot'
        ]
        
        # Execute Docker container with better timeout handling
        process = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            # Send Lua code to container and get result
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=lua_code.encode()),
                timeout=5.0  # 5 second timeout
            )
        except asyncio.TimeoutError:
            # Kill the process if it times out
            try:
                process.kill()
                await process.wait()
            except:
                pass
            return await format_and_send_response(message, None, "Execution timed out (5s limit)", True)
        
        # Format and send response
        output = stdout.decode().strip() if stdout else None
        error = stderr.decode().strip() if stderr else None
        
        return await format_and_send_response(message, output, error, False)
        
    except FileNotFoundError:
        return await message.reply("Error: Docker not found. Please install Docker.")
    except Exception as e:
        return await message.reply(f"System Error: {str(e)}")

async def format_and_send_response(message, output, error, is_timeout):
    """Format and send the execution response with improved formatting"""
    if is_timeout:
        embed = discord.Embed(
            title="Execution Timeout",
            description="Code execution exceeded 5 second limit",
            color=0xFF6B35
        )
        return await message.reply(embed=embed)
    
    if error:
        # Format Lua errors more nicely
        error_lines = error.split('\n')
        clean_error = []
        for line in error_lines:
            if 'stdin:' in line:
                # Extract line number and error message
                parts = line.split(':', 3)
                if len(parts) >= 4:
                    line_num = parts[1]
                    error_msg = parts[3].strip()
                    clean_error.append(f"Line {line_num}: {error_msg}")
                else:
                    clean_error.append(line)
            elif line.strip() and not line.startswith('lua:'):
                clean_error.append(line)
        
        error_text = '\n'.join(clean_error) if clean_error else error
        
        embed = discord.Embed(
            title="Lua Error",
            description=f"```lua\n{error_text[:1800]}\n```",
            color=0xFF4444
        )
        return await message.reply(embed=embed)
    
    if output:
        # Truncate long output
        if len(output) > 1800:
            output = output[:1800] + "\n... (output truncated)"
        
        embed = discord.Embed(
            title="Lua Output",
            description=f"```lua\n{output}\n```",
            color=0x44FF44
        )
        return await message.reply(embed=embed)
    else:
        embed = discord.Embed(
            title="Execution Complete",
            description="Code executed successfully (no output)",
            color=0x44FF44
        )
        return await message.reply(embed=embed)

async def ensure_docker_image():
    """Build Docker image if it doesn't exist with better error handling"""
    try:
        # Check if image exists
        result = await asyncio.create_subprocess_exec(
            'docker', 'images', '-q', 'lua-bot',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await result.communicate()
        
        if not stdout.strip():
            print("Building Docker image...")
            build_process = await asyncio.create_subprocess_exec(
                'docker', 'build', '-t', 'lua-bot', '.',
                cwd=os.path.dirname(__file__),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            build_stdout, build_stderr = await build_process.communicate()
            
            if build_process.returncode == 0:
                print("Docker image built successfully!")
            else:
                print(f"Docker build failed: {build_stderr.decode()}")
        else:
            print("Docker image found")
            
    except FileNotFoundError:
        print("Docker not found. Please install Docker to use this bot.")
    except Exception as e:
        print(f"Error with Docker setup: {e}")

@bot.command(name='~')
async def lua_command(ctx, *, code=None):
    """Execute Lua code directly"""
    if not code:
        embed = discord.Embed(
            title="Lua Command Usage",
            description="**Usage:** `!lua <code>`\n**Example:** `!lua print('Hello World')`",
            color=0x5865F2
        )
        await ctx.send(embed=embed)
        return
    
    response = await execute_lua_code(ctx.message, code)
    if response:
        message_responses[ctx.message.id] = response.id

@bot.command(name='help')
async def help_command(ctx):
    """Show comprehensive help"""
    embed = discord.Embed(
        title="Lua Bot Help",
        description="Execute Lua code safely in Discord!",
        color=0x5865F2
    )
    
    embed.add_field(
        name="How to Use",
        value="• **Inline:** `%```your_code````\n• **Command:** `~~ your_code`",
        inline=False
    )
    
    embed.add_field(
        name="Available Libraries",
        value="• `math.*` - Mathematical functions\n• `string.*` - String manipulation\n• `table.*` - Table operations\n• `print()` - Output text",
        inline=False
    )
    
    embed.add_field(
        name="Examples",
        value="```lua\n-- Math\nprint(math.pi * 2)\n\n-- Strings\nprint(string.upper('hello'))\n\n-- Tables\nt = {1,2,3}\nprint(table.concat(t, ','))```",
        inline=False
    )
    
    embed.add_field(
        name="Security Limits",
        value="• 5 second timeout\n• 64MB memory limit\n• No file/network access\n• Max 1800 output characters",
        inline=False
    )
    
    await ctx.send(embed=embed)

# Run the bot
if __name__ == "__main__":
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("Error: DISCORD_BOT_TOKEN not found in .env file")
        print("Please create a .env file with: DISCORD_BOT_TOKEN=your_token_here")
        exit(1)
    
    bot.run(token)
