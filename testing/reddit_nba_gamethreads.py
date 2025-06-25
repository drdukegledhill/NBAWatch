import praw

# Replace these with your Reddit API credentials
CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
USER_AGENT = "nba-game-thread-analyzer by /u/YOUR_USERNAME"

# Initialize Reddit API client
reddit = praw.Reddit(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    user_agent=USER_AGENT
)

subreddit = reddit.subreddit("nba")

print("Recent Game Threads in r/nba:")
for submission in subreddit.search("Game Thread", sort="new", limit=10):
    print(f"Title: {submission.title}")
    print(f"Comments: {submission.num_comments}")
    print(f"URL: {submission.url}\n")

# Sentiment analysis can be performed on submission.comments in a next step. 