"""
Debug Routes for Database Inspection
Add these routes to your Flask app for easy database inspection during testing.
"""

from flask import Blueprint, jsonify, render_template_string
from modules.extensions import db
from modules.models import Player, Match, Game, Play, Pick, Draft, GameActions, Removed, CardsPlayed, TaskHistory

debug_bp = Blueprint('debug', __name__, url_prefix='')

@debug_bp.route('/db')
def inspect_database():
    """Web interface for database inspection"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MTGO-DB Database Inspector</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .table { margin: 20px 0; padding: 15px; border: 1px solid #ddd; }
            .count { font-weight: bold; color: #007bff; }
            .error { color: #dc3545; }
            .success { color: #28a745; }
            .sample { margin: 10px 0; padding: 10px; background: #f8f9fa; }
            pre { background: #f1f3f4; padding: 10px; overflow-x: auto; }
        </style>
    </head>
    <body>
        <h1>MTGO-DB Database Inspector</h1>
        <p><em>Real-time view of your database contents</em></p>
        
        {% for table_info in tables %}
        <div class="table">
            <h3>{{ table_info.name }}</h3>
            <p>Records: <span class="count">{{ table_info.count }}</span></p>
            
            {% if table_info.error %}
                <p class="error">Error: {{ table_info.error }}</p>
            {% elif table_info.samples %}
                <div class="sample">
                    <strong>Sample records:</strong>
                    <pre>{{ table_info.samples }}</pre>
                </div>
            {% else %}
                <p><em>No records found</em></p>
            {% endif %}
        </div>
        {% endfor %}
        
        <hr>
        <p><strong>Quick Actions:</strong></p>
        <ul>
            <li><a href="/db/json">View as JSON</a></li>
            <li><a href="/db/players">View Players Only</a></li>
            <li><a href="/db/matches">View Matches Only</a></li>
            <li><a href="/db/task_history">View Task History</a></li>
            <li><a href="/recent">View Recent Activity</a></li>
        </ul>
    </body>
    </html>
    """
    
    # Inspect all tables
    models = [
        ("Players", Player),
        ("Matches", Match),
        ("Games", Game),
        ("Plays", Play),
        ("Picks", Pick),
        ("Drafts", Draft),
        ("Game Actions", GameActions),
        ("Removed Games", Removed),
        ("Cards Played", CardsPlayed),
        ("Task History", TaskHistory)
    ]
    
    tables = []
    for name, model in models:
        try:
            count = model.query.count()
            samples = ""
            
            if count > 0:
                records = model.query.limit(3).all()
                record_details = []
                for record in records:
                    if hasattr(record, 'as_dict'):
                        # Use as_dict method if available
                        record_data = record.as_dict()
                        formatted = "\n".join([f"  {key}: {value}" for key, value in record_data.items()])
                    else:
                        # For Player model, manually extract fields
                        record_data = {}
                        for column in record.__table__.columns:
                            record_data[column.name] = getattr(record, column.name, None)
                        formatted = "\n".join([f"  {key}: {value}" for key, value in record_data.items()])
                    
                    record_details.append(f"Record {record.uid if hasattr(record, 'uid') else getattr(record, 'task_id', 'ID')}:\n{formatted}")
                
                samples = "\n\n".join(record_details)
                if count > 3:
                    samples += f"\n\n... and {count - 3} more records"
            
            tables.append({
                'name': name,
                'count': count,
                'samples': samples,
                'error': None
            })
        except Exception as e:
            tables.append({
                'name': name,
                'count': 0,
                'samples': "",
                'error': str(e)
            })
    
    return render_template_string(html, tables=tables)

@debug_bp.route('/db/json')
def inspect_database_json():
    """JSON API for database inspection"""
    models = [
        ("players", Player),
        ("matches", Match),
        ("games", Game),
        ("plays", Play),
        ("picks", Pick),
        ("drafts", Draft),
        ("game_actions", GameActions),
        ("removed_cards", Removed),
        ("cards_played", CardsPlayed),
        ("task_history", TaskHistory)
    ]
    
    result = {}
    for name, model in models:
        try:
            count = model.query.count()
            result[name] = {
                'count': count,
                'status': 'success'
            }
            
            if count > 0:
                # Get sample records (first 5)
                records = model.query.limit(5).all()
                record_details = []
                for record in records:
                    if hasattr(record, 'as_dict'):
                        record_details.append(record.as_dict())
                    else:
                        # For Player model, manually extract fields
                        record_data = {}
                        for column in record.__table__.columns:
                            record_data[column.name] = getattr(record, column.name, None)
                        record_details.append(record_data)
                result[name]['samples'] = record_details
        except Exception as e:
            result[name] = {
                'count': 0,
                'status': 'error',
                'error': str(e)
            }
    
    return jsonify(result)

@debug_bp.route('/db/<table_name>')
def inspect_specific_table(table_name):
    """Inspect a specific table"""
    model_map = {
        'players': Player,
        'matches': Match,
        'games': Game,
        'plays': Play,
        'picks': Pick,
        'drafts': Draft,
        'game_actions': GameActions,
        'removed_cards': Removed,
        'cards_played': CardsPlayed,
        'task_history': TaskHistory
    }
    
    model = model_map.get(table_name.lower())
    if not model:
        return jsonify({'error': f'Unknown table: {table_name}', 'available': list(model_map.keys())}), 404
    
    try:
        count = model.query.count()
        records = model.query.limit(20).all()
        
        record_details = []
        for record in records:
            if hasattr(record, 'as_dict'):
                record_details.append(record.as_dict())
            else:
                # For Player model, manually extract fields
                record_data = {}
                for column in record.__table__.columns:
                    record_data[column.name] = getattr(record, column.name, None)
                record_details.append(record_data)
        
        return jsonify({
            'table': table_name,
            'count': count,
            'records': record_details,
            'status': 'success'
        })
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@debug_bp.route('/recent')
def show_recent_activity():
    """Show recent database activity"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Recent Activity - MTGO-DB</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .activity { margin: 20px 0; padding: 15px; border: 1px solid #ddd; }
            .record { margin: 5px 0; padding: 5px; background: #f8f9fa; }
        </style>
    </head>
    <body>
        <h1>🕒 Recent Database Activity</h1>
        
        {% if recent_players %}
        <div class="activity">
            <h3>👥 Recent Players</h3>
            {% for player in recent_players %}
            <div class="record">{{ player }}</div>
            {% endfor %}
        </div>
        {% endif %}
        
        {% if recent_matches %}
        <div class="activity">
            <h3>🎮 Recent Matches</h3>
            {% for match in recent_matches %}
            <div class="record">{{ match }}</div>
            {% endfor %}
        </div>
        {% endif %}
        
        {% if recent_games %}
        <div class="activity">
            <h3>🎯 Recent Games</h3>
            {% for game in recent_games %}
            <div class="record">{{ game }}</div>
            {% endfor %}
        </div>
        {% endif %}
        
        {% if recent_tasks %}
        <div class="activity">
            <h3>📋 Recent Tasks</h3>
            {% for task in recent_tasks %}
            <div class="record">{{ task }}</div>
            {% endfor %}
        </div>
        {% endif %}
        
        <hr>
        <p><a href="/db">← Back to Database Inspector</a></p>
    </body>
    </html>
    """
    
    try:
        recent_players = Player.query.order_by(Player.uid.desc()).limit(10).all()
        recent_matches = Match.query.limit(10).all()  # Match doesn't have single ID column
        recent_games = Game.query.limit(10).all()     # Game doesn't have single ID column
        recent_tasks = TaskHistory.query.order_by(TaskHistory.task_id.desc()).limit(10).all()
        
        # Format players with complete data
        formatted_players = []
        for player in recent_players:
            player_data = {}
            for column in player.__table__.columns:
                player_data[column.name] = getattr(player, column.name, None)
            formatted_players.append(f"Player {player.uid}: {player_data}")
        
        # Format matches with complete data
        formatted_matches = []
        for match in recent_matches:
            if hasattr(match, 'as_dict'):
                match_data = match.as_dict()
                formatted_matches.append(f"Match {match.match_id}: {match_data}")
        
        # Format games with complete data
        formatted_games = []
        for game in recent_games:
            if hasattr(game, 'as_dict'):
                game_data = game.as_dict()
                formatted_games.append(f"Game {game.match_id}-{game.game_num}: {game_data}")
        
        # Format tasks with complete data
        formatted_tasks = []
        for task in recent_tasks:
            if hasattr(task, 'as_dict'):
                task_data = task.as_dict()
                formatted_tasks.append(f"Task {task.task_id}: {task_data}")
        
        return render_template_string(html, 
                                    recent_players=formatted_players,
                                    recent_matches=formatted_matches,
                                    recent_games=formatted_games,
                                    recent_tasks=formatted_tasks)
    except Exception as e:
        return f"Error: {str(e)}", 500

# Instructions for adding to your app:
"""
To use these debug routes, add this to your app.py:

from debug_routes import debug_bp
app.register_blueprint(debug_bp)

Then visit:
- http://localhost:8000/db - Web interface for database inspection
- http://localhost:8000/db/json - JSON API for database data
- http://localhost:8000/recent - Recent activity view
- http://localhost:8000/db/players - View players table
- http://localhost:8000/db/task_history - View task history table
""" 