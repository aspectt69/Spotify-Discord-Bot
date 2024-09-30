import discord
from discord.ext import commands
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time
import os
import asyncio
import sqlite3
from flask import Flask, request
import threading
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import logging

load_dotenv()

encryption_key = os.getenv('ENCRYPTION_KEY')
bot_token = os.getenv('BOT_TOKEN')
client_id = os.getenv('CLIENT_ID')
client_secret = os.getenv('CLIENT_SECRET')


if not all([[bot_token, client_id, client_secret, encryption_key]]):
    raise ValueError("One or more required environment variables are missing.")

logging.basicConfig(level=logging.DEBUG)
cipher = Fernet(encryption_key.encode())

# Function to encrypt data
def encrypt_data(data):
    return cipher.encrypt(data.encode()).decode()

# Function to decrypt data
def decrypt_data(encrypted_data):
    return cipher.decrypt(encrypted_data.encode()).decode()

encrypted_bot_token = encrypt_data(bot_token)
encrypted_client_id = encrypt_data(client_id)
encrypted_client_secret = encrypt_data(client_secret)

decrypted_bot_token = decrypt_data(encrypted_bot_token)
decrypted_client_id = decrypt_data(encrypted_client_id)
decrypted_client_secret = decrypt_data(encrypted_client_secret)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

db_directory = "spotify_bot"
if not os.path.exists(db_directory):
    os.makedirs(db_directory)

connection = sqlite3.connect(os.path.join(db_directory, 'spotify_tokens.db'), check_same_thread=False)
cursor = connection.cursor()

# Creates a table in the database that stores tokens
cursor.execute('''
CREATE TABLE IF NOT EXISTS tokens (
    user_id INTEGER PRIMARY KEY,
    token TEXT
)
''')
connection.commit()

# Simple flask app for the Spotify authentication
app = Flask(__name__)

def store_token(user_id, token):
    try:
        try:
            encrypted_token = encrypt_data(token)
            cursor.execute('INSERT OR REPLACE INTO tokens (user_id, token) VALUES (?, ?)', (user_id, encrypted_token))
            connection.commit()
            logging.debug("Done inserting")
        except:
            logging.debug("Inserting error")
        logging.debug(f"Successfully added the user token into database")
    except:
        logging.debug("Token storing error")

def get_token(user_id):
    cursor.execute('SELECT token FROM tokens WHERE user_id = ?', (user_id))
    result = cursor.fetchone()
    return decrypt_data(result[0]) if result else None

@app.route("/callback")
def spotify_callback():
    code = request.args.get('code')
    state = request.args.get('state')

    auth_manager = SpotifyOAuth(client_id=client_id,
                                client_secret=client_secret,
                                redirect_uri='https://spotify-authentication.onrender.com/callback',
                                scope="user-library-read user-read-playback-state user-read-currently-playing user-read-recently-played user-top-read playlist-read-private",
                                state=state)

    # Store the user's token
    try:
        token_info = auth_manager.get_access_token(code)

        #Store the users token
        if token_info and 'access_token' in token_info:
            try:
                store_token(state, token_info['access_token'])
                return "Authentication complete! You can return to discord"
            except:
                logging.debug("error 69")
                return "error 69", token_info
        else:
            logging.debug("Failed to retrieve token_info:", token_info)
            return "Failed to retrieve token. Please try again."
    except Exception as e:
        logging.debug(f"error 2: {e}")
        return "Failed. Try again:", (e)

def run_flask():
    app.run(host="0.0.0.0", port=8888)

@bot.event
async def on_ready(): 
    logging.debug(f"{bot.user} is ready")

@bot.command()
async def spotify_login(ctx):
    logging.debug(f"Login command received from {ctx.author}")
    user_id = str(ctx.author.id)
    auth_manager = SpotifyOAuth(client_id=client_id,
                                client_secret=client_secret,
                                redirect_uri='https://spotify-authentication.onrender.com/callback',
                                scope="user-library-read user-read-playback-state user-read-currently-playing user-read-recently-played user-top-read playlist-read-private")
    
    auth_url = auth_manager.get_authorize_url(state=user_id)
    await ctx.send(f"Authenticate your account here (If nothing happens just wait): {auth_url}")

@bot.command()
async def liked_songs(ctx, likedsongslimit):
    global auth_manager

    logging.debug(f"Liked Songs command from {ctx.author}")

    if likedsongslimit:
        likedsongslimit = likedsongslimit
        logging.debug("Limit received")
    else:
        likedsongslimit = 50
        logging.debug("Limit not received, defaulting to 50")

    cursor.execute('SELECT token FROM tokens WHERE user_id = ?', {ctx.author})
    result = cursor.fetchone()

    if result:
        logging.debug("Found a result for users token")
        limit = 50
        offset = 0
        fetched_songs = 0

        # Checks if its printed all the songs the user requested
        while fetched_songs < likedsongslimit:
            remaining_songs = likedsongslimit - fetched_songs
            limit = min(50, remaining_songs)
            likedsongs = auth_manager.current_user_saved_tracks(limit=limit, offset=offset)
            # For everything in liked songs, it prints the track name, id, and artist, until it's gone through the limit
            for idx, item in enumerate(likedsongs['items'], start=fetched_songs + 1):
                track = item['track']
                await ctx.send(idx, track['artists'][0]['name'], " – ", track['name'], "-->", track['id'])
                time.sleep(0.15)
                fetched_songs += 1
            # Since the limit for the api is 50, you need to use an offset to go past this limit
            offset += limit
        else:
            await ctx.send("")
            await ctx.send("All tracks printed!")
    else:
        logging.debug("Couldn't find this users stats")
        await ctx.send("I couldn't find your spotify stats! Try '!spotify_login' to link your spotify then retry")

threading.Thread(target=run_flask).start()
bot.run(bot_token)