import discord
from discord.ext import commands
import asyncio
import re
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='~', intents=intents, help_command=None)

message_responses = {}


@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await ensure_docker_image()


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # handle ~~ prefix
    if message.content.strip().startswith('~~'):
        await process_message(message)
        return  # don't process as command

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

    # handle ```code``` blocks
    matches = re.findall(r"%```(?:lua\s*)?(.*?)```",
                         message.content, re.DOTALL | re.IGNORECASE)

    # Handle %`code` blocks
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
                break
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
    """Execute Lua code using Docker"""
    try:
        docker_cmd = [
            'docker', 'run', '--rm', '-i',
            '--memory=64m', '--memory-swap=96m', '--cpus=0.25',
            '--network=none', '--user=botuser', '--read-only',
            'lua-bot'
        ]

        process = await asyncio.create_subprocess_exec(
            *docker_cmd,
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
                process.kill()
                await process.wait()
            except:
                pass
            embed = await create_embed("Execution Timeout", "Code execution exceeded 5 second limit", 0xFF4444, "")
            return await send_or_edit_response(message, embed, existing_response)

        output = stdout.decode().strip() if stdout else ""
        error = stderr.decode().strip() if stderr else ""

        if error:
            # make error more readable
            clean_error = []
            for line in error.split('\n'):
                if 'stdin:' in line:
                    parts = line.split(':', 3)
                    if len(parts) >= 4:
                        clean_error.append(
                            f"Line {parts[1]}: {parts[3].strip()}")
                    else:
                        clean_error.append(line)
                elif line.strip() and not line.startswith('lua:'):
                    clean_error.append(line)

            final_error = '\n'.join(clean_error) if clean_error else error
            error_lines = final_error.count('\n') + 1 if final_error else 0

            if len(final_error) > 512 or error_lines > 32:
                embed = await create_embed("Lua Error", "Error output too long, see attached file", 0xFF8C00, "")
                file = await create_output_file(final_error, "error.txt")
                return await send_or_edit_response(message, embed, existing_response, file)
            else:
                embed = await create_embed("Lua Error", final_error, 0xFF8C00)
                return await send_or_edit_response(message, embed, existing_response)
        elif output:
            output_lines = output.count('\n') + 1 if output else 0

            if len(output) > 512 or output_lines > 32:
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
            title="Docker Error", description="Docker not found. Please install Docker.", color=0xFF4444)
        return await send_or_edit_response(message, embed, existing_response)
    except Exception as e:
        embed = discord.Embed(
            title="System Error", description=f"System Error: {str(e)}", color=0xFF4444)
        return await send_or_edit_response(message, embed, existing_response)


async def send_or_edit_response(message, embed, existing_response=None, file=None):
    """Send new response or edit existing one"""
    if existing_response:
        # delete and recreate if there's a file involved
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


async def ensure_docker_image():
    """Build Docker image if it doesn't exist"""
    try:
        result = await asyncio.create_subprocess_exec(
            'docker', 'images', '-q', 'lua-bot',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await result.communicate()

        if not stdout.strip():
            print("Building Docker image...")
            build_process = await asyncio.create_subprocess_exec(
                'docker', 'build', '-t', 'lua-bot', '.',
                cwd=os.path.dirname(__file__),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            _, build_stderr = await build_process.communicate()

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
        # silently ignore command not found errors
        return
    # log other errors
    print(f"Command error: {error}")


# run the code :3
if __name__ == "__main__":
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("Error: DISCORD_BOT_TOKEN not found in .env file")
        exit(1)

    bot.run(token)
