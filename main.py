import logging
import sqlite3
import requests
import os
import random
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, CallbackContext
from telegram.ext import filters

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# OMDB API setup (get free API key from http://www.omdbapi.com/)
OMDB_API_KEY = os.environ.get('OMDB_API_KEY', 'YOUR_OMDB_API_KEY_HERE')

# Database setup
def init_db():
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS movies
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  year INTEGER,
                  genre TEXT,
                  rating REAL,
                  description TEXT,
                  poster_url TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

# Add initial admin (you can change this to your actual Telegram user ID)
def add_admin(user_id):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

# Check if user is admin
def is_admin(user_id):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

# Movie search states
SEARCH_TITLE, SEARCH_GENRE, SEARCH_YEAR, SEARCH_ACTOR, SEARCH_DIRECTOR, SEARCH_RATING = range(6)

# Start command
async def start(update: Update, context: CallbackContext) -> None:
    welcome_message = (
        "🎬 *Welcome to Movie Search Bot!*\n\n"
        "I can help you find information about movies.\n\n"
        "Commands:\n"
        "/search - Search for movies\n"
        "/random - Get a random movie recommendation\n"
        "/admin - Admin panel (for authorized users only)\n\n"
        "Just type /search to begin finding movies!"
    )
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN)

# Search command handler
async def search(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Please enter the movie title (or /cancel to cancel):")
    return SEARCH_TITLE

# Handle movie title input
async def search_title(update: Update, context: CallbackContext) -> int:
    context.user_data['title'] = update.message.text
    await update.message.reply_text("Enter genre (optional, press /skip to skip):")
    return SEARCH_GENRE

# Skip genre
async def skip_genre(update: Update, context: CallbackContext) -> int:
    context.user_data['genre'] = None
    await update.message.reply_text("Enter release year (optional, press /skip to skip):")
    return SEARCH_YEAR

# Handle genre input
async def search_genre(update: Update, context: CallbackContext) -> int:
    context.user_data['genre'] = update.message.text
    await update.message.reply_text("Enter release year (optional, press /skip to skip):")
    return SEARCH_YEAR

# Skip year
async def skip_year(update: Update, context: CallbackContext) -> int:
    context.user_data['year'] = None
    await update.message.reply_text("Enter actor name (optional, press /skip to skip):")
    return SEARCH_ACTOR

# Handle year input
async def search_year(update: Update, context: CallbackContext) -> int:
    try:
        context.user_data['year'] = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Please enter a valid year (e.g., 2020) or /skip to skip:")
        return SEARCH_YEAR
    await update.message.reply_text("Enter actor name (optional, press /skip to skip):")
    return SEARCH_ACTOR

# Skip actor
async def skip_actor(update: Update, context: CallbackContext) -> int:
    context.user_data['actor'] = None
    await update.message.reply_text("Enter director name (optional, press /skip to skip):")
    return SEARCH_DIRECTOR

# Handle actor input
async def search_actor(update: Update, context: CallbackContext) -> int:
    context.user_data['actor'] = update.message.text
    await update.message.reply_text("Enter director name (optional, press /skip to skip):")
    return SEARCH_DIRECTOR

# Skip director
async def skip_director(update: Update, context: CallbackContext) -> int:
    context.user_data['director'] = None
    await update.message.reply_text("Enter minimum rating (0-10, optional, press /skip to skip):")
    return SEARCH_RATING

# Handle director input
async def search_director(update: Update, context: CallbackContext) -> int:
    context.user_data['director'] = update.message.text
    await update.message.reply_text("Enter minimum rating (0-10, optional, press /skip to skip):")
    return SEARCH_RATING

# Skip rating
async def skip_rating(update: Update, context: CallbackContext) -> int:
    context.user_data['rating'] = None
    # Perform search
    return await perform_search(update, context)

# Handle rating input
async def search_rating(update: Update, context: CallbackContext) -> int:
    try:
        rating = float(update.message.text)
        if 0 <= rating <= 10:
            context.user_data['rating'] = rating
        else:
            await update.message.reply_text("Rating must be between 0 and 10. Press /skip to skip:")
            return SEARCH_RATING
    except ValueError:
        await update.message.reply_text("Please enter a valid rating (e.g., 7.5) or /skip to skip:")
        return SEARCH_RATING
    
    # Perform search
    return await perform_search(update, context)

# Perform the actual search
async def perform_search(update: Update, context: CallbackContext) -> int:
    # Extract search criteria
    title = context.user_data.get('title')
    genre = context.user_data.get('genre')
    year = context.user_data.get('year')
    actor = context.user_data.get('actor')
    director = context.user_data.get('director')
    rating = context.user_data.get('rating')
    
    # Search in local database first
    movies = search_movies_in_db(title, genre, year, actor, director, rating)
    
    if movies:
        await send_movie_results(update, movies)
    else:
        # If not found locally, try to fetch from OMDB API
        omdb_movies = search_movies_in_omdb(title, year, genre)
        if omdb_movies:
            await send_omdb_movie_results(update, omdb_movies)
        else:
            # If still not found, suggest similar movies
            await suggest_similar_movies(update, title)
    
    # Clear user data and end conversation
    context.user_data.clear()
    return ConversationHandler.END

# Search movies in local database
def search_movies_in_db(title=None, genre=None, year=None, actor=None, director=None, min_rating=None):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    
    query = "SELECT * FROM movies WHERE 1=1"
    params = []
    
    if title:
        query += " AND title LIKE ?"
        params.append(f"%{title}%")
    
    if genre:
        query += " AND genre LIKE ?"
        params.append(f"%{genre}%")
    
    if year:
        query += " AND year = ?"
        params.append(year)
    
    if min_rating:
        query += " AND rating >= ?"
        params.append(min_rating)
    
    # Note: Simple implementation - in a real app, you'd want more sophisticated search
    # for actor and director fields
    
    c.execute(query, params)
    movies = c.fetchall()
    conn.close()
    
    return movies

# Search movies using OMDB API
def search_movies_in_omdb(title=None, year=None, genre=None):
    if not title:
        return []
    
    params = {
        'apikey': OMDB_API_KEY,
        's': title,  # Search term
        'type': 'movie'
    }
    
    if year:
        params['y'] = year
    
    try:
        response = requests.get('http://www.omdbapi.com/', params=params)
        data = response.json()
        
        if data.get('Response') == 'True':
            return data.get('Search', [])
        else:
            logger.info(f"OMDB API error: {data.get('Error', 'Unknown error')}")
            return []
    except Exception as e:
        logger.error(f"Error fetching from OMDB API: {e}")
        return []

# Send movie results to user
async def send_movie_results(update: Update, movies):
    if not movies:
        await update.message.reply_text("No movies found matching your criteria.")
        return
    
    # Show first 5 results
    for movie in movies[:5]:
        movie_id, title, year, genre, rating, description, poster_url = movie
        
        message = f"*{title} ({year})*\n"
        if genre:
            message += f"Genre: {genre}\n"
        if rating:
            message += f"Rating: {rating}/10\n"
        if description:
            message += f"\n{description}\n"
        
        if poster_url:
            # Send photo with caption
            try:
                await update.message.reply_photo(photo=poster_url, caption=message, parse_mode=ParseMode.MARKDOWN)
            except:
                # If photo sending fails, just send text
                await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    if len(movies) > 5:
        await update.message.reply_text(f"... and {len(movies) - 5} more movies.")

# Send OMDB movie results to user
async def send_omdb_movie_results(update: Update, movies):
    if not movies:
        await update.message.reply_text("No movies found matching your criteria.")
        return
    
    # Show first 5 results
    for movie in movies[:5]:
        title = movie.get('Title', 'N/A')
        year = movie.get('Year', 'N/A')
        imdb_id = movie.get('imdbID', '')
        poster_url = movie.get('Poster', '')
        
        # Get detailed info for each movie
        details = get_movie_details_from_omdb(imdb_id)
        
        message = f"*{title} ({year})*\n"
        if details:
            genre = details.get('Genre', 'N/A')
            rating = details.get('imdbRating', 'N/A')
            plot = details.get('Plot', 'No description available.')
            
            if genre != 'N/A':
                message += f"Genre: {genre}\n"
            if rating != 'N/A':
                message += f"IMDB Rating: {rating}/10\n"
            if plot != 'No description available.':
                message += f"\n{plot}\n"
        
        if poster_url and poster_url != 'N/A':
            # Send photo with caption
            try:
                await update.message.reply_photo(photo=poster_url, caption=message, parse_mode=ParseMode.MARKDOWN)
            except:
                # If photo sending fails, just send text
                await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    if len(movies) > 5:
        await update.message.reply_text(f"... and {len(movies) - 5} more movies.")

# Get detailed movie info from OMDB
def get_movie_details_from_omdb(imdb_id):
    if not imdb_id:
        return None
    
    params = {
        'apikey': OMDB_API_KEY,
        'i': imdb_id,  # IMDB ID
        'plot': 'short'
    }
    
    try:
        response = requests.get('http://www.omdbapi.com/', params=params)
        data = response.json()
        
        if data.get('Response') == 'True':
            return data
        else:
            logger.info(f"OMDB API error: {data.get('Error', 'Unknown error')}")
            return None
    except Exception as e:
        logger.error(f"Error fetching movie details from OMDB API: {e}")
        return None

# Suggest similar movies
async def suggest_similar_movies(update: Update, title):
    # Try a broader search with just the first word of the title
    first_word = title.split()[0] if title.split() else title
    omdb_movies = search_movies_in_omdb(first_word)
    
    if omdb_movies:
        message = f"Sorry, I couldn't find '{title}'. Here are some similar movies:"
        await update.message.reply_text(message)
        await send_omdb_movie_results(update, omdb_movies[:3])  # Send top 3 suggestions
    else:
        await update.message.reply_text("Sorry, I couldn't find any movies matching your search criteria.")

# Cancel search
async def cancel(update: Update, context: CallbackContext) -> int:
    context.user_data.clear()
    await update.message.reply_text("Search cancelled.")
    return ConversationHandler.END

# Random movie recommendation
async def random_movie(update: Update, context: CallbackContext) -> None:
    # First try to get a random movie from local database
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("SELECT * FROM movies ORDER BY RANDOM() LIMIT 1")
    movie = c.fetchone()
    conn.close()
    
    if movie:
        movie_id, title, year, genre, rating, description, poster_url = movie
        
        message = f"*Random Movie Recommendation:*\n\n"
        message += f"*{title} ({year})*\n"
        if genre:
            message += f"Genre: {genre}\n"
        if rating:
            message += f"Rating: {rating}/10\n"
        if description:
            message += f"\n{description}\n"
        
        if poster_url:
            try:
                await update.message.reply_photo(photo=poster_url, caption=message, parse_mode=ParseMode.MARKDOWN)
            except:
                await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    else:
        # If no local movies, try to get a popular movie from OMDB
        try:
            params = {
                'apikey': OMDB_API_KEY,
                's': 'popular',  # Search for popular movies
                'type': 'movie'
            }
            
            response = requests.get('http://www.omdbapi.com/', params=params)
            data = response.json()
            
            if data.get('Response') == 'True' and data.get('Search'):
                # Pick a random movie from the results
                random_movie = random.choice(data['Search'])
                imdb_id = random_movie.get('imdbID', '')
                
                # Get detailed info
                details = get_movie_details_from_omdb(imdb_id)
                
                if details:
                    title = details.get('Title', 'N/A')
                    year = details.get('Year', 'N/A')
                    genre = details.get('Genre', 'N/A')
                    rating = details.get('imdbRating', 'N/A')
                    plot = details.get('Plot', 'No description available.')
                    poster_url = details.get('Poster', '')
                    
                    message = f"*Random Movie Recommendation:*\n\n"
                    message += f"*{title} ({year})*\n"
                    if genre != 'N/A':
                        message += f"Genre: {genre}\n"
                    if rating != 'N/A':
                        message += f"IMDB Rating: {rating}/10\n"
                    if plot != 'No description available.':
                        message += f"\n{plot}\n"
                    
                    if poster_url and poster_url != 'N/A':
                        try:
                            await update.message.reply_photo(photo=poster_url, caption=message, parse_mode=ParseMode.MARKDOWN)
                        except:
                            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
                    else:
                        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
                else:
                    await update.message.reply_text("Unable to fetch random movie recommendation at the moment.")
            else:
                await update.message.reply_text("Unable to fetch random movie recommendation at the moment.")
        except Exception as e:
            logger.error(f"Error fetching random movie: {e}")
            await update.message.reply_text("Unable to fetch random movie recommendation at the moment.")

# Admin panel
async def admin(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ You don't have permission to access the admin panel.")
        return
    
    admin_message = (
        "🔐 *Admin Panel*\n\n"
        "Available commands:\n"
        "/addmovie - Add a new movie\n"
        "/listmovies - List all movies\n"
        "/delmovie <id> - Delete a movie by ID\n\n"
        "Use these commands to manage the movie database."
    )
    await update.message.reply_text(admin_message, parse_mode=ParseMode.MARKDOWN)

# Add movie command
async def add_movie_start(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ You don't have permission to add movies.")
        return
    
    await update.message.reply_text(
        "Please provide movie details in the following format:\n\n"
        "Title: <movie title>\n"
        "Year: <release year>\n"
        "Genre: <genre>\n"
        "Rating: <rating>\n"
        "Description: <movie description>\n"
        "Poster: <poster URL (optional)>\n\n"
        "Or type /cancel to cancel."
    )

# Handle add movie input
async def add_movie_process(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ You don't have permission to add movies.")
        return
    
    text = update.message.text
    lines = text.split('\n')
    
    movie_data = {}
    for line in lines:
        if ':' in line:
            key, value = line.split(':', 1)
            movie_data[key.strip().lower()] = value.strip()
    
    # Required fields
    required_fields = ['title', 'year', 'genre', 'rating', 'description']
    missing_fields = [field for field in required_fields if field not in movie_data]
    
    if missing_fields:
        await update.message.reply_text(f"Missing required fields: {', '.join(missing_fields)}. Please try again.")
        return
    
    # Validate year
    try:
        year = int(movie_data['year'])
    except ValueError:
        await update.message.reply_text("Year must be a number. Please try again.")
        return
    
    # Validate rating
    try:
        rating = float(movie_data['rating'])
        if not (0 <= rating <= 10):
            await update.message.reply_text("Rating must be between 0 and 10. Please try again.")
            return
    except ValueError:
        await update.message.reply_text("Rating must be a number. Please try again.")
        return
    
    # Add to database
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("""
        INSERT INTO movies (title, year, genre, rating, description, poster_url)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        movie_data['title'],
        year,
        movie_data['genre'],
        rating,
        movie_data['description'],
        movie_data.get('poster', '')
    ))
    conn.commit()
    movie_id = c.lastrowid
    conn.close()
    
    await update.message.reply_text(f"✅ Movie added successfully with ID: {movie_id}")

# List movies command
async def list_movies(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ You don't have permission to list movies.")
        return
    
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("SELECT id, title, year, genre FROM movies ORDER BY title")
    movies = c.fetchall()
    conn.close()
    
    if not movies:
        await update.message.reply_text("No movies in the database.")
        return
    
    message = "*Movie List:*\n\n"
    for movie in movies:
        movie_id, title, year, genre = movie
        message += f"ID: {movie_id} | {title} ({year}) | {genre}\n"
    
    # Split message if too long
    if len(message) > 4096:
        chunks = [message[i:i+4096] for i in range(0, len(message), 4096)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

# Delete movie command
async def del_movie(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ You don't have permission to delete movies.")
        return
    
    if not context.args:
        await update.message.reply_text("Please provide a movie ID to delete. Usage: /delmovie <id>")
        return
    
    try:
        movie_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid movie ID. Please provide a numeric ID.")
        return
    
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("SELECT title FROM movies WHERE id=?", (movie_id,))
    movie = c.fetchone()
    
    if not movie:
        conn.close()
        await update.message.reply_text(f"No movie found with ID: {movie_id}")
        return
    
    c.execute("DELETE FROM movies WHERE id=?", (movie_id,))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ Movie '{movie[0]}' deleted successfully.")

# Error handler
async def error_handler(update: object, context: CallbackContext) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)
    # Don't send error details to user for security reasons

# Webhook setup
def setup_webhook(application, token):
    """Setup webhook for the bot"""
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL', '')
    PORT = int(os.environ.get('PORT', 8443))
    
    if WEBHOOK_URL:
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=token,
            webhook_url=f"{WEBHOOK_URL}/{token}"
        )
        logger.info("Bot started with webhook")
    else:
        application.run_polling()
        logger.info("Bot started with polling")

# Main function
def main():
    # Initialize database
    init_db()
    
    # Add your Telegram bot token here or set it as an environment variable
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')
    
    # Create the Application
    application = Application.builder().token(TOKEN).build()
    
    # Add conversation handler for movie search
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('search', search)],
        states={
            SEARCH_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_title)],
            SEARCH_GENRE: [
                CommandHandler('skip', skip_genre),
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_genre)
            ],
            SEARCH_YEAR: [
                CommandHandler('skip', skip_year),
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_year)
            ],
            SEARCH_ACTOR: [
                CommandHandler('skip', skip_actor),
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_actor)
            ],
            SEARCH_DIRECTOR: [
                CommandHandler('skip', skip_director),
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_director)
            ],
            SEARCH_RATING: [
                CommandHandler('skip', skip_rating),
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_rating)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    application.add_handler(conv_handler)
    
    # Add other handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("random", random_movie))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CommandHandler("addmovie", add_movie_start))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, add_movie_process))
    application.add_handler(CommandHandler("listmovies", list_movies))
    application.add_handler(CommandHandler("delmovie", del_movie))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Setup webhook or polling
    setup_webhook(application, TOKEN)

if __name__ == '__main__':
    main()