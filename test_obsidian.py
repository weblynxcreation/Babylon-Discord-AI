"""
Quick test for Obsidian tool integration.
Run from the project root:  python test_obsidian.py
"""
import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from tools.obsidian import obsidian_search, obsidian_read


async def test_obsidian():
    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH")
    
    if not vault_path:
        print("❌ OBSIDIAN_VAULT_PATH not set in .env")
        return False
    
    vault = Path(vault_path)
    if not vault.exists():
        print(f"❌ Vault path does not exist: {vault_path}")
        return False
    
    print(f"✓ Vault found: {vault_path}")
    
    # Test search
    print("\n🔍 Testing obsidian_search('foundry iron')...")
    result = await obsidian_search("foundry iron")
    print(f"Result: {result}")
    
    # Test read
    print("\n📖 Testing obsidian_read with a sample file...")
    result = await obsidian_read("Wiki/Production")
    print(f"Result (first 500 chars): {result[:500]}")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_obsidian())
    sys.exit(0 if success else 1)
