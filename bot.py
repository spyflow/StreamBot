import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import json
import asyncio
import shutil # For shutil.which to check for ffmpeg

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
RADIO_STREAM_URL = os.getenv("RADIO_STREAM_URL", "YOUR_STREAM_URL_HERE") # Global fallback
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}
CONFIG_FILE = 'config.json'

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f: config = json.load(f)
    except FileNotFoundError: config = {}
    except json.JSONDecodeError: config = {}; print(f"Error decoding {CONFIG_FILE}.")
    return config

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f: json.dump(config, f, indent=4)
    except IOError: print(f"Error writing to {CONFIG_FILE}.")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command('help')

active_guilds_playback_status = {} # Stores runtime status, including resolved stream_url

async def play_stream_continuous(voice_client, stream_url_to_play, guild_id, text_channel_for_notif=None):
    guild_status = active_guilds_playback_status.get(guild_id)
    if not guild_status:
        print(f"Guild {guild_id} not in active_guilds_playback_status for play_stream_continuous.")
        return

    if not stream_url_to_play or stream_url_to_play == "YOUR_STREAM_URL_HERE":
        msg = f"Error: URL del stream no configurada o inválida para el servidor {voice_client.guild.name}."
        print(msg)
        if text_channel_for_notif:
            try: await text_channel_for_notif.send(msg)
            except discord.Forbidden: print(f"No permission to send message in {text_channel_for_notif.name}")
        guild_status['playing'] = False
        return

    async def after_playing(error):
        current_guild_status_after = active_guilds_playback_status.get(guild_id) # Re-fetch status
        if error:
            print(f"Error durante la reproducción en {voice_client.guild.name}: {error}")
            if text_channel_for_notif:
                try: await text_channel_for_notif.send(f"Error durante la reproducción: `{error}`. Intentando reconectar en 10 segundos...")
                except discord.Forbidden: pass
                except discord.HTTPException: pass # Catch other potential send errors
        else:
            print(f"Stream finalizado/interrumpido en {voice_client.guild.name}. Reiniciando...")

        if not voice_client.is_connected() or not current_guild_status_after or not current_guild_status_after.get('playing'):
            print(f"Playback detenido o bot desconectado de {voice_client.guild.name}. No se reinicia automáticamente.")
            if current_guild_status_after: current_guild_status_after['playing'] = False
            return

        await asyncio.sleep(10)
        if voice_client.is_connected() and current_guild_status_after.get('playing'):
            # --- Modification Start ---
            guild_status_for_retry = active_guilds_playback_status.get(guild_id)
            if not guild_status_for_retry:
                print(f"Error en retry: No se encontró estado para guild {guild_id}. No se puede reintentar.")
                if text_channel_for_notif:
                    try: await text_channel_for_notif.send("Error interno: No se encontró el estado del servidor para reintentar la reproducción.")
                    except discord.Forbidden: pass
                return

            latest_stream_url = guild_status_for_retry.get('current_stream_url')

            if not latest_stream_url or latest_stream_url == "YOUR_STREAM_URL_HERE":
                error_msg = f"Error en retry: URL de stream inválida o no configurada para {voice_client.guild.name} (URL: '{latest_stream_url}'). No se puede reintentar."
                print(error_msg)
                if text_channel_for_notif:
                    try: await text_channel_for_notif.send("Error: La URL del stream no está configurada o es inválida. No se puede reintentar la reproducción.")
                    except discord.Forbidden: pass
                current_guild_status_after['playing'] = False # Ensure we don't try to play a bad URL again
                return

            print(f"Reintentando reproducir stream con URL actualizada ({latest_stream_url}) en {voice_client.guild.name}")
            bot.loop.create_task(play_stream_continuous(voice_client, latest_stream_url, guild_id, text_channel_for_notif))
            # --- Modification End ---
        else:
            print(f"No se reinicia el stream en {voice_client.guild.name}, estado cambió o desconectado.")

    try:
        if not voice_client.is_connected():
            print(f"Voice client para {voice_client.guild.name} no conectado al inicio de play_stream_continuous.")
            guild_status['playing'] = False
            # Rely on maintain_voice_connections_task to re-establish connection
            return

        if voice_client.is_playing() or voice_client.is_paused(): voice_client.stop(); await asyncio.sleep(0.5)

        audio_source = discord.FFmpegPCMAudio(stream_url_to_play, **FFMPEG_OPTIONS)
        voice_client.play(audio_source, after=lambda e: asyncio.run_coroutine_threadsafe(after_playing(e), bot.loop))
        print(f"Stream iniciado en {voice_client.channel.name} ({voice_client.guild.name}) con URL: {stream_url_to_play}")
        guild_status['playing'] = True
        guild_status['current_stream_url'] = stream_url_to_play # Store the actual URL being played
    except discord.ClientException as e:
        msg = f"Error de cliente (FFmpeg/URL?) al reproducir en {voice_client.guild.name}: {e}."
        print(msg)
        if text_channel_for_notif:
            try: await text_channel_for_notif.send(msg)
            except discord.Forbidden: pass
        guild_status['playing'] = False
    except Exception as e:
        msg = f"Error inesperado al iniciar stream en {voice_client.guild.name}: {e}"
        print(msg)
        if text_channel_for_notif:
            try: await text_channel_for_notif.send(msg)
            except discord.Forbidden: pass
        guild_status['playing'] = False

async def ensure_voice_connection_and_play(guild_id: int, target_channel_id: int, text_channel_for_notif=None):
    guild = bot.get_guild(guild_id)
    if not guild:
        if guild_id in active_guilds_playback_status: del active_guilds_playback_status[guild_id]
        return

    voice_channel = guild.get_channel(target_channel_id)
    if not voice_channel or not isinstance(voice_channel, discord.VoiceChannel):
        if guild_id in active_guilds_playback_status: del active_guilds_playback_status[guild_id]
        print(f"Canal de voz {target_channel_id} no encontrado en {guild.name}.")
        return

    # Determine the stream URL: Guild-specific from config.json, or global fallback
    config = load_config()
    guild_specific_config = config.get(str(guild_id), {})
    stream_url_to_use = guild_specific_config.get('stream_url', RADIO_STREAM_URL)

    # Update active_guilds_playback_status with the resolved URL and intent to play
    if guild_id not in active_guilds_playback_status: active_guilds_playback_status[guild_id] = {}
    status = active_guilds_playback_status[guild_id]
    status.update({
        'target_channel_id': target_channel_id,
        'stream_url': stream_url_to_use, # Store the resolved URL
        'playing': True # Set intent to play
    })

    notification_channel = text_channel_for_notif or guild.system_channel

    vc = guild.voice_client
    try:
        if vc and vc.is_connected():
            if vc.channel.id != target_channel_id:
                await vc.move_to(voice_channel) # Move if in wrong channel
            status['voice_client'] = vc
        else: # Not connected, so connect
            vc = await voice_channel.connect()
            status['voice_client'] = vc

        # At this point, vc should be valid and connected to target_channel_id
        # Start playback using the resolved stream_url_to_use
        bot.loop.create_task(play_stream_continuous(vc, stream_url_to_use, guild_id, notification_channel))

    except discord.Forbidden:
        msg = f"Error de permisos al unirse o moverse a **{voice_channel.name}**. Verifica los permisos del bot."
        print(f"{msg} en guild {guild.name}")
        if notification_channel:
            try: await notification_channel.send(msg)
            except discord.Forbidden: pass
        status['playing'] = False
    except discord.ClientException as e:
        msg = f"Error de cliente al conectar a **{voice_channel.name}**: {e}"
        print(f"{msg} en guild {guild.name}")
        if notification_channel:
            try: await notification_channel.send(msg)
            except discord.Forbidden: pass
        status['playing'] = False
    except Exception as e:
        msg = f"Error inesperado al conectar a **{voice_channel.name}**: {e}"
        print(f"{msg} en guild {guild.name}")
        if notification_channel:
            try: await notification_channel.send(msg)
            except discord.Forbidden: pass
        status['playing'] = False
    active_guilds_playback_status[guild_id] = status


@tasks.loop(seconds=45)
async def maintain_voice_connections_task():
    await bot.wait_until_ready()
    config = load_config()
    # Consider all guilds from config and any currently active guilds
    guild_ids_to_check = set(map(int, config.keys())) | set(g_id for g_id, stat in active_guilds_playback_status.items() if stat.get('playing'))

    for guild_id in guild_ids_to_check:
        guild_config_from_file = config.get(str(guild_id)) # Config from file for this guild
        current_status_in_memory = active_guilds_playback_status.get(guild_id, {})
        guild = bot.get_guild(guild_id)

        if not guild: # Bot is no longer in this guild
            if guild_id in active_guilds_playback_status: del active_guilds_playback_status[guild_id]
            continue

        notif_channel_id = current_status_in_memory.get('text_channel_for_notif_id')
        notification_channel = bot.get_channel(notif_channel_id) if notif_channel_id else guild.system_channel

        if current_status_in_memory.get('playing'): # If bot is intended to be playing
            if not guild_config_from_file or 'channel_id' not in guild_config_from_file:
                # Was told to play, but configuration is gone. Stop it.
                print(f"Maintain task: Guild {guild_id} quiere reproducir pero ya no está configurado. Deteniendo.")
                if guild_id in active_guilds_playback_status:
                    vc = current_status_in_memory.get('voice_client')
                    if vc and vc.is_connected():
                        if vc.is_playing(): vc.stop()
                        await vc.disconnect()
                    del active_guilds_playback_status[guild_id]
                continue

            target_channel_id = guild_config_from_file['channel_id']
            vc = guild.voice_client

            if not vc or not vc.is_connected() or vc.channel.id != target_channel_id:
                print(f"Maintain task: Bot no en canal correcto para {guild.name} (Objetivo: {target_channel_id}). (Re)conectando.")
                await ensure_voice_connection_and_play(guild_id, target_channel_id, notification_channel)
            elif vc.is_connected() and not vc.is_playing():
                # In correct channel, but not playing. Resolve URL and start.
                resolved_stream_url = current_status_in_memory.get('stream_url') or guild_config_from_file.get('stream_url', RADIO_STREAM_URL)
                print(f"Maintain task: Bot en {vc.channel.name} pero no reproduciendo. Reiniciando stream con {resolved_stream_url}.")
                bot.loop.create_task(play_stream_continuous(vc, resolved_stream_url, guild_id, notification_channel))

        elif guild_config_from_file and 'channel_id' in guild_config_from_file and guild_config_from_file.get('auto_join_on_startup', True):
            # Configured for auto-join, but not currently marked as 'playing' (e.g., after restart and initial on_ready population)
            if not current_status_in_memory.get('playing'): # Ensure it's not already processing
                print(f"Maintain task: Guild {guild_id} configurado para auto-join y no reproduciendo. Iniciando.")
                target_channel_id = guild_config_from_file['channel_id']
                await ensure_voice_connection_and_play(guild_id, target_channel_id, notification_channel)


@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    if shutil.which("ffmpeg"): print("FFmpeg encontrado.")
    else: print("ADVERTENCIA: FFmpeg no parece estar instalado o en el PATH. La reproducción de audio fallará.")

    print(f'Conectado a {len(bot.guilds)} servidor(es).')
    for guild in bot.guilds: print(f'- {guild.name} (ID: {guild.id})')

    if not os.path.exists(CONFIG_FILE): save_config({})
    else: print(f"{CONFIG_FILE} cargado.")

    config = load_config()
    for guild_id_str, conf_data_from_file in config.items():
        guild_id = int(guild_id_str)
        if 'channel_id' in conf_data_from_file and conf_data_from_file.get('auto_join_on_startup', True):
            # Pre-populate status for maintain_task.
            # stream_url here is pre-resolved to assist maintain_task if it calls play_stream_continuous directly.
            active_guilds_playback_status[guild_id] = {
                'target_channel_id': conf_data_from_file['channel_id'],
                'playing': True, # Set intent to play
                'voice_client': None, # To be populated by ensure_voice_connection_and_play
                'text_channel_for_notif_id': None, # No specific command context on startup
                'stream_url': conf_data_from_file.get('stream_url', RADIO_STREAM_URL)
            }
            print(f"Guild {guild_id} marcado para auto-join y play en startup.")

    if not maintain_voice_connections_task.is_running():
        maintain_voice_connections_task.start()
    print("on_ready setup completo. Tarea de mantenimiento iniciada.")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.id != bot.user.id: return # Only care about the bot's state changes
    guild_id = member.guild.id
    status = active_guilds_playback_status.get(guild_id)

    if not status or not status.get('playing'): return # Not supposed to be playing, so ignore

    if before.channel and not after.channel: # Bot was disconnected (kicked, or channel deleted)
        print(f"Bot desconectado de {before.channel.name} en {member.guild.name}.")
        target_channel_id = status.get('target_channel_id')
        notif_channel_id = status.get('text_channel_for_notif_id')
        notif_channel = bot.get_channel(notif_channel_id) if notif_channel_id else member.guild.system_channel

        if target_channel_id: # If a target channel is known
            print(f"Intentando re-unirse inmediatamente a {target_channel_id} en {member.guild.name} debido a desconexión.")
            await asyncio.sleep(5) # Brief delay
            # ensure_voice_connection_and_play will resolve the correct stream URL
            await ensure_voice_connection_and_play(guild_id, target_channel_id, notif_channel)


@bot.command(name='ping')
async def ping(ctx): await ctx.send(f'Pong! Latencia: {round(bot.latency * 1000)}ms')

@bot.command(name='configurechannel')
@commands.has_permissions(administrator=True)
async def configurechannel(ctx, *, channel_name: str):
    guild = ctx.guild
    if not guild: await ctx.send("Solo en servidor."); return
    voice_channel = discord.utils.get(guild.voice_channels, name=channel_name)
    if voice_channel:
        config = load_config()
        guild_config = config.get(str(guild.id), {})
        guild_config['channel_id'] = voice_channel.id
        guild_config['channel_name'] = voice_channel.name
        guild_config['auto_join_on_startup'] = True
        config[str(guild.id)] = guild_config
        save_config(config)
        await ctx.send(f"Canal configurado: **{voice_channel.name}**. Intentando unirse y reproducir.")

        current_status = active_guilds_playback_status.get(guild.id, {})
        current_status.update({
            'target_channel_id': voice_channel.id,
            'playing': True,
            'text_channel_for_notif_id': ctx.channel.id
            # stream_url will be resolved by ensure_voice_connection_and_play
        })
        active_guilds_playback_status[guild.id] = current_status
        await ensure_voice_connection_and_play(guild.id, voice_channel.id, ctx.channel) # No URL directly passed
    else:
        await ctx.send(f"Canal de voz '{channel_name}' no encontrado.")

@configurechannel.error
async def cex_error(ctx, error): # Renamed to avoid conflict
    if isinstance(error, commands.MissingPermissions): await ctx.send("Necesitas permisos de Administrador.")
    elif isinstance(error, commands.MissingRequiredArgument): await ctx.send("Uso: `!configurechannel <nombre_canal>`")
    else: await ctx.send(f"Error en configurechannel: {error}"); print(f"Error en configurechannel: {error}")

@bot.command(name='join')
async def join(ctx):
    guild = ctx.guild
    if not guild: await ctx.send("Solo en servidor."); return
    config_data = load_config() # Renamed to avoid conflict with global 'config' name
    guild_conf = config_data.get(str(guild.id))
    if not guild_conf or 'channel_id' not in guild_conf:
        await ctx.send("Canal no configurado. Usa `!configurechannel`."); return
    target_channel_id = guild_conf['channel_id']

    if guild.id not in active_guilds_playback_status: active_guilds_playback_status[guild.id] = {}
    active_guilds_playback_status[guild.id].update({
        'target_channel_id': target_channel_id,
        'playing': True,
        'text_channel_for_notif_id': ctx.channel.id
        # stream_url will be resolved by ensure_voice_connection_and_play
    })
    await ctx.send(f"Intentando unirme y reproducir en el canal configurado...")
    await ensure_voice_connection_and_play(guild.id, target_channel_id, ctx.channel) # No URL directly passed

@join.error
async def join_error(ctx, error):
    await ctx.send(f"Error en `!join`: {error}. Revisa consola."); print(f"Error en join: {error}")

@bot.command(name='leave')
async def leave(ctx):
    guild = ctx.guild
    if not guild: await ctx.send("Solo en servidor."); return
    if guild.id in active_guilds_playback_status:
        active_guilds_playback_status[guild.id]['playing'] = False
        # Also clear current_stream_url if it exists
        active_guilds_playback_status[guild.id].pop('current_stream_url', None)
    vc = guild.voice_client
    if vc and vc.is_connected():
        cn = vc.channel.name
        if vc.is_playing(): vc.stop()
        await vc.disconnect()
        await ctx.send(f"Desconectado de **{cn}**.")
        if guild.id in active_guilds_playback_status:
             active_guilds_playback_status[guild.id]['voice_client'] = None
    else:
        await ctx.send("No estoy en un canal de voz.")

@leave.error
async def leave_error(ctx, error):
    await ctx.send(f"Error en `!leave`: {error}. Revisa consola."); print(f"Error en leave: {error}")

@bot.command(name='setstreamurl')
@commands.has_permissions(administrator=True)
async def setstreamurl(ctx, *, url: str):
    guild = ctx.guild
    if not guild: await ctx.send("Este comando solo puede usarse en un servidor."); return
    if not (url.startswith('http://') or url.startswith('https://')):
        await ctx.send("La URL del stream no es válida."); return

    config_data = load_config() # Renamed
    guild_config = config_data.get(str(guild.id), {})
    guild_config['stream_url'] = url # Save new URL to be read by ensure_voice_connection_and_play
    config_data[str(guild.id)] = guild_config
    save_config(config_data)
    await ctx.send(f"URL del stream actualizada para este servidor a: <{url}>")
    print(f"Server '{guild.name}' updated stream URL to: {url}")

    current_status = active_guilds_playback_status.get(guild.id, {})
    current_status['stream_url'] = url # Update in-memory status immediately

    if current_status.get('playing'): # If it was already supposed to be playing
        active_guilds_playback_status[guild.id] = current_status # Save back updated status
        vc = guild.voice_client
        if vc and vc.is_connected():
            await ctx.send("Reiniciando la reproducción con la nueva URL...")
            if vc.is_playing() or vc.is_paused(): vc.stop(); await asyncio.sleep(0.5)

            target_channel_id = current_status.get('target_channel_id') or guild_config.get('channel_id')
            if target_channel_id:
                # ensure_voice_connection_and_play will now pick up the new URL from config or the updated active_guilds_playback_status
                await ensure_voice_connection_and_play(guild.id, target_channel_id, ctx.channel)
            else:
                await ctx.send("No hay canal configurado. Usa `!configurechannel`.")
        else: # Not connected but was 'playing'
            active_guilds_playback_status[guild.id] = current_status
            await ctx.send("URL guardada. Se usará al (re)conectar.")
    else: # Not playing, just save the URL and update status
        current_status['playing'] = False
        active_guilds_playback_status[guild.id] = current_status
        await ctx.send("URL del stream guardada.")

@setstreamurl.error
async def setstreamurl_error(ctx, error):
    if isinstance(error, commands.MissingPermissions): await ctx.send("No tienes permisos de Administrador.")
    elif isinstance(error, commands.MissingRequiredArgument): await ctx.send("Uso: `!setstreamurl <URL>`")
    else: await ctx.send(f"Error en `setstreamurl`: {error}"); print(f"Error en setstreamurl: {error}")

@bot.command(name='help')
async def help_command(ctx):
    """Muestra este mensaje de ayuda con todos los comandos disponibles."""
    embed = discord.Embed(
        title="Ayuda de StreamBot",
        description="Aquí tienes una lista de todos los comandos disponibles:",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="`!configurechannel <nombre_del_canal_de_voz>`",
        value="Configura el canal de voz donde el bot reproducirá la radio. **(Solo Administradores)**\n*Ejemplo: `!configurechannel Radio FM`*",
        inline=False
    )
    embed.add_field(
        name="`!setstreamurl <URL_del_stream>`",
        value="Establece o actualiza la URL del stream de radio para este servidor. **(Solo Administradores)**\nLa URL global del archivo `.env` se usará si no se configura una específica.\n*Ejemplo: `!setstreamurl http://stream.example.com/mi_radio`*",
        inline=False
    )
    embed.add_field(
        name="`!join`",
        value="Hace que el bot se una al canal de voz configurado y comience a reproducir la radio (usando la URL de stream del servidor o la global).",
        inline=False
    )
    embed.add_field(
        name="`!leave`",
        value="Hace que el bot se desconecte del canal de voz actual.",
        inline=False
    )
    embed.add_field(
        name="`!ping`",
        value="Comprueba la latencia del bot.",
        inline=False
    )
    embed.add_field(
        name="`!help`",
        value="Muestra este mensaje de ayuda.",
        inline=False
    )
    embed.set_footer(text="StreamBot - Tu radio 24/7")
    await ctx.send(embed=embed)

if __name__ == "__main__":
    if DISCORD_TOKEN and RADIO_STREAM_URL != "YOUR_STREAM_URL_HERE": # Global fallback must be changed
        try: bot.run(DISCORD_TOKEN)
        except discord.errors.PrivilegedIntentsRequired: print("Error: Intents privilegiados no habilitados.")
        except Exception as e: print(f"Error al ejecutar bot: {e}")
    else:
        if not DISCORD_TOKEN: print("Error: DISCORD_TOKEN no encontrado en .env.")
        if RADIO_STREAM_URL == "YOUR_STREAM_URL_HERE": print("Error: Global RADIO_STREAM_URL no configurado en .env.")
