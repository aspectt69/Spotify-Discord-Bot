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

load_dotenv()

encryption_key = os.getenv('ENCRYPTION_KEY')
bot_token = os.getenv('BOT_TOKEN')
client_id = os.getenv('CLIENT_ID')
client_secret = os.getenv('CLIENT_SECRET')


if not all([[bot_token, client_id, client_secret, encryption_key]]):
    raise ValueError("One or more required environment variables are missing.")

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

connection = sqlite3.connect('discord_bots/spotify_tokens.db', check_same_thread=False)
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
    encrypted_token = encrypt_data(token)
    cursor.execute('INSERT OR REPLACE INTO tokens (user_id, token) VALUES (?, ?)', (user_id, encrypted_token))
    connection.commit()
    print(f"Successfully added the user token into database")

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
                                redirect_uri='http://localhost:8888/callback',
                                scope="user-library-read user-read-playback-state user-read-currently-playing user-read-recently-played user-top-read playlist-read-private",
                                state=state)
    token_info = auth_manager.get_access_token(code)

    #Store the users token
    store_token(state, token_info['access_token'])

    return "Authentication complete! You can return to discord"

def run_flask():
    app.run(host="0.0.0.0", port=8888)

@bot.event
async def on_ready():
    print(f"{bot.user} is ready")

@bot.command()
async def spotify_login(ctx):
    print("fLogin command received from {ctx.author}")
    user_id = str(ctx.author.id)
    auth_manager = SpotifyOAuth(client_id=client_id,
                                client_secret=client_secret,
                                redirect_uri='http://localhost:8888/callback',
                                scope="user-library-read user-read-playback-state user-read-currently-playing user-read-recently-played user-top-read playlist-read-private")
    
    auth_url = auth_manager.get_authorize_url(state=user_id)
    await ctx.send(f"Authenticate your account here: {auth_url}")

threading.Thread(target=run_flask).start()
bot.run(bot_token)