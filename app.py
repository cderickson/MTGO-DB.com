from flask import Flask
import os
from celery import Celery, Task
from modules.models import Player, Match, Game, Play, Pick, Draft, GameActions, Removed, CardsPlayed
from flask import request, url_for, flash, render_template, redirect
from flask_login import login_user, login_required, logout_user, current_user
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from modules.extensions import db, mail, login_manager
from modules.debug_routes import debug_bp

DB_NAME = 'database.db'

def make_celery(app):
	celery = Celery(
		app.import_name,
		backend=app.config['CELERY_RESULT_BACKEND'],
		broker=app.config['CELERY_BROKER_URL']
	)
	
	# Simplified Celery configuration to avoid conflicts
	celery_config = {
		'broker_url': app.config.get('CELERY_BROKER_URL'),
		'result_backend': app.config.get('CELERY_RESULT_BACKEND'),
		'task_serializer': 'pickle',  # Changed to pickle for better compatibility
		'accept_content': ['pickle', 'json'],  # Allow both
		'result_serializer': 'pickle',
		'timezone': 'UTC',
		'enable_utc': True,
		'worker_prefetch_multiplier': 1,  # Process one task at a time
		'task_acks_late': True,  # Acknowledge tasks only after completion
		'worker_hijack_root_logger': False,  # Don't interfere with logging
	}
	celery.conf.update(celery_config)

	class ContextTask(celery.Task):
		def __call__(self, *args, **kwargs):
			with app.app_context():
				return self.run(*args, **kwargs)

	celery.Task = ContextTask
	return celery

def create_app():
	app = Flask(__name__)
	
	# Determine environment and load appropriate config
	env = os.environ.get('FLASK_ENV', 'development')
	if env == 'development' or env == 'local':
		app.config.from_pyfile('local-dev/local_config.cfg')
		print("Running in LOCAL/DEVELOPMENT mode")
	else:
		# In production, config file may not be baked into the image; fall back to env-only
		try:
			app.config.from_pyfile('auxiliary/config.cfg')
			print("Running in PRODUCTION mode (file config)")
		except Exception:
			print("Running in PRODUCTION mode (env-only config)")
	
	# Override with environment variables if they exist (for production)
	app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", app.config.get('SECRET_KEY'))
	app.config['MAIL_SERVER'] = os.environ.get("MAIL_SERVER", app.config.get('MAIL_SERVER'))

	# Mail transport overrides: allow switching ports and TLS/SSL via env
	def _as_bool(value, default=False):
		if value is None:
			return default
		return str(value).strip().lower() in ("1", "true", "yes", "on")

	app.config['MAIL_PORT'] = int(os.environ.get("MAIL_PORT", app.config.get('MAIL_PORT', 587)))
	app.config['MAIL_USE_TLS'] = _as_bool(os.environ.get("MAIL_USE_TLS", app.config.get('MAIL_USE_TLS', True)))
	app.config['MAIL_USE_SSL'] = _as_bool(os.environ.get("MAIL_USE_SSL", app.config.get('MAIL_USE_SSL', False)))

	app.config['MAIL_USERNAME'] = os.environ.get("MAIL_USERNAME", app.config.get('MAIL_USERNAME'))
	app.config['MAIL_PASSWORD'] = os.environ.get("MAIL_PASSWORD", app.config.get('MAIL_PASSWORD'))
	app.config['MAIL_DEFAULT_SENDER'] = os.environ.get("MAIL_DEFAULT_SENDER", app.config.get('MAIL_DEFAULT_SENDER'))
	app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("SQLALCHEMY_DATABASE_URI", app.config.get('SQLALCHEMY_DATABASE_URI'))
	app.config['CELERY_RESULT_BACKEND'] = os.environ.get("CELERY_RESULT_BACKEND", app.config.get('CELERY_RESULT_BACKEND'))
	app.config['CELERY_BROKER_URL'] = os.environ.get("CELERY_BROKER_URL", app.config.get('CELERY_BROKER_URL'))
	app.config['URL_SAFETIMEDSERIALIZER'] = os.environ.get("URL_SAFETIMEDSERIALIZER", app.config.get('URL_SAFETIMEDSERIALIZER'))
	app.config['EMAIL_CONFIRMATION_SALT'] = os.environ.get("EMAIL_CONFIRMATION_SALT", app.config.get('EMAIL_CONFIRMATION_SALT'))
	app.config['RESET_PASSWORD_SALT'] = os.environ.get("RESET_PASSWORD_SALT", app.config.get('RESET_PASSWORD_SALT'))

	# Reset debug log file on app startup
	# try:
	# 	log_dir = os.path.join('local-dev', 'data', 'logs')
	# 	os.makedirs(log_dir, exist_ok=True)
	# 	log_file = os.path.join(log_dir, 'debug_log.txt')
		
	# 	# Clear the debug log file
	# 	with open(log_file, 'w', encoding='utf-8') as f:
	# 		f.write(f"=== MTGO-DB Debug Log - Started {datetime.now()} ===\n")
	# 	print(f"Debug log reset: {log_file}")
	# except Exception as e:
	# 	print(f"Warning: Could not reset debug log file: {e}")

	# Initialize extensions
	mail.init_app(app)
	db.init_app(app)

	from modules.views import views
	from modules.auth import auth

	app.register_blueprint(views, url_prefix='/')
	app.register_blueprint(auth, url_prefix='/')
	app.register_blueprint(debug_bp)

	from modules.models import Player

	with app.app_context():
		db.create_all()

	login_manager.login_view = 'views.login'
	login_manager.init_app(app)

	@login_manager.user_loader
	def load_user(uid):
		return Player.query.get(int(uid))

	return app

app = create_app()
celery = make_celery(app)

# Register tasks by importing the module
try:
	import modules.views
	print(f"Tasks registered: {len(celery.tasks)} tasks found")
except Exception as e:
	print(f"Warning: Could not import tasks: {e}")

celery.set_default()

#mail = Mail(app)

if __name__ == '__main__':
	# Set environment for local development
	os.environ['FLASK_ENV'] = 'local'
	app.run(host="0.0.0.0", port=8000, debug=True)