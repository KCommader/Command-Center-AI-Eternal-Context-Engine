"""
Keyword-based conversation classifier.

Default categories cover common project types.
Customize by passing your own categories dict to Classifier().

Categories dict format:
    {
        "Category Label": ["keyword1", "keyword2", ...],
        ...
    }

Title matches score 3x, body matches score 1x.
"""
from __future__ import annotations
from collections import defaultdict


DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "Crypto Trading": [
        "polymarket", "hyperliquid", "crypto", "trading", "bitcoin", "btc",
        "eth", "ethereum", "defi", "blockchain", "wallet", "solana",
        "arbitrage", "liquidation", "leverage", "futures", "perp", "perpetual",
        "dex", "swap", "yield", "staking", "prediction market", "token", "altcoin",
        "market maker", "order book", "liquidate", "antigravity", "orderflow",
        "price action", "ltr", "liquidity trap", "fvg", "bos", "avwap",
        "coreflow", "trading bot", "algo trading",
    ],
    "AI / Bots / Automation": [
        "openai", "gpt", "claude", "llm", "langchain", "ai agent", "chatbot",
        "prompt engineering", "embedding", "vector", "rag", "lancedb",
        "mcp", "anthropic", "gemini", "whisper", "tts", "voice assistant",
        "command center", "memory system", "kai", "openclaw",
        "telegram bot", "discord bot", "webhook", "n8n", "make.com", "zapier",
        "fine-tun", "llama", "mistral", "local ai", "automation bot",
    ],
    "Web Development": [
        "react", "next.js", "nextjs", "vue", "svelte", "tailwind", "javascript",
        "typescript", "node.js", "nodejs", "express", "fastapi", "flask",
        "django", "graphql", "websocket", "vercel", "netlify", "three.js",
        "webgl", "scroll animation", "landing page", "website",
        "frontend", "backend", "fullstack", "web app", "spa",
        "api endpoint", "rest api", "supabase", "firebase",
    ],
    "Flutter / Mobile": [
        "flutter", "dart", "mobile app", "android", "ios", "app store",
        "google play", "widget", "stateful", "stateless", "bloc", "riverpod",
        "provider", "getx", "push notification", "flutter app",
    ],
    "NFTs / Web3": [
        "nft collection", "opensea", "mint", "smart contract", "solidity",
        "web3.py", "ethers.js", "metamask", "ens", "dao", "uniswap", "aave",
        "polygon", "layer 2", "rollup", "zk proof", "nft project",
        "crypto kennel", "ckc", "kingswitch",
    ],
    "Fitness / Health": [
        "workout", "gym", "fitness", "diet plan", "nutrition", "calories",
        "protein", "exercise", "muscle", "weight loss", "cardio",
        "supplement", "creatine", "bulk", "bodybuilding", "calisthenics",
        "running", "marathon", "hyrox", "hybrid athlete", "more than human", "mth",
    ],
    "Business / Brand": [
        "shopify", "ecommerce", "dropshipping", "revenue model", "business plan",
        "startup", "pricing strategy", "brand identity",
        "trademark", "marketing", "content strategy", "youtube channel",
        "affiliate", "monetiz", "saas",
    ],
    "Writing / Creative": [
        "story", "novel", "fiction", "character design", "screenplay",
        "script writing", "poem", "essay", "blog post", "copywriting",
        "content creation", "video script", "lore", "worldbuilding", "narrative",
    ],
    "DevOps / Infra": [
        "docker", "kubernetes", "aws", "gcp", "azure", "linux", "ubuntu",
        "server", "vps", "nginx", "caddy", "ssl", "ci/cd", "github actions",
        "ansible", "terraform", "systemd", "cron", "bash script",
    ],
    "Python / Data": [
        "pandas", "numpy", "matplotlib", "sklearn", "pytorch", "tensorflow",
        "jupyter", "data science", "machine learning", "neural network",
        "dataset", "sql query", "postgres", "mysql", "sqlite", "mongodb",
        "data pipeline", "etl", "scraping", "beautifulsoup",
    ],
    "Personal / General": [
        "puerto rico", "personal advice", "life advice", "relationship",
        "resume", "salary", "budget", "travel", "food recipe",
        "cook", "what is", "how does", "explain",
    ],
}


class Classifier:
    def __init__(self, categories: dict[str, list[str]] | None = None):
        self.categories = categories or DEFAULT_CATEGORIES

    def classify(self, title: str, user_msg: str, asst_msg: str) -> str:
        title_lower = title.lower()
        body_lower = (user_msg + " " + asst_msg).lower()
        full = title_lower + " " + body_lower

        scores: dict[str, int] = defaultdict(int)
        for cat, keywords in self.categories.items():
            for kw in keywords:
                if kw in full:
                    scores[cat] += 3 if kw in title_lower else 1

        if not scores:
            return "Other"
        return max(scores, key=scores.get)

    def classify_batch(self, conversations) -> list:
        """Classify a list of Conversation objects in place. Returns them."""
        for c in conversations:
            c.category = self.classify(c.title, c.user_msg, c.asst_msg)
        return conversations
