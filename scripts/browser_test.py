#!/usr/bin/env python3
"""
Quick browser-use test. Run with:
    ANTHROPIC_API_KEY=your_key .venv/bin/python scripts/browser_test.py
"""
import asyncio
from browser_use import Agent
from browser_use.llm import ChatAnthropic

async def main():
    agent = Agent(
        task="Go to google.com and tell me the top news headline today.",
        llm=ChatAnthropic(model="claude-haiku-4-5-20251001"),  # cheapest — just for testing
    )
    result = await agent.run()
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
