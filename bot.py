import discord
from discord.ext import commands
import asyncio
import re
import os
import signal
import atexit
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='~', intents=intents, help_command=None)

message_responses = {}
container_id = None
container_lock = asyncio.Lock()


async def create_persistent_container():
    """Create a single persistent container"""
    global container_id

    try:
        # Remove any existing container
        await asyncio.create_subprocess_exec(
            'podman', 'rm', '-f', 'lua-bot-persistent',
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )

        print("Creating persistent container...")

        # Create new persistent container
        process = await asyncio.create_subprocess_exec(
            'podman', 'run', '-d', '--name', 'lua-bot-persistent',
            '--memory=64m', '--memory-swap=96m', '--cpus=0.64',
            '--network=none', '--user=botuser', '--read-only',
            'lua-bot', 'sleep', 'infinity',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            container_id = stdout.decode().strip()
            print(f"Persistent container created: {container_id[:12]}")
            return True
        else:
            print(f"Failed to create persistent container: {stderr.decode()}")
            return False

    except Exception as e:
        print(f"Error creating persistent container: {e}")
        return False


async def cleanup_container():
    """Clean up the persistent container"""
    global container_id

    if container_id:
        print("Cleaning up persistent container...")
        try:
            await asyncio.create_subprocess_exec(
                'podman', 'rm', '-f', container_id,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            print("Container cleanup complete")
        except Exception as e:
            print(f"Error cleaning up container: {e}")
        finally:
            container_id = None


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    print(f"\nReceived signal {signum}, shutting down...")
    asyncio.create_task(cleanup_container())
    exit(0)


# Register signal handlers and exit cleanup
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(lambda: asyncio.run(cleanup_container()))


@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await ensure_podman_image()

    # Create persistent container
    if not await create_persistent_container():
        print("Failed to create persistent container. Bot may not work properly.")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Handle ~~ prefix before processing commands to avoid CommandNotFound errors
    if message.content.strip().startswith('~~'):
        await process_message(message)
        return  # Don't process as command

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
    # Handle ~~ prefix
    if message.content.strip().startswith('~~'):
        code = message.content.strip()[2:].lstrip()
        if code:
            response = await execute_lua_code(message, code, existing_response)
            if response:
                message_responses[message.id] = response.id
        elif existing_response:
            await delete_response(message.id, message.channel)
        return

    # Handle ```code``` blocks (with optional 'lua' keyword)
    matches = re.findall(r"%```(?:lua\s*)?(.*?)```",
                         message.content, re.DOTALL | re.IGNORECASE)

    # Handle %`code` blocks (with optional 'lua' keyword)
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
                break  # Only execute first code block
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
    """Create a Discord File object with the given content"""
    import io
    file_content = io.BytesIO(content.encode('utf-8'))
    return discord.File(file_content, filename=filename)


async def execute_lua_code(message, lua_code, existing_response=None):
    """Execute Lua code using the persistent Podman container"""
    global container_id

    if not container_id:
        embed = discord.Embed(
            title="System Error", description="Persistent container not available", color=0xFF4444)
        return await send_or_edit_response(message, embed, existing_response)

    # Use lock to prevent concurrent executions from interfering
    async with container_lock:
        try:
            # Execute code in the persistent container
            process = await asyncio.create_subprocess_exec(
                'podman', 'exec', '-i', container_id, 'python', 'run_lua.py',
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=lua_code.encode()),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                try:
                    # Kill the exec process, but keep container alive
                    process.kill()
                    await process.wait()
                except:
                    pass
                embed = await create_embed("Execution Timeout", "Code execution exceeded 5 second limit", 0xFF4444, "")
                return await send_or_edit_response(message, embed, existing_response)

            output = stdout.decode().strip() if stdout else ""
            error = stderr.decode().strip() if stderr else ""

            if error:
                # Clean up Lua error messages
                clean_error = []
                for line in error.split('\n'):
                    if 'stdin:' in line:
                        parts = line.split(':', 2)
                        if len(parts) >= 3:
                            clean_error.append(
                                f"line {parts[1]}: {parts[2].strip()}")
                        elif line.strip():
                            clean_error.append(line)
                    elif line.strip():
                        clean_error.append(line)

                final_error = '\n'.join(clean_error) if clean_error else error
                error_lines = final_error.count('\n') + 1 if final_error else 0

                if len(final_error) > 1024 or error_lines > 64:
                    embed = await create_embed("Lua Error", "Error output too long, see attached file", 0xFF8C00, "")
                    file = await create_output_file(final_error, "error.txt")
                    return await send_or_edit_response(message, embed, existing_response, file)
                else:
                    embed = await create_embed("Lua Error", final_error, 0xFF8C00)
                    return await send_or_edit_response(message, embed, existing_response)
            elif output:
                output_lines = output.count('\n') + 1 if output else 0

                if len(output) > 1024 or output_lines > 64:
                    embed = await create_embed("Lua Output", "Output too long, see attached file", 0x44FF44, "")
                    file = await create_output_file(output, "output.txt")
                    return await send_or_edit_response(message, embed, existing_response, file)
                else:
                    embed = await create_embed("Lua Output", output, 0x44FF44)
                    return await send_or_edit_response(message, embed, existing_response)
            else:
                embed = await create_embed("Execution Complete", "", 0xFFD700)
                return await send_or_edit_response(message, embed, existing_response)

        except FileNotFoundError:
            embed = discord.Embed(
                title="Podman Error", description="Podman not found. Please install Podman.", color=0xFF4444)
            return await send_or_edit_response(message, embed, existing_response)
        except Exception as e:
            embed = discord.Embed(
                title="System Error", description=f"System Error: {str(e)}", color=0xFF4444)
            return await send_or_edit_response(message, embed, existing_response)


async def send_or_edit_response(message, embed, existing_response=None, file=None):
    """Send new response or edit existing one"""
    if existing_response:
        # Always delete and recreate when there's a file involved (either new file or previous had file)
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
        result = await asyncio.create_subprocess_exec(
            'podman', 'images', '-q', 'lua-bot',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await result.communicate()

        if not stdout.strip():
            print("Building Podman image...")
            build_process = await asyncio.create_subprocess_exec(
                'podman', 'build', '-t', 'lua-bot', '.',
                cwd=os.path.dirname(__file__),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            _, build_stderr = await build_process.communicate()

            if build_process.returncode == 0:
                print("Podman image built successfully!")
            else:
                print(f"Podman build failed: {build_stderr.decode()}")
        else:
            print("Podman image found")

    except FileNotFoundError:
        print("Podman not found. Please install Podman to use this bot.")
    except Exception as e:
        print(f"Error with Podman setup: {e}")


@bot.command(name='help')
async def help_command(ctx):
    """Show help information"""
    embed = discord.Embed(
        title="Lua Bot Help",
        description="Execute Lua code safely in Discord!",
        color=0x5865F2
    )

    embed.add_field(
        name="Usage",
        value="• **Triple backticks:** ` %```<your_code>``` ` or single backticks\n• **Command:** `~~<your_code>`",
        inline=False
    )

    embed.add_field(
        name="Available Libraries",
        value="• `math.*` - Mathematical functions\n• `string.*` - String manipulation\n• `table.*` - Table operations\n• `print()` - Output text",
        inline=False
    )

    embed.add_field(
        name="Security Limits",
        value="• 5 second timeout\n• 64MB memory limit\n• No file/network access\n• Max 1800 output characters",
        inline=False
    )

    await ctx.send(embed=embed)


@bot.event
async def on_command_error(ctx, error):
    """Handle command errors silently"""
    if isinstance(error, commands.CommandNotFound):
        # Silently ignore command not found errors
        return
    # Log other errors
    print(f"Command error: {error}")


# Run the bot
if __name__ == "__main__":
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("Error: DISCORD_BOT_TOKEN not found in .env file")
        exit(1)

    try:
        bot.run(token)
    except KeyboardInterrupt:
        print("\nBot interrupted by user")
    finally:
        if container_id:
            asyncio.run(cleanup_container())
