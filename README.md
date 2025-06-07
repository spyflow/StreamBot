# StreamBot - Tu Radio 24/7 en Discord

StreamBot es un bot de Discord diseñado para reproducir un stream de radio en un canal de voz específico de tu servidor, de forma continua (24/7). Permite configurar el canal, **establecer URLs de stream de radio por servidor,** unirse, salir y obtener ayuda sobre los comandos. Está pensado para ser compatible con múltiples servidores de Discord simultáneamente.

## Características

- Reproducción de radio 24/7 desde una URL de stream.
- Configuración de canal por servidor.
- **Configuración de URL de stream de radio por servidor** (con una URL global de fallback).
- Comandos intuitivos en español.
- Soporte para múltiples servidores.
- Reconexión automática en caso de desconexiones o errores del stream.

## Configuración del Bot

Sigue estos pasos para poner en marcha StreamBot en tu servidor:

### Prerrequisitos

- **Python 3.8 o superior.**
- **FFmpeg:** Debes tener FFmpeg instalado y accesible en el PATH de tu sistema. FFmpeg es necesario para la codificación y decodificación de audio.
    - Para Windows: Puedes descargarlo desde [ffmpeg.org](https://ffmpeg.org/download.html) y añadir la carpeta `bin` a tu PATH.
    - Para Linux (Debian/Ubuntu): `sudo apt update && sudo apt install ffmpeg`
    - Para macOS (usando Homebrew): `brew install ffmpeg`

### Pasos de Instalación

1.  **Clona este repositorio (si aún no lo has hecho):**
    ```bash
    git clone https://github.com/spyflow/StreamBot.git
    cd StreamBot
    ```

2.  **Crea un Entorno Virtual (Recomendado):**
    ```bash
    python -m venv venv
    ```
    Actívalo:
    - Windows: `.\venv\Scripts\activate`
    - Linux/macOS: `source venv/bin/activate`

3.  **Instala las Dependencias:**
    Asegúrate de que tu entorno virtual esté activado.
    ```bash
    pip install -r requirements.txt
    ```

4.  **Obtén un Token de Bot de Discord:**
    - Ve al [Portal de Desarrolladores de Discord](https://discord.com/developers/applications).
    - Crea una "Nueva Aplicación". Dale un nombre (ej. StreamBot).
    - Ve a la pestaña "Bot" y haz clic en "Añadir Bot".
    - **Habilita los Intents Privilegiados:**
        - `SERVER MEMBERS INTENT` - **Necesario.**
        - `MESSAGE CONTENT INTENT` - **Necesario.**
    - Copia el Token del Bot. **¡No compartas este token con nadie!**

5.  **Configura las Variables de Entorno:**
    - Crea un archivo llamado `.env` en la raíz del proyecto.
    - Copia el contenido de `.env.example` y pégalo en tu nuevo archivo `.env`.
    - Reemplaza los valores:
      ```env
      DISCORD_TOKEN=TU_TOKEN_DE_DISCORD_AQUI
      RADIO_STREAM_URL=URL_DE_TU_STREAM_DE_RADIO_GLOBAL_FALLBACK_AQUI
      ```
      - `DISCORD_TOKEN`: Pega el token que copiaste.
      - `RADIO_STREAM_URL`: Introduce la URL del stream de radio que quieres que el bot reproduzca **por defecto o como fallback global**. Si un servidor no configura su propia URL de stream, se usará esta. Asegúrate de que sea un stream de audio directo.

6.  **Invita el Bot a tu Servidor:**
    - En el Portal de Desarrolladores de Discord, ve a tu aplicación, luego a "OAuth2" -> "URL Generator".
    - Selecciona los siguientes scopes:
        - `bot`
        - `applications.commands` (Aunque este bot usa prefijos, es buena práctica)
    - Selecciona los siguientes Permisos de Bot:
        - `View Channels` (Ver Canales)
        - `Send Messages` (Enviar Mensajes)
        - `Embed Links` (Incrustar Enlaces) - Para el comando `!help`.
        - `Connect` (Conectar a Canales de Voz)
        - `Speak` (Hablar en Canales de Voz)
        - `Read Message History` (Leer Historial de Mensajes) - Para procesar comandos.
    - Copia la URL generada y pégala en tu navegador. Selecciona el servidor al que quieres añadir el bot y autoriza.

## Ejecutar el Bot

Una vez completada la configuración:

1.  Asegúrate de que tu entorno virtual (si creaste uno) esté activado.
2.  Ejecuta el bot desde la raíz del proyecto:
    ```bash
    python bot.py
    ```
3.  Si todo está configurado correctamente, verás mensajes en la consola indicando que el bot se ha conectado y el chequeo de FFmpeg.

## Comandos Disponibles

Aquí tienes una lista de los comandos que puedes usar con StreamBot:

-   `!configurechannel <nombre_del_canal_de_voz>`
    -   Configura el canal de voz donde el bot reproducirá la radio.
    -   **Solo para Administradores.**
    -   *Ejemplo: `!configurechannel Radio FM`*

-   `!setstreamurl <URL_del_stream>`
    -   Establece o actualiza la URL del stream de radio específica para este servidor.
    -   Si no se establece una URL para el servidor, se usará la URL global definida en el archivo `.env` del bot.
    -   **Solo para Administradores.**
    -   *Ejemplo: `!setstreamurl http://stream.servidor.com/mi_radio_local`*

-   `!join`
    -   Hace que el bot se una al canal de voz configurado y comience a reproducir la radio.
    -   Utilizará la URL de stream configurada para el servidor. Si no hay ninguna, usará la URL global de fallback.

-   `!leave`
    -   Hace que el bot se desconecte del canal de voz actual.

-   `!ping`
    -   Comprueba la latencia del bot y te responde con "Pong!".

-   `!help`
    -   Muestra un mensaje de ayuda con todos los comandos disponibles.

## Solución de Problemas Comunes

-   **El bot no se conecta / error de token:** Asegúrate de que `DISCORD_TOKEN` en tu archivo `.env` es correcto y no tiene espacios extra.
-   **El bot se une pero no reproduce audio / errores de FFmpeg:**
    -   Verifica que FFmpeg esté instalado y que su directorio `bin` esté en el PATH del sistema. Puedes probar escribiendo `ffmpeg -version` en tu terminal.
    -   Asegúrate de que `RADIO_STREAM_URL` en tu archivo `.env` (para fallback global) o la URL configurada con `!setstreamurl` (para el servidor específico) es una URL de stream de audio válida y funcional.
-   **El bot no responde a comandos:**
    -   Verifica que los Intents Privilegiados (`SERVER MEMBERS INTENT` y `MESSAGE CONTENT INTENT`) estén habilitados en el portal de desarrolladores de Discord para tu bot.
    -   Asegúrate de que el bot tiene los permisos necesarios en el canal/servidor (Ver Canales, Enviar Mensajes, Leer Historial de Mensajes).
-   **`PrivilegedIntentsRequired` en la consola:** Habilita los intents mencionados arriba en el portal de desarrolladores.

---

¡Disfruta de tu radio 24/7 con StreamBot!
