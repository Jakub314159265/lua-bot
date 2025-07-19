import discord
from discord.ext import commands
import asyncio
import re
import os
import json
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='~', intents=intents, help_command=None)
MAX_FILE_SIZE = 8 * 1024 * 1024

message_responses = {}
CONTAINER_NAME = "lua-bot-p"
IMAGE_NAME = "lua-bot-p-img"
PREAMBLE_FILE = "preamble.json"

TIMEOUT = 10

# preamble as a list
preamble_code = []

# colors
COLOR_SYSTEM_ERROR = 0xFF4444
COLOR_SUCCESS = 0x44FF44
COLOR_ERROR = 0xFF8C00
COLOR_INFO = 0x5865F2
COLOR_EXECUTION_COMPLETE = 0xFFD700


async def load_preamble():
    """Load preamble from file"""
    global preamble_code
    try:
        if os.path.exists(PREAMBLE_FILE):
            with open(PREAMBLE_FILE, 'r') as f:
                preamble_code = json.load(f)
    except Exception as e:
        print(f"Error loading preamble: {e}")
        preamble_code = []


async def save_preamble():
    """Save preamble to file"""
    try:
        with open(PREAMBLE_FILE, 'w') as f:
            json.dump(preamble_code, f, indent=2)
    except Exception as e:
        print(f"Error saving preamble: {e}")


@bot.event
async def on_ready():
    print(f'{bot.user} has connected!')
    await load_preamble()
    await setup_container()


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # handle ~~ so no 'no command' errors will show
    if message.content.strip().startswith('~~'):
        await process_message(message)
        return  # don't process as command because weird discord shit happens otherwise

    await process_message(message)
    await bot.process_commands(message)


@bot.event
async def on_message_edit(before, after):
    if after.author == bot.user:
        return

    existing_response = await get_existing_response(before.id, after.channel)
    await process_message(after, existing_response)


@bot.event
async def on_message_delete(message):
    await delete_response(message.id, message.channel)


async def get_existing_response(message_id, channel):
    """Get existing response message if it exists"""
    if message_id not in message_responses:
        return None

    try:
        response_id = message_responses[message_id]
        return await channel.fetch_message(response_id)
    except (discord.NotFound, KeyError):
        message_responses.pop(message_id, None)
        return None


async def delete_response(message_id, channel):
    """Delete bot response and clean up tracking"""
    existing_response = await get_existing_response(message_id, channel)
    if existing_response:
        try:
            await existing_response.delete()
        except discord.NotFound:
            pass
        message_responses.pop(message_id, None)


async def process_message(message, existing_response=None):
    """Process message for Lua code execution"""
    # handle ~~ prefix
    if message.content.strip().startswith('~~'):
        code = message.content.strip()[2:].lstrip()
        if code:
            response = await execute_lua_code(message, code, existing_response)
            if response:
                message_responses[message.id] = response.id
        elif existing_response:
            await delete_response(message.id, message.channel)
        return

    # handle ```code``` blocks (with or without lua)
    matches = re.findall(r"%```(?:lua\s*)?(.*?)```",
                         message.content, re.DOTALL | re.IGNORECASE)

    # handle %`code` blocks (with or without lua)
    if not matches:
        matches = re.findall(r"%`(?:lua\s*)?(.*?)`",
                             message.content, re.DOTALL | re.IGNORECASE)

    if matches:
        for lua_code in matches:
            lua_code = lua_code.strip()
            if lua_code:
                response = await execute_lua_code(message, lua_code, existing_response)
                if response:
                    message_responses[message.id] = response.id
                break  # this break is here so if more than one code is in message only first one is run, delete it if you want
    elif existing_response:
        await delete_response(message.id, message.channel)


async def create_embed(title, description, color, language="lua"):
    """Create formatted embed for responses"""
    return discord.Embed(
        title=title,
        description=f"```{language}\n{description}\n```" if description else "Code executed successfully (no output)",
        color=color
    )


async def create_output_file(content, filename="output.txt"):
    """Create a Discordd message with file"""
    import io
    encoded = content.encode('utf-8')
    if len(encoded) > MAX_FILE_SIZE:
        # Truncate and add a warning
        truncated = encoded[:MAX_FILE_SIZE - 100]
        truncated += b"\n\n[...output truncated due to Discord file size limit...]"
        file_content = io.BytesIO(truncated)
    else:
        file_content = io.BytesIO(encoded)
    return discord.File(file_content, filename=filename)


async def run_podman_command(cmd, ignore_errors=False):
    """Run a podman command and return (returncode, stdout, stderr)"""  # some black magic happens here
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        return process.returncode, stdout.decode().strip(), stderr.decode().strip()
    except Exception as e:
        if not ignore_errors:
            print(f"Error running command {' '.join(cmd)}: {e}")
        return 1, "", str(e)


async def setup_container():
    """Set up container for Lua execution"""
    try:
        await ensure_podman_image()
        await cleanup_container()

        create_cmd = [
            'podman', 'create', '--name', CONTAINER_NAME,
            '--memory=512m', '--memory-swap=596m', '--cpus=0.75',  # delete this line if on rpi
            '--network=none', '--user=botuser', '--read-only',
            '-i', IMAGE_NAME
        ]

        returncode, _, stderr = await run_podman_command(create_cmd)
        if returncode == 0:
            print(f"Created container: {CONTAINER_NAME}")

            # start the container
            start_returncode, _, start_stderr = await run_podman_command(['podman', 'start', CONTAINER_NAME])
            if start_returncode == 0:
                print(f"Started container: {CONTAINER_NAME}")
            else:
                print(f"Failed to start container: {CONTAINER_NAME}")
                print(f"Start error: {start_stderr}")
        else:
            print(f"Failed to create container: {CONTAINER_NAME}")
            print(f"Error: {stderr}")

    except Exception as e:
        print(f"Error setting up container: {e}")


async def cleanup_container():
    """Clean up container"""
    for cmd in [['podman', 'stop', '--timeout=1', CONTAINER_NAME], ['podman', 'rm', CONTAINER_NAME]]:
        returncode, _, stderr = await run_podman_command(cmd, ignore_errors=True)
        if returncode != 0 and "no such container" not in stderr.lower():
            print(f"Cleanup warning for {' '.join(cmd)}: {stderr}")


async def ensure_container_running():  # todo: merge this and setup_container
    """Ensure container is running before executing code"""
    try:
        # check if it even exists and is running
        inspect_cmd = ['podman', 'inspect', '--format',
                       '{{.State.Running}}', CONTAINER_NAME]
        returncode, stdout, stderr = await run_podman_command(inspect_cmd, ignore_errors=True)

        if returncode != 0:
            # it doesnt exist
            await setup_container()
            return True

        is_running = stdout.strip().lower() == 'true'
        if not is_running:
            # not running
            start_returncode, _, start_stderr = await run_podman_command(['podman', 'start', CONTAINER_NAME])
            if start_returncode != 0:
                print(f"Failed to start container: {start_stderr}")
                # recreate if fails
                await setup_container()
            return True

        return True
    except Exception as e:
        print(f"Error ensuring container is running: {e}")
        return False


async def execute_lua_code(message, lua_code, existing_response=None):
    """Execute Lua code using Podman container"""
    try:
        # Ensure container is running before executing
        if not await ensure_container_running():
            embed = discord.Embed(
                title="Container Error", description="Failed to start execution container", color=COLOR_SYSTEM_ERROR)
            return await send_or_edit_response(message, embed, existing_response)

        # combine preamble and users code
        full_code = '\n'.join(preamble_code) + '\n' + \
            lua_code if preamble_code else lua_code

        output = ""
        error = ""
        exit_flag = False

        while (output == "" and error == ""):
            exec_cmd = ['podman', 'exec', '-i',
                        CONTAINER_NAME, 'python', 'run_lua.py']

            process = await asyncio.create_subprocess_exec(
                *exec_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=full_code.encode()),
                    timeout=TIMEOUT
                )
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except:
                    pass
                embed = await create_embed("Execution Timeout", f"Code execution exceeded {TIMEOUT} second limit", COLOR_SYSTEM_ERROR, "")
                return await send_or_edit_response(message, embed, existing_response)

            output = stdout.decode().strip() if stdout else ""
            error = stderr.decode().strip() if stderr else ""

            if output == "" and error == "":
                full_code = '\n'.join(preamble_code) + '\nreturn ' + \
                    lua_code if preamble_code else 'return ' + lua_code
                if exit_flag:
                    break
                exit_flag = True
            
        if error is not "" and exit_flag:
            error = ""
            output = ""

        # black magic ends here

        if error:
            error_lines = error.count('\n') + 1 if error else 0

            # Adjust error line numbers by subtracting preamble lines
            if preamble_code:
                preamble_lines = sum(code.count('\n') + 1 for code in preamble_code)
                def adjust_line(match):
                    orig_line = int(match.group(1))
                    new_line = max(0, orig_line - preamble_lines - 1)
                    return f":{new_line}:"
                import re
                error = re.sub(r":(\d+):", adjust_line, error)

            # i am deeply sorry if someone needs to read this code :u
            if len(error) > 1024 or error_lines > 64:
                embed = await create_embed("Lua Error", "Errors too long, see attached file", COLOR_ERROR, "")
                file = await create_output_file(error, "error.txt")
                return await send_or_edit_response(message, embed, existing_response, file)
            else:
                embed = await create_embed("Lua Error", error, COLOR_ERROR)
                return await send_or_edit_response(message, embed, existing_response)
        elif output:
            output_lines = output.count('\n') + 1 if output else 0

            if len(output) > 1024 or output_lines > 64:
                embed = await create_embed("Lua Output", "Output too long, see attached file", COLOR_SUCCESS, "")
                file = await create_output_file(output, "output.txt")
                return await send_or_edit_response(message, embed, existing_response, file)
            else:
                embed = await create_embed("Lua Output", output, COLOR_SUCCESS)
                return await send_or_edit_response(message, embed, existing_response)
        else:
            embed = await create_embed("Execution Complete", "", COLOR_EXECUTION_COMPLETE)
            return await send_or_edit_response(message, embed, existing_response)

    except FileNotFoundError:
        embed = discord.Embed(
            title="Podman Error", description="Podman not found. Please install Podman.", color=COLOR_SYSTEM_ERROR)
        return await send_or_edit_response(message, embed, existing_response)
    except Exception as e:
        embed = discord.Embed(
            title="System Error", description=f"System Error: {str(e)}", color=COLOR_SYSTEM_ERROR)
        return await send_or_edit_response(message, embed, existing_response)


async def send_or_edit_response(message, embed, existing_response=None, file=None):
    """Send new response or edit existing one"""
    if existing_response:
        # always delete and recreate when there's a file involved because stupid discord doesnt let me edit files
        if file or (existing_response.attachments):
            try:
                await existing_response.delete()
            except discord.NotFound:
                pass
            return await message.reply(embed=embed, file=file)
        else:
            await existing_response.edit(embed=embed)
            return existing_response
    else:
        if file:
            return await message.reply(embed=embed, file=file)
        else:
            return await message.reply(embed=embed)


async def ensure_podman_image():
    """Build Podman image if it doesn't exist"""
    try:
        returncode, stdout, _ = await run_podman_command(['podman', 'images', '-q', IMAGE_NAME])

        if returncode == 0 and not stdout:
            print("Building Podman image...")
            build_returncode, _, build_stderr = await run_podman_command(
                ['podman', 'build', '-t', IMAGE_NAME, '.'],
            )

            if build_returncode == 0:
                print("Podman image built successfully!")
            else:
                print(f"Podman build failed: {build_stderr}")
        elif returncode == 0:
            print("Podman image found")

    except FileNotFoundError:
        print("Podman not found. Please install Podman to use this bot.")
    except Exception as e:
        print(f"Error with Podman setup: {e}")


@bot.command(name='add')
@commands.has_permissions(manage_messages=True)
async def add_preamble(ctx, *, code):
    """Add code to preamble"""

    # strip code of whitespaces
    clean_code = code.strip()

    # remove triple backtics
    if clean_code.startswith('```') and clean_code.endswith('```'):
        clean_code = clean_code[3:-3].strip()

    # see above but for single backtics
    elif clean_code.startswith('`') and clean_code.endswith('`') and clean_code.count('`') == 2:
        clean_code = clean_code[1:-1].strip()

    if not clean_code:
        embed = discord.Embed(
            title="Error", description="Please provide code to add", color=COLOR_ERROR)
        await ctx.send(embed=embed)
        return

    preamble_code.append(clean_code)
    await save_preamble()

    embed = discord.Embed(
        title="Preamble Updated",
        description=f"Added code snippet #{len(preamble_code)-1}",
        color=COLOR_SUCCESS
    )
    embed.add_field(name="Added Code",
                    value=f"```lua\n{clean_code}\n```", inline=False)
    await ctx.send(embed=embed)


@bot.command(name='show')
async def show_preamble(ctx):
    """Show current preamble code"""
    if not preamble_code:
        embed = discord.Embed(
            title="Preamble", description="No preamble code set", color=COLOR_EXECUTION_COMPLETE)
        await ctx.send(embed=embed)
        return

    embed = discord.Embed(title="Current Preamble", color=COLOR_INFO)

    for i, code in enumerate(preamble_code):
        embed.add_field(
            name=f"#{i}",
            value=f"```lua\n{code}\n```",
            inline=False
        )

    await ctx.send(embed=embed)


@bot.command(name='del')
@commands.has_permissions(manage_messages=True)
async def delete_preamble(ctx, num: int):
    """Delete preamble code by number"""
    if not preamble_code:
        embed = discord.Embed(
            title="Error", description="No preamble code to delete", color=COLOR_ERROR)
        await ctx.send(embed=embed)
        return

    if num < 0 or num >= len(preamble_code):
        embed = discord.Embed(
            title="Error",
            description=f"Invalid number. Use 0-{len(preamble_code)-1}",
            color=COLOR_ERROR
        )
        await ctx.send(embed=embed)
        return

    deleted_code = preamble_code.pop(num)
    await save_preamble()

    embed = discord.Embed(title="Preamble Updated",
                          description=f"Deleted snippet #{num}", color=COLOR_EXECUTION_COMPLETE)
    embed.add_field(name="Deleted Code",
                    value=f"```lua\n{deleted_code}\n```", inline=False)
    await ctx.send(embed=embed)


@bot.command(name='help')
async def help_command(ctx):
    """Show help information"""  # very pwetty format isnt it :3
    embed = discord.Embed(
        title="Lua Bot Help",
        description="Execute Lua code safely in Discord!",
        color=COLOR_INFO
    )

    embed.add_field(
        name="Usage",
        value="• **Triple backticks:** ` %```<your_code>``` ` or single backticks\n• **Command:** `~~<your_code>`",
        inline=False
    )

    embed.add_field(
        name="Preamble Commands",
        value="• `~add <code>` - Add permanent code\n• `~show` - Show current preamble\n• `~del <num>` - Delete preamble by number",
        inline=False
    )

    embed.add_field(
        name="Available Libraries",
        value="• `math.*` - Mathematical functions\n• `string.*` - String manipulation\n• `table.*` - Table operations\n• `print()` - Output text",
        inline=False
    )

    embed.add_field(
        name="Security Limits",
        value="• {TIMEOUT} second timeout\n• 64MB memory limit\n• No file/network access\n• Max 1800 output characters",
        inline=False
    )

    await ctx.send(embed=embed)


@bot.event
async def on_command_error(ctx, error):
    """Handle command errors silently"""
    if isinstance(error, commands.CommandNotFound):
        # silently ignore command not found errors, i want to keep it clean
        return
    elif isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="Permission Denied",
            description="You need the **Manage Messages** permission to use this command.",
            color=COLOR_ERROR
        )
        await ctx.send(embed=embed)
        return
    # log other errors
    print(f"Command error: {error}")


# run the code >w<
if __name__ == "__main__":
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("Error: DISCORD_BOT_TOKEN not found in .env file")
        exit(1)

    try:
        bot.run(token)
    finally:
        # Cleanup on exit
        asyncio.run(cleanup_container())
