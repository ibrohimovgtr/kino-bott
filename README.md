# Movie Search Telegram Bot

A Telegram bot that allows users to search for movies by title, genre, year, actor, director, and rating. Features include an admin panel for managing movies, database storage, and 24/7 operation support with webhook.

## Features

- 🔍 **Movie Search**: Search by title, genre, year, actor, director, and rating
- 🎲 **Random Movie**: Get random movie recommendations
- 👨‍💼 **Admin Panel**: Add, delete, and list movies (admin access required)
- 💾 **Database Storage**: SQLite database for storing movie information
- 🌐 **Webhook Support**: 24/7 operation with webhook or polling
- 📱 **User-Friendly**: Formatted responses with Markdown and posters when available

## Requirements

- Python 3.11+
- A Telegram Bot Token (get from [@BotFather](https://t.me/BotFather))
- OMDB API Key (get free key from [OMDB API](http://www.omdbapi.com/))

## Installation

1. Clone this repository:

   ```
   git clone <repository-url>
   cd movie-search-bot
   ```

2. Install required packages:

   ```
   pip install -r requirements.txt
   ```

3. Set up environment variables by copying `.env.example` to `.env` and filling in your values:

   ```
   cp .env.example .env
   ```

   Then edit the `.env` file with your actual values.

4. Run the bot:
   ```
   python main.py
   ```

## Usage

### User Commands

- `/start` - Welcome message and instructions
- `/search` - Start movie search wizard
- `/random` - Get a random movie recommendation

### Admin Commands

- `/admin` - Open admin panel
- `/addmovie` - Add a new movie to the database
- `/listmovies` - List all movies in the database
- `/delmovie <id>` - Delete a movie by ID

To make a user an admin, add their Telegram user ID to the `admins` table in the database.

## Deployment

### Local Deployment

1. Set environment variables in the `.env` file:

   ```
   TELEGRAM_BOT_TOKEN=your_bot_token
   OMDB_API_KEY=your_omdb_api_key
   ```

2. Run the bot:
   ```
   python main.py
   ```

### Webhook Deployment (for 24/7 hosting)

1. Set environment variables in the `.env` file:

   ```
   TELEGRAM_BOT_TOKEN=your_bot_token
   OMDB_API_KEY=your_omdb_api_key
   WEBHOOK_URL=https://yourdomain.com
   PORT=8443
   ```

2. Run the bot:
   ```
   python main.py
   ```

### Hosting Options

- **Heroku**: Deploy with Procfile
- **Render**: Deploy as a web service
- **VPS**: Run with systemd or similar process manager

## Adding Admin Users

To add admin users, you need to manually insert their Telegram user IDs into the database:

```sql
INSERT INTO admins (user_id) VALUES (123456789);
```

Replace `123456789` with the actual Telegram user ID.

## Security

- Admin commands are protected by user ID verification
- No personal user data is stored
- API keys should be kept secret

## License

MIT License
