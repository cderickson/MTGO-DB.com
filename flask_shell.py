#!/usr/bin/env python3
"""
Flask Shell for MTGO-DB
Quick database queries and testing
"""

import os
os.environ['FLASK_ENV'] = 'local'

from app import app
from modules.extensions import db
from modules.models import Player, Match, Game, Play, Pick, Draft, GameActions, Removed, CardsPlayed

def quick_stats():
    """Show quick database statistics"""
    with app.app_context():
        print("📊 MTGO-DB Quick Stats")
        print("=" * 30)
        
        models = [
            ("Players", Player),
            ("Matches", Match),
            ("Games", Game),
            ("Plays", Play),
            ("Picks", Pick),
            ("Drafts", Draft),
            ("Game Actions", GameActions),
            ("Removed Cards", Removed),
            ("Cards Played", CardsPlayed)
        ]
        
        for name, model in models:
            try:
                count = model.query.count()
                print(f"{name}: {count}")
            except Exception as e:
                print(f"{name}: Error - {e}")

def show_players():
    """Show all players"""
    with app.app_context():
        players = Player.query.all()
        print(f"👥 Players ({len(players)} total):")
        for player in players:
            print(f"  - {player}")

def show_recent_matches():
    """Show recent matches"""
    with app.app_context():
        matches = Match.query.order_by(Match.id.desc()).limit(10).all()
        print(f"🎮 Recent Matches ({len(matches)} shown):")
        for match in matches:
            print(f"  - {match}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "stats":
            quick_stats()
        elif command == "players":
            show_players()
        elif command == "matches":
            show_recent_matches()
        else:
            print("Available commands:")
            print("  python flask_shell.py stats    # Show quick statistics")
            print("  python flask_shell.py players  # Show all players")
            print("  python flask_shell.py matches  # Show recent matches")
    else:
        # Interactive shell
        with app.app_context():
            print("🐍 MTGO-DB Interactive Shell")
            print("Available models: Player, Match, Game, Play, Pick, Draft, GameActions, Removed, CardsPlayed")
            print("Database: db")
            print("Example: Player.query.all()")
            print("-" * 50)
            
            # Start interactive Python shell with context
            import code
            code.interact(local=locals()) 