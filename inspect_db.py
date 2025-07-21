#!/usr/bin/env python3
"""
Database Inspection Script for MTGO-DB
Use this to view and inspect data in your database during testing.
"""

import os
from app import app
from modules.extensions import db
from modules.models import Player, Match, Game, Play, Pick, Draft, GameActions, Removed, CardsPlayed

def inspect_database():
    """Main function to inspect database contents"""
    with app.app_context():
        print("MTGO-DB Database Inspector")
        print("=" * 50)
        
        # Check database connection
        try:
            db.engine.connect()
            print("Database connection successful")
        except Exception as e:
            print(f"Database connection failed: {e}")
            return
        
        # Get all tables
        tables = db.engine.table_names()
        print(f"\n📊 Available tables: {len(tables)}")
        for table in tables:
            print(f"  - {table}")
        
        print("\n" + "=" * 50)
        
        # Inspect each model
        models = [
            ("Players", Player),
            ("Matches", Match),
            ("Games", Game),
            ("Plays", Play),
            ("Picks", Pick),
            ("Drafts", Draft),
            ("GameActions", GameActions),
            ("Removed", Removed),
            ("CardsPlayed", CardsPlayed)
        ]
        
        for name, model in models:
            try:
                count = model.query.count()
                print(f"{name}: {count} records")
                
                if count > 0:
                    # Show first few records
                    records = model.query.limit(3).all()
                    print(f"   Sample records:")
                    for i, record in enumerate(records, 1):
                        print(f"   {i}. {record}")
                    if count > 3:
                        print(f"   ... and {count - 3} more records")
                print()
                
            except Exception as e:
                print(f"Error inspecting {name}: {e}")
                print()

def inspect_specific_table(table_name):
    """Inspect a specific table in detail"""
    with app.app_context():
        model_map = {
            'player': Player,
            'match': Match,
            'game': Game,
            'play': Play,
            'pick': Pick,
            'draft': Draft,
            'gameactions': GameActions,
            'removed': Removed,
            'cardsplayed': CardsPlayed
        }
        
        model = model_map.get(table_name.lower())
        if not model:
            print(f"Unknown table: {table_name}")
            print(f"Available tables: {list(model_map.keys())}")
            return
        
        print(f"Inspecting {table_name} table")
        print("=" * 50)
        
        try:
            count = model.query.count()
            print(f"Total records: {count}")
            
            if count > 0:
                records = model.query.limit(10).all()
                print(f"\nFirst {min(10, count)} records:")
                print("-" * 50)
                
                for i, record in enumerate(records, 1):
                    print(f"{i}. {record}")
                    # Try to show some attributes
                    if hasattr(record, '__dict__'):
                        attrs = {k: v for k, v in record.__dict__.items() 
                                if not k.startswith('_')}
                        for key, value in list(attrs.items())[:5]:  # Show first 5 attributes
                            print(f"   {key}: {value}")
                        if len(attrs) > 5:
                            print(f"   ... and {len(attrs) - 5} more attributes")
                    print()
            else:
                print("No records found in this table.")
                
        except Exception as e:
            print(f"Error inspecting table: {e}")

def show_recent_activity():
    """Show recent database activity"""
    with app.app_context():
        print("Recent Database Activity")
        print("=" * 50)
        
        try:
            # Show recent players
            recent_players = Player.query.order_by(Player.id.desc()).limit(5).all()
            if recent_players:
                print("Recent Players:")
                for player in recent_players:
                    print(f"  - {player}")
            
            # Show recent matches
            recent_matches = Match.query.order_by(Match.id.desc()).limit(5).all()
            if recent_matches:
                print("\nRecent Matches:")
                for match in recent_matches:
                    print(f"  - {match}")
            
            # Show recent games
            recent_games = Game.query.order_by(Game.id.desc()).limit(5).all()
            if recent_games:
                print("\nRecent Games:")
                for game in recent_games:
                    print(f"  - {game}")
                    
        except Exception as e:
            print(f"Error showing recent activity: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "inspect":
            inspect_database()
        elif command == "recent":
            show_recent_activity()
        elif command == "table" and len(sys.argv) > 2:
            inspect_specific_table(sys.argv[2])
        else:
            print("Usage:")
            print("  python inspect_db.py inspect          # Full database inspection")
            print("  python inspect_db.py recent           # Show recent activity")
            print("  python inspect_db.py table <name>     # Inspect specific table")
            print("  Available tables: player, match, game, play, pick, draft, gameactions, removed, cardsplayed")
    else:
        # Default: run full inspection
        inspect_database() 