import requests
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio
from datetime import datetime
import threading
from dotenv import load_dotenv
import os


load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN missing. Fix your .env file")

CHECK_INTERVAL = 300  # 5 minutes in seconds



class LeetCodeTracker:
    def __init__(self):
        self.user_data = {}
        self.subscribers = set()
        self.user_tracking = {} 

        self.app = None
        self.load_state()
    
    def load_state(self):
        """Load previous state from file"""
        try:
            with open('leetcode_state.json', 'r') as f:
                data = json.load(f)
                self.user_data = data.get('user_data', {})
                self.subscribers = set(data.get('subscribers', []))
                self.user_tracking = data.get('user_tracking', {})

        except FileNotFoundError:
            self.user_data = {}
            self.subscribers = set()
            self.user_tracking = {}
    
        # json.dump({
        #     'user_data': self.user_data,
        #     'subscribers': list(self.subscribers),
        #     'user_tracking': self.user_tracking
        # }, f, indent=2)
    
    def save_state(self):
        """Save current state to file"""
        with open('leetcode_state.json', 'w') as f:
            json.dump({
                'user_data': self.user_data,
                'subscribers': list(self.subscribers),
                'user_tracking': self.user_tracking
            }, f, indent=2)

    
    # async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # chat_id = str(update.effective_chat.id)

    # if len(context.args) < 2:
    #     await update.message.reply_text("Usage: /add username name")
    #     return

    # username = context.args[0]
    # name = " ".join(context.args[1:])

    # if chat_id not in tracker.user_tracking:
    #     tracker.user_tracking[chat_id] = []

    # tracker.user_tracking[chat_id].append({
    #     "username": username,
    #     "name": name
    # })

    # tracker.save_state()

    # await update.message.reply_text(f"✅ Added {name} (@{username})")


    def get_user_stats(self, username):
        """Fetch user stats from LeetCode API"""
        # Try multiple API endpoints
        apis = [
            f"https://leetcode-stats-api.herokuapp.com/{username}",
            f"https://alfa-leetcode-api.onrender.com/{username}/solved",
            f"https://leetcode.com/graphql"
        ]
        
        # Try first API
        try:
            response = requests.get(apis[0], timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    return data
        except:
            pass
        
        # Try second API
        try:
            response = requests.get(apis[1], timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Convert format to match our expected format
                if "solvedProblem" in data:
                    return {
                        "totalSolved": data.get("solvedProblem", 0),
                        "easySolved": data.get("easySolved", 0),
                        "mediumSolved": data.get("mediumSolved", 0),
                        "hardSolved": data.get("hardSolved", 0)
                    }
        except:
            pass
        
        # Try GraphQL API
        try:
            query = """
            query getUserProfile($username: String!) {
                matchedUser(username: $username) {
                    submitStats {
                        acSubmissionNum {
                            difficulty
                            count
                        }
                    }
                }
            }
            """
            response = requests.post(
                apis[2],
                json={"query": query, "variables": {"username": username}},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if "data" in data and data["data"]["matchedUser"]:
                    stats = data["data"]["matchedUser"]["submitStats"]["acSubmissionNum"]
                    result = {"totalSolved": 0, "easySolved": 0, "mediumSolved": 0, "hardSolved": 0}
                    for item in stats:
                        if item["difficulty"] == "All":
                            result["totalSolved"] = item["count"]
                        elif item["difficulty"] == "Easy":
                            result["easySolved"] = item["count"]
                        elif item["difficulty"] == "Medium":
                            result["mediumSolved"] = item["count"]
                        elif item["difficulty"] == "Hard":
                            result["hardSolved"] = item["count"]
                    return result
        except Exception as e:
            print(f"Error fetching data for {username}: {e}")
        
        return None
    
    def check_updates(self):
        """Check for new solved problems for all users"""
        all_updates = {}  # {chat_id: [messages]}
        
        for chat_id, students in self.user_tracking.items():
            updates = []
            
            for student in students:
                username = student["username"]
                name = student["name"]
                
                stats = self.get_user_stats(username)
                if not stats:
                    continue
                
                total_solved = stats.get("totalSolved", 0)
                easy_solved = stats.get("easySolved", 0)
                medium_solved = stats.get("mediumSolved", 0)
                hard_solved = stats.get("hardSolved", 0)
                
                # Initialize user data if not exists
                user_key = f"{chat_id}:{username}"
                if user_key not in self.user_data:
                    self.user_data[user_key] = {
                        "total": total_solved,
                        "easy": easy_solved,
                        "medium": medium_solved,
                        "hard": hard_solved
                    }
                    continue
                
                # Check for changes
                prev_data = self.user_data[user_key]
                
                if total_solved > prev_data["total"]:
                    # Determine difficulty of solved problem
                    difficulty = ""
                    emoji = ""
                    if easy_solved > prev_data["easy"]:
                        difficulty = "Easy"
                        emoji = "🟢"
                    elif medium_solved > prev_data["medium"]:
                        difficulty = "Medium"
                        emoji = "🟡"
                    elif hard_solved > prev_data["hard"]:
                        difficulty = "Hard"
                        emoji = "🔴"
                    
                    problems_solved = total_solved - prev_data["total"]
                    
                    update_msg = f"{emoji} *{name}* just solved {problems_solved} {difficulty} problem!\n"
                    update_msg += f"📊 Total: *{total_solved}* | Easy: {easy_solved} | Medium: {medium_solved} | Hard: {hard_solved}"
                    
                    updates.append(update_msg)
                    
                    # Update stored data
                    self.user_data[user_key] = {
                        "total": total_solved,
                        "easy": easy_solved,
                        "medium": medium_solved,
                        "hard": hard_solved
                    }
            
            if updates:
                all_updates[chat_id] = updates
        
        return all_updates
    
    def get_leaderboard(self, chat_id):
        """Get current leaderboard for a specific user"""
        students = self.user_tracking.get(chat_id, [])
        leaderboard = []
        
        for student in students:
            username = student["username"]
            name = student["name"]
            user_key = f"{chat_id}:{username}"
            
            if user_key in self.user_data:
                data = self.user_data[user_key]
                leaderboard.append({
                    'name': name,
                    'total': data['total'],
                    'easy': data['easy'],
                    'medium': data['medium'],
                    'hard': data['hard']
                })
        
        # Sort by total solved
        leaderboard.sort(key=lambda x: x['total'], reverse=True)
        return leaderboard

# Global tracker instance
tracker = LeetCodeTracker()

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - subscribe to notifications"""
    chat_id = str(update.effective_chat.id)
    tracker.subscribers.add(chat_id)
    tracker.save_state()
    
    welcome_msg = (
        "🎉 *Welcome to LeetCode Tracker Bot!*\n\n"
        "📢 You are now subscribed to notifications!\n\n"
        "*Available Commands:*\n"
        "/start - Subscribe to notifications\n"
        "/stop - Unsubscribe from notifications\n"
        "/add username name - Add a friend to track\n"
        "/remove username - Remove a friend\n"
        "/mylist - View your tracking list\n"
        "/status - Check current status\n"
        "/leaderboard - View top performers\n"
        "/check - Manually check for updates\n"
        "/help - Show this message\n\n"
        "💡 *Get Started:*\n"
        "Add your first friend with:\n"
        "`/add leetcode_username Friend Name`\n\n"
        "Example: `/add john_doe John Doe`"
    )
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop command - unsubscribe from notifications"""
    chat_id = str(update.effective_chat.id)
    if chat_id in tracker.subscribers:
        tracker.subscribers.remove(chat_id)
        tracker.save_state()
        await update.message.reply_text("👋 You've been unsubscribed from notifications.\nSend /start to subscribe again!")
    else:
        await update.message.reply_text("You're not subscribed. Send /start to subscribe!")


async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a friend to track"""
    chat_id = str(update.effective_chat.id)
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ *Invalid format!*\n\n"
            "Usage: `/add username name`\n\n"
            "Example:\n"
            "`/add john_doe John Doe`",
            parse_mode='Markdown'
        )
        return
    
    username = context.args[0]
    name = " ".join(context.args[1:])
    
    # Initialize tracking list if doesn't exist
    if chat_id not in tracker.user_tracking:
        tracker.user_tracking[chat_id] = []
    
    # Check if user already exists
    for user in tracker.user_tracking[chat_id]:
        if user["username"] == username:
            await update.message.reply_text(f"⚠️ {name} (@{username}) is already in your list!")
            return
    
    # Add user
    tracker.user_tracking[chat_id].append({
        "username": username,
        "name": name
    })
    
    tracker.save_state()
    
    await update.message.reply_text(
        f"✅ *Added to your tracking list!*\n\n"
        f"👤 Name: {name}\n"
        f"🔗 LeetCode: @{username}\n\n"
        f"📊 Current Stats:\n"
        # f"Total: *{total}*\n"
        # f"🟢 {easy} | 🟡 {medium} | 🔴 {hard}",
        f"Bot will start tracking their progress!",
        parse_mode='Markdown'
    )


async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a friend from tracking"""
    chat_id = str(update.effective_chat.id)
    
    if not context.args:
        await update.message.reply_text(
            "❌ *Invalid format!*\n\n"
            "Usage: `/remove username`\n\n"
            "Example:\n"
            "`/remove john_doe`",
            parse_mode='Markdown'
        )
        return
    
    username = context.args[0]
    
    if chat_id not in tracker.user_tracking:
        await update.message.reply_text("You don't have any tracked users yet!")
        return
    
    # Find and remove user
    original_count = len(tracker.user_tracking[chat_id])
    tracker.user_tracking[chat_id] = [
        u for u in tracker.user_tracking[chat_id]
        if u["username"] != username
    ]
    
    if len(tracker.user_tracking[chat_id]) == original_count:
        await update.message.reply_text(f"❌ User @{username} not found in your list!")
        return
    
    tracker.save_state()
    await update.message.reply_text(f"✅ Removed @{username} from your tracking list!")
 
async def mylist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View your tracking list"""
    chat_id = str(update.effective_chat.id)
    
    users = tracker.user_tracking.get(chat_id, [])
    
    if not users:
        await update.message.reply_text(
            "📭 *Your tracking list is empty!*\n\n"
            "Add friends with:\n"
            "`/add username name`\n\n"
            "Example:\n"
            "`/add john_doe John Doe`",
            parse_mode='Markdown'
        )
        return
    
    msg = "📌 *Your Tracking List:*\n\n"
    for i, u in enumerate(users, 1):
        msg += f"{i}. *{u['name']}* (@{u['username']})\n"
    
    msg += f"\n👥 Total: {len(users)} friend(s)"
    
    await update.message.reply_text(msg, parse_mode='Markdown')



async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Status command - show tracking status"""
    chat_id = str(update.effective_chat.id)
    subscribed = "✅ Subscribed" if chat_id in tracker.subscribers else "❌ Not subscribed"
    
    tracked_count = len(tracker.user_tracking.get(chat_id, []))
    
    status_msg = (
        f"*📊 Your Bot Status*\n\n"
        f"👥 Tracking: *{tracked_count}* friend(s)\n"
        f"📢 Notifications: {subscribed}\n"
        f"🔄 Auto-check: Every 5 minutes\n"
        f"💾 Data saved: Yes\n\n"
        f"Use /mylist to see who you're tracking!"
    )
    await update.message.reply_text(status_msg, parse_mode='Markdown')

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Leaderboard command - show top performers"""
    chat_id = str(update.effective_chat.id)
    board = tracker.get_leaderboard(chat_id)
    
    if not board:
        await update.message.reply_text(
            "📊 *No leaderboard data yet!*\n\n"
            "Reasons:\n"
            "• You haven't added any friends yet\n"
            "• Bot is still collecting data\n\n"
            "Add friends with: `/add username name`",
            parse_mode='Markdown'
        )
        return
    
    msg = "🏆 *Your LeetCode Leaderboard*\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for i, student in enumerate(board, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        msg += (
            f"{medal} *{student['name']}*\n"
            f"   📊 Total: {student['total']} | "
            f"🟢 {student['easy']} | "
            f"🟡 {student['medium']} | "
            f"🔴 {student['hard']}\n\n"
        )
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual check command"""
    chat_id = str(update.effective_chat.id)
    
    if chat_id not in tracker.user_tracking or not tracker.user_tracking[chat_id]:
        await update.message.reply_text(
            "⚠️ You haven't added any friends yet!\n\n"
            "Add friends with:\n"
            "`/add username name`",
            parse_mode='Markdown'
        )
        return
    
    await update.message.reply_text("🔍 Checking for updates...")
    
    all_updates = tracker.check_updates()
    updates = all_updates.get(chat_id, [])
    
    if updates:
        tracker.save_state()
        for msg in updates:
            await update.message.reply_text(msg, parse_mode='Markdown')
        await update.message.reply_text(f"✅ Found {len(updates)} new update(s)!")
    else:
        await update.message.reply_text("✅ No new updates. Everyone's scores are up to date!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    help_msg = (
        "*🤖 LeetCode Tracker Bot - Help*\n\n"
        "*📋 Commands:*\n\n"
        "*Getting Started:*\n"
        "/start - Subscribe to notifications\n"
        "/add username name - Track a friend\n"
        "/mylist - View your tracking list\n\n"
        "*Managing Friends:*\n"
        "/remove username - Stop tracking someone\n"
        "/leaderboard - See rankings\n"
        "/check - Manual update check\n\n"
        "*Settings:*\n"
        "/status - Your bot status\n"
        "/stop - Unsubscribe from notifications\n"
        "/help - Show this message\n\n"
        "*💡 How it works:*\n"
        "• Add friends using their LeetCode username\n"
        "• Bot checks every 5 minutes for updates\n"
        "• Get instant notifications when they solve problems\n"
        "• Track progress with the leaderboard\n\n"
        "*Example:*\n"
        "`/add john_doe John Doe`\n"
        "Then sit back and get notified! 🎉"
    )
    await update.message.reply_text(help_msg, parse_mode='Markdown')

async def periodic_check_loop(app):
    """Background loop for periodic checks"""
    await asyncio.sleep(10)  # Wait 10 seconds before first check
    
    while True:
        try:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for updates...")
            
            all_updates = tracker.check_updates()
            
            if all_updates:
                tracker.save_state()
                total_updates = sum(len(updates) for updates in all_updates.values())
                print(f"Found {total_updates} update(s) across {len(all_updates)} user(s)")
                
                # Send to subscribers
                for chat_id, updates in all_updates.items():
                    if chat_id in tracker.subscribers:
                        try:
                            for msg in updates:
                                await app.bot.send_message(
                                    chat_id=chat_id,
                                    text=msg,
                                    parse_mode='Markdown'
                                )
                                await asyncio.sleep(0.5)
                        except Exception as e:
                            print(f"Error sending to {chat_id}: {e}")
            else:
                print("No new updates")
            
            # Wait for next check
            await asyncio.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"Error in periodic check: {e}")
            await asyncio.sleep(60)  # Wait 1 minute before retry

async def post_init(application: Application):
    """Called after bot initialization"""
    # Start the periodic check loop
    asyncio.create_task(periodic_check_loop(application))

def main():
    """Main function"""
    if TELEGRAM_BOT_TOKEN == "[YOUR_BOT_TOKEN]":
        print("❌ ERROR: Please set TELEGRAM_BOT_TOKEN environment variable!")
        print("   Set it in Railway/Render or export it locally:")
        print("   export TELEGRAM_BOT_TOKEN='your_token_here'")
        return
    
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    # Store app reference
    tracker.app = application
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("add", add_user))
    application.add_handler(CommandHandler("remove", remove_user))
    application.add_handler(CommandHandler("mylist", mylist))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("check", check_now))
    application.add_handler(CommandHandler("help", help_command))
    
    print("🤖 LeetCode Tracker Bot started!")
    print("✅ Multi-user mode enabled")
    print("📢 Bot is ready to receive commands...")
    print("💡 Users can now add their own friends!")
    
    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)
 
if __name__ == "__main__":
    main()