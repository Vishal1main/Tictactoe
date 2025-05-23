import logging
import os
import random
import asyncio
from typing import List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Game constants
EMPTY = " "
X = "X"
O = "O"

# Game state storage
games = {}
invitations = {}
player_games = {}

class TicTacToeGame:
    def __init__(self, player1: int, player2: int, game_id: str):
        self.board = [EMPTY] * 9
        self.players = {X: player1, O: player2}
        self.current_player = X
        self.winner = None
        self.draw = False
        self.game_id = game_id

    def make_move(self, position: int) -> bool:
        if 0 <= position < 9 and self.board[position] == EMPTY and not self.winner:
            self.board[position] = self.current_player
            self.check_winner()
            if not self.winner and EMPTY not in self.board:
                self.draw = True
            else:
                self.current_player = O if self.current_player == X else X
            return True
        return False

    def check_winner(self):
        win_combinations = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],
            [0, 3, 6], [1, 4, 7], [2, 5, 8],
            [0, 4, 8], [2, 4, 6]
        ]
        for a, b, c in win_combinations:
            if self.board[a] != EMPTY and self.board[a] == self.board[b] == self.board[c]:
                self.winner = self.board[a]
                return

def generate_game_id() -> str:
    return ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=6))

def escape_html(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

async def get_player_name(context, chat_id: int, user_id: int) -> str:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return escape_html(member.user.first_name)
    except Exception:
        return "Player"

def create_game_markup(board: List[str], game_id: str) -> InlineKeyboardMarkup:
    keyboard = []
    for i in range(0, 9, 3):
        row = [
            InlineKeyboardButton(board[i + j], callback_data=f"move_{i + j}_{game_id}")
            for j in range(3)
        ]
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🚩 Surrender", callback_data=f"surrender_{game_id}")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! I'm a Tic Tac Toe bot. Use /play to start a game in this group!",
        parse_mode='HTML'
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    username = update.message.from_user.first_name

    if user_id in player_games:
        await update.message.reply_text("⚠️ You're already in a game! Finish it first.", parse_mode='HTML')
        return

    game_id = generate_game_id()
    keyboard = [
        [InlineKeyboardButton("🎮 Join Game", callback_data=f"join_{user_id}_{game_id}")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{user_id}_{game_id}")]
    ]
    message = await update.message.reply_text(
        f"🎲 {escape_html(username)} wants to play Tic Tac Toe! (Game ID: {game_id})\n\n"
        "Click <b>Join Game</b> to play!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    invitations[chat_id] = {'message_id': message.message_id, 'host': user_id, 'game_id': game_id}

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("join_"):
        await handle_join(query, context)
    elif data.startswith("cancel_"):
        await handle_cancel(query)
    elif data.startswith("move_"):
        await handle_move(query, context)
    elif data.startswith("surrender_"):
        await handle_surrender(query, context)

async def handle_join(query, context):
    parts = query.data.split('_')
    chat_id = query.message.chat_id
    host_id = int(parts[1])
    game_id = parts[2]
    user_id = query.from_user.id

    if chat_id not in invitations or invitations[chat_id]['game_id'] != game_id:
        await query.answer("Game invitation expired", show_alert=True)
        return

    if user_id == host_id:
        await query.answer("Can't play against yourself!", show_alert=True)
        return

    if user_id in player_games:
        await query.answer("You're already in a game!", show_alert=True)
        return

    game_key = (chat_id, game_id)
    games[game_key] = TicTacToeGame(host_id, user_id, game_id)
    player_games[host_id] = game_key
    player_games[user_id] = game_key

    host_name = await get_player_name(context, chat_id, host_id)
    player_name = await get_player_name(context, chat_id, user_id)

    await query.edit_message_text(
        f"<b>Game {game_id} started!</b>\n\n"
        f"<b>{X}:</b> {host_name}\n<b>{O}:</b> {player_name}\n\n"
        f"It's <b>{X}'s</b> turn!",
        reply_markup=create_game_markup(games[game_key].board, game_id),
        parse_mode='HTML'
    )
    del invitations[chat_id]

async def handle_cancel(query):
    parts = query.data.split('_')
    chat_id = query.message.chat_id
    host_id = int(parts[1])
    game_id = parts[2]
    user_id = query.from_user.id

    if chat_id in invitations and user_id == host_id and invitations[chat_id]['game_id'] == game_id:
        del invitations[chat_id]
        await query.edit_message_text("❌ Game cancelled", parse_mode='HTML')

async def handle_move(query, context):
    parts = query.data.split('_')
    chat_id = query.message.chat_id
    position = int(parts[1])
    game_id = parts[2]
    game_key = (chat_id, game_id)
    user_id = query.from_user.id

    if game_key not in games:
        await query.answer("Game not found", show_alert=True)
        return

    game = games[game_key]
    if user_id != game.players[game.current_player]:
        current_player = await get_player_name(context, chat_id, game.players[game.current_player])
        await query.answer(f"It's {current_player}'s turn", show_alert=True)
        return

    if not game.make_move(position):
        await query.answer("Invalid move", show_alert=True)
        return

    await update_game_state(query, context, game_key)

async def handle_surrender(query, context):
    game_id = query.data.split('_')[1]
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    game_key = (chat_id, game_id)

    if game_key not in games:
        await query.answer("Game not found", show_alert=True)
        return

    game = games[game_key]
    if user_id not in game.players.values():
        await query.answer("You're not in this game", show_alert=True)
        return

    winner_id = game.players[O] if user_id == game.players[X] else game.players[X]
    winner_name = await get_player_name(context, chat_id, winner_id)

    del games[game_key]
    player_games.pop(game.players[X], None)
    player_games.pop(game.players[O], None)

    await query.edit_message_text(
        f"🏳️ Game surrendered!\n\n🎉 Winner: <b>{winner_name}</b>",
        parse_mode='HTML'
    )

async def update_game_state(query, context, game_key):
    game = games[game_key]
    chat_id, game_id = game_key

    player1 = await get_player_name(context, chat_id, game.players[X])
    player2 = await get_player_name(context, chat_id, game.players[O])

    if game.winner:
        winner_name = player1 if game.winner == X else player2
        text = (f"🏆 Game Over!\n\n"
                f"<b>{X}:</b> {player1}\n<b>{O}:</b> {player2}\n\n"
                f"🎉 Winner: <b>{winner_name}</b>")
        del games[game_key]
        player_games.pop(game.players[X], None)
        player_games.pop(game.players[O], None)
        await query.edit_message_text(text, parse_mode='HTML')

    elif game.draw:
        text = (f"🤝 Game Over!\n\n"
                f"<b>{X}:</b> {player1}\n<b>{O}:</b> {player2}\n\n"
                f"<b>It's a draw!</b>")
        del games[game_key]
        player_games.pop(game.players[X], None)
        player_games.pop(game.players[O], None)
        await query.edit_message_text(text, parse_mode='HTML')

    else:
        current_player = player1 if game.current_player == X else player2
        text = (f"🎮 Game {game_id}\n\n"
                f"<b>{X}:</b> {player1}\n<b>{O}:</b> {player2}\n\n"
                f"It's <b>{game.current_player}'s</b> turn (<i>{current_player}</i>)")
        await query.edit_message_text(
            text,
            reply_markup=create_game_markup(game.board, game_id),
            parse_mode='HTML'
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = """
<b>🎮 Tic Tac Toe Bot Commands:</b>

/play - Create a game invitation
/help - Show this help message

<b>How to play:</b>
1. Use /play to create a game
2. Another player clicks "Join Game"
3. Take turns clicking the board
4. First to get 3 in a row wins!
5. Click 🚩 Surrender to quit
"""
    await update.message.reply_text(help_text, parse_mode='HTML')

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error {context.error}")
    if hasattr(update, 'callback_query'):
        try:
            await update.callback_query.answer("⚠️ An error occurred", show_alert=True)
        except:
            pass

async def main():
    token = os.getenv("BOT_TOKEN")  # Set your bot token in environment
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("play", play))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_error_handler(error_handler)

    logger.info("Bot started...")
    PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

await application.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    webhook_url=WEBHOOK_URL,
)
if __name__ == '__main__':
    asyncio.run(main())
